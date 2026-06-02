from dotenv import load_dotenv
import json

from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool

from schemas import AgentState, PostFormat
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

    return {"messages": [response]}

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
            if observation_str.startswith("Contenuto Storico:"):
                summary_txt = observation_str
            else:
                try:
                    # Estraiamo comodamente tutte e tre le informazioni passate dal tool
                    data = json.loads(observation_str)
                    
                    consistency_txt = data["context"]
                    requested_topic_txt = data["requested_topic"]  # <-- Preso direttamente dal JSON
                    matched_topic_txt = data["matched_topic"]
                    
                    # Consegniamo all'LLM solo il testo pulito, nascondendo i metadati del JSON
                    observation_str = data["context"]
                except Exception as e:
                    print(f"[ERRORE PARSING JSON TOOL]: {e}")
                    consistency_txt = observation_str

        # Verifichiamo se è stato chiamato il tool RAG
        if tool_call["name"] == "rag_tool" and observation: # observation non deve essere ""
            rag_retrieved_docs = str(observation).split("|")
        
            #print(f"[TOOL] Documenti recuperati: {rag_retrieved_docs}\n")

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

def should_continue(state: AgentState):
    """Decide se è possibile scrivere la bozza dell'articolo oppure è necessario chiamare altri tool"""
    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "continue"
    else:
        return "format_article"
    
def save_to_kg_node(state: AgentState):
    """
    Nodo finale del grafo: prende la bozza formattata dall'LLM, 
    estrae i claim dal testo e salva tutto su Neo4j.
    """
    post = state["post_draft"]
    requested_topic = state.get("requested_topic")
    matched_topic = state.get("matched_topic", "")
    
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

    return state
    
graph = StateGraph(AgentState)

graph.add_node("llm", llm_node)
graph.add_node("tool", tool_node)
graph.add_node("format", llm_format_node)
graph.add_node("save_to_kg", save_to_kg_node)

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

graph.add_edge("format", "save_to_kg")
graph.add_edge("save_to_kg", END)

agent = graph.compile()