#!/usr/bin/env python3
"""Turn the supplied village lists into importer input.

Deliberately mechanical. It splits a parenthetical into an alias and leaves
everything else exactly as written -- no spelling is corrected, no duplicate is
dropped, no coordinate is invented. Whatever is wrong in the source stays wrong
here, so the importer's own validation is what finds it rather than this script
quietly deciding.

    python3 data/master/convert_villages.py > data/master/ghorband-villages.csv
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

SOURCE = Path(__file__).with_name("ghorband-villages-source.md")

# The heading each district's table sits under, and the code it was given.
DISTRICTS = {
    "سیاه‌گرد": "GRB-SYG",
    "شینواری": "GRB-SHW",
    "سرخ پارسا": "GRB-SPA",
    "شیخ‌علی": "GRB-SHA",
}

# A parenthetical is one of three things, and they are not interchangeable:
#   (تکرار)        a note from the compiler that this repeats an earlier row
#   (یا X)         "or X" -- an alternative name
#   (X)            an alternative name, or a Latin transliteration
NOTE_MARKERS = ("تکرار",)


def split_name(raw: str) -> tuple[str, list[str], str | None]:
    """Return the name, its aliases, and any compiler note.

    The name keeps whatever was written outside the brackets. Section 7: an
    alias is never folded into the name, because the name people actually use
    for a place is not ours to overwrite.
    """
    aliases: list[str] = []
    note: str | None = None

    def take(match: re.Match[str]) -> str:
        inner = match.group(1).strip()
        if any(marker in inner for marker in NOTE_MARKERS):
            nonlocal note
            note = inner
        else:
            # "یا X" is "or X"; the word itself is not part of the name.
            aliases.append(re.sub(r"^یا\s+", "", inner).strip())
        return " "

    name = re.sub(r"[（(]([^)）]*)[)）]", take, raw)
    return " ".join(name.split()), [a for a in aliases if a], note


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["district_code", "name", "alternative_names", "note"],
        lineterminator="\n",
    )
    writer.writeheader()

    district_code: str | None = None
    written = 0
    for line in text.splitlines():
        heading = re.match(r"^##\s+\d+\.\s*ولسوالی\s+(.+?)\s*$", line)
        if heading:
            district_code = DISTRICTS.get(heading.group(1).strip())
            if district_code is None:
                print(f"unknown district: {heading.group(1)!r}", file=sys.stderr)
                return 1
            continue

        row = re.match(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|\s*$", line)
        if not row or district_code is None:
            continue

        name, aliases, note = split_name(row.group(2))
        if not name:
            print(f"row {row.group(1)} has no name outside its brackets", file=sys.stderr)
            continue
        writer.writerow({
            "district_code": district_code,
            "name": name,
            # The importer splits on these itself; one separator, chosen because
            # no Afghan place name contains it.
            "alternative_names": " | ".join(aliases),
            "note": note or "",
        })
        written += 1

    print(f"{written} villages", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
