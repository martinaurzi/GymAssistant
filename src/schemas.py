from typing import Annotated, Literal, Optional, TypedDict, Union, List
from langchain_core.messages import BaseMessage, ToolMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

def add_trace(current_trace: list[str], new_trace: list[str]) -> list[str]:
    """Funzione per accumulare i pensieri della reasoning trace"""
    return current_trace + new_trace

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages] # Cronologia dei messaggi
    reasoning_trace: Annotated[list[str], add_trace] 
    tool_outputs: Annotated[list[ToolMessage], add_messages]
    retrived_documents: list[str] # RAG
    #web_search_results: list[str]
    post_draft: Annotated[PostFormat, lambda old_draft, new_draft: new_draft]
    kg_summary: str #contiene i topic già trattati e titolo,categoria e topic dei post piu recenti
    kg_consistency_context: str #contiene titoli e claim dei post relativi al topic corrente
    #requested_topic: str  # SI PUO TOGLIERE PERCHE HO MESSO planning_information
    matched_topic: str    # Il topic più simile trovato dall'indice vettoriale di Neo4j
    planning_information: Annotated[PlannerFormat, lambda old_plan, new_plan: new_plan]
    tool_usage_justification: str

class PlannedPost(BaseModel):
    category: str = Field(description="La categoria scelta (es. HOW TO, REVIEW, NEWS, EVENTS)")
    topic: str = Field(description="L'argomento del post")

class PlannerFormat(BaseModel):
    planned_post_sequence: list[PlannedPost] = Field(description="La sequenza dei prossimi post da pubblicare.")
    topic_justification: str = Field(description="Il motivo per cui è stato scelto questo argomento")

class PostFormat(BaseModel):
    category: str = Field(description="La categoria scelta (es. HOW_TO, REVIEW, NEWS, EVENTS)")
    title: str = Field(description="Il titolo del post")
    introduction: str = Field(description="L'introduzione del post")
    body: str = Field(description="Il corpo dell'articolo organizzato in paragrafi e punti elenco")
    conclusion: str = Field(description="La conclusione del post")
    sources: list[str] = Field(description="Fonti da cui sono state recuperate le informazioni del post")

class EvaluatedSource(BaseModel):
    url: str = Field(description="URL della fonte valutata")
    title: str = Field(description="Titolo della risorsa")
    accuracy_score: int = Field(description="Punteggio di accuratezza percetuale da 0 a 100")
    interestingness_score: int = Field(description="Punteggio di interesse/originalità per i lettori da 1 a 10")
    justification: str = Field(description="Breve motivazione del punteggio assegnato e verifica dei fatti")
    is_selected: bool = Field(description="True se la fonte supera i criteri di qualità ed è consigliata per il post, False altrimenti")

class JudgeEvaluation(BaseModel):
    evaluated_sources: List[EvaluatedSource] = Field(description="Lista delle fonti analizzate con i relativi giudizi")
    verdict_summary: str = Field(description="Sintesi complessiva della qualità del materiale raccolto")

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