import re
from html import escape, unescape

from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

# Variáveis mock (alinhadas ao front). Inclui links longo vs curto para SMS.
MOCK_TEMPLATE_CONTEXT: dict[str, str] = {
    "nome": "João Silva",
    "email": "joao@empresa.com",
    "telefone": "(11) 98888-7777",
    "data_ocorrencia": "12/02/2026",
    "hora_ocorrencia": "14:32",
    "link_confirmacao": "https://app.exemplo.com/confirmar/abc123def456",
    "link_curto": "https://ex.io/x7k",
    "link_confirmacao_curta": "https://ex.io/c9m",
    "empresa": "Sipremo MCS",
    "titulo_alerta": "Nova ocorrência registrada",
}

_HTML_BLOCK = re.compile(
    r"<\s*/?\s*(p|div|span|table|ul|ol|li|br|h[1-6]|a|img|strong|em|b|i|section|article)\b",
    re.I,
)


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


def strip_urls_for_toast(text: str) -> str:
    """Remove URLs para prévia PWA (toast só com mensagem)."""
    s = re.sub(r"https?://[^\s]+", "", text or "", flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


def sanitize_brand_color(value: str | None) -> str:
    """Aceita #RRGGBB ou hsl(...); evita injeção em atributos style."""
    if not value or not isinstance(value, str):
        return "#4f46e5"
    v = value.strip()[:120]
    if re.match(r"^#[0-9a-fA-F]{3,8}$", v):
        return v
    if re.match(r"^hsla?\([^)]{0,100}\)$", v, re.I):
        return v
    if re.match(r"^rgb\([^)]{0,100}\)$", v, re.I):
        return v
    return "#4f46e5"


def _looks_like_html_fragment(s: str) -> bool:
    return bool(_HTML_BLOCK.search(s or ""))


def _plain_text_to_email_html(text: str) -> str:
    """
    Converte texto simples em HTML seguro: quebras de linha, parágrafos e listas (- ou *).
    Se o autor já usar tags HTML, use _looks_like_html_fragment e pule esta etapa.
    """
    raw = (text or "").strip()
    if not raw:
        return ""
    esc = escape(raw)
    lines = esc.split("\n")
    blocks: list[str] = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "":
            i += 1
            continue
        if re.match(r"^[-*]\s+", stripped):
            items: list[str] = []
            while i < len(lines):
                ln = lines[i].strip()
                m = re.match(r"^[-*]\s+(.*)$", ln)
                if not m:
                    break
                items.append(
                    f'<li style="margin:3px 0;color:#334155;font-size:14px;line-height:1.5;">{m.group(1)}</li>',
                )
                i += 1
            blocks.append(
                '<ul style="margin:6px 0 12px;padding-left:22px;list-style-type:disc;">'
                + "".join(items)
                + "</ul>",
            )
            continue
        para: list[str] = []
        while i < len(lines):
            ln = lines[i]
            st = ln.strip()
            if st == "":
                i += 1
                break
            if re.match(r"^[-*]\s+", st):
                break
            para.append(ln)
            i += 1
        if para:
            inner = "<br/>".join(para)
            blocks.append(
                f'<p style="margin:0 0 10px;line-height:1.55;color:#334155;font-size:14px;">{inner}</p>',
            )
    return "".join(blocks)


def enrich_email_fragment(fragment: str) -> str:
    """Quebras de linha e listas para trechos sem HTML; preserva HTML explícito."""
    frag = (fragment or "").strip()
    if not frag:
        return ""
    if _looks_like_html_fragment(frag):
        return frag
    return _plain_text_to_email_html(frag)


def wrap_email_document(
    inner_html: str,
    preview_title: str = "Pré-visualização",
    brand_primary: str | None = None,
) -> str:
    """Layout HTML compacto, tema claro — acento na cor principal do tenant."""
    primary = sanitize_brand_color(brand_primary)
    safe_inner = inner_html or ""
    safe_title = (
        preview_title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="X-UA-Compatible" content="IE=edge" />
  <title>{safe_title}</title>
</head>
<body style="margin:0;padding:12px;background-color:#eef1f5;font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;margin:0 auto;">
    <tr>
      <td style="background:#ffffff;border-radius:10px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 1px 3px rgba(15,23,42,0.06);">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
          <tr>
            <td style="padding:12px 16px 10px;border-left:4px solid {primary};background:#f8fafc;">
              <p style="margin:0;font-size:10px;font-weight:600;letter-spacing:0.12em;text-transform:uppercase;color:#64748b;">Notificação</p>
              <p style="margin:4px 0 0;font-size:17px;font-weight:700;line-height:1.3;color:#0f172a;">{safe_title}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:14px 16px 16px;background:#ffffff;color:#334155;font-size:14px;line-height:1.6;">
              {safe_inner}
            </td>
          </tr>
          <tr>
            <td style="padding:10px 16px;background:#f1f5f9;border-top:1px solid #e2e8f0;">
              <p style="margin:0;font-size:11px;line-height:1.45;color:#94a3b8;">
                Pré-visualização com dados de exemplo · tema claro.
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
    <tr>
      <td align="center" style="padding:10px 8px 0;">
        <p style="margin:0;font-size:10px;color:#94a3b8;">© {escape(MOCK_TEMPLATE_CONTEXT.get("empresa", ""))}</p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def build_inner_html(header: str, body: str, footer: str) -> str:
    parts = [(header or "").strip(), (body or "").strip(), (footer or "").strip()]
    non_empty = [p for p in parts if p]
    chunks: list[str] = []
    for i, p in enumerate(non_empty):
        border = "border-bottom:1px solid #eef2f6;" if i < len(non_empty) - 1 else ""
        chunks.append(
            f'<div style="margin-bottom:12px;padding-bottom:12px;{border}">{p}</div>',
        )
    return "".join(chunks)


def render_preview_bundle(
    header_template: str,
    body_template: str,
    footer_template: str,
    sms_template: str,
    *,
    preview_title: str = "Pré-visualização",
    brand_primary: str | None = None,
    context: dict | None = None,
) -> dict:
    h = render_jinja_fragment(header_template, context)
    b = render_jinja_fragment(body_template, context)
    f = render_jinja_fragment(footer_template, context)

    h_r = enrich_email_fragment(h)
    b_r = enrich_email_fragment(b)
    f_r = enrich_email_fragment(f)

    inner = build_inner_html(h_r, b_r, f_r)
    email_html = wrap_email_document(
        inner,
        preview_title=preview_title,
        brand_primary=brand_primary,
    )

    main_plain = strip_html_to_plain(f"{h_r} {b_r} {f_r}")
    sms_rendered = render_jinja_fragment(sms_template, context)
    sms_text = strip_html_to_plain(sms_rendered)

    # Toast PWA: título = nome do template (evita repetir cabeçalho no corpo).
    toast_title = (preview_title or "Notificação").strip()[:120] or "Notificação"
    body_html_for_pwa = f"{b_r} {f_r}".strip()
    body_plain = strip_html_to_plain(body_html_for_pwa) if body_html_for_pwa else ""
    if not body_plain and b_r:
        body_plain = strip_html_to_plain(b_r)
    if not body_plain and h_r:
        body_plain = strip_html_to_plain(h_r)
    body_for_pwa = strip_urls_for_toast(body_plain)[:900]

    return {
        "email_html": email_html,
        "sms_text": sms_text,
        "main_plain": main_plain,
        "pwa": {"title": toast_title, "body": body_for_pwa},
    }
