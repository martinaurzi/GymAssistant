from langchain_core.messages import HumanMessage

from graph import agent
from tools.knowledge_graph_tool import kg_manager

initial_input = {
    "messages": [HumanMessage(content="[AVVIO]: Genera il prossimo post tenendo in considerazione la cronologia dei post recenti.")]
}

try:
    result = agent.invoke(initial_input)
    
    #post = result["post_draft"]

    #print(f"\n--- POST {post.category} ---\n")
    #print(f"Titolo: {post.title}\n")
    #print(f"{post.introduction}\n")
    #print(f"{post.body}\n")
    #print(f"{post.conclusion}\n")

    #print("Fonti:")
    #for source in post.sources:
    #   print(f"- {source}")

    print(f"CRONOLOGIA DEI MESSAGGI: {result["messages"]}\n")
except Exception as e:
    print(f"\n[ERRORE AGENTE]: Si è verificato un problema durante l'esecuzione: {e}")
finally:
    # Garanzia di chiusura del driver.
    print("\n[MAIN]: Chiusura delle connessioni con il database...")
    kg_manager.close()
    print("[MAIN]: Chiusura completata.")