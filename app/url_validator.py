import re
from urllib.parse import urlparse

from .models import InvalidUrl

ALLOWED_HOSTS = {"chatgpt.com", "www.chatgpt.com", "chat.openai.com"}
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_PATH = re.compile(rf"^/share/(?:e/)?({_UUID})/?$")


def validate_share_url(raw: str) -> str:
    """Return a canonical share URL or raise InvalidUrl.

    The allow-list is also our SSRF protection: the server never
    navigates to a host that is not ChatGPT.
    """
    try:
        u = urlparse((raw or "").strip())
    except ValueError:
        raise InvalidUrl("That doesn't look like a valid URL.")
    if u.scheme != "https" or (u.hostname or "").lower() not in ALLOWED_HOSTS:
        raise InvalidUrl(
            "Please paste a public ChatGPT share link (https://chatgpt.com/share/...)."
        )
    m = _PATH.match(u.path)
    if not m:
        raise InvalidUrl(
            "The link must look like https://chatgpt.com/share/<id>."
        )
    return f"https://chatgpt.com/share/{m.group(1).lower()}"
