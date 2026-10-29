"""Test double for the xai_client module.

`make_xai_mock()` returns a MagicMock whose chat / web_search / generate_text calls are routed
to `mock.models.generate_content(contents=prompt, **kwargs)`, so tests configure one canned
response object (`.text`, optional `.sources`) and inspect `call_args.kwargs['contents']`.
"""
from unittest.mock import MagicMock

import xai_client


def make_xai_mock():
    m = MagicMock()

    def _chat(prompt, **kw):
        return m.models.generate_content(contents=prompt, **kw)

    def _text(prompt, **kw):
        return _chat(prompt, **kw).text

    def _web_search(prompt, **kw):
        r = _chat(prompt, **kw)
        return (r.text or "", _sources(r))

    def _image(prompt, **kw):
        r = _chat(prompt, **kw)
        data = _image_bytes(r)
        if data is None:
            raise xai_client.XaiError("xAI returned no image")
        return data

    m.chat.side_effect = _chat
    m.generate_image.side_effect = _image
    m.generate_text.side_effect = _text
    m.web_search.side_effect = _web_search
    m.TextResponse = xai_client.TextResponse
    m.parse_json = xai_client.parse_json
    m.XaiError = xai_client.XaiError
    return m


def _sources(r):
    """Cited sources from a canned response: `.sources` list, or legacy-style
    candidates[0].grounding_metadata.grounding_chunks[*].web.uri fixtures."""
    sources = getattr(r, "sources", None)
    if isinstance(sources, (list, tuple)):
        return list(sources)
    try:
        chunks = r.candidates[0].grounding_metadata.grounding_chunks or []
        return [{"url": c.web.uri, "title": ""} for c in chunks if isinstance(c.web.uri, str)]
    except (AttributeError, IndexError, TypeError):
        return []


def _image_bytes(r):
    """Image bytes from a canned response: `.image` bytes, or legacy-style
    candidates[*].content.parts[*].inline_data.data fixtures."""
    if isinstance(getattr(r, "image", None), bytes):
        return r.image
    try:
        for cand in r.candidates:
            for part in cand.content.parts:
                data = getattr(getattr(part, "inline_data", None), "data", None)
                if isinstance(data, bytes):
                    return data
    except (AttributeError, TypeError):
        pass
    return None
