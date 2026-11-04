#!/usr/bin/env python3
"""Genre example coverage for the Word surface of lmoffice."""
from pathlib import Path
import importlib.util
import zipfile
import xml.etree.ElementTree as ET


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"w": W, "r": R, "pr": PKG}


def _xml(package, name):
    return ET.fromstring(package.read(name))


def _texts(root):
    return " ".join(node.text or "" for node in root.findall(".//w:t", NS))


def _check_features(api, documents):
    def package(path):
        return zipfile.ZipFile(path)

    with package(documents["legal-nda"]) as z:
        numbering = _xml(z, "word/numbering.xml")
        start = numbering.find(".//w:abstractNum[@w:abstractNumId='2']/w:lvl/w:start", NS)
        api.check("ordinary numbered lists start at one", start is not None and start.attrib.get(f"{{{W}}}val") == "1")
        levels = numbering.findall(".//w:abstractNum[@w:abstractNumId='3']/w:lvl", NS)
        formats = [node.attrib.get(f"{{{W}}}val") for node in numbering.findall(".//w:abstractNum[@w:abstractNumId='3']/w:lvl/w:numFmt", NS)]
        document = _xml(z, "word/document.xml")
        api.check("legal multilevel clause numbering", len(levels) >= 3 and formats[:3] == ["decimal", "decimal", "lowerLetter"] and {node.attrib.get(f"{{{W}}}val") for node in document.findall(".//w:numPr/w:ilvl", NS)} >= {"0", "1"})
        api.check("legal clause levels", {x.attrib.get(f"{{{W}}}val") for x in document.findall(".//w:numPr/w:ilvl", NS)} == {"0", "1", "2"})
        api.check("legal page dimensions and margins", document.find(".//w:sectPr/w:pgSz", NS) is not None and document.find(".//w:sectPr/w:pgMar", NS) is not None)

    with package(documents["legal-lease"]) as z:
        document = _xml(z, "word/document.xml")
        margins = document.find(".//w:sectPr/w:pgMar", NS)
        api.check("lease page settings", document.find(".//w:sectPr/w:pgSz", NS) is not None and margins is not None and margins.attrib.get(f"{{{W}}}top") == "1080")

    with package(documents["business-report-with-toc"]) as z:
        document = _xml(z, "word/document.xml")
        fields = " ".join(node.text or "" for node in document.findall(".//w:instrText", NS))
        cached = _texts(document.find(".//w:sdtContent", NS)) if document.find(".//w:sdtContent", NS) is not None else ""
        api.check("table of contents field and cached headings", "TOC" in fields and "Executive summary" in cached and "Customer operations" in cached)
        styles = _xml(z, "word/styles.xml")
        api.check("paragraph heading keep-next", styles.find(".//w:style[@w:styleId='Heading1']//w:keepNext", NS) is not None)

    with package(documents["legal-nda"]) as z:
        header_names = [n for n in z.namelist() if n.startswith("word/header") and n.endswith(".xml")]
        footer_names = [n for n in z.namelist() if n.startswith("word/footer") and n.endswith(".xml")]
        instructions = []
        for name in header_names + footer_names:
            part = _xml(z, name)
            instructions.extend(node.attrib.get(f"{{{W}}}instr", "") for node in part.findall(".//w:fldSimple", NS))
            instructions.extend(node.text or "" for node in part.findall(".//w:instrText", NS))
        fields = {instruction.strip().split()[0] for instruction in instructions if instruction.strip()}
        api.check("page and date are live Word fields", {"PAGE", "NUMPAGES", "DATE"} <= fields)
        root = _xml(z, "word/document.xml")
        api.check("header and footer remain referenced", root.find(".//w:sectPr/w:headerReference", NS) is not None and root.find(".//w:sectPr/w:footerReference", NS) is not None)

    with package(documents["resume-academic-cv"]) as z:
        footnotes = _xml(z, "word/footnotes.xml")
        document = _xml(z, "word/document.xml")
        refs = {r.attrib.get(f"{{{W}}}id") for r in document.findall(".//w:footnoteReference", NS)}
        definitions = {n.attrib.get(f"{{{W}}}id") for n in footnotes.findall("w:footnote", NS)}
        api.check("footnotes with references", refs and refs <= definitions and all(int(value) > 0 for value in refs))
        rels = _xml(z, "word/_rels/document.xml.rels")
        api.check("external hyperlink relationship", any(x.attrib.get("Type", "").endswith("/hyperlink") and x.attrib.get("Target", "").startswith("https://") for x in rels.findall("pr:Relationship", NS)))

    with package(documents["resume-two-column"]) as z:
        document = _xml(z, "word/document.xml")
        api.check("resume right tab stop", document.find(".//w:tabs/w:tab[@w:val='right']", NS) is not None and document.find(".//w:tab", NS) is not None)
        api.check("borderless table with widths", document.find(".//w:tblPr/w:tblBorders/w:insideH[@w:val='nil']", NS) is not None and len(document.findall(".//w:tblGrid/w:gridCol", NS)) >= 2)

    with package(documents["business-purchase-order"]) as z:
        document = _xml(z, "word/document.xml")
        size = document.find(".//w:sectPr/w:pgSz", NS)
        api.check("landscape purchase order", size.attrib[f"{{{W}}}orient"] == "landscape" and int(size.attrib[f"{{{W}}}w"]) > int(size.attrib[f"{{{W}}}h"]))
        api.check("purchase order shaded headers and widths", len(document.findall(".//w:tcPr/w:shd", NS)) == 5 and [n.attrib[f"{{{W}}}w"] for n in document.findall(".//w:tblGrid/w:gridCol", NS)] == ["7200", "1200", "2640", "2640"])

    with package(documents["feature-probe"]) as z:
        document = _xml(z, "word/document.xml")
        api.check("feature probe three clause levels", {x.attrib.get(f"{{{W}}}val") for x in document.findall(".//w:numPr/w:ilvl", NS)} >= {"0", "1", "2"})
        api.check("borderless table with shading", document.find(".//w:tblBorders/w:top[@w:val='nil']", NS) is not None and document.find(".//w:shd", NS) is not None)
        api.check("paragraph indent and keep-next", document.find(".//w:ind", NS) is not None and document.find(".//w:keepNext", NS) is not None)

    with package(documents["business-job-offer"]) as z:
        document = _xml(z, "word/document.xml")
        api.check("signature underline", document.find(".//w:u", NS) is not None)

    with package(documents["business-press-release"]) as z:
        document = _xml(z, "word/document.xml")
        api.check("text columns", document.find(".//w:sectPr/w:cols[@w:num='2']", NS) is not None)

    with package(documents["legal-nda"]) as z:
        document = _xml(z, "word/document.xml")
        paragraph = document.find(".//w:spacing", NS)
        api.check("paragraph spacing", paragraph is not None and paragraph.attrib.get(f"{{{W}}}after") is not None)


