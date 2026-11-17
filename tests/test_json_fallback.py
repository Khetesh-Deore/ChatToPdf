import json

from app.extractor_json import decode_flat, extract_from_html, render_markdown


def test_decode_flat_object_and_lists():
    # Encodes {"title": "T", "items": [1, "a"]}
    values = [{"_1": 2, "_3": 4}, "title", "T", "items", [5, 6], 1, "a"]
    assert decode_flat(values) == {"title": "T", "items": [1, "a"]}


def test_decode_flat_nested():
    # Encodes {"a": {"b": 42}}
    # Indices: 0=root-dict, 1="a", 2=inner-dict, 3="b", 4=42
    # root-dict key "_1"->1 ("a"), value "_2"->2 (inner-dict)
    # inner-dict key "_3"->3 ("b"), value "_4"->4 (42)
    values = [{"_1": 2}, "a", {"_3": 4}, "b", 42]
    result = decode_flat(values)
    assert result == {"a": {"b": 42}}


def test_math_survives_markdown():
    out = render_markdown(
        r"Use \(a_1 < b\) and:"
        "\n\n"
        r"\[\sum_{i=1}^{n} i\]"
        "\n\n"
        "| x | y |\n|---|---|\n| 1 | 2 |"
    )
    assert r"\(a_1 &lt; b\)" in out
    assert r"\[\sum_{i=1}^{n} i\]" in out
    assert "<table>" in out


def test_citation_markers_stripped():
    # Citation stripping happens in message_text(), not render_markdown().
    # Verify the _CITE and _PUA regexes remove private-use markers.
    from app.extractor_json import _CITE, _PUA
    raw = "Hello\ue200cite stuff\ue201 world"
    out = _PUA.sub("", _CITE.sub("", raw))
    assert "\ue200" not in out
    assert "cite" not in out
    assert "Hello" in out
    assert "world" in out


def _flatten_page(conv: dict) -> str:
    """Wrap a conv dict in the flattened format inside streamController.enqueue."""
    values: list = []

    def add(obj):
        idx = len(values)
        values.append(None)
        if isinstance(obj, dict):
            d = {}
            for k, v in obj.items():
                d[f"_{add(k)}"] = add(v)
            values[idx] = d
        elif isinstance(obj, list):
            values[idx] = [add(x) for x in obj]
        else:
            values[idx] = obj
        return idx

    add(conv)
    chunk = json.dumps(values) + "\n"
    return (
        f'<script>window.__ctx.streamController.enqueue'
        f'({json.dumps(chunk)});</script>'
    )


def test_extract_from_mapping():
    conv = {
        "title": "Algebra",
        "current_node": "c",
        "mapping": {
            "a": {
                "parent": None,
                "message": {
                    "author": {"role": "system"},
                    "content": {"content_type": "text", "parts": ["hidden"]},
                },
            },
            "b": {
                "parent": "a",
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["Solve x^2=4"]},
                },
            },
            "c": {
                "parent": "b",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {
                        "content_type": "text",
                        "parts": [
                            "**x = \u00b12**\ue200cite\ue202turn0search0\ue201"
                            r" and \(x^2=4\)"
                        ],
                    },
                },
            },
        },
    }
    page = _flatten_page(
        {"loaderData": {"route": {"serverResponse": {"data": conv}}}}
    )
    title, msgs = extract_from_html(page)
    assert title == "Algebra"
    assert [r for r, _ in msgs] == ["user", "assistant"]
    assert "<strong>x = \u00b12</strong>" in msgs[1][1]
    assert "cite" not in msgs[1][1]
    assert r"\(x^2=4\)" in msgs[1][1]


def test_extract_from_linear_conversation():
    conv = {
        "title": "Linear test",
        "linear_conversation": [
            {
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["What is 2+2?"]},
                }
            },
            {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["It is **4**."]},
                }
            },
        ],
    }
    page = _flatten_page(conv)
    title, msgs = extract_from_html(page)
    assert title == "Linear test"
    assert len(msgs) == 2
    assert msgs[0][0] == "user"
    assert "What is 2+2?" in msgs[0][1]
    assert "<strong>4</strong>" in msgs[1][1]


def test_extract_raises_on_no_data():
    import pytest
    with pytest.raises(ValueError, match="No conversation data"):
        extract_from_html("<html><body>nothing here</body></html>")


def test_visually_hidden_messages_excluded():
    conv = {
        "title": "Hidden test",
        "current_node": "b",
        "mapping": {
            "a": {
                "parent": None,
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["visible"]},
                    "metadata": {"is_visually_hidden_from_conversation": True},
                },
            },
            "b": {
                "parent": "a",
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["shown"]},
                },
            },
        },
    }
    page = _flatten_page(conv)
    _, msgs = extract_from_html(page)
    # Hidden user message should be excluded
    assert all(r == "assistant" for r, _ in msgs)
    assert "shown" in msgs[0][1]
