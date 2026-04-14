from pydantic import BaseModel, Field
from typing import List, Optional


class ListItem(BaseModel):
    label: str
    value: str


class GenericListCreate(BaseModel):
    name: str
    description: Optional[str] = None
    items: List[ListItem] = Field(default_factory=list)


class GenericListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    items: Optional[List[ListItem]] = None
