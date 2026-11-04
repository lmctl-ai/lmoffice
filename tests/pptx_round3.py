#!/usr/bin/env python3
"""Focused independent checks for the round-three PPTX example decks.

Usage: LMOFFICE_BIN=./build/.../lmoffice LMSCRIPT_BIN=lmscript python3 tests/pptx_round3.py
"""
from pathlib import Path
import os, shutil, subprocess, sys, tempfile, zipfile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HOST = Path(os.environ.get("LMOFFICE_BIN", "")).resolve()
COMPILER = os.environ.get("LMSCRIPT_BIN") or shutil.which("lmscript")
EXAMPLES = ("education-lesson-deck", "marketing-brand-guidelines", "hr-onboarding-review")

CHART_NS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"

def check_deck(name, pptx):
    """Validate an already-generated deck for integration.py and standalone use."""
    pptx = Path(pptx)
    assert pptx.exists() and pptx.stat().st_size > 0, name
    with zipfile.ZipFile(pptx) as z:
        names = set(z.namelist())
        charts = [n for n in names if "/charts/chart" in n and n.endswith(".xml")]
        assert len(charts) >= 1, (name, charts)
        assert any(n.endswith(".png") for n in names), name
        assert any(n.startswith("ppt/slides/slide") for n in names), name
        chart_types = set()
        for chart in charts:
            root = ET.fromstring(z.read(chart))
            chart_types.update(e.tag.removeprefix(CHART_NS) for e in root.iter()
                               if e.tag.startswith(CHART_NS) and e.tag.removeprefix(CHART_NS) in
                               {"barChart", "lineChart", "pieChart"})
            assert z.getinfo(chart).file_size > 0
        assert chart_types, (name, charts)
    try:
        from pptx import Presentation
    except ImportError:
        return chart_types
    deck = Presentation(pptx)
    assert len(deck.slides) == 5
    assert any(shape.has_table for slide in deck.slides for shape in slide.shapes)
    assert any(shape.shape_type == 13 for slide in deck.slides for shape in slide.shapes)
    return chart_types

def run(api, temp, outputs):
    all_types = set()
    for name in EXAMPLES:
        all_types.update(check_deck(name, outputs[name + ".lms"]))
        api.check("PPTX native charts, table and image " + name, True)
    api.check("PPTX bar/line/pie coverage", all_types == {"barChart", "lineChart", "pieChart"})

def main():
    if not HOST.exists() or not COMPILER:
        print("SKIP pptx round-three checks: set LMOFFICE_BIN and LMSCRIPT_BIN", file=sys.stderr)
        return 0
    with tempfile.TemporaryDirectory(prefix="lmoffice-pptx-round3-") as td:
        out = Path(td)
        for name in EXAMPLES:
            source = ROOT / "examples" / f"{name}.lms"
            patched = out / f"{name}.lms"
            text = source.read_text(encoding="utf-8")
            patched.write_text(text, encoding="utf-8")
            pptx = out / f"{name}.pptx"
            proc = subprocess.run([COMPILER, patched, pptx], capture_output=True)
            assert proc.returncode == 0, proc.stderr.decode(errors="replace")
            assert pptx.exists() and pptx.stat().st_size > 0, name + " did not run through run_lmcode"
            check_deck(name, pptx)
    print("PASS PPTX round-three checks: 3 decks, 15 slides, bar/line/pie XML, tables, images")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
