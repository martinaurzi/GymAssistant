from typing import Literal, Union
from dotenv import load_dotenv
import json
from datetime import datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, RemoveMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
#from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_groq import ChatGroq

from schemas import AgentState, HumanInterrupt, PostFormat, PlannerFormat
from prompts import SYSTEM_PROMPT, PLANNER_PROMPT, FORMAT_ARTICLE_PROMPT, EXTRACTION_SYSTEM_PROMPT
from database.neo4j_graph import EditorialKnowledgeGraphManager

from tools.web_search_tool import web_search_tool
from tools.rag_tool import rag_tool
from tools.knowledge_graph_tool import knowledge_graph_tool, kg_manager
from tools.research_judge_tool import research_judge_tool
from tools.extract_claims_tool import extract_claims_tool

load_dotenv(".env")

# Lista di tool
tools = [web_search_tool, rag_tool, knowledge_graph_tool, research_judge_tool, extract_claims_tool] 
tools_by_name = {tool.name: tool for tool in tools}

# Inizializzazione del modello
#llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
llm_groq = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

from pydantic import create_model, Field
from langchain_core.tools import Tool

# Diamo accesso al modello ai tool
llm_with_tools = llm.bind_tools(tools)
#llm_extractor = llm.bind_tools([extract_claims_tool])

kgManager = EditorialKnowledgeGraphManager()

def llm_planner_node(state: AgentState):
    """Recupera lo storico del blog dal knowledge graph sulla base del quale decide la categoria e l'argomento del prossimo post fornendo anche
       una giustificazione sulla scelta di quel determinato argomento.
    """
    # Recuperiamo lo storico del blog
    blog_history = kgManager.get_kg_summary()

    llm_planner_structured = llm_groq.with_structured_output(PlannerFormat)

    response = llm_planner_structured.invoke([SystemMessage(content=PLANNER_PROMPT.format(blog_history=blog_history))])

    print(f"[PLANNER NODE]: {response}\n")

    return{
        "planning_information": response
    }

def llm_node(state: AgentState) -> Union[Command[Literal["__end__"]], dict]:
    """Il modello analizza lo stato corrente e decide se chiamare un tool oppure fornire la risposta finale.

       Restituisce lo stato aggiornato con la risposta del modello e aggiorna la reasoning trace con i suoi pensieri.
    """      
    new_messages = []
    
    planning_info = state.get("planning_information")

    if not planning_info or not planning_info.planned_post_sequence:
        print(f"[LLM]: Nessun post da generare: {planning_info}\n")
        return Command(goto=END)
    
    if state.get("post_draft") and not state.get("extracted_claims"):
        post = state.get("post_draft")
        post_content = f"{post.category}\n{post.title}\n{post.introduction}\n{post.body}\n{post.conclusion}"
        
        response = llm_with_tools.invoke([
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=f"Estrai i claim per il seguente post:\n{post_content}")
        ])
        
        new_messages.append(response)
    else:
        current_post = planning_info.planned_post_sequence[0]

        current_post_str = f"Categoria: {current_post.category} | Argomento (Topic): {current_post.topic}"

        print(f"[LLM]: Fare il post su {current_post_str}\n")

        input_messages = state.get("messages", [])

        if not input_messages:
            # Generiamo un messaggio da inviare a LLM dato che abbiamo cancellato la cronologia dei messaggi
            input_msg = HumanMessage(content="Procedi con la generazione del prossimo post.")

            input_messages = [input_msg]

            new_messages.append(input_msg)
                            
        # Invocazione del modello
        response = llm_with_tools.invoke([SystemMessage(content=SYSTEM_PROMPT.format(planning_info=current_post_str))] + input_messages)

        new_messages.append(response)

    print(f"[LLM]: new_messages: {new_messages}")

    updated_state = {
        "messages": new_messages
    }

    tool_justification = ""
    current_thought = ""

    if response.tool_calls:
        print(f"[RISPOSTA CHATGPT]: {response}\n")
        # Reasoning trace con modello gemini-2.5-flash
        #if isinstance(response.content, list):
             #reasoning_text = []

            #for block in response.content:
                #if isinstance(block, dict) and "text" in block:
                    #reasoning_text.append(block["text"])
                #elif isinstance(block, str): # continuo dopo "extras"
                    #reasoning_text.append(block)
            
            # Uniamo tutti i pezzi in un'unica stringa
            #current_thought = "".join(reasoning_text)
        #else:
           # current_thought = str(response.content)
        
        # Reasoning trace con modello gpt-4o-mini
        tool_thought = response.tool_calls[0]["args"].get("justification", "Nessuna giustificazione rilevata.")
        current_thought = tool_thought
        
        if isinstance(tool_thought, str):
            current_thought = tool_thought.strip()
        else:
            current_thought = str(tool_thought)

        #current_thought = current_thought.strip()

        tool_name = response.tool_calls[0]["name"]
        tool_justification = f"Ho usato il tool {tool_name} per il seguente motivo: {current_thought}"

        print(f"[LLM]: giustificazione uso dei tool: {tool_justification}\n")

        updated_state["reasoning_trace"] = [current_thought]
        updated_state["tool_usage_justification"] = tool_justification
    
    return updated_state

