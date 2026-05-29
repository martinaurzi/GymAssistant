from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages] # storia dei messaggi
    post_draft: PostFormat

class PostFormat(BaseModel):
    category: str = Field(description="La categoria scelta (es. HOW_TO, REVIEW, NEWS, EVENTS)")
    title: str = Field(description="Il titolo del post")
    introduction: str = Field(description="L'introduzione del post")
    body: str = Field(description="Il corpo dell'articolo formattato in Markdown con paragrafi e punti elenco")
    conclusion: str = Field(description="La conclusione del post")