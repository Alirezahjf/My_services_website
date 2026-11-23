#!/usr/bin/env python3
"""Compare two sets of pictures and say how much they differ.

The tool is used to check that a change to the sheet of the site did
not change what the reader sees. It compares the pictures of two
directories, page by page, and reports the share of pixels that are
different.

Usage::

    python tools/compare_shots.py <first-directory> <second-directory>
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops


def main() -> int:
    first = Path(sys.argv[1])
    second = Path(sys.argv[2])

    names = sorted(p.name for p in first.glob("*.png") if p.is_file())
    if not names:
        print("the first directory has no pictures")
        return 1

    worst = 0.0
    for name in names:
        other = second / name
        if not other.exists():
            print(f"  {name}: missing in the second directory")
            continue
        a = Image.open(first / name).convert("RGB")
        b = Image.open(other).convert("RGB")
        if a.size != b.size:
            print(f"  {name}: the size changed {a.size} -> {b.size}")
            continue
        diff = ImageChops.difference(a, b)
        # A pixel is different when any channel moved by more than a
        # small step; a step that small is the noise of the drawing.
        grey = diff.convert("L").point(lambda v: 255 if v > 16 else 0)
        changed = sum(grey.histogram()[255:])
        share = changed / (a.size[0] * a.size[1])
        worst = max(worst, share)
        print(f"  {name}: {share * 100:.3f}% of the pixels differ")

    print(f"the largest difference is {worst * 100:.3f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
