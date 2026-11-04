#!/usr/bin/env python3
"""Round-trip checks for Office.to_markdown (called by integration.py)."""
import json
import difflib
from pathlib import Path


def run(api, temp: Path, outputs=None):
    temp = Path(temp)
    docx, docx_copy = temp / "export-source.docx", temp / "export-docx-copy.docx"
    pptx, pptx_copy = temp / "export-source.pptx", temp / "export-pptx-copy.docx"
    xlsx, xlsx_copy = temp / "export-source.xlsx", temp / "export-xlsx-copy.docx"
    source = """---
title: Export probe
author: Ada Example
---
# Agreement

This is **bold** and [linked](https://example.test).

| Name | Value |
| --- | ---: |
| Alpha | 42 |
"""
    body = f'''let d=docx.create({api.literal(docx)}); d.markdown({json.dumps(source, ensure_ascii=False)}); d.save();
let md=docx.to_markdown({api.literal(docx)}); let copy=docx.create({api.literal(docx_copy)}); copy.markdown(md); copy.save();'''
    response = api.result(["docx", "--lmcode", api.chunk(temp, "markdown-export-docx", body)])
    api.check("DOCX Markdown extraction round trip", response.get("ok") is True, response)
    inspected = api.result(["inspect", docx_copy])
    text = inspected.get("result", {}).get("text", "")
    api.check("DOCX extraction came from package structure", "Agreement" in text and "Alpha" in text, inspected)

    slides = """# Briefing

- First point

---

# Decision

Note: Review next week.
"""
    body = f'''let d=pptx.create({api.literal(pptx)}); d.markdown({json.dumps(slides, ensure_ascii=False)}); d.save();
let md=pptx.to_markdown({api.literal(pptx)});'''
    response = api.result(["pptx", "--lmcode", api.chunk(temp, "markdown-export-pptx", body)])
    api.check("PPTX Markdown extraction succeeds", response.get("ok") is True, response)
    extracted = api.result(["inspect", pptx, "--markdown"]).get("result", {}).get("markdown", "")
    copy_body = f'''let copy=docx.create({api.literal(pptx_copy)}); copy.markdown({json.dumps(extracted, ensure_ascii=False)}); copy.save();'''
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-export-pptx-copy", copy_body)])
    inspected = api.result(["inspect", pptx_copy])
    text = inspected.get("result", {}).get("text", "")
    api.check("PPTX extraction includes slide text", "Briefing" in text and "Decision" in text, inspected)

    table = """# Scores

| Name | Score |
| --- | ---: |
| Alpha | 42 |
| Beta | true |
"""
    body = f'''let d=xlsx.create({api.literal(xlsx)}); d.sheet_from_markdown_table("Scores", {json.dumps(table, ensure_ascii=False)}); d.save();
let md=xlsx.to_markdown({api.literal(xlsx)});'''
    response = api.result(["xlsx", "--lmcode", api.chunk(temp, "markdown-export-xlsx", body)])
    api.check("XLSX Markdown extraction succeeds", response.get("ok") is True, response)
    extracted = api.result(["inspect", xlsx, "--markdown"]).get("result", {}).get("markdown", "")
    copy_body = f'''let copy=docx.create({api.literal(xlsx_copy)}); copy.markdown({json.dumps(extracted, ensure_ascii=False)}); copy.save();'''
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-export-xlsx-copy", copy_body)])
    inspected = api.result(["inspect", xlsx_copy])
    text = inspected.get("result", {}).get("text", "")
    api.check("XLSX extraction includes headed table", "Scores" in text and "Alpha" in text, inspected)

    # Canonical fixed-point check: the second export must be byte-for-byte
    # equal to the first export, rather than merely containing the same text.
    fixed = temp / "export-fixed.docx"
    image = temp / "markdown-image.png"
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-image", f'docx.sample_image({api.literal(image)});')])
    fixture = r"""---
title: Fixed point: full grammar
author: Ada Example
subject: A document-as-code fixture
header: Confidential | {{page}} of {{pages}}
footer: Published {{date}}
page_size: a4
orientation: landscape
theme: legal
numbering: true
toc: true
---
# Heading

Inline **bold and *nested italic***, *italic and **nested bold***, *italic*, `x*y`, ~~removed~~ and [**link**](https://example.test).

A footnote[^a] and another[^b]. Right date{{tab}}June 2026.

> A quoted **paragraph**.

- first **bullet**
  - nested *bullet*
1. ordered
  1. nested ordered

```text
literal code: * star and | pipe
second line with `ticks`
```

{widths=160,240}
| Name {bg=#D9EAF7} | Amount |
| :---: | ---: |
| **Alpha** | 42 {bg=#EAF2F8} |
| Escaped \| pipe | text |

{{clause: 1}} First **clause**.
{{clause: 2}} Child clause.
{{clause: 3}} Lettered clause.

{{sign: Ada Example}}

{{pagebreak}}

![Badge](IMAGE_PATH){width=64 height=32}

[^a]: A supporting **note**.
[^b]: A second note.
""".replace("IMAGE_PATH", str(image).replace("\\", "/"))
    first = temp / "fixed-first.docx"
    body = f'''let d=docx.create({api.literal(first)}); d.markdown({json.dumps(fixture, ensure_ascii=False)}); d.save();'''
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-fixed-first", body)])
    api.check("source Markdown OpenXmlValidator", api.result(["inspect", first])["result"]["valid"])
    md1 = api.result(["inspect", first, "--markdown"]).get("result", {}).get("markdown", "")
    body = f'''let d=docx.create({api.literal(fixed)}); d.markdown({json.dumps(md1, ensure_ascii=False)}); d.save();'''
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-fixed-second", body)])
    api.check("round-trip Markdown OpenXmlValidator", api.result(["inspect", fixed])["result"]["valid"])
    md2 = api.result(["inspect", fixed, "--markdown"]).get("result", {}).get("markdown", "")
    api.check("DOCX Markdown canonical fixed point", md1 == md2, "\n".join(difflib.unified_diff(md1.splitlines(), md2.splitlines(), n=0))[:4000])
    for expected in ("{widths=160,240}", "{bg=#D9EAF7}", "[^fn1]", "{{tab}}", "{{clause: 3}}", "{{toc}}", "{{sign: Ada Example}}", "data:image/png;base64,", "```text", "header: Confidential | {{page}} of {{pages}}"):
        api.check("canonical Markdown retains " + expected[:28], expected in md1, md1)
    import importlib.util
    if importlib.util.find_spec("docx"):
        from docx import Document
        d = Document(fixed)
        api.check("independent reader retains image dimensions", len(d.inline_shapes) == 1 and d.inline_shapes[0].width == 64 * 9525)
        api.check("independent reader retains shaded aligned table", len(d.tables) == 1 and d.tables[0].cell(0, 1).paragraphs[0].alignment == 2)



if __name__ == "__main__":
    raise SystemExit("This module is called by tests/integration.py")
