from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class GenericListCreate(BaseModel):
    name: str
    description: Optional[str] = None
    items: List[Dict[str, str]] = Field(default_factory=list)
    option_schema: Optional[Dict[str, object]] = None


class GenericListUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    items: Optional[List[Dict[str, str]]] = None
    option_schema: Optional[Dict[str, object]] = None
