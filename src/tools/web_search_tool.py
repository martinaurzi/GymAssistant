from typing import Annotated
from dotenv import load_dotenv

from langchain_core.tools import InjectedToolArg, tool
from tavily import TavilyClient

load_dotenv(".env")

tavily_client = TavilyClient()

@tool
def web_search_tool(query: str, max_results: Annotated[int, InjectedToolArg] = 3,) -> str:
    """Cerca informazioni su internet usando la Tavily search API.

    Argomenti:
        query: Una singola query di ricerca da eseguire
        max_results: Massimo numero di risultati da restituire
        
    Restituisce:
        Una stringa formattata con i risultati della ricerca
    """
    tavily_results = tavily_client.search(query=query, max_results=max_results, include_raw_content=True)

    return tavily_results