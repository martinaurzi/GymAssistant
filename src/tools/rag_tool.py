from langchain_core.tools import tool

from typing import Annotated

from rag.rag_manager import RagManager

rag_manager = RagManager()

@tool
def rag_tool(
    query: str,
    justification: Annotated[str, "Spiegazione obbligatoria del perché stai usando questo tool proprio adesso."]
) -> str:
    """Recupera i documenti più rilevanti rispetto alla query.

    Argomenti:
        query: La stringa di ricerca da usare per il recupero dei documenti.
        justification: La giustificazione obbligatoria per l'utilizzo del tool.
    """

    retrieved_docs = rag_manager.retrieve_documents(query=query)

    if not retrieved_docs:
        return "" 

    print(f"[RAG TOOL] Recuperati {len(retrieved_docs)} documenti\n")

    # Restituisco una singola stringa ottenuta dalla concatenazione dei singoli documenti separati da "|"
    return ("|").join(retrieved_docs)