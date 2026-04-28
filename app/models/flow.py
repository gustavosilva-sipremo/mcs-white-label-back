# app/models/flow.py
from typing import Any, Optional

from pydantic import BaseModel, Field, AliasChoices


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
    #: Preview na Home/runtime: usar versão publicada existente; `null` remove override.
    home_runtime_version: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("home_runtime_version", "homeRuntimeVersion"),
    )


class FlowVersionSave(BaseModel):
    graph: FlowGraphPayload
