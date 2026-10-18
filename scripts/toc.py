#!/usr/bin/env python3
"""Idempotent Table of Contents for Markdown files (stdlib only).

The TOC sits at the top of each file between two identical `<!-- TOC -->` markers
(the closing `<!-- /TOC -->` form conflicts with editor plugins), lists every
heading level including `#`, nests them like the Markdown All in One plugin and
uses GitHub-style anchors. Running it twice changes nothing.

    scripts/toc.py                 # every Markdown file of the repo (protected paths skipped)
    scripts/toc.py README.md docs  # specific files or directories
    scripts/toc.py --check         # exit 1 if any TOC is missing or stale (no writes)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

MARKER = "<!-- TOC -->"
ROOT = Path(__file__).resolve().parents[1]
# Never touched: challenge files that must stay byte-identical, plus tool directories.
PROTECTED = {"dados", "validador", "exemplos", ".git", ".venv", "node_modules", ".pytest_cache", ".ruff_cache"}
PROTECTED_FILES = {"TASK.md"}

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


def plain_text(title: str) -> str:
    """Heading text without inline Markdown: links keep their label, code keeps its content."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", title)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"(\*\*|__|\*|_)(.+?)\1", r"\2", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def slugify(title: str) -> str:
    """GitHub anchor: lowercase, keep letters/digits/_/-/spaces (Unicode aware), spaces -> '-'."""
    text = plain_text(title).lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def strip_toc(lines: list[str]) -> list[str]:
    """Remove an existing TOC block (first pair of markers) and the blank line after it."""
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == MARKER)
        end = next(i for i in range(start + 1, len(lines)) if lines[i].strip() == MARKER)
    except StopIteration:
        return lines
    rest = lines[:start] + lines[end + 1 :]
    while start < len(rest) and start == 0 and rest and not rest[0].strip():
        rest.pop(0)
    return rest


def headings(lines: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            found.append((len(match.group(1)), match.group(2)))
    return found


def build_toc(found: list[tuple[int, str]]) -> list[str]:
    if not found:
        return []
    base = min(level for level, _ in found)
    seen: dict[str, int] = {}
    items = []
    for level, title in found:
        anchor = slugify(title)
        count = seen.get(anchor, 0)
        seen[anchor] = count + 1
        if count:
            anchor = f"{anchor}-{count}"
        items.append(f"{'  ' * (level - base)}- [{plain_text(title)}](#{anchor})")
    return [MARKER, *items, MARKER]


def render(text: str) -> str:
    lines = strip_toc(text.splitlines())
    toc = build_toc(headings(lines))
    if not toc:
        return text
    body = "\n".join(lines).lstrip("\n")
    return "\n".join(toc) + "\n\n" + body.rstrip("\n") + "\n"


def is_protected(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT)
    except ValueError:
        return False
    return bool(PROTECTED.intersection(rel.parts)) or rel.as_posix() in PROTECTED_FILES


def collect(targets: list[str]) -> list[Path]:
    paths = [Path(t) for t in targets] or [ROOT]
    files: list[Path] = []
    for path in paths:
        candidates = sorted(path.rglob("*.md")) if path.is_dir() else [path]
        files.extend(p for p in candidates if p.suffix == ".md" and not is_protected(p))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("paths", nargs="*", help="files or directories (default: whole repository)")
    parser.add_argument("--check", action="store_true", help="only report files whose TOC is missing or stale")
    args = parser.parse_args()

    stale = []
    for path in collect(args.paths):
        original = path.read_text(encoding="utf-8")
        updated = render(original)
        if updated == original:
            continue
        stale.append(path)
        if not args.check:
            path.write_text(updated, encoding="utf-8")
    verb = "needs update" if args.check else "updated"
    for path in stale:
        print(f"{verb}: {path.resolve().relative_to(ROOT) if path.resolve().is_relative_to(ROOT) else path}")
    if args.check and stale:
        print("Run `make toc` to fix.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
