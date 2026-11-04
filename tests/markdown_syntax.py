"""Strict Markdown grammar regressions through the real compiler and host."""
import json
from pathlib import Path


def run(api, temp: Path, outputs=None):
    cases = [
        ("unknown", "# Test\n\n{{mystery}}", 3, "directive"),
        ("wrapped", "First line\nSecond {{nope}}", 2, "directive"),
        ("unclosed", "A **broken phrase", 1, "emphasis"),
        ("fence", "# Code\n```\nunclosed", 2, "fenced"),
        ("list-skip", "- top\n    - skipped", 2, "indentation"),
        ("list-odd", "- top\n - odd", 2, "indentation"),
        ("table-ragged", "| A | B |\n| --- | --- |\n| one |", 3, "ragged"),
        ("table-directive", "| A | B |\n| --- | --- |\n| one | {{nope}} |", 3, "directive"),
        ("width-count", "{widths=100}\n| A | B |\n| --- | --- |", 1, "widths"),
        ("width-orphan", "{widths=100}", 1, "widths"),
        ("footnote", "Missing [^nope]", 1, "footnote"),
        ("footnote-duplicate", "[^a]: one\n[^a]: two", 2, "duplicate"),
        ("metadata", "---\nunknown: value\n---", 2, "front matter"),
        ("metadata-size", "---\npage_size: huge\n---", 2, "page_size"),
        ("metadata-bool", "---\ntoc: yes\n---", 2, "true or false"),
        ("image-attr", "![alt](x.png){rotation=90}", 1, "attributes"),
        ("link-scheme", "[link](javascript:bad)", 1, "hyperlink"),
    ]
    for name, source, line, message in cases:
        body = f'docx.create({api.literal(temp / (name+".docx"))}).markdown({json.dumps(source, ensure_ascii=False)}).save();'
        code = api.chunk(temp, "markdown-syntax-" + name, body)
        response = api.result(["docx", "--lmcode", code], 3)
        api.check("strict Markdown " + name, f"Markdown line {line}:" in response.get("message", "") and message in response["message"], response)
