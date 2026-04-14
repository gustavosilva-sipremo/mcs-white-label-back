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
    username: Optional[str] = None
    password: str
    email: EmailStr
    phone: Optional[str] = None
    type: str
    assignments: List[Assignment] = Field(default_factory=list)
    terms: List[Terms] = Field(default_factory=list)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    type: Optional[str] = None
    assignments: Optional[List[Assignment]] = None
    terms: Optional[List[Terms]] = None
    active: Optional[bool] = None