def tool_node(state: AgentState):
    """Esegue tutte le chiamate ai tool relative alla precedente risposta dell'LLM.

       Restituisce lo stato aggiornato con i risultati delle esecuzioni dei tool.
    """
    last_message = state["messages"][-1] # Ultimo messaggio generato dall'LLM
    
    tool_calls = last_message.tool_calls # Richieste di chiamate ai tool dell'LLM

    tool_outputs = []
    rag_retrieved_docs = []
    #web_search_res = []
    
    consistency_txt = state.get("kg_consistency_context", "")
    matched_topic_txt = state.get("matched_topic", "")
    extracted_claims = state.get("extracted_claims", [])

    # Eseguiamo tutte le chiamate ai tool
    for tool_call in tool_calls: 
        tool = tools_by_name[tool_call["name"]]

        print(f"[TOOL] L'agente ha richiesto il tool: '{tool_call["name"]}' con argomenti: {tool_call['args']}")

        observation = tool.invoke(tool_call["args"]) 

        observation_str = str(observation)

        if tool_call["name"] == "knowledge_graph_tool":
            try:
                data = json.loads(observation_str)
                
                consistency_txt = data["context"]
                matched_topic_txt = data["matched_topic"]
                
                observation_str = data.get("context", "")
            except Exception as e:
                print(f"[ERRORE PARSING JSON TOOL]: {e}")
                consistency_txt = observation_str

        # Verifichiamo se è stato chiamato il tool RAG
        if tool_call["name"] == "rag_tool" and observation_str: # observation non deve essere ""
            rag_retrieved_docs = observation_str.split("|")
            
        # Se il tool chiamato è quello dei claim, estraiamo subito i dati nello stato
        if tool_call["name"] == "extract_claims_tool":
            try:
                data = json.loads(observation_str)
                # Salviamo i claim direttamente nel dizionario di ritorno
                extracted_claims = data.get("claims", [])
            except:
                extracted_claims = []

        #if tool_call["name"] == "web_search_tool" and observation_str:
         #   web_search_res = observation_str.split("|")

        # Messaggio di risposta del tool
        tool_outputs.append(
            ToolMessage(
                content=observation_str,
                name=tool_call["name"],
                tool_call_id=tool_call["id"]
            ) 
        )

    return {
        "messages": tool_outputs, 
        "tool_outputs": tool_outputs,
        "retrived_documents": rag_retrieved_docs,
        "kg_consistency_context": consistency_txt, 
        "matched_topic": matched_topic_txt,
        "extracted_claims": extracted_claims 
    }

def llm_format_node(state: AgentState):
    """Formatta le informazioni restituite dal tool di ricerca per generare la bozza dell'articolo"""

    print("[WRITER] Formatto l'articolo...")
    
    # Recuperiamo il contesto di coerenza salvato nello state
    consistency_data = state.get("kg_consistency_context", "")

    if not consistency_data or consistency_data.strip() == "":
        # !! VEDERE SE CONVIENE FORNIRE STRINGA VUOTA
        consistency_data = "Nessun vincolo precedente trovato per questo argomento. Procedi liberamente."

    #rag_docs = state.get("retrived_documents")
    #web_search_res = state.get("web_search_results")
    #llm_writer_structured = llm_groq.with_structured_output(PostFormat)

    llm_writer_structured = llm.with_structured_output(PostFormat)

    results = llm_writer_structured.invoke([SystemMessage(content=FORMAT_ARTICLE_PROMPT.format(consistency_context=consistency_data))] + state["messages"])

    return {"post_draft": results}

