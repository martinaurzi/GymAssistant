from typing import Annotated, Literal, Optional, TypedDict, Union
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

def add_thought_trace(current_trace: list[str], new_thought: list[str]) -> list[str]:
    """Funzione per accumulare le reasoning traces"""
    return current_trace + new_thought

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages] # Cronologia dei messaggi
    reasoning_trace: Annotated[list[str], add_thought_trace] 
    tool_outputs: Annotated[list[ToolMessage], add_messages]
    retrived_documents: list[str] # RAG
    post_draft: Annotated[PostFormat, lambda old_draft, new_draft: new_draft]
    kg_summary: str #contiene i topic già trattati e titolo,categoria e topic dei post piu recenti
    kg_consistency_context: str #contiene titoli e claim dei post relativi al topic corrente
    requested_topic: str  # Il topic scelto dall'LLM
    matched_topic: str    # Il topic più simile trovato dall'indice vettoriale di Neo4j

class PostFormat(BaseModel):
    category: str = Field(description="La categoria scelta (es. HOW_TO, REVIEW, NEWS, EVENTS)")
    title: str = Field(description="Il titolo del post")
    introduction: str = Field(description="L'introduzione del post")
    body: str = Field(description="Il corpo dell'articolo organizzato in paragrafi e punti elenco")
    conclusion: str = Field(description="La conclusione del post")
    sources: list[str] = Field(description="Fonti da cui sono state recuperate le informazioni del post")

class HumanInterruptConfig(TypedDict):
    allow_ignore: bool
    allow_respond: bool
    allow_edit: bool
    allow_accept: bool

class ActionRequest(TypedDict):
    action: str
    args: dict

class HumanInterrupt(TypedDict):
    action_request: ActionRequest
    config: HumanInterruptConfig
    description: Optional[str]

class HumanResponse(TypedDict):
    type: Literal['accept', 'response', 'edit']
    args: Union[None, str, ActionRequest]