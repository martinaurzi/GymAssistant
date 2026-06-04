from typing import Literal

from dotenv import load_dotenv

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool

from schemas import AgentState, HumanInterrupt, PostFormat
from prompts import SYSTEM_PROMPT, FORMAT_ARTICLE_PROMPT

from tools.web_search_tool import web_search_tool
from tools.rag_tool import rag_tool

load_dotenv(".env")

# Lista di tool
tools = [web_search_tool, rag_tool] 
tools_by_name = {tool.name: tool for tool in tools}

# Inizializzazione del modello
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# Diamo accesso al modello ai tool
llm_with_tools = llm.bind_tools(tools)

def llm_node(state: AgentState):
    """Il modello analizza lo stato corrente e decide se chiamare un tool oppure fornire la risposta finale.

        Restituisce lo stato aggiornato con la risposta del modello
    """
    
    # Deve essere sostituito dal Knowledge Graph
    MOCK_BLOG_HISTORY = """
    - Post 1 - HOW TO: "Esercizi spalle con manubri" - Pubblicato il 15/05/2026
    - Post 2 - REVIEW: "Recensione cintura per trazioni" - Pubblicato il 22/05/2026
    - Post 3 - NEWS: "Nuova scoperta nel mondo del bodybuilding!" - Pubblicato il 23/05/2026
    """

    response = llm_with_tools.invoke([SystemMessage(content=SYSTEM_PROMPT.format(blog_history=MOCK_BLOG_HISTORY))] + state["messages"]) # Uniamo il SYSTEM PROMPT con la cronologia di messaggi

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

    # Eseguiamo tutte le chiamate ai tool
    for tool_call in tool_calls: 
        tool = tools_by_name[tool_call["name"]]

        print(f"[TOOL] L'agente ha richiesto il tool: '{tool_call["name"]}' con argomenti: {tool_call['args']}")

        observation = tool.invoke(tool_call["args"]) 

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
        "retrived_documents": rag_retrieved_docs
    }

def llm_format_node(state: AgentState):
    """Formatta le informazioni restituite dal tool di ricerca per generare la bozza dell'articolo"""

    print("[WRITER] Formatto l'articolo...")

    structured_output_llm = llm.with_structured_output(PostFormat)

    results = structured_output_llm.invoke([SystemMessage(content=FORMAT_ARTICLE_PROMPT)] + state["messages"])

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
        
        goto = "knowledge_graph" # INSERIRE NODO KNOWLEDGE GRAPH

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

        goto = "knowledge_graph" # INSERIRE NODO KNOWLEDGE GRAPH

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

def knowledge_graph_node(state: AgentState):
    """"""
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

    return {}

def should_continue(state: AgentState):
    """Decide se è possibile scrivere la bozza dell'articolo oppure è necessario chiamare altri tool"""
    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "continue"
    else:
        return "format_article"
    
graph = StateGraph(AgentState)

graph.add_node("llm", llm_node)
graph.add_node("tool", tool_node)
graph.add_node("format", llm_format_node)
graph.add_node("hitl_review", hitl_review_post)
graph.add_node("knowledge_graph", knowledge_graph_node)

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