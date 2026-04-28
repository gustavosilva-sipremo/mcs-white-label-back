import re
import unicodedata
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


def strip_urls_keep_newlines(text: str) -> str:
    """Remove URLs mantendo quebras de linha (toast PWA)."""

    def _clean_line(line: str) -> str:
        s = re.sub(r"https?://[^\s]+", "", line or "", flags=re.I)
        return re.sub(r"[ \t]+", " ", s).rstrip()

    lines = [_clean_line(line) for line in (text or "").split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


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


def sanitize_logo_url(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    u = value.strip()
    if re.match(r"^data:image/(png|jpeg|jpg|gif|webp);base64,[a-zA-Z0-9+/=\s]+$", u):
        return u
    u = u[:800]
    if not re.match(r"^https?://", u, re.I):
        return None
    if re.search(r"[\s\"'<>]", u):
        return None
    return u


def sanitize_sms_text(text: str) -> str:
    raw = re.sub(r"<[^>]*>?", "", text or "")
    normalized = unicodedata.normalize("NFD", raw)
    no_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    ascii_only = re.sub(r"[^\x00-\x7F]", "", no_accents)
    return re.sub(r"\s+", " ", ascii_only).strip()


def _looks_like_html_fragment(s: str) -> bool:
    return bool(_HTML_BLOCK.search(s or ""))


def _fragment_to_plain_multiline(s: str) -> str:
    if not (s or "").strip():
        return ""
    if _looks_like_html_fragment(s):
        t = s
        t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
        t = re.sub(r"</p\s*>", "\n\n", t, flags=re.I)
        t = re.sub(r"</div\s*>", "\n", t, flags=re.I)
        t = re.sub(r"<li[^>]*>", "\n- ", t, flags=re.I)
        t = re.sub(r"</li>\s*", "", t, flags=re.I)
        t = re.sub(r"<[^>]+>", "", t)
        t = unescape(t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        return t.strip()
    return (s or "").strip()


def _pwa_plain_from_body_footer(b_raw: str, f_raw: str) -> str:
    parts: list[str] = []
    for frag in (b_raw.strip(), f_raw.strip()):
        if frag:
            parts.append(_fragment_to_plain_multiline(frag))
    return strip_urls_keep_newlines("\n\n".join(parts))[:2000]


def _plain_text_to_email_html(text: str) -> str:
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
    frag = (fragment or "").strip()
    if not frag:
        return ""
    if _looks_like_html_fragment(frag):
        return frag
    return _plain_text_to_email_html(frag)


def _anchor_to_button_block(url: str, primary: str, foreground: str) -> str:
    safe = escape(url, quote=True)
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        'style="margin:14px 0 10px;">'
        '<tr><td align="center" style="text-align:center;padding:0 12px;">'
        f'<a href="{safe}" target="_blank" rel="noopener noreferrer" '
        f'style="display:inline-block;padding:11px 22px;background-color:{primary};'
        f"color:{foreground} !important;text-decoration:none;border-radius:9999px;font-weight:600;"
        "font-size:13px;font-family:inherit;line-height:1.25;"
        'border:1px solid rgba(15,23,42,0.08);">Confirmar Visualização</a>'
        "</td></tr></table>"
    )


def linkify_email_inner_html(
    html: str,
    primary: str,
    primary_foreground: str | None = None,
) -> str:
    """Transforma <a href=http...> e URLs soltas em botões estilo CTA (tema claro)."""

    fg = sanitize_brand_color(primary_foreground) if primary_foreground else "#ffffff"

    def replace_anchor(m: re.Match) -> str:
        tag = m.group(0)
        hm = re.search(r'href\s*=\s*["\']([^"\']+)["\']', tag, re.I)
        url = (hm.group(1).strip() if hm else "")[:900]
        if not re.match(r"^https?://", url, re.I):
            return tag
        return _anchor_to_button_block(url, primary, fg)

    out = re.sub(r"<a\s[^>]*href\s*=\s*[\"'][^\"']+[\"'][^>]*>.*?</a>", replace_anchor, html, flags=re.I | re.S)

    def bare_url(m: re.Match) -> str:
        prefix, url = m.group(1), m.group(2)
        if prefix == "=" or prefix == '"' or prefix == "'":
            return m.group(0)
        if not re.match(r"^https?://", url, re.I):
            return m.group(0)
        return prefix + _anchor_to_button_block(url, primary, fg)

    out = re.sub(r"(.)(https?://[^\s<>'\"]+)", bare_url, out)
    return out


def wrap_email_document(
    inner_html: str,
    preview_title: str = "Pré-visualização",
    brand_primary: str | None = None,
    logo_url: str | None = None,
) -> str:
    """Layout HTML compacto, tema claro — logo opcional, acento na cor do tenant."""
    primary = sanitize_brand_color(brand_primary)
    safe_inner = inner_html or ""
    safe_title = (
        preview_title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    logo = sanitize_logo_url(logo_url)
    logo_row = ""
    if logo:
        le = escape(logo, quote=True)
        logo_row = f"""<tr>
            <td style="padding:14px 16px 0;background:#ffffff;text-align:left;">
              <img src="{le}" alt="" width="140" height="44" style="max-height:44px;width:auto;height:auto;display:block;border:0;outline:none;text-decoration:none;" />
            </td>
          </tr>"""

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
          {logo_row}
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
    *,
    channels: list[str] | None = None,
    channel_templates: dict | None = None,
    preview_title: str = "Pré-visualização",
    brand_primary: str | None = None,
    brand_primary_foreground: str | None = None,
    logo_url: str | None = None,
    context: dict | None = None,
) -> dict:
    enabled_channels = [str(c).strip().lower() for c in (channels or [])]
    raw_templates = channel_templates if isinstance(channel_templates, dict) else {}

    def pick_channel_template(channel: str) -> dict[str, str]:
        raw = raw_templates.get(channel) if isinstance(raw_templates, dict) else None
        if isinstance(raw, dict):
            return {
                "header_template": str(raw.get("header_template") or ""),
                "body_template": str(raw.get("body_template") or ""),
                "footer_template": str(raw.get("footer_template") or ""),
            }
        return {"header_template": "", "body_template": "", "footer_template": ""}

    email_tpl = pick_channel_template("email")
    whatsapp_tpl = pick_channel_template("whatsapp")
    pwa_tpl = pick_channel_template("pwa")
    sms_tpl = pick_channel_template("sms")

    if not any(email_tpl.values()):
        email_tpl = whatsapp_tpl if any(whatsapp_tpl.values()) else pwa_tpl
    if not any(pwa_tpl.values()):
        pwa_tpl = whatsapp_tpl if any(whatsapp_tpl.values()) else email_tpl

    h = render_jinja_fragment(email_tpl.get("header_template", ""), context)
    b = render_jinja_fragment(email_tpl.get("body_template", ""), context)
    f = render_jinja_fragment(email_tpl.get("footer_template", ""), context)

    h_r = enrich_email_fragment(h)
    b_r = enrich_email_fragment(b)
    f_r = enrich_email_fragment(f)

    inner = build_inner_html(h_r, b_r, f_r)
    primary = sanitize_brand_color(brand_primary)
    inner_linked = linkify_email_inner_html(
        inner,
        primary,
        brand_primary_foreground,
    )
    email_html = wrap_email_document(
        inner_linked,
        preview_title=preview_title,
        brand_primary=brand_primary,
        logo_url=logo_url,
    )

    main_plain = strip_html_to_plain(f"{h_r} {b_r} {f_r}")
    sms_rendered = render_jinja_fragment(
        " ".join(
            [
                sms_tpl.get("header_template", ""),
                sms_tpl.get("body_template", ""),
                sms_tpl.get("footer_template", ""),
            ],
        ),
        context,
    )
    sms_text = sanitize_sms_text(strip_html_to_plain(sms_rendered))

    toast_title = (preview_title or "Notificação").strip()[:120] or "Notificação"
    pwa_h = render_jinja_fragment(pwa_tpl.get("header_template", ""), context)
    pwa_b = render_jinja_fragment(pwa_tpl.get("body_template", ""), context)
    pwa_f = render_jinja_fragment(pwa_tpl.get("footer_template", ""), context)
    pwa_body = _pwa_plain_from_body_footer(pwa_b, pwa_f)
    if not pwa_body and pwa_h:
        pwa_body = strip_urls_keep_newlines(_fragment_to_plain_multiline(pwa_h))[:2000]

    whatsapp_h = render_jinja_fragment(whatsapp_tpl.get("header_template", ""), context)
    whatsapp_b = render_jinja_fragment(whatsapp_tpl.get("body_template", ""), context)
    whatsapp_f = render_jinja_fragment(whatsapp_tpl.get("footer_template", ""), context)
    whatsapp_text = strip_html_to_plain(f"{whatsapp_h} {whatsapp_b} {whatsapp_f}")

    return {
        "email_html": email_html,
        "sms_text": sms_text,
        "main_plain": main_plain,
        "whatsapp_text": whatsapp_text,
        "pwa": {"title": toast_title, "body": pwa_body},
        "channel_templates": {
            c: pick_channel_template(c)
            for c in ("email", "whatsapp", "pwa", "sms")
            if not enabled_channels or c in enabled_channels
        },
    }
