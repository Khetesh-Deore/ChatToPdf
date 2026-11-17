"""Fallback extractor: read the conversation JSON that the share page embeds in its HTML.

Best effort — the embedding format is undocumented and changes. Use it when the DOM
selectors in fetcher.py stop matching. Images are NOT resolved here (placeholders only).
"""
import html as html_lib
import json
import re

from markdown_it import MarkdownIt

_ENQ = re.compile(r'streamController\.enqueue\(("(?:[^"\\]|\\.)*")\)')
_CITE = re.compile(r"\ue200.*?\ue201", re.S)
_PUA = re.compile(r"[\ue200-\ue206]")
_MATH = re.compile(r"(\\\[.+?\\\]|\\\(.+?\\\)|\$\$.+?\$\$)", re.S)
_TAGS = {"D", "U", "B", "Y", "R", "Set", "Map", "Error", "P"}
_md = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


# ------------------------------------------------------- stream decoding ----
def decode_flat(values: list):
    """Decode the 'flattened' array format (objects use '_N' keys; values are indices)."""
    cache: dict[int, object] = {}

    def val(i: int):
        if not isinstance(i, int) or i < 0 or i >= len(values):
            return None
        if i in cache:
            return cache[i]
        v = values[i]
        if isinstance(v, list):
            if v and isinstance(v[0], str) and v[0] in _TAGS:
                cache[i] = v
                return v
            out: list = []
            cache[i] = out
            out.extend(val(x) for x in v)
            return out
        if isinstance(v, dict):
            d: dict = {}
            cache[i] = d
            for k, vi in v.items():
                key = values[int(k[1:])] if k.startswith("_") and k[1:].isdigit() else k
                d[key] = val(vi)
            return d
        cache[i] = v
        return v

    return val(0)


def stream_payloads(page_html: str) -> list:
    out = []
    for m in _ENQ.finditer(page_html):
        try:
            chunk = json.loads(m.group(1))          # JS string literal -> str
            first = chunk.split("\n", 1)[0]
            out.append(decode_flat(json.loads(first)))
        except (ValueError, TypeError, IndexError):
            continue
    return out


def find_conversation(obj) -> dict | None:
    stack = [obj]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if o.get("linear_conversation") or ("mapping" in o and "current_node" in o):
                return o
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    return None


# ------------------------------------------------------------ tree walk ----
def ordered_nodes(conv: dict) -> list[dict]:
    if conv.get("linear_conversation"):
        return conv["linear_conversation"]
    mapping, nid, chain = conv["mapping"], conv["current_node"], []
    while nid and nid in mapping:
        chain.append(mapping[nid])
        nid = mapping[nid].get("parent")
    return chain[::-1]


def message_text(msg: dict) -> tuple[str, int]:
    """Return (markdown, number_of_images) for one message; tool steps yield ('', 0)."""
    c = msg.get("content") or {}
    if c.get("content_type") not in ("text", "multimodal_text"):
        return "", 0
    texts, images = [], 0
    for p in c.get("parts") or []:
        if isinstance(p, str):
            texts.append(p)
        elif isinstance(p, dict) and p.get("content_type") == "image_asset_pointer":
            images += 1
    return _PUA.sub("", _CITE.sub("", "\n\n".join(texts))).strip(), images


def render_markdown(text: str) -> str:
    """Markdown -> HTML while protecting \\( \\) \\[ \\] $$ from markdown escaping."""
    stash: list[str] = []

    def keep(m):
        stash.append(m.group(0))
        return f"MATHPH{len(stash) - 1}END"

    out = _md.render(_MATH.sub(keep, text))
    return re.sub(
        r"MATHPH(\d+)END",
        lambda m: html_lib.escape(stash[int(m.group(1))], quote=False),
        out,
    )


def extract_from_html(page_html: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (title, [(role, html), ...]) or raise ValueError."""
    for payload in stream_payloads(page_html):
        conv = find_conversation(payload)
        if not conv:
            continue
        msgs = []
        for node in ordered_nodes(conv):
            m = node.get("message")
            if not m:
                continue
            role = (m.get("author") or {}).get("role")
            if role not in ("user", "assistant"):
                continue
            if (m.get("metadata") or {}).get("is_visually_hidden_from_conversation"):
                continue
            text, n_img = message_text(m)
            body = (
                render_markdown(text)
                if role == "assistant"
                else f"<div>{html_lib.escape(text)}</div>"
            )
            body += '<div class="img-missing">[Image unavailable]</div>' * n_img
            if text or n_img:
                msgs.append((role, body))
        if msgs:
            return conv.get("title") or "ChatGPT conversation", msgs
    raise ValueError("No conversation data found in page HTML")
