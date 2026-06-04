from typing import Literal

from dotenv import load_dotenv
import json

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool

from schemas import AgentState, HumanInterrupt, PostFormat
from prompts import SYSTEM_PROMPT, FORMAT_ARTICLE_PROMPT

from tools.web_search_tool import web_search_tool
from tools.rag_tool import rag_tool
from tools.knowledge_graph_tool import knowledge_graph_tool, kg_manager

load_dotenv(".env")

# Lista di tool
tools = [web_search_tool, rag_tool, knowledge_graph_tool] 
tools_by_name = {tool.name: tool for tool in tools}

# Inizializzazione del modello
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# Diamo accesso al modello ai tool
llm_with_tools = llm.bind_tools(tools)
    
def llm_node(state: AgentState):
    """Il modello analizza lo stato corrente e decide se chiamare un tool oppure fornire la risposta finale.

        Restituisce lo stato aggiornato con la risposta del modello
    """
    # Usiamo .get("kg_summary", "") per prendere il contesto e restituire una stringa vuota nella prima esecuzione
    blog_history_content = state.get("kg_summary", "")
    
    # Formattiamo il SYSTEM_PROMPT in modo sicuro
    formatted_system_prompt = SYSTEM_PROMPT.format(blog_history=blog_history_content)
    
    # Invocazione del modello
    response = llm_with_tools.invoke(
        [SystemMessage(content=formatted_system_prompt)] + state["messages"]
    )

    # Per tenere traccia del ragionamento
    current_thought = [response.text] if response.text else []

    return {
        "messages": [response],
        "reasoning_trace": current_thought
    }

def tool_node(state: AgentState):
    """Esegue tutte le chiamate ai tool relative alla precedente risposta dell'LLM.

       Restituisce lo stato aggiornato con i risultati delle esecuzioni dei tool.
    """
    last_message = state["messages"][-1] # Ultimo messaggio generato dall'LLM
    
    tool_calls = last_message.tool_calls # Richieste di chiamate ai tool dell'LLM

    tool_outputs = []
    rag_retrieved_docs = []
    
    summary_txt = state.get("kg_summary", "")
    consistency_txt = state.get("kg_consistency_context", "")
    
    requested_topic_txt = state.get("requested_topic", "")
    matched_topic_txt = state.get("matched_topic", "")

    # Eseguiamo tutte le chiamate ai tool
    for tool_call in tool_calls: 
        tool = tools_by_name[tool_call["name"]]

        print(f"[TOOL] L'agente ha richiesto il tool: '{tool_call["name"]}' con argomenti: {tool_call['args']}")

        observation = tool.invoke(tool_call["args"]) 

        if tool_call["name"] == "knowledge_graph_tool":
            observation_str = str(observation)
            if observation_str.startswith("Contenuto Storico:"): # Non è stato fornito il topic al tool
                summary_txt = observation_str
            else:
                try:
                    # E' stato fornito il topic al tool
                    data = json.loads(observation_str)
                    
                    consistency_txt = data["context"]
                    requested_topic_txt = data["requested_topic"] 
                    matched_topic_txt = data["matched_topic"]
                    
                    # Consegniamo all'LLM solo il testo pulito, nascondendo i metadati del JSON
                    observation_str = data["context"]
                except Exception as e:
                    print(f"[ERRORE PARSING JSON TOOL]: {e}")
                    consistency_txt = observation_str

        # Verifichiamo se è stato chiamato il tool RAG
        if tool_call["name"] == "rag_tool" and observation: # observation non deve essere ""
            rag_retrieved_docs = str(observation).split("|")

        # Messaggio di risposta del tool
        tool_outputs.append(
            ToolMessage(
                content=str(observation),
                name=tool_call["name"],
                tool_call_id=tool_call["id"]
            ) 
        )

    return {
        "messages": tool_outputs, 
        "tool_outputs": tool_outputs,
        "retrived_documents": rag_retrieved_docs,
        "kg_summary": summary_txt,
        "kg_consistency_context": consistency_txt,
        "requested_topic": requested_topic_txt,  
        "matched_topic": matched_topic_txt
    }

