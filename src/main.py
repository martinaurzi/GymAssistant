from langchain_core.messages import HumanMessage

from graph import agent 

initial_input = {
    "messages": [HumanMessage(content="Pianifica un post su come fare un allenamento di dorso.")]
}

result = agent.invoke(initial_input)

post = result["post_draft"]

print("\n--- POST ---")
print(f"Categoria: {post.category}")
print(f"Titolo: {post.title}")
print(f"\n{post.introduction}")
print(f"\n{post.body}")
print(f"\n{post.conclusion}")