def run(api, temp):
    root = Path(api.ROOT)
    example_dir = root / "examples"
    expected = {
        "legal": {"legal-nda", "legal-services-agreement", "legal-lease", "legal-terms-of-service", "legal-power-of-attorney", "legal-demand-letter"},
        "resume": {"resume-classic", "resume-two-column", "resume-academic-cv", "resume-cover-letter", "resume-reference-sheet"},
        "business": {"business-memo", "business-proposal", "business-letter", "business-press-release", "business-report-with-toc", "business-purchase-order", "business-job-offer", "business-agenda"},
    }
    actual = {genre: {p.stem for p in example_dir.glob(f"{genre}-*.lms")} for genre in expected}
    for genre, names in expected.items():
        api.check(f"{genre} example count", actual[genre] == names, sorted(actual[genre]))

    documents = {}
    for name in sorted(set().union(*actual.values())):
        source = example_dir / f"{name}.lms"
        output = Path(temp) / f"{name}.docx"
        api.compiler(source, output, cwd=temp)
        inspected = api.result(["inspect", output])
        api.check(f"{name} OpenXmlValidator", inspected.get("ok") and inspected.get("result", {}).get("valid"))
        api.check(f"{name} nonempty text", bool(inspected.get("result", {}).get("text", "").strip()))
        documents[name] = output

    probe_output = Path(temp) / "feature-probe.docx"
    probe = api.chunk(temp, "feature-probe", f'''let d=docx.create({api.literal(probe_output)});
        d.page_size(612.0,792.0).margins(54.0,54.0,54.0,54.0).columns(2,24.0);
d.clause("One",1); d.clause("One point one",2); d.clause("One point one a",3);
d.paragraph("Probe").spacing(0.0,8.0,1.0).indent(10.0,20.0,30.0).keep_with_next(true).tab_stop(400.0,"right").hyperlink("link","https://example.com").footnote("note");
d.table(1,1).borders(false).column_width(1,100.0).shade(1,1,"#D9EAF7");
d.signature("Signer"); d.header_fields("{{PAGE}} of {{NUMPAGES}}").save();''')
    api.result(["docx", "--lmcode", probe])
    inspected_probe = api.result(["inspect", probe_output])
    api.check("feature probe OpenXmlValidator", inspected_probe.get("ok") and inspected_probe.get("result", {}).get("valid"))
    documents["feature-probe"] = probe_output

    if importlib.util.find_spec("docx"):
        from docx import Document
        for name, path in documents.items():
            doc = Document(path)
            api.check(f"python-docx opens {name}", bool(doc.paragraphs or doc.tables))
    else:
        print("SKIP independent DOCX readers: python-docx not installed")

    _check_features(api, documents)

    target = api.literal(Path(temp) / "genre-errors.docx")
    cases = [
        ("invalid-clause-level", f'docx.create({target}).clause("x", 4);', "clause level"),
        ("negative-margin", f'docx.create({target}).margins(-1.0, 54.0, 54.0, 54.0);', "margin"),
        ("empty-font", f'docx.create({target}).font("");', "font"),
        ("bad-tab-alignment", f'docx.create({target}).paragraph("x").tab_stop(100.0, "diagonal");', "tab alignment"),
        ("negative-tab", f'docx.create({target}).paragraph("x").tab_stop(-1.0, "right");', "tab"),
        ("bad-column-width", f'docx.create({target}).table(1, 1).column_width(1, 0.0);', "column width"),
        ("bad-hyperlink", f'docx.create({target}).paragraph("x").hyperlink("x", "javascript:alert(1)");', "hyperlink"),
        ("after-save-paragraph-method", f'let d=docx.create({target}); let p=d.paragraph("x"); d.save(); p.keep_with_next(true);', "saved"),
    ]
    for name, body, message in cases:
        api.error_case(temp, name, body, 3, "RUN_HOST", message)

    return sum(len(names) for names in expected.values())
