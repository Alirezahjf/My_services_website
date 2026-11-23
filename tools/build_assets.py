#!/usr/bin/env python3
"""Prepare the files of the appearance that the browser receives.

The sheet and the script of the site are written by hand and read by
hand. What is served is shortened, so that the browser has less to read
before the page can be drawn.

The source stays in the repository. The files that are built are
written next to it and are not kept in the repository, so the two can
never drift apart unnoticed.

The sheet is served as one file. A sheet that arrives in two pieces
was tried and thrown away: the second piece changed the place of the
things on the page, and the page jumped by more than a twentieth of
the screen. One sheet that the browser waits for is shorter to read
than the two together, and the page never moves.

Usage::

    python tools/build_assets.py [--check]

``--check`` only reports what would change and writes nothing.
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CSS_SOURCE = ROOT / "app" / "static" / "css" / "site.src.css"
CSS_TARGET = ROOT / "app" / "static" / "css" / "main.css"
JS_SOURCE = ROOT / "app" / "static" / "js" / "site.src.js"
JS_TARGET = ROOT / "app" / "static" / "js" / "main.js"
VERSION_TARGET = ROOT / "app" / "static" / "css" / ".asset-version"

# The colours whose name is longer than their short form.
COLOURS = {
    "white": "#fff",
    "black": "#000",
}

# The names of the parts of the page that are drawn first. A rule that
# speaks of one of these belongs to the first screen.
# ---------------------------------------------------------------------------
# The sheet
# ---------------------------------------------------------------------------


def strip_comments(css: str) -> str:
    """Remove the comments.

    A comment that is written with a bang is a note for the reader, but
    the file that is served is not read by a person, so every comment
    is removed.
    """
    out: list[str] = []
    index = 0
    length = len(css)
    while index < length:
        start = css.find("/*", index)
        if start == -1:
            out.append(css[index:])
            break
        out.append(css[index:start])
        end = css.find("*/", start + 2)
        if end == -1:
            break
        index = end + 2
    return "".join(out)


def shorten_colours(css: str) -> str:
    """Replace the long name of a colour with its short form."""
    names = "|".join(COLOURS)
    return re.sub(r"\b(" + names + r")\b",
                  lambda m: COLOURS[m.group(1)], css)


def collapse(css: str) -> str:
    """Remove the space that is not needed."""
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};])\s*", r"\1", css)
    css = css.replace(";}", "}")
    css = re.sub(r";{2,}", ";", css)
    css = re.sub(r"[^{}]*\{\s*\}", "", css)
    return css.strip()


def minify_css(css: str) -> str:
    return collapse(shorten_colours(strip_comments(css)))


# ---------------------------------------------------------------------------
# The script
# ---------------------------------------------------------------------------


def minify_js(source: str) -> str:
    """Leave the script as it was written.

    The script of the site is a few kilobytes and is read by the
    browser on every page. Joining its lines would save very little,
    and a line break in the wrong place can change the meaning of a
    script, so the file is copied as it is.
    """
    return source


# ---------------------------------------------------------------------------
# The split of the sheet
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------


def write(path: Path, text: str, check: bool) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current == text:
        print(f"  {path.name}: up to date ({len(text)} bytes)")
        return True
    if check:
        print(f"  {path.name}: would change ({len(current)} -> {len(text)} bytes)")
        return False
    path.write_text(text, encoding="utf-8")
    print(f"  {path.name}: written ({len(text)} bytes)")
    return True


def main() -> int:
    check = "--check" in sys.argv

    print("Preparing the files of the appearance")

    good = True

    if CSS_SOURCE.exists():
        source = CSS_SOURCE.read_text(encoding="utf-8")
        good &= write(CSS_TARGET, minify_css(source), check)
    else:
        print(f"  the source is missing: {CSS_SOURCE}")
        good = False

    if JS_SOURCE.exists():
        good &= write(JS_TARGET, minify_js(JS_SOURCE.read_text(encoding="utf-8")),
                      check)

    # The number that belongs to these files. The page puts it in the
    # address of the sheet and of the script, so that a browser that
    # kept an old file asks for the old address and still gets a file
    # that belongs with the script it already has.
    version = hashlib.sha256()
    for path in (CSS_TARGET, JS_TARGET):
        if path.exists():
            version.update(path.read_bytes())
    good &= write(VERSION_TARGET, version.hexdigest()[:12] + "\n", check)

    if check and not good:
        print("The files of the appearance are not in step with their source.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
