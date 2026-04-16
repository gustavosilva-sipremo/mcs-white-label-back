from pydantic import BaseModel, Field


class QuestionnaireCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    questions: list[dict] = Field(default_factory=list)


class QuestionnaireUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    questions: list[dict] | None = None
