from typing import Annotated
from dotenv import load_dotenv

from langchain_core.tools import InjectedToolArg, tool
from tavily import TavilyClient

load_dotenv(".env")

tavily_client = TavilyClient()

@tool
def web_search_tool(
    query: str, 
    justification: Annotated[str, "Spiegazione obbligatoria del perché stai usando questo tool proprio adesso."],
    max_results: Annotated[int, InjectedToolArg] = 3,
)-> str:
    """Cerca informazioni su internet usando la Tavily search API.

        Argomenti:
            - query: Una singola query di ricerca da eseguire
            - justification: La giustificazione obbligatoria per l'utilizzo del tool.
            - max_results: Massimo numero di risultati da restituire
            
        Restituisce:
            Una stringa formattata con i risultati della ricerca
    """
    
    tavily_results = tavily_client.search(query=query, max_results=max_results, include_raw_content='markdown', include_images=False)

    cleaned_res = []

    print(f"[WEB SEARCH TOOL]: {tavily_results}")

    if "results" in tavily_results:
        for res in tavily_results["results"]:
            source = res.get("url")
            title = res.get("title")
            score = res.get("score")
            content = res.get("raw_content") or res.get("content")

            cleaned_res.append(f"Fonte: {source}, Titolo: {title}, Score: {score}, Contenuto: {content.strip()}")

    return ("|").join(cleaned_res)