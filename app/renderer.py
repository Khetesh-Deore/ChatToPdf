from jinja2 import Environment, FileSystemLoader, select_autoescape
from pygments.formatters import HtmlFormatter

from .config import BASE_DIR, VENDOR_DIR
from .models import Conversation

_env = Environment(
    loader=FileSystemLoader(BASE_DIR / "templates"),
    autoescape=select_autoescape(enabled_extensions=("html", "j2")),
)
PYGMENTS_CSS = HtmlFormatter(style="default").get_style_defs(".code-block")


def render_html(conv: Conversation) -> str:
    return _env.get_template("chat.html.j2").render(
        conv=conv,
        pygments_css=PYGMENTS_CSS,
        vendor_url=VENDOR_DIR.as_uri(),     # file:///.../app/vendor
    )
