from io import BytesIO

from PIL import Image

from .config import IMAGE_MAX_WIDTH_PX


def shrink(mime: str, data: bytes) -> tuple[str, bytes]:
    """Downscale / recompress big rasters so the PDF stays small."""
    if mime in ("image/svg+xml", "image/gif"):
        return mime, data
    try:
        im = Image.open(BytesIO(data))
        im.load()
    except Exception:
        return mime, data

    resized = False
    if im.width > IMAGE_MAX_WIDTH_PX:
        h = round(im.height * IMAGE_MAX_WIDTH_PX / im.width)
        im = im.resize((IMAGE_MAX_WIDTH_PX, h), Image.Resampling.LANCZOS)
        resized = True
    if not resized and len(data) < 400_000:
        return mime, data

    buf = BytesIO()
    has_alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
    if has_alpha:
        im.save(buf, "PNG", optimize=True)
        return "image/png", buf.getvalue()
    im.convert("RGB").save(buf, "JPEG", quality=85, optimize=True)
    return "image/jpeg", buf.getvalue()
