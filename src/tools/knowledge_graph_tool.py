from langchain_core.tools import tool
from database.neo4j_graph import EditorialKnowledgeGraphManager
import json

kg_manager = EditorialKnowledgeGraphManager()

@tool
def knowledge_graph_tool(topic: str = "") -> str:
    """
    Strumento unico per interagire con la base di conoscenza interna su Neo4j.
    - Se NON passi alcun argomento (stringa vuota): restituisce lo STORICO completo del blog.
    - Se PASSI un argomento (topic specifico): effettua una RICERCA SEMANTICA per ricavare quanto già è stato scritto sul topic e poter scrivere un post coerente sull'argomento.
    """
    try:
        # Se l'argomento è vuoto, restituiamo lo storico del blog
        if not topic or topic.strip() == "":
            kg_summary = kg_manager.get_kg_summary()
            print(f"[KG TOOL] {kg_summary}\n")
            return kg_summary
        
        # Se viene passato un topic, eseguiamo il controllo di coerenza semantica
        kg_res = kg_manager.search_similar_content(topic)
        print(f"[KG TOOL] {kg_res['context']}\n")
        
        return json.dumps({
            "context": kg_res["context"],
            "requested_topic": topic,
            "matched_topic": kg_res["matched_topic"]
        })
        
    except Exception as e:
        return f"Errore durante l'interrogazione del database grafico: {str(e)}"