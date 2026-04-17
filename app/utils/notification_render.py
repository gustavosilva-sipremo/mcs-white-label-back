import re
from html import unescape

from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

# Variáveis de exemplo para prévia e teste PWA (substituíveis no futuro por contexto real).
MOCK_TEMPLATE_CONTEXT: dict[str, str] = {
    "nome": "João Silva",
    "email": "joao@empresa.com",
    "telefone": "(11) 98888-7777",
    "data_ocorrencia": "12/02/2026",
    "hora_ocorrencia": "14:32",
    "link_confirmacao": "https://app.exemplo.com/confirmar/abc123",
    "empresa": "Sipremo MCS",
    "titulo_alerta": "Nova ocorrência registrada",
}


def _env() -> SandboxedEnvironment:
    return SandboxedEnvironment(autoescape=True)


def render_jinja_fragment(template_str: str, context: dict | None = None) -> str:
    ctx = {**(context or {}), **MOCK_TEMPLATE_CONTEXT}
    try:
        return _env().from_string(template_str or "").render(**ctx)
    except (TemplateSyntaxError, UndefinedError) as e:
        raise ValueError(f"Erro no template Jinja2: {e}") from e


def strip_html_to_plain(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def wrap_email_document(inner_html: str, preview_title: str = "Pré-visualização") -> str:
    """Layout HTML moderno para e-mail (corpo já renderizado com Jinja)."""
    safe_inner = inner_html or ""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{preview_title}</title>
</head>
<body style="margin:0;padding:0;background-color:#0f172a;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:linear-gradient(160deg,#0f172a 0%,#1e293b 45%,#312e81 100%);padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width:560px;border-radius:16px;overflow:hidden;box-shadow:0 25px 50px -12px rgba(0,0,0,0.45);">
          <tr>
            <td style="background:linear-gradient(90deg,#6366f1,#8b5cf6);padding:20px 24px;">
              <p style="margin:0;font-size:11px;font-weight:600;letter-spacing:0.2em;text-transform:uppercase;color:rgba(255,255,255,0.85);">Notificação</p>
              <p style="margin:6px 0 0;font-size:20px;font-weight:700;color:#ffffff;line-height:1.25;">{preview_title}</p>
            </td>
          </tr>
          <tr>
            <td style="background:#ffffff;padding:28px 24px 32px;color:#0f172a;font-size:15px;line-height:1.65;">
              <div style="color:#334155;">{safe_inner}</div>
              <table role="presentation" width="100%" style="margin-top:28px;border-top:1px solid #e2e8f0;padding-top:20px;">
                <tr>
                  <td style="font-size:12px;color:#94a3b8;">
                    Mensagem gerada automaticamente · não responda a este e-mail de prévia.
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_inner_html(header: str, body: str, footer: str) -> str:
    chunks: list[str] = []
    for part in (header, body, footer):
        p = (part or "").strip()
        if p:
            chunks.append(f'<div style="margin-bottom:18px;">{p}</div>')
    return "".join(chunks)


def render_preview_bundle(
    header_template: str,
    body_template: str,
    footer_template: str,
    *,
    preview_title: str = "Pré-visualização",
    context: dict | None = None,
) -> dict:
    h = render_jinja_fragment(header_template, context)
    b = render_jinja_fragment(body_template, context)
    f = render_jinja_fragment(footer_template, context)
    inner = build_inner_html(h, b, f)
    email_html = wrap_email_document(inner, preview_title=preview_title)
    combined_plain = strip_html_to_plain(f"{h} {b} {f}")
    sms_text = strip_html_to_plain(combined_plain)
    # PWA: título curto + corpo
    title = strip_html_to_plain(h)[:80] or preview_title
    body = combined_plain[:600] if combined_plain else ""
    return {
        "email_html": email_html,
        "sms_text": sms_text,
        "pwa": {"title": title, "body": body},
    }
