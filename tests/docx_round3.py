#!/usr/bin/env python3
"""Round-three DOCX feature checks; callable by tests/integration.py's API harness."""
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}


def run(api, temp, outputs=None):
    out = Path(temp) / "docx-round3.docx"
    source = api.chunk(temp, "docx-round3", f'''let d=docx.create({api.literal(out)});
 d.title("Review packet").author("Avery"); d.heading_numbering(true); d.heading("Review packet",1).comment("Check this heading", "Avery");
 d.paragraph("Inserted wording").inserted("Added clause", "Avery").deleted("Old clause", "Avery");
d.table(2,2).cell(1,1,"Merged header").merge(1,1,1,2).shade(1,1,"#D9EAF7").cell_border(1,1,"bottom","#185A80",8);
d.text_box("Callout",180.0,54.0); d.section_break("landscape"); d.heading("Landscape appendix",2); d.save();''')
    result = api.result(["docx", "--lmcode", source])
    api.check("round3 run succeeds", result.get("ok"))
    with zipfile.ZipFile(out) as package:
        document = ET.fromstring(package.read("word/document.xml"))
        comments = ET.fromstring(package.read("word/comments.xml"))
        api.check("merged table cells", document.find(".//w:hMerge", NS) is not None and document.find(".//w:tcBorders/w:bottom", NS) is not None)
        api.check("text box", document.find(".//w:pict", NS) is not None and document.find(".//w:txbxContent", NS) is not None)
        sections = document.findall(".//w:sectPr", NS)
        api.check("section break landscape", len(sections) >= 2 and sections[-1].find("w:pgSz[@w:orient='landscape']", NS) is not None)
        api.check("comments", comments.find(".//w:comment", NS) is not None and document.find(".//w:commentRangeStart", NS) is not None)
        api.check("tracked insert/delete", document.find(".//w:ins", NS) is not None and document.find(".//w:del", NS) is not None)
        api.check("deterministic change date", document.find(".//w:ins[@w:date='2026-01-01T00:00:00Z']", NS) is not None)
        styles = ET.fromstring(package.read("word/styles.xml"))
        numbering = ET.fromstring(package.read("word/numbering.xml"))
        api.check("heading style numbering link", styles.find(".//w:style[@w:styleId='Heading1']/w:pPr/w:numPr/w:numId[@w:val='4']", NS) is not None and numbering.find(".//w:abstractNum[@w:abstractNumId='4']/w:lvl/w:pStyle[@w:val='Heading1']", NS) is not None)
        api.check("tracked deletion retains original wording", document.find(".//w:del/w:r/w:delText", NS).text == "Old clause")
    original = out.read_bytes()
    api.result(["docx", "--lmcode", source])
    api.check("review package is byte deterministic", original == out.read_bytes())
    api.error_case(temp, "merge-overflow", f'docx.create({api.literal(out)}).table(2,2).merge(1,1,9007199254740992 * 1024 - 1,1);', 3, "RUN_HOST", "range")
    inspected = api.result(["inspect", out])
    api.check("round3 OpenXmlValidator", inspected.get("ok") and inspected.get("result", {}).get("valid"))
    columns = Path(temp) / "columns.docx"
    bytecode = api.chunk(temp, "columns", f'let d=docx.create({api.literal(columns)}); d.columns(2,24.0); d.table(2,2).cell(1,1,"Left"); d.save();')
    api.result(["docx", "--lmcode", bytecode])
    with zipfile.ZipFile(columns) as package:
        doc = ET.fromstring(package.read("word/document.xml"))
        width = doc.find(".//w:tblPr/w:tblW", NS).get(f"{{{W}}}w")
        api.check("table fits its text column", width == "4800")
    api.error_case(temp, "column-gap-too-wide", f'docx.create({api.literal(columns)}).columns(4,400.0);', 3, "RUN_HOST", "width")


if __name__ == "__main__":
    raise SystemExit("This module is called by tests/integration.py")
