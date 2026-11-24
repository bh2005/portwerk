"""Release-Hinweise: liest ``CHANGELOG.md`` (neben diesem Modul) und liefert sie strukturiert für die Verwaltung.

Format: ``## <Version> – <Datum>``, darunter je Änderung ``- Titel: Beschreibung``; neueste Version zuerst.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).with_name("CHANGELOG.md")
_HEAD = re.compile(r"^##\s+(\S+)\s*[–-]\s*(\d{4}-\d{2}-\d{2})\s*$")


def parse(text: str) -> list[dict]:
    out: list[dict] = []
    for line in text.splitlines():
        m = _HEAD.match(line.strip())
        if m:
            out.append({"version": m.group(1), "date": m.group(2), "items": []})
        elif line.startswith("- ") and out:
            title, _, body = line[2:].strip().partition(": ")
            out[-1]["items"].append({"title": title, "text": body} if body else {"title": "", "text": title})
    return out


@lru_cache(maxsize=1)
def load() -> list[dict]:
    try:
        return parse(FILE.read_text(encoding="utf-8"))
    except OSError:
        return []


def current_version(default: str = "0.0.0") -> str:
    r = load()
    return r[0]["version"] if r else default
