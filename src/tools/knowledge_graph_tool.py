from langchain_core.tools import tool
from database.neo4j_graph import EditorialKnowledgeGraphManager
import json
from typing import Annotated

kg_manager = EditorialKnowledgeGraphManager()

@tool
def knowledge_graph_tool(
    topic: str,
    justification: Annotated[str, "Spiegazione obbligatoria del perché stai usando questo tool proprio adesso."]
) -> str:
    """
        Effettua una ricerca semantica per ricavare quanto già è stato scritto sul topic e poter scrivere un post coerente sull'argomento.
        
        Argomenti:
            - topic: Il topic o argomento da cercare nel grafo per la coerenza semantica.
            - justification: La giustificazione obbligatoria per l'utilizzo del tool.
    """
    try:
        kg_res = kg_manager.search_similar_content(topic)

        print(f"[KG TOOL] {kg_res['context']}\n")
        
        return json.dumps({
            "context": kg_res["context"],
            "matched_topic": kg_res["matched_topic"]
        })
    except Exception as e:
        return f"Errore durante l'interrogazione del database grafico: {str(e)}"