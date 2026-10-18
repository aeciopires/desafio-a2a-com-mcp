"""scripts/toc.py: idempotent, plugin-compatible markers, includes the H1, GitHub anchors."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("toc", ROOT / "scripts" / "toc.py")
toc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(toc)

DOC = """# Título Principal

Texto.

## Seção `com código` e [link](http://x)

```bash
# not a heading
```

### Subseção: detalhes (1)

## Seção `com código` e [link](http://x)
"""


def test_toc_lists_h1_and_nests_levels():
    rendered = toc.render(DOC)
    lines = rendered.splitlines()
    assert lines[0] == toc.MARKER
    assert lines[1] == "- [Título Principal](#título-principal)"
    assert lines[2] == "  - [Seção com código e link](#seção-com-código-e-link)"
    assert lines[3] == "    - [Subseção: detalhes (1)](#subseção-detalhes-1)"
    assert lines[4] == "  - [Seção com código e link](#seção-com-código-e-link-1)"
    assert lines[5] == toc.MARKER
    assert "not a heading" not in "\n".join(lines[:6])


def test_toc_uses_the_same_marker_to_open_and_close():
    rendered = toc.render(DOC)
    assert rendered.count("<!-- TOC -->") == 2
    assert "<!-- /TOC -->" not in rendered


def test_render_is_idempotent():
    once = toc.render(DOC)
    assert toc.render(once) == once


def test_existing_toc_is_replaced_not_duplicated():
    stale = "<!-- TOC -->\n- [Old](#old)\n<!-- TOC -->\n\n" + DOC
    rendered = toc.render(stale)
    assert rendered.count(toc.MARKER) == 2
    assert "[Old]" not in rendered


def test_protected_paths_are_skipped():
    assert toc.is_protected(ROOT / "validador" / "README.md")
    assert toc.is_protected(ROOT / "TASK.md")
    assert not toc.is_protected(ROOT / "README.md")


def test_repository_docs_are_up_to_date():
    stale = [p for p in toc.collect([]) if toc.render(p.read_text(encoding="utf-8")) != p.read_text(encoding="utf-8")]
    assert stale == [], f"run make toc: {stale}"
