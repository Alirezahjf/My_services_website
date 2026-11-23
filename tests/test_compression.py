"""The files of the site are sent in a shorter form."""

from __future__ import annotations

import gzip
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


@pytest.fixture()
def client():
    app = create_app({"TESTING": True,
                      "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.test_client() as test_client:
        yield test_client


def test_the_sheet_is_shortened(client):
    answer = client.get("/static/css/main.css", headers={"Accept-Encoding": "gzip"})
    assert answer.status_code == 200
    assert answer.headers.get("Content-Encoding") == "gzip"
    assert len(answer.data) < len(
        (ROOT / "app" / "static" / "css" / "main.css").read_bytes()
    )


def test_the_browser_that_does_not_know_brotli_gets_gzip(client):
    answer = client.get("/static/css/main.css",
                        headers={"Accept-Encoding": "br, gzip"})
    assert answer.status_code == 200
    assert answer.headers.get("Content-Encoding") == "br"


def test_a_browser_that_asks_for_nothing_gets_the_whole_file(client):
    answer = client.get("/static/css/main.css")
    assert answer.status_code == 200
    assert not answer.headers.get("Content-Encoding")


def test_the_shortened_file_is_the_same_file(client):
    answer = client.get("/static/css/main.css", headers={"Accept-Encoding": "gzip"})
    raw = (ROOT / "app" / "static" / "css" / "main.css").read_bytes()
    assert gzip.decompress(answer.data) == raw


def test_a_font_is_not_shortened(client):
    answer = client.get("/static/fonts/Vazirmatn-Regular.woff2",
                        headers={"Accept-Encoding": "gzip"})
    assert answer.status_code == 200
    assert not answer.headers.get("Content-Encoding")


def test_the_page_of_the_site_is_shortened():
    from app.services.compression import _encoding_for, _shorten_body

    assert _encoding_for("br, gzip") == "br"
    assert _encoding_for("gzip, deflate") == "gzip"
    assert _encoding_for("") is None

    body = b"<html><body>" + b"x" * 4000 + b"</body></html>"
    short = _shorten_body(body, "gzip")
    assert len(short) < len(body)
    assert gzip.decompress(short) == body


def test_a_file_that_is_not_there_is_not_found(client):
    answer = client.get("/static/css/nothing-here.css")
    assert answer.status_code == 404


def test_the_address_of_a_file_is_the_same_as_before(client):
    with client.application.test_request_context():
        from flask import url_for
        assert url_for("static", filename="css/main.css") == "/static/css/main.css"
