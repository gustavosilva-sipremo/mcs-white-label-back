from pydantic import BaseModel, Field
from typing import List, Optional


class TeamCreate(BaseModel):
    name: str
    description: Optional[str] = None
    member_user_ids: List[str] = Field(default_factory=list)


class TeamUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    member_user_ids: Optional[List[str]] = None