def hitl_review_post(state: AgentState) -> Command[Literal["llm"]]:
    """Implementa Human In The Loop. Presenta la bozza del post generata all'utente in modo che possa: approvarla, modificarla, rifiutarla in modo
       che possa essere rigenerata.
    """

    # Recuperiamo la bozza del post scritta da llm
    post_draft = state.get("post_draft")

    if not post_draft:
        return Command(goto="llm")

    # Formattiamo la bozza
    post_draft_markdown = (
        f"**Titolo**: {post_draft.title}\n\n"
        f"**Categoria**: {post_draft.category}\n\n"
        f"{post_draft.introduction}\n"
        f"{post_draft.body}\n"
        f"{post_draft.conclusion}\n\n"
        f"**Fonti**: {post_draft.sources}\n"
    )

    # Creiamo dei messaggi
    msg = [HumanMessage(content=f"Revisione della bozza del post con titolo {post_draft.title}.")]

    reasoning_trace = state.get("reasoning_trace")
    topic_selection_justification = reasoning_trace[-1] if reasoning_trace else "Nessuna giustificazione per la selezione del topic."

    # Creiamo interrupt che viene mostrato all'utente
    request: HumanInterrupt  = {
        "action_request": {
            "action": "Revisione della bozza dell'articolo",
            "topic_selection_justification": topic_selection_justification,
            "args": {
                "title": post_draft.title,
                "introduction": post_draft.introduction,
                "body": post_draft.body,
                "conclusion": post_draft.conclusion
            }
        },
        "config": {
            "allow_ignore": False,  
            "allow_respond": True, 
            "allow_edit": True, 
            "allow_accept": True, 
        },
        "description": post_draft_markdown
    }

    response = interrupt([request])[0]

    # Inizializzazione di goto e update
    goto = "llm"
    update = {}

    if response["type"] == "accept":
        # L'utente ha approvato la bozza generata
        msg.append(HumanMessage(content=f"La bozza del post {post_draft.title} è stata approvata."))
        
        #goto = "knowledge_graph" 

        update = {"messages": msg}

    elif response["type"] == "edit":
        # L'utente modifica la bozza prima di approvarla
        edited_args = response["args"]

        # Controllo per Agent Inbox
        if isinstance(edited_args, dict) and "args" in edited_args:
            edited_args = edited_args["args"]

        edited_post_draft = PostFormat(
            category = edited_args.get("category", post_draft.category),
            title = edited_args.get("title", post_draft.title),
            introduction = edited_args.get("introduction", post_draft.introduction),
            body = edited_args.get("body", post_draft.body),
            conclusion = edited_args.get("conclusion", post_draft.conclusion),
            sources = post_draft.sources
        )

        msg.append(HumanMessage(content=f"La bozza del post {post_draft.title} è stata modificata manualmente dall'utente e poi approvata."))

        #goto = "knowledge_graph" 

        update = {
            "messages": msg,
            "post_draft": edited_post_draft
        }

    elif response["type"] == "response":
        # L'utente rifiuta la bozza che deve essere rigenerata
        response_args = response["args"]

        # Controllo effettuato se si usa Agent Inbox
        if isinstance(response_args, dict) and "args" in response_args:
            response_args = response_args["args"]

        if isinstance(response_args, dict) and "response" in response_args:
            user_feedback = response_args.get("response")
        else:
            user_feedback = str(response_args)

        msg.append(HumanMessage(content=f"L'utente ha rifiutato la bozza del post {post_draft.title}. Usa questo feedback per riscrivere il post: {user_feedback}"))

        #goto = "llm"

        update = {"messages": msg}

    else:
        raise ValueError(f"Risposta non valida: {response}")
    
    return Command(goto=goto, update=update)

def should_continue(state: AgentState):
    """Decide se è possibile scrivere la bozza dell'articolo oppure è necessario chiamare altri tool"""
    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "continue"
    elif state.get("extracted_claims"):
        return "save_to_knowledge_graph"
    else:
        return "format_article"
    
#def extract_claims_node(state: AgentState):
    post = state.get("post_draft")
    post_content = f"{post.category}\n{post.title}\n{post.introduction}\n{post.body}\n{post.conclusion}"
    
    response = llm_extractor.invoke([
        SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
        HumanMessage(content=f"Estrai i claim per il seguente post:\n{post_content}")
    ])
    
    tool_justification = ""
    current_thought = ""
    
    if response.tool_calls:
        print(f"[RISPOSTA CHATGPT]: {response}\n")
        
        tool_thought = response.tool_calls[0]["args"].get("justification", "Nessuna giustificazione rilevata.")
        current_thought = tool_thought
        
        # Gestione di sicurezza per lo strip
        if isinstance(tool_thought, str):
            current_thought = tool_thought.strip()
        else:
            current_thought = str(tool_thought)
            
        tool_name = response.tool_calls[0]["name"]
        tool_justification = f"Ho usato il tool {tool_name} per il seguente motivo: {current_thought}"

        print(f"[LLM]: giustificazione uso dei tool: {tool_justification}\n")

    return {
        "messages": [response],
        "reasoning_trace": [current_thought],
        "tool_usage_justification" : tool_justification
    }
      

