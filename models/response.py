from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class ActionType(str, Enum):
    CREATE_EVENT = "create_event"
    LIST_EVENTS = "list_events"
    ADD_ATTENDEE = "add_attendee"
    DELETE_EVENT = "delete_event"
    UNKNOWN = "unknown"

class AIResponse(BaseModel):
    action: ActionType = Field(..., description="The type of calendar action to perform")
    message: str = Field(..., description="A natural language response to the user")
    parameters: Optional[dict] = Field(None, description="Parameters required for the calendar action")
