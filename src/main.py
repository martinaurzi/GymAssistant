from langchain_core.messages import HumanMessage

from graph import agent

initial_input = {
    "messages": [HumanMessage(content="[AVVIO]: Genera il prossimo post tenendo in considerazione la cronologia dei post recenti.")]
}

result = agent.invoke(initial_input)

print(f"CRONOLOGIA DEI MESSAGGI: {result["messages"]}\n")
