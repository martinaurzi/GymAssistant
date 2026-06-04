from langchain_core.messages import HumanMessage

from graph import agent
from tools.knowledge_graph_tool import kg_manager

#initial_input = {
#    "messages": [HumanMessage(content="Pianifica un post su come fare un allenamento di dorso.")]
#}

initial_input = {
    "messages": [HumanMessage(content="[AVVIO]: Genera il prossimo post tenendo in considerazione la cronologia dei post recenti.")]
}

try:
    result = agent.invoke(initial_input)

    print(f"CRONOLOGIA DEI MESSAGGI: {result["messages"]}\n")

#post = result["post_draft"]

#print(f"\n--- POST {post.category} ---\n")
#print(f"Titolo: {post.title}\n")
#print(f"{post.introduction}\n")
#print(f"{post.body}\n")
#print(f"{post.conclusion}\n")

#print("Fonti:")
#for source in post.sources:
 #   print(f"- {source}")