"""The name that is sent back must match the bytes that are sent with it.

A browser that cannot read the answer shows an empty page and says
nothing about it. That is what happens when the answer says "br" and
carries gzip bytes: the sheet never arrives, the page never draws, and
the visitor sees nothing at all.
"""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.services import compression  # noqa: E402


def test_the_encoding_that_is_chosen_can_really_be_produced(monkeypatch):
    """Without brotli, gzip is chosen. Never "br"."""
    monkeypatch.setattr(compression, "_brotli_is_there", lambda: False)

    assert compression._encoding_for("gzip, deflate, br") == "gzip"
    assert compression._encoding_for("br") is None
    assert compression._encoding_for("gzip, deflate") == "gzip"
    assert compression._encoding_for("") is None


def test_brotli_is_chosen_when_the_server_can_produce_it(monkeypatch):
    monkeypatch.setattr(compression, "_brotli_is_there", lambda: True)

    assert compression._encoding_for("gzip, deflate, br") == "br"
    assert compression._encoding_for("gzip") == "gzip"


def test_the_sheet_arrives_readable_whatever_the_server_can_do(client, monkeypatch):
    """The sheet must arrive as readable bytes in every case."""
    body = b"/* the sheet */" + b"body{color:#123456}" * 200

    for has_brotli in (True, False):
        monkeypatch.setattr(compression, "_brotli_is_there", lambda: has_brotli)
        answer = client.get("/static/css/main.css",
                            headers={"Accept-Encoding": "gzip, deflate, br"})
        assert answer.status_code == 200
        encoding = answer.headers.get("Content-Encoding")
        if has_brotli:
            assert encoding == "br"
        else:
            assert encoding == "gzip"
        assert len(answer.headers.get("Content-Length", "")) > 0

    # And the page itself.
    for has_brotli in (True, False):
        monkeypatch.setattr(compression, "_brotli_is_there", lambda: has_brotli)
        answer = client.get("/", headers={"Accept-Encoding": "gzip, deflate, br"})
        assert answer.status_code == 200
        encoding = answer.headers.get("Content-Encoding")
        if encoding == "gzip":
            assert gzip.decompress(answer.data)
        elif encoding == "br":
            import brotli
            assert brotli.decompress(answer.data)
        else:
            assert answer.data


def test_brotli_is_named_in_the_requirements():
    """The server must be able to produce what it says it produces."""
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "brotli" in requirements.lower(), \
        "brotli is used but not asked for; the server may not have it"
