"""The page must never be able to go black.

The entrance of the pages hides a part of the text for a moment and lets
it appear again. That is a promise between the sheet and the script. If
the script is stopped with an error after it has hidden the text, the
promise is not kept and the visitor gets a page without text.

These tests hold the site to that promise. They also hold it to the
other half of it: the sheet and the script that the browser receives
must belong to the same update, or the page shows the movement of one
and the rules of the other.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


def built_css() -> str:
    path = ROOT / "app" / "static" / "css" / "main.css"
    if not path.exists():
        pytest.skip("the sheet of the site has not been built yet")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The sheet keeps its own promise
# ---------------------------------------------------------------------------


def test_the_sheet_has_a_way_back_for_the_hidden_text():
    """Every part that the entrance hides must have a way back of its own.

    The rule has to be in the sheet itself and not in the script, because
    the script is the thing that may fail.
    """
    css = built_css()
    assert "@keyframes reveal-in" in css, \
        "the sheet has no movement that lets the hidden text come back"
    assert "@keyframes reveal-line-in" in css, \
        "the sheet has no movement that lifts the mask of a heading"

    # The rule that hides the text must be answered by one that shows it
    # again, and the answer must come after it in the sheet.
    hidden_at = css.find(".has-reveal .reveal{opacity:0")
    answer_at = css.find("@keyframes reveal-in")
    assert hidden_at != -1, "the text is not hidden at all, which is fine"
    assert answer_at > hidden_at, \
        "the way back comes before the hiding and would not be used"


def test_the_way_back_has_a_deadline_of_its_own():
    """The way back must not wait for the script.

    A movement that starts at once and ends in the visible state needs
    no help from anywhere.
    """
    css = built_css()
    matches = re.findall(r"animation:\s*reveal-in[^;}]*", css)
    assert matches, "the hidden text is not given a movement of its own"
    for rule in matches:
        assert "forwards" in rule, \
            f"the movement does not hold the text in sight: {rule}"
        assert "2.6s" in rule or "2s" in rule, \
            f"the movement has no deadline: {rule}"


def test_the_mask_of_a_heading_is_lifted_by_the_sheet_too():
    css = built_css()
    matches = re.findall(r"animation:\s*reveal-line-in[^;}]*", css)
    assert matches, "a heading can stay behind its mask"
    for rule in matches:
        assert "forwards" in rule, f"the mask is never lifted: {rule}"


# ---------------------------------------------------------------------------
# The sheet and the script belong together
# ---------------------------------------------------------------------------


def test_the_page_carries_the_number_of_the_files(client):
    """The address of the sheet and the script must carry a number.

    Without a number the browser keeps an old file for a year, and the
    page then shows the movement of the new script with the rules of the
    old sheet.
    """
    answer = client.get("/")
    assert answer.status_code == 200
    page = answer.get_data(as_text=True)

    sheet = re.search(r'href="([^"]*main\.css[^"]*)"', page)
    script = re.search(r'src="([^"]*main\.js[^"]*)"', page)
    assert sheet, "the page does not ask for the sheet"
    assert script, "the page does not ask for the script"

    for address in (sheet.group(1), script.group(1)):
        assert "v=" in address, \
            f"the address of a file of the appearance carries no number: {address}"

    number_of_sheet = sheet.group(1).split("v=")[1]
    number_of_script = script.group(1).split("v=")[1]
    assert number_of_sheet == number_of_script, \
        "the sheet and the script come from two different updates"


def test_a_file_with_a_number_may_be_kept_for_a_year(client):
    """The number makes the address unique, so the file may be kept.

    The plain address is asked for by other places, so it must not be
    kept for long.
    """
    versioned = client.get("/static/css/main.css?v=abc123",
                           headers={"Accept-Encoding": "gzip"})
    assert versioned.status_code == 200
    assert "immutable" in versioned.headers.get("Cache-Control", ""), \
        "a file with a number in its address is not kept"

    plain = client.get("/static/css/main.css", headers={"Accept-Encoding": "gzip"})
    assert plain.status_code == 200
    assert "immutable" not in plain.headers.get("Cache-Control", ""), \
        "a file that changes under the same address is kept for a year"


def test_the_number_changes_when_the_files_change(client, tmp_path, monkeypatch):
    """A new build must give a new number."""
    from app.services import asset_version

    marker = ROOT / "app" / "static" / "css" / ".asset-version"
    first = asset_version.asset_version(client.application)
    assert first

    asset_version.reset_cache()
    try:
        marker.write_text("another-number\n", encoding="utf-8")
        second = asset_version.asset_version(client.application)
        assert second == "another-number"
    finally:
        asset_version.reset_cache()
        if marker.exists():
            marker.write_text(first + "\n", encoding="utf-8")
        asset_version.reset_cache()
