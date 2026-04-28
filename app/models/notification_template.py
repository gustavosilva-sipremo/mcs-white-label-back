from pydantic import BaseModel, Field, field_validator, model_validator

ALLOWED_CHANNELS: frozenset[str] = frozenset({"email", "sms", "whatsapp", "pwa"})


class ChannelSubtemplates(BaseModel):
    header_template: str = ""
    body_template: str = ""
    footer_template: str = ""


class NotificationTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1)
    channels: list[str] = Field(..., min_length=1)
    channel_templates: dict[str, ChannelSubtemplates] | None = None
    header_template: str = ""
    body_template: str = ""
    footer_template: str = ""
    sms_template: str = Field(
        default="",
        description="Texto curto legado para SMS. Ex.: {{ link_curto }}",
    )

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

    @model_validator(mode="after")
    def validate_templates_for_channels(self):
        # Compat: aceita payload legado, mas exige conteúdo para todos os canais ativos.
        channel_templates = self.channel_templates or {}
        for channel in self.channels:
            tpl = channel_templates.get(channel)
            if tpl:
                if not (
                    tpl.header_template.strip()
                    and tpl.body_template.strip()
                    and tpl.footer_template.strip()
                ):
                    raise ValueError(
                        f"channel_templates.{channel} must contain 3 non-empty subtemplates",
                    )
                continue

            if channel == "sms":
                if not self.sms_template.strip():
                    raise ValueError(
                        "sms_template is required when channel 'sms' is selected",
                    )
                continue

            if not (
                self.header_template.strip()
                and self.body_template.strip()
                and self.footer_template.strip()
            ):
                raise ValueError(
                    f"Missing 3 subtemplates for channel '{channel}'",
                )
        return self


class NotificationTemplateUpdate(BaseModel):
    name: str | None = None
    channels: list[str] | None = None
    channel_templates: dict[str, ChannelSubtemplates] | None = None
    header_template: str | None = None
    body_template: str | None = None
    footer_template: str | None = None
    sms_template: str | None = None

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
    channel_templates: dict[str, ChannelSubtemplates] | None = None
    header_template: str = ""
    body_template: str = ""
    footer_template: str = ""
    sms_template: str = ""
    preview_title: str = "Pré-visualização"
    brand_primary: str | None = Field(
        default=None,
        description="Cor principal do tenant (#hex ou hsl(...)) para o e-mail.",
    )
    brand_primary_foreground: str | None = Field(
        default=None,
        description="Cor do texto sobre o botão / acento (tema claro), ex.: hsl(...).",
    )
    logo_url: str | None = Field(
        default=None,
        description="URL absoluta https do logo do tenant para o cabeçalho do e-mail.",
    )
