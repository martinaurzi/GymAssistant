from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool

from schemas import AgentState, PostFormat
from prompts import SYSTEM_PROMPT, FORMAT_ARTICLE_PROMPT
from tools.web_search_tool import web_search_tool

load_dotenv(".env")

# Creiamo una lista di tool
tools = [web_search_tool] 
tools_by_name = {tool.name: tool for tool in tools}

# Inizializziamo il modello
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)

# Diamo accesso al modello ai tool
llm_with_tools = llm.bind_tools(tools) #, tool_choice="any"

def llm_node(state: AgentState):
    """Il modello analizza lo stato corrente e decide se chiamare un tool oppure fornire la risposta finale.

        Restituisce lo stato aggiornato con la risposta del modello
    """
    response = llm_with_tools.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]) # Uniamo il SYSTEM PROMPT con la cronologia di messaggi

    return {"messages": [response]}

def tool_node(state: AgentState):
    """Esegue tutte le chiamate ai tool relative alla precedente risposta dell'LLM.

       Restituisce lo stato aggiornato con i risultati delle esecuzioni dei tool.
    """
    last_message = state["messages"][-1] # Ultimo messaggio generato dall'LLM
    
    tool_calls = last_message.tool_calls # Richieste di chiamate ai tool dell'LLM

    # Eseguiamo tutte le chiamate ai tool
    tool_outputs = []

    for tool_call in tool_calls: # vedere se si può togliere
        tool = tools_by_name[tool_call["name"]]

        print(f"[TOOL] L'agente ha richiesto il tool: '{tool_call["name"]}' con argomenti: {tool_call['args']}")

        observation = tool.invoke(tool_call["args"]) 

        # Messaggio di risposta del tool
        tool_outputs.append(
            ToolMessage(
                content=str(observation),
                name=tool_call["name"],
                tool_call_id=tool_call["id"]
            ) 
        )

    return {"messages": tool_outputs}

def llm_format_node(state: AgentState):
    """Formatta le informazioni restituite dal tool di ricerca per generare la bozza dell'articolo"""

    print("[WRITER] Formatto l'articolo...")

    structured_output_llm = llm.with_structured_output(PostFormat)

    results = structured_output_llm.invoke([SystemMessage(content=FORMAT_ARTICLE_PROMPT)] + state["messages"])

    return {"post_draft": results}

def should_continue(state: AgentState) -> AgentState:
    """Decide se è possibile scrivere la bozza dell'articolo oppure è necessario chiamare altri tool"""
    last_message = state["messages"][-1]

    if last_message.tool_calls:
        return "continue"
    else:
        print("[FORMAT] Formatto la bozza dell'articolo")
        return "format_article"
    
graph = StateGraph(AgentState)

graph.add_node("llm", llm_node)
graph.add_node("tool", tool_node)
graph.add_node("format", llm_format_node)

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
graph.add_edge("format", END)

agent = graph.compile()