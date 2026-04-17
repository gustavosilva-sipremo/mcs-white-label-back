# app/models/flow.py
from typing import Any, Optional

from pydantic import BaseModel, Field


class FlowGraphPayload(BaseModel):
    """React Flow compatible graph snapshot."""

    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)


class FlowCreate(BaseModel):
    name: str
    description: Optional[str] = None
    graph: Optional[FlowGraphPayload] = None


class FlowUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None
    is_main: Optional[bool] = None


class FlowVersionSave(BaseModel):
    graph: FlowGraphPayload
