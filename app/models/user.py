from pydantic import BaseModel, EmailStr
from typing import List, Optional
from uuid import UUID


class Assignment(BaseModel):
    type: str
    value: str


class Terms(BaseModel):
    name: str
    value: bool


class User(BaseModel):
    id: Optional[str]
    tenant_id: str
    name: str
    username: str
    email: EmailStr
    phone: Optional[str]
    type: str
    assignments: List[Assignment] = []
    teams: List[str] = []
    active: bool
    terms: List[Terms] = []