def add_post_to_kg_node(state: AgentState) -> Command[Literal["llm", "__end__"]]:
    """Nodo finale del grafo: prende la bozza formattata dall'LLM, estrae i claim dal testo e salva tutto su Neo4j."""
    
    planning_info = state.get("planning_information")
    post = state.get("post_draft")
    matched_topic = state.get("matched_topic", "")
    count = state.get("posts_published_count", 0) # 0 deafult
    claims = state.get("extracted_claims", [])
    
    # Calcolo data di pubblicazione con delay di 2 giorni per post
    publish_date = datetime.now() + timedelta(days=count * 2)
    
    requested_topic = post.title

    if planning_info and planning_info.planned_post_sequence:
        requested_topic = planning_info.planned_post_sequence[0].topic

    print(f"[KNOWLEDGE GRAPH]: procedo ad aggiungere il post:")
    print(f"\nTitolo: {post.title}\n")
    print(f"Categoria: {post.category}\n")
    print(f"{post.introduction}\n")
    print(f"{post.body}\n")
    print(f"{post.conclusion}\n")

    print("Fonti:")
    for source in post.sources:
        print(f"- {source}")

    # Estrazione automatica dei Claim dalle righe del body
    #lines = [line.strip() for line in post.body.split("\n") if line.strip()]
    #claims_database = lines[:4] if lines else [f"Linee guida e indicazioni tecniche per {post.title}"]

    print("\n[KNOWLEDGE GRAPH]: Salvataggio dell'articolo e aggiornamento delle relazioni in corso...")
    
    try:
        kg_manager.add_approved_post(
            post_draft=post.model_dump(), # Converte l'oggetto Pydantic in dizionario standard
            requested_topic=requested_topic, 
            matched_topic=matched_topic, 
            claims=claims,
            publish_date=publish_date.date().isoformat()
        )
        print(f"[KNOWLEDGE GRAPH]: Il post con titolo {post.title} è stato aggiunto nel Knowledge graph")
    except Exception as e:
        print(f"[KNOWLEDGE GRAPH]: Impossibile aggiungere il post al Knowledge graph: {str(e)}")

    # Escludiamo il post che abbiamo appena aggiunto che si trova in posizione 0 della lista planned_post_sequence
    remaining_planned_posts = planning_info.planned_post_sequence[1:] if planning_info.planned_post_sequence else []

    if remaining_planned_posts:
        print(f"[KNOWLEDGE GRAPH]: rimangono ancora {len(remaining_planned_posts)} da pubblicare\n")
        
        updated_planning_info = planning_info.model_copy(update={"planned_post_sequence": remaining_planned_posts})

        delete_messages = [RemoveMessage(id=msg.id) for msg in state["messages"] if hasattr(msg, "id")]

        return Command(
            goto="llm",
            update={
                "messages": delete_messages, # Eliminiamo tutti i messaggi riguardanti il post appena pubblicato
                "posts_published_count": count + 1, # incrementiamo il numero di post pubblicati
                "planning_information": updated_planning_info,
                "post_draft": None,        # <--- RESET: Impedisce ri-esecuzioni
                "extracted_claims": []           
            }
        )
    else:
        print(f"[KNOWLEDGE GRAPH]: Non ci sono più post da pubblicare\n")

        return Command(
            goto=END
        )
    
graph = StateGraph(AgentState)

graph.add_node("planner", llm_planner_node)
graph.add_node("llm", llm_node)
graph.add_node("tool", tool_node)
graph.add_node("format", llm_format_node)
graph.add_node("knowledge_graph", add_post_to_kg_node)
graph.add_node("hitl_review", hitl_review_post)
#graph.add_node("llm_extractor", extract_claims_node)

graph.add_edge(START, "planner")
graph.add_edge("planner", "llm")
graph.add_conditional_edges(
    "llm",
    should_continue,
    {
        "continue": "tool",
        "format_article": "format",
        "save_to_knowledge_graph": "knowledge_graph"
    }
)

graph.add_edge("tool", "llm")
graph.add_edge("format", "hitl_review")
#graph.add_edge("llm_extractor", "tool") 
#graph.add_edge("tool", "knowledge_graph")

agent = graph.compile()