from pydantic import BaseModel, Field, field_validator

ALLOWED_CHANNELS: frozenset[str] = frozenset({"email", "sms", "whatsapp", "pwa"})


class NotificationTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1)
    channels: list[str] = Field(..., min_length=1)
    header_template: str = ""
    body_template: str = ""
    footer_template: str = ""

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one channel is required")
        seen: set[str] = set()
        out: list[str] = []
        for c in v:
            s = str(c).strip().lower()
            if s not in ALLOWED_CHANNELS:
                raise ValueError(f"Invalid channel: {c}")
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out


class NotificationTemplateUpdate(BaseModel):
    name: str | None = None
    channels: list[str] | None = None
    header_template: str | None = None
    body_template: str | None = None
    footer_template: str | None = None

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        if not v:
            raise ValueError("channels cannot be empty")
        seen: set[str] = set()
        out: list[str] = []
        for c in v:
            s = str(c).strip().lower()
            if s not in ALLOWED_CHANNELS:
                raise ValueError(f"Invalid channel: {c}")
            if s not in seen:
                seen.add(s)
                out.append(s)
        return out


class NotificationPreviewBody(BaseModel):
    header_template: str = ""
    body_template: str = ""
    footer_template: str = ""
    preview_title: str = "Pré-visualização"
