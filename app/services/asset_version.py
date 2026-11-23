"""A name for the files of the appearance, so a browser never holds an old one.

The stylesheet and the script of the site are built from their source and
are given the same address every time. The browser is told to keep them
for a year and never to ask again. That is a good answer for a file that
never changes, and a wrong one here: when the site is renewed, the
browser keeps the old stylesheet and asks for the new script, and the two
no longer belong to each other.

The page therefore carries a number with the address of every file. The
number is taken from the content of the file, so it changes exactly when
the file changes. A browser that has the old file asks for the old
address and gets it; a browser that asks for the new address gets the
new file. The two always match.

The number is written next to the built files by the build, and it is
read from there. When the file is missing, the number is empty and the
address stays as it was, so nothing breaks while the site is being put
together.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# The name of the file that holds the number. It sits next to the built
# files, so that the build and the site always read the same place.
VERSION_FILE = "app/static/css/.asset-version"

_cache: dict[str, str] = {}


def _root(app) -> Path:
    return Path(app.root_path).parent


def asset_version(app) -> str:
    """The number that belongs to the current files of the appearance.

    The number is short, so that the address stays short, and it is
    written with letters and digits only, so that it is safe to put in
    an address.
    """
    if "version" in _cache:
        return _cache["version"]

    version = ""
    marker = _root(app) / VERSION_FILE
    try:
        if marker.is_file():
            version = marker.read_text(encoding="utf-8").strip()
    except OSError:
        version = ""

    if not version:
        # The marker is missing. The number is then taken from the files
        # themselves, so that the address is still right for this run.
        digest = hashlib.sha256()
        for name in ("app/static/css/main.css", "app/static/js/main.js"):
            path = _root(app) / name
            try:
                if path.is_file():
                    digest.update(path.read_bytes())
            except OSError:
                continue
        version = digest.hexdigest()[:12]

    _cache["version"] = version
    return version


def reset_cache() -> None:
    """Forget the number, so that it is read again on the next request."""
    _cache.clear()
