#!/usr/bin/env python3
"""Round-three XLSX checks; called by tests/integration.py's API harness."""
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET

def run(api, temp, outputs=None):
    temp = Path(temp)
    out = temp / "xlsx-round3.xlsx"
    image = temp / "xlsx-round3.png"
    source = api.chunk(temp, "xlsx-round3", f'''let image_path = {api.literal(image)};
 xlsx.sample_image(image_path);
let d = xlsx.create({api.literal(out)});
let s = d.sheet("Scores");
s.set(1,1,"Score").set(2,1,92).set(3,1,67).set(2,2,"Alpha").set(3,2,"Beta");
s.bar_chart(5,1,15,6,"Scores","B2:B3","A2:A3");
s.conditional_icon_set(2,1,3,1,"3TrafficLights1");
d.image(image_path,1,3,64,64); d.save();''')
    result = api.result(["xlsx", "--lmcode", source])
    api.check("round3 XLSX run succeeds", result.get("ok"), result)
    with zipfile.ZipFile(out) as package:
        names = set(package.namelist())
        drawing_names = [n for n in names if n.endswith(".xml") and ET.fromstring(package.read(n)).tag == "{http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing}wsDr"]
        api.check("worksheet drawing exists", bool(drawing_names))
        drawing_bytes = package.read(drawing_names[0])
        drawing = ET.fromstring(drawing_bytes)
        ns = {"xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"}
        api.check("one-cell image anchor", drawing.find("xdr:oneCellAnchor", ns) is not None and drawing.find(".//xdr:pic", ns) is not None)
        api.check("worksheet image part", any(n.endswith(".png") for n in names))
        sheet = package.read("xl/worksheets/sheet1.xml").decode("utf-8")
        api.check("icon-set conditional formatting", "iconSet" in sheet and "3TrafficLights1" in sheet)
        api.check("drawing relationship", "drawing" in sheet)
    inspected = api.result(["inspect", out])
    api.check("round3 OpenXmlValidator", inspected.get("ok") and inspected.get("result", {}).get("valid"), inspected)
    try:
        import openpyxl
    except ImportError:
        print("SKIP independent XLSX image reader")
    else:
        book = openpyxl.load_workbook(out)
        sheet = book["Scores"]
        api.check("openpyxl image and chart coexist", len(sheet._images) == 1 and len(sheet._charts) == 1)
        api.check("openpyxl image cell and dimensions", sheet._images[0].anchor._from.col == 2 and sheet._images[0].anchor.ext.cx == 64 * 9525)
        api.check("openpyxl native icons", next(iter(sheet.conditional_formatting._cf_rules.values()))[0].iconSet.iconSet == "3TrafficLights1")
    bad = api.chunk(temp, "xlsx-round3-bad", f'''let d = xlsx.create({api.literal(temp / "bad.xlsx")});
let s = d.sheet("Bad"); s.image({api.literal(image)},1,1,0,20);''')
    failure = api.result(["xlsx", "--lmcode", bad], 3)
    api.check("rejects zero image width", failure.get("code") == "RUN_HOST" and "dimension" in failure.get("message", "").lower(), failure)
    invalid = api.chunk(temp, "xlsx-round3-icon-bad", f'''let d = xlsx.create({api.literal(temp / "bad-icon.xlsx")});
let s = d.sheet("Bad"); s.conditional_icon_set(1,1,2,1,"not-an-icon");''')
    failure = api.result(["xlsx", "--lmcode", invalid], 3)
    api.check("rejects unknown icon set", failure.get("code") == "RUN_HOST" and "icon set" in failure.get("message", "").lower(), failure)
    bad_cell = api.chunk(temp, "xlsx-round3-row-bad", f'''let d = xlsx.create({api.literal(temp / "bad-row.xlsx")});
let s = d.sheet("Bad"); s.image({api.literal(image)},0,1,20,20);''')
    failure = api.result(["xlsx", "--lmcode", bad_cell], 3)
    api.check("rejects zero image row", failure.get("code") == "RUN_HOST" and "row" in failure.get("message", "").lower(), failure)
    return 9

if __name__ == "__main__":
    raise SystemExit("This module is called by tests/integration.py")
