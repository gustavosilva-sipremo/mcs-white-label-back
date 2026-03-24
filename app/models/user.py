from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional


class Assignment(BaseModel):
    type: str
    value: str


class Terms(BaseModel):
    name: str
    value: bool


class UserCreate(BaseModel):
    name: str
    username: str
    password: str
    email: EmailStr
    phone: Optional[str] = None
    type: str
    assignments: List[Assignment] = Field(default_factory=list)
    teams: List[str] = Field(default_factory=list)
    terms: List[Terms] = Field(default_factory=list)
