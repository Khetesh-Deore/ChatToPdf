from dataclasses import dataclass, field


class ConvertError(Exception):
    """An error whose message is safe to show to the end user."""


class InvalidUrl(ConvertError):
    pass


class PageBlocked(ConvertError):
    pass


class NoMessagesFound(ConvertError):
    pass


@dataclass
class RawMessage:
    role: str                       # "user" | "assistant" | "tool"
    html: str                       # innerHTML captured from the live page
    extra_images: list[str] = field(default_factory=list)


@dataclass
class RawCapture:
    title: str
    messages: list[RawMessage]
    blobs: dict[str, tuple[str, bytes]]   # image url -> (mime, bytes)


@dataclass
class Message:
    role: str
    html: str                       # sanitized, self-contained HTML


@dataclass
class Conversation:
    title: str
    source_url: str
    messages: list[Message]
    created_at: str
