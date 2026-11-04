"""Focused checks for the Word Markdown adapter (called by integration.py)."""

import json
from pathlib import Path
from zipfile import ZipFile


def run(h, temp: Path, outputs=None):
    output = temp / "markdown-docx.docx"
    source = """---
title: Markdown contract
author: Ada Example
page_numbers: true
numbering: true
---
# Agreement

This is **bold**, *italic*, `code`, ~~removed~~ and [a link](https://example.test).

- outer
  - nested
1. ordered

| Name | Amount |
| :--- | ---: |
| Alpha {bg=#EAF2F8} | 42 |

> A quoted paragraph.

[^n] is a footnote.

[^n]: A supporting note.

```text
literal code
```

{{sign: Ada Example}}
"""
    # The outer lmscript string is ordinary UTF-8 here; compiler-side heredocs
    # can replace it without changing the host API being exercised.
    body = f"let d = docx.create({h.literal(output)}); d.markdown({json.dumps(source, ensure_ascii=False)}); d.save();"
    bytecode = h.chunk(temp, "markdown-docx", body)
    response = h.result(["docx", "--lmcode", bytecode])
    h.check("Markdown DOCX render succeeds", response.get("ok") is True, response)
    inspected = h.result(["inspect", output])
    summary = inspected.get("result", {})
    h.check("Markdown DOCX headings and table", inspected.get("ok") is True and summary.get("tables") == 1 and "Agreement" in summary.get("text", ""), summary)
    h.check("Markdown DOCX footnote and signature", output.exists() and summary.get("valid") is True, summary)
    with ZipFile(output) as package:
        names = set(package.namelist())
        document_xml = package.read("word/document.xml").decode("utf-8")
        h.check("Markdown DOCX emits footnotes and links", "word/footnotes.xml" in names and "hyperlink" in document_xml, names)
        h.check("Markdown DOCX emits structural numbering and shading", "w:numPr" in document_xml and "w:shd" in document_xml, document_xml[:500])

    bad = "---\nunknown: value\n---\ntext"
    bad_body = f"let d = docx.create({h.literal(temp / 'markdown-bad.docx')}); d.markdown({json.dumps(bad, ensure_ascii=False)}); d.save();"
    bad_bytecode = h.chunk(temp, "markdown-docx-bad", bad_body)
    failure = h.result(["docx", "--lmcode", bad_bytecode], 3)
    h.check("Markdown unknown metadata is rejected", failure.get("ok") is False and failure.get("code") == "RUN_HOST" and "unknown" in failure.get("message", "").lower(), failure)
