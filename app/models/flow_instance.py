# app/models/flow_instance.py
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FlowInstanceCreate(BaseModel):
    """Start a run from the tenant main flow (pinned version + plan snapshot)."""

    model_config = ConfigDict(populate_by_name=True)

    entry_branch_key: str = Field(..., min_length=1, validation_alias="entryBranchKey")
    client_request_id: Optional[str] = Field(
        default=None,
        validation_alias="clientRequestId",
    )


class FlowInstanceAdvance(BaseModel):
    """Advance compass along the current branch (linear next step)."""

    model_config = ConfigDict(populate_by_name=True)

    client_request_id: Optional[str] = Field(
        default=None,
        validation_alias="clientRequestId",
    )
    payload: Optional[dict[str, Any]] = None
