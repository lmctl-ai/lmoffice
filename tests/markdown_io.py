"""File boundary, scalar inference, and strict renderer regressions."""
import importlib.util
import json
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


def run(api, temp, outputs=None):
    directory = Path(temp) / "markdown-assets"
    directory.mkdir()
    image = directory / "badge.png"
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-file-image", f'docx.sample_image({api.literal(image)});')])
    source = directory / "document.md"
    source.write_text('# A file document\n\n![Badge](badge.png){width=64 height=32}\n', encoding="utf-8")
    target = Path(temp) / "markdown-file.docx"
    code = api.chunk(temp, "markdown-file", f'docx.create({api.literal(target)}).markdown_file({api.literal(source)}).save();')
    api.result(["docx", "--lmcode", code])
    api.check("Markdown file resolves relative image", api.result(["inspect", target])["result"]["images"] == 1)
    first = target.read_bytes()
    api.result(["docx", "--lmcode", code])
    api.check("Markdown image package is deterministic", target.read_bytes() == first)
    invalid = directory / "invalid.md"
    invalid.write_bytes(b'# Bad\n\xff\xfe')
    api.error_case(temp, "markdown-file-invalid-utf8", f'docx.create({api.literal(target)}).markdown_file({api.literal(invalid)});', 3, "RUN_HOST", "UTF-8")

    values = 'Name,Code,Enabled,Amount,Formula\r\n"Ada, Example",0012,true,3.5,=SUM(A1:A2)\r\n"Line 1\nLine 2",-001,false,-2.25,=literal\r\n'
    workbook = Path(temp) / "markdown-inference.xlsx"
    api.result(["xlsx", "--lmcode", api.chunk(temp, "markdown-inference", f'let b=xlsx.create({api.literal(workbook)}); b.sheet_from_csv("Data",{json.dumps(values)}); b.save();')])
    api.check("quoted CSV validates", api.result(["inspect", workbook])["result"]["valid"])
    if importlib.util.find_spec("openpyxl"):
        import openpyxl
        sheet = openpyxl.load_workbook(workbook)["Data"]
        api.check("CSV quoted commas and newlines", sheet["A2"].value == "Ada, Example" and sheet["A3"].value == "Line 1\nLine 2")
        api.check("CSV preserves leading-zero identifiers", sheet["B2"].value == "0012" and sheet["B3"].value == "-001")
        api.check("CSV infers bool and numeric cells", sheet["C2"].value is True and sheet["C3"].value is False and sheet["D2"].value == 3.5)
        api.check("CSV formulas stay literal", sheet["E2"].value == "=SUM(A1:A2)" and sheet["E2"].data_type == "s")
        api.check("CSV header is styled", sheet["A1"].font.bold and sheet["A1"].fill.fgColor.rgb == "FF173D55")
    for name, value, line in (("unclosed", 'a,b\n"open', 2), ("mid-quote", 'a,b\na"b,c', 2), ("quote-tail", 'a,b\n"a"x,c', 2)):
        failure = api.result(["xlsx", "--lmcode", api.chunk(temp, "csv-"+name, f'xlsx.create({api.literal(workbook)}).sheet_from_csv("Data",{json.dumps(value)});')], 3)
        api.check("strict CSV " + name, f"CSV line {line}:" in failure["message"], failure)

    deck = Path(temp) / "markdown-inline.pptx"
    text = '# Heading\n\nA **bold** [link](https://example.test/).\n\n- Top\n  - Nested\n\nNote: First note\nNote: Second note\n'
    api.result(["pptx", "--lmcode", api.chunk(temp, "markdown-slide-inline", f'pptx.create({api.literal(deck)}).markdown({json.dumps(text)}).save();')])
    api.check("Markdown slide links validate", api.result(["inspect", deck])["result"]["valid"])
    if importlib.util.find_spec("pptx"):
        from pptx import Presentation
        d = Presentation(deck)
        runs = [run for shape in d.slides[0].shapes if shape.has_text_frame for paragraph in shape.text_frame.paragraphs for run in paragraph.runs]
        api.check("PPTX Markdown bold and hyperlink", any(run.text == "bold" and run.font.bold for run in runs) and any(run.hyperlink.address == "https://example.test/" for run in runs))
        api.check("PPTX appends speaker notes", "First note\nSecond note" in d.slides[0].notes_slide.notes_text_frame.text)
        api.check("PPTX preserves nested bullet levels", any(p.level == 1 for s in d.slides[0].shapes if s.has_text_frame for p in s.text_frame.paragraphs))
    # Width-only images retain their aspect ratio without System.Drawing.
    width_only = '# Image\n\n![Badge](' + str(image).replace("\\", "/") + '){width=80}'
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-aspect", f'docx.create({api.literal(target)}).markdown({json.dumps(width_only)}).save();')])
    with ZipFile(target) as package:
        xml = ET.fromstring(package.read("word/document.xml"))
        extent = xml.find(".//{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}extent")
        api.check("Markdown width-only image preserves aspect", extent.get("cx") == extent.get("cy") == str(80 * 9525))
    literal_doc = Path(temp) / "markdown-literal-source.docx"
    literal_copy = Path(temp) / "markdown-literal-copy.docx"
    literal_source = f'let d=docx.create({api.literal(literal_doc)}); d.paragraph("---"); d.paragraph("- literal marker"); d.paragraph("+ literal plus"); d.header("Confidential * copy"); d.save(); let text=docx.to_markdown({api.literal(literal_doc)}); docx.create({api.literal(literal_copy)}).markdown(text).save();'
    api.result(["docx", "--lmcode", api.chunk(temp, "markdown-literal-structure", literal_source)])
    with ZipFile(literal_copy) as package:
        xml = ET.fromstring(package.read("word/document.xml"))
        w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs = xml.find(w + "body").findall(w + "p")
        api.check("literal list and rule markers remain paragraphs", ["".join(p.itertext()) for p in paragraphs] == ["---", "- literal marker", "+ literal plus"] and xml.find(".//" + w + "numPr") is None and xml.find(".//" + w + "br") is None)
    api.check("literal header punctuation survives extraction", "header: Confidential * copy" in api.result(["inspect", literal_copy, "--markdown"])["result"]["markdown"])
    overflow = '# Too much\n\n' + 'word ' * 1000
    error = api.result(["pptx", "--lmcode", api.chunk(temp, "markdown-overflow", f'pptx.create({api.literal(deck)}).markdown({json.dumps(overflow)});')], 3)
    api.check("slide overflow is explicit with Markdown line", "Markdown line 3:" in error["message"] and "overflows" in error["message"], error)
