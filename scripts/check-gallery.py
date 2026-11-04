#!/usr/bin/env python3
"""Check README image links against committed Git files; no host/renderer needed."""
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    links = set(re.findall(r'!\[[^\]]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)', readme))
    links.update(re.findall(r'<img\b[^>]*\bsrc=["\']([^"\']+)', readme, re.I))
    committed = set(subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "HEAD"], cwd=ROOT, text=True).splitlines())
    failures, paths = [], set()
    for link in sorted(links):
        parsed = urlsplit(link.strip("<>"))
        if parsed.scheme or parsed.netloc:
            failures.append(f"README image must be committed locally: {link}")
            continue
        image = (ROOT / unquote(parsed.path)).resolve()
        if not image.is_relative_to(ROOT):
            failures.append(f"image escapes repository: {link}")
            continue
        relative = image.relative_to(ROOT).as_posix()
        paths.add(relative)
        if relative not in committed:
            failures.append(f"image is not committed: {relative}")
        if not image.is_file():
            failures.append(f"missing image: {relative}")
        elif not 0 < image.stat().st_size < 300000:
            failures.append(f"image must be nonempty and below 300 KB: {relative}")
        elif image.suffix.lower() == ".png" and image.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
            failures.append(f"not a PNG: {relative}")
    examples = {p.stem for p in (ROOT / "examples").glob("*.lms")}
    manifest = json.loads((ROOT / "docs/gallery.json").read_text(encoding="utf-8"))["examples"]
    if len(manifest) != len(examples) or {e["name"] for e in manifest} != examples:
        failures.append("gallery manifest must cover each example exactly once")
    for entry in manifest:
        if entry.get("source_preview"):
            source = (ROOT / "examples" / (entry["name"] + ".lms")).read_text(encoding="utf-8")
            if source.count(chr(34) * 3) != 2:
                failures.append(f"source preview needs exactly one triple-quoted body: {entry['name']}")
        source = (ROOT / "examples" / (entry["name"] + ".lms")).read_text(encoding="utf-8")
        schemas = re.findall(r'load_schema\(schema="\.\./schema/(docx|xlsx|pptx)\.dsl\.json"\)', source)
        commands = re.findall(r'run_lmcode\([^,]+,\s*\{command:\["lmoffice","(docx|xlsx|pptx)","--lmcode","\$DSLFILE"\]\}\)', source)
        if not schemas or len(commands) != len(re.findall(r'run_lmcode\(', source)):
            failures.append(f"source example must bind a local schema and run through lmcode: {entry['name']}")
        elif any(fmt not in schemas for fmt in commands):
            failures.append(f"source example command must match its local schema: {entry['name']}")
    stats = ROOT / "scripts/markdown-example-stats.py"
    if stats.exists():
        comparison = subprocess.check_output([sys.executable, str(stats)], cwd=ROOT, text=True).strip()
        if comparison not in readme:
            failures.append("README Markdown line-count comparison is stale; run scripts/markdown-example-stats.py")
    for name in sorted(examples):
        if f"docs/images/{name}.png" not in paths:
            failures.append(f"README has no preview for {name}")
        if not re.search(r"`lmctl(?: autorun)? https://raw\.githubusercontent\.com/lmctl-ai/lmoffice/main/examples/" + re.escape(name) + r"\.lms`", readme):
            failures.append(f"README has no autorun caption for {name}")
    if failures:
        print("Gallery check failed:\n" + "\n".join(f"- {failure}" for failure in failures), file=sys.stderr)
        return 1
    print(f"PASS gallery: {len(examples)} examples, {len(paths)} committed README images; all below 300 KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
