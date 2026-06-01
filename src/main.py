from langchain_core.messages import HumanMessage

from graph import agent
from tools.knowledge_graph_tool import kg_manager

#initial_input = {
#    "messages": [HumanMessage(content="Pianifica un post su come fare un allenamento di dorso.")]
#}

initial_input = {
    "messages": [HumanMessage(content="[AVVIO]: Genera il prossimo post tenendo in considerazione la cronologia dei post recenti.")]
}

result = agent.invoke(initial_input)

print(f"CRONOLOGIA DEI MESSAGGI: {result["messages"]}\n")

post = result["post_draft"]

print(f"\n--- POST {post.category} ---\n")
print(f"Titolo: {post.title}\n")
print(f"{post.introduction}\n")
print(f"{post.body}\n")
print(f"{post.conclusion}\n")

print("Fonti:")
for source in post.sources:
    print(f"- {source}")
    
# Estrazione automatica dei Claim dalle righe del body
lines = [line.strip() for line in post.body.split("\n") if line.strip()]
claims_database = lines[:4] if lines else [f"Linee guida e indicazioni tecniche per {post.title}"]

# Converte l'oggetto Pydantic in dizionario standard
post_dict = post.model_dump()

try:
    print("[NEO4J]: Salvataggio dell'articolo e aggiornamento delle relazioni...")
    kg_manager.add_approved_post(
        post_draft=post_dict, 
        topic_name=post.title, 
        claims=claims_database
    )
    print("[NEO4J]: Grafo aggiornato con successo!")
except Exception as e:
    print(f"[ERRORE NEO4J]: Impossibile salvare il post nel database: {str(e)}")
    
kg_manager.close()