def llm_format_node(state: AgentState):
    """Formatta le informazioni restituite dal tool di ricerca per generare la bozza dell'articolo"""

    print("[WRITER] Formatto l'articolo...")
    
    # Recuperiamo il contesto di coerenza salvato dallo state
    consistency_data = state.get("kg_consistency_context", "")
    if not consistency_data or consistency_data.strip() == "":
        # !! VEDERE SE CONVIENE FORNIRE STRINGA VUOTA
        consistency_data = "Nessun vincolo precedente trovato per questo argomento. Procedi liberamente."

    # Iniettiamo dinamicamente il contesto nel prompt finale
    formatted_prompt = FORMAT_ARTICLE_PROMPT.format(consistency_context=consistency_data)

    structured_output_llm = llm.with_structured_output(PostFormat)

    results = structured_output_llm.invoke([SystemMessage(content=formatted_prompt)] + state["messages"])

    return {"post_draft": results}

def hitl_review_post(state: AgentState) -> Command[Literal["llm", "knowledge_graph"]]:
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

    # Creiamo interrupt che viene mostrato all'utente
    request: HumanInterrupt  = {
        "action_request": {
            "action": "Revisione della bozza dell'articolo",
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
        
        goto = "knowledge_graph" 

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

        goto = "knowledge_graph" 

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

        goto = "llm"

        update = {"messages": msg}

    else:
        raise ValueError(f"Risposta non valida: {response}")
    
    return Command(goto=goto, update=update)

def should_continue(state: AgentState):
    """Decide se è possibile scrivere la bozza dell'articolo oppure è necessario chiamare altri tool"""
    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "continue"
    else:
        return "format_article"
    
def add_post_to_kg_node(state: AgentState):
    """
    Nodo finale del grafo: prende la bozza formattata dall'LLM, 
    estrae i claim dal testo e salva tutto su Neo4j.
    """
    requested_topic = state.get("requested_topic")
    matched_topic = state.get("matched_topic", "")
    
    post = state.get("post_draft")
    print(f"[KNOWLEDGE GRAPH]: procedo ad aggiungere il post:")
    print(f"\nTitolo: {post.title}\n")
    print(f"Categoria: {post.category}\n")
    print(f"{post.introduction}\n")
    print(f"{post.body}\n")
    print(f"{post.conclusion}\n")

    print("Fonti:")
    for source in post.sources:
        print(f"- {source}")
    
    # Fallback sul titolo se l'LLM non ha popolato il requested_topic
    if not requested_topic or requested_topic.strip() == "":
        requested_topic = post.title

    # Estrazione automatica dei Claim dalle righe del body
    lines = [line.strip() for line in post.body.split("\n") if line.strip()]
    claims_database = lines[:4] if lines else [f"Linee guida e indicazioni tecniche per {post.title}"]

    print("\n[NEO4J NODO]: Salvataggio dell'articolo e aggiornamento delle relazioni in corso...")
    
    try:
        kg_manager.add_approved_post(
            post_draft=post.model_dump(), # Converte l'oggetto Pydantic in dizionario standard
            requested_topic=requested_topic, 
            matched_topic=matched_topic, 
            claims=claims_database
        )
        print("[NEO4J NODO]: Knowledge Graph aggiornato con successo!")
    except Exception as e:
        print(f"[ERRORE NEO4J NODO]: Impossibile salvare il post: {str(e)}")
    finally:
        kg_manager.close()
        print("[NEO4J NODO]: Chiuso collegamento con il database")

    return state
    
graph = StateGraph(AgentState)

graph.add_node("llm", llm_node)
graph.add_node("tool", tool_node)
graph.add_node("format", llm_format_node)
graph.add_node("knowledge_graph", add_post_to_kg_node)
graph.add_node("hitl_review", hitl_review_post)

graph.add_edge(START, "llm")
graph.add_conditional_edges(
    "llm",
    should_continue,
    {
        "continue": "tool",
        "format_article": "format"
    }
)
graph.add_edge("tool", "llm")
graph.add_edge("format", "hitl_review")
graph.add_edge("knowledge_graph", END)

agent = graph.compile()