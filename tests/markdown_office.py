"""Focused checks for presentation and worksheet Markdown adapters."""

import json
from pathlib import Path


def run(api, temp: Path, outputs=None):
    temp = Path(temp)
    deck = temp / "markdown-slides.pptx"
    book = temp / "markdown-table.xlsx"
    csv_book = temp / "markdown-csv.xlsx"
    source = """# Markdown deck

Generated from **plain text**.

- first point
  - nested point

| Name | Score |
| --- | ---: |
| Alpha | 42 |
| Beta | 17 |

Note: Speaker notes survive the import.

---

# Second slide

{{layout: two-column}}

![sample](data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=){width=32 height=32}
"""
    body = f'''let d = pptx.create({api.literal(deck)}); d.markdown({json.dumps(source, ensure_ascii=False)}); d.save();'''
    bytecode = api.chunk(temp, "markdown-pptx", body)
    result = api.result(["pptx", "--lmcode", bytecode])
    api.check("Markdown PPTX render succeeds", result.get("ok") is True, result)
    inspected = api.result(["inspect", deck])
    api.check("Markdown PPTX has two slides", inspected.get("ok") and inspected.get("result", {}).get("slides") == 2, inspected)

    table = """# Scores

| Name | Score |
| --- | ---: |
| Alpha | 42 |
| Beta | true |
"""
    body = f'''let d = xlsx.create({api.literal(book)}); d.sheet_from_markdown_table("Scores", {json.dumps(table, ensure_ascii=False)}); d.save();'''
    result = api.result(["xlsx", "--lmcode", api.chunk(temp, "markdown-xlsx", body)])
    api.check("Markdown XLSX table succeeds", result.get("ok") is True, result)
    inspected = api.result(["inspect", book])
    api.check("Markdown XLSX table is valid", inspected.get("ok") and inspected.get("result", {}).get("valid"), inspected)

    csv = 'Name,Code,Amount\r\n"Ada, Example",0012,3.5\r\n"Line 1\nLine 2",true,=literal\r\n'
    body = f'''let d = xlsx.create({api.literal(csv_book)}); d.sheet_from_csv("Data", {json.dumps(csv, ensure_ascii=False)}); d.save();'''
    result = api.result(["xlsx", "--lmcode", api.chunk(temp, "markdown-csv", body)])
    api.check("CSV import succeeds", result.get("ok") is True, result)

    bad = 'a,b\n1\n'
    body = f'''let d = xlsx.create({api.literal(temp / "bad-csv.xlsx")}); d.sheet_from_csv("Data", {json.dumps(bad, ensure_ascii=False)});'''
    failure = api.result(["xlsx", "--lmcode", api.chunk(temp, "markdown-csv-bad", body)], 3)
    api.check("ragged CSV is rejected", failure.get("ok") is False and failure.get("line", 0) > 0, failure)
    return 5


if __name__ == "__main__":
    raise SystemExit("This module is called by tests/integration.py")
