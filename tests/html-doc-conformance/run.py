#!/usr/bin/env python3
"""Verify the pinned HTML document corpus and characterize released host behavior."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parent
HTML_NS = "http://www.w3.org/1999/xhtml"
CSS_NS = "urn:lmctl:css:1"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
PROFILE_ELEMENTS = {
    "article", "div", "h1", "h2", "h3", "p", "span", "strong", "em",
    "br", "ul", "ol", "li", "table", "tr", "th", "td", "img", "a",
}
BLOCKS = {"article", "div", "h1", "h2", "h3", "p", "ul", "ol", "table", "img"}
INLINE = {"span", "strong", "em", "br", "a"}
CSS_PROPERTIES = {
    "font-family", "font-size", "font-weight", "font-style", "color",
    "text-align", "margin-top", "margin-bottom", "page-break-before",
    "page-break-after",
}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
ASCII_WS = re.compile(r"[\t\r\n ]+")
BR_MARK = "\ufdd0"
FIELD = "$" + "{"
INSTALLS = {
    "lmpdf": "github:lmctl-ai/lmpdf@v0.2.6",
    "lmoffice": "github:lmctl-ai/lmoffice@v0.1.31",
}
RELEASES = {"lmpdf": "0.2.6", "lmoffice": "0.1.31"}
ARTIFACTS = {"lmpdf": "pdf", "lmoffice": "docx"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def inline_text(node: ET.Element) -> str:
    parts = [node.text or ""]
    for child in node:
        parts.append(BR_MARK if local(child.tag) == "br" else inline_text(child))
        parts.append(child.tail or "")
    value = ASCII_WS.sub(" ", "".join(parts))
    return re.sub(r" *" + BR_MARK + r" *", "\n", value).strip(" ")


def parse_css(text: str) -> tuple[list[dict], dict]:
    root = ET.fromstring(text)
    require(root.tag == f"{{{CSS_NS}}}style", "CSS root namespace/name mismatch")
    require(root.tag == f"{{{CSS_NS}}}style", "CSS root must be css-doc style")
    rules: list[dict] = []
    page: dict = {}
    for rule in root:
        require(rule.tag == f"{{{CSS_NS}}}rule", "CSS style children must be rule")
        selector = rule.get("select")
        require(selector is not None, "CSS rule requires select")
        sets = []
        names: set[str] = set()
        for item in rule:
            require(item.tag == f"{{{CSS_NS}}}set", "CSS rule children must be set")
            name, value = item.get("name"), item.get("value")
            require(name is not None and value is not None, "CSS set requires name/value")
            require(name not in names, f"duplicate property {name} in {selector}")
            names.add(name)
            sets.append({"name": name, "value": value})
        if selector == "@page":
            for item in sets:
                require(item["name"] not in page, f"duplicate @page property {item['name']}")
                page[item["name"]] = item["value"]
            rules.append({"select": selector, "sets": sets})
        else:
            rules.append({"select": selector, "sets": sets})
    return rules, page


def css_trace(text: str) -> list[dict]:
    root=ET.fromstring(text)
    return [{"select":rule.get("select"),
             "sets":[{"name":item.get("name"),"value":item.get("value")} for item in rule]}
            for rule in root]


def validate_length(value: str, positive: bool = False, font: bool = False) -> str:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(pt|mm)", value)
    require(match is not None, f"length must be decimal pt/mm: {value}")
    number = Decimal(match.group(1))
    if match.group(2) == "mm":
        number = number * Decimal(72) / Decimal("25.4")
    quantum = Decimal("0.5") if font else Decimal("0.05")
    normalized = (number / quantum).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * quantum
    require(not positive or normalized > 0, f"positive length rounds to zero: {value}")
    return f"{normalized.normalize()}pt" if normalized != normalized.to_integral() else f"{normalized:.0f}pt"


def validate_css(rules: list[dict], page: dict) -> None:
    for selector, values in [("@page", page)] + [(r["select"], {s["name"]: s["value"] for s in r["sets"]}) for r in rules]:
        if selector != "@page":
            token = selector[1:] if selector.startswith((".", "#")) else selector
            require(selector == "*" or IDENT.fullmatch(token) is not None, f"unsupported selector: {selector}")
            if selector not in {"*"} and not selector.startswith((".", "#")):
                require(selector in PROFILE_ELEMENTS, f"selector names unsupported element: {selector}")
        for name, value in values.items():
            allowed = CSS_PROPERTIES | ({"size", "margin-right", "margin-left"} if selector == "@page" else set())
            require(name in allowed, f"unsupported CSS property: {name}")
            if name in {"font-size", "margin-top", "margin-bottom", "margin-right", "margin-left"}:
                validate_length(value, positive=name == "font-size", font=name == "font-size")
            elif name == "font-family":
                require(value in {"Arial", "Calibri", "Times New Roman", "Courier New"}, f"unsupported font: {value}")
            elif name == "font-weight":
                require(value in {"normal", "bold"}, f"unsupported font-weight: {value}")
            elif name == "font-style":
                require(value in {"normal", "italic"}, f"unsupported font-style: {value}")
            elif name == "color":
                require(re.fullmatch(r"#[0-9A-Fa-f]{6}", value) is not None, f"invalid color: {value}")
            elif name == "text-align":
                require(value in {"left", "center", "right"}, f"unsupported text-align: {value}")
            elif name in {"page-break-before", "page-break-after"}:
                require(value in {"auto", "always"}, f"unsupported page-break value: {value}")
            elif name == "size":
                require(value in {"letter", "a4", "Letter", "A4"}, f"unsupported page size: {value}")


def validate_html(root: ET.Element, case_id: str, assets: dict[str, str]) -> None:
    require(root.tag in {f"{{{HTML_NS}}}article", f"{{{HTML_NS}}}div"}, f"{case_id}: root must be XHTML article/div")
    ids: set[str] = set()

    def check(node: ET.Element) -> None:
        name = local(node.tag)
        require(node.tag.startswith("{" + HTML_NS + "}"), f"{case_id}: wrong namespace on {name}")
        require(name in PROFILE_ELEMENTS, f"{case_id}: unsupported element <{name}>")
        attrs = {local(k): v for k, v in node.attrib.items()}
        allowed = {"id", "class"}
        if name == "img":
            allowed |= {"src", "alt", "width", "height"}
        if name == "a":
            allowed.add("href")
        require(set(attrs) <= allowed, f"{case_id}: unsupported attributes on <{name}>")
        if "id" in attrs:
            require(IDENT.fullmatch(attrs["id"]) is not None and attrs["id"] not in ids, f"{case_id}: invalid/duplicate id")
            ids.add(attrs["id"])
        require(all(IDENT.fullmatch(value) is not None for value in attrs.get("class", "").split()), f"{case_id}: invalid class")
        if name == "img":
            src = attrs.get("src", "")
            require(src and not Path(src).is_absolute() and ".." not in Path(src).parts, f"{case_id}: image src must be relative")
            require((ROOT/src).resolve().is_relative_to(ROOT.resolve()),f"{case_id}: image path escapes corpus root")
            require(all(key in attrs for key in ("alt", "width", "height")), f"{case_id}: image requires alt/width/height")
            validate_length(attrs["width"], positive=True)
            validate_length(attrs["height"], positive=True)
            require(src in assets, f"{case_id}: image asset is not pinned")
        if name == "a":
            href = attrs.get("href", "")
            url = urlsplit(href)
            require(url.scheme in {"http", "https", "mailto"} and not url.username and not url.password and not any(c.isspace() for c in href), f"{case_id}: unsafe href")
        if name == "br":
            require(not list(node) and not (node.text or ""), f"{case_id}: br must be empty")
        if name in {"article", "div", "ul", "ol", "table", "tr"}:
            require(not (node.text or "").strip(), f"{case_id}: direct text is not allowed in <{name}>")
        children = [local(c.tag) for c in node]
        if name in {"article", "div"}:
            allowed_children = BLOCKS
        elif name in {"h1", "h2", "h3", "p", "li", "th", "td", "span", "strong", "em", "a"}:
            allowed_children = INLINE
            if name == "a":
                allowed_children = {"span","strong","em","br"}
        elif name in {"ul", "ol"}:
            allowed_children = {"li"}
            require(bool(children), f"{case_id}: list is empty")
        elif name == "table":
            allowed_children = {"tr"}
            rows = list(node)
            widths = [len(list(row)) for row in rows]
            require(bool(rows) and widths[0] > 0 and len(set(widths)) == 1, f"{case_id}: table grid is ragged/empty")
            header_rows = [i for i, row in enumerate(rows) if list(row) and all(local(c.tag) == "th" for c in row)]
            has_headers = [i for i, row in enumerate(rows) if any(local(c.tag) == "th" for c in row)]
            require(not has_headers or header_rows == [0], f"{case_id}: th must form the first all-th row")
        elif name == "tr":
            allowed_children = {"th", "td"}
            require(bool(children), f"{case_id}: empty table row")
        else:
            allowed_children = set()
        for child in node:
            require(local(child.tag) in allowed_children, f"{case_id}: <{local(child.tag)}> not allowed in <{name}>")
            check(child)

    check(root)


def matches(selector: str, node: ET.Element) -> bool:
    name = local(node.tag)
    if selector == "*":
        return True
    if selector.startswith("#"):
        return node.get("id") == selector[1:]
    if selector.startswith("."):
        return selector[1:] in node.get("class", "").split()
    return name == selector


def computed_style(node: ET.Element, parent: dict, rules: list[dict], defaults: dict) -> dict:
    style = {k: parent[k] for k in ("font-family", "font-size", "font-weight", "font-style", "color", "text-align") if k in parent}
    if not parent:
        style.update(defaults.get("*", {}))
    style.update(defaults.get(local(node.tag), {}))
    applicable = []
    for order, rule in enumerate(rules):
        selector = rule["select"]
        if selector != "@page" and matches(selector, node):
            specificity = 0 if selector == "*" else 3 if selector.startswith("#") else 2 if selector.startswith(".") else 1
            applicable.append((specificity, order, rule))
    for _, _, rule in sorted(applicable):
        for item in rule["sets"]:
            name, value = item["name"], item["value"]
            if name in {"font-size", "margin-top", "margin-bottom"}:
                style[name] = validate_length(value, positive=name == "font-size", font=name == "font-size")
            else:
                style[name] = value
    return style


def source_trace(xml_text: str, css_text: str, expected: dict, manifest: dict) -> dict:
    root = ET.fromstring(xml_text)
    rules, page = parse_css(css_text)
    validate_css(rules, page)
    validate_html(root, expected.get("case_id", "case"), {a["path"]:a["sha256"] for a in manifest["assets"]})
    blocks = [local(child.tag) for child in root]
    headings, lists, tables, images, links, reading = [], [], [], [], [], []
    for node in root:
        name = local(node.tag)
        if name in {"h1", "h2", "h3"}:
            headings.append({"level": int(name[1]), "text": inline_text(node)})
            reading.append(inline_text(node))
        elif name == "p":
            reading.append(inline_text(node))
        elif name in {"ul", "ol"}:
            items = [inline_text(item) for item in node]
            lists.append({"kind": name, "items": items, **({"starts_at": 1} if name == "ol" else {})})
            reading.extend(items)
        elif name == "table":
            rows = [[inline_text(cell) for cell in row] for row in node]
            header_rows = [i for i, row in enumerate(node) if list(row) and all(local(c.tag) == "th" for c in row)]
            alignments = [[computed_style(cell, {}, rules, manifest["default_styles"]).get("text-align", "left") for cell in row] for row in node]
            table = {"rows": len(rows), "columns": len(rows[0]) if rows else 0, "header_rows": header_rows,
                     "repeat_header": bool(header_rows), "cells": rows}
            if any(v != "left" for row in alignments for v in row):
                table["cell_alignments"] = alignments
            if len(rows) > 5:
                table.pop("cells")
                table["first_row"] = rows[0]
                table["last_row"] = rows[-1]
                table["cell_text_sha256"] = hashlib.sha256("\n".join("|".join(row) for row in rows).encode()).hexdigest()
            tables.append(table)
            reading.extend(cell for row in rows for cell in row)
    for node in root.iter():
        if local(node.tag) == "img":
            images.append({k:node.get(k) for k in ("src","alt","width","height")})
        if local(node.tag) == "a":
            links.append({"href":node.get("href"),"text":inline_text(node)})
    styles = {}
    tag_counts = {}
    def walk(node, parent_style):
        name=local(node.tag)
        ident=node.get("id"); classes=node.get("class","").split()
        tag_counts[name]=tag_counts.get(name,0)+1
        key=f"{name}#{ident}" if ident else f"{name}.{classes[0]}" if classes else f"{name}[{tag_counts[name]-1}]"
        style=computed_style(node,parent_style,rules,manifest["default_styles"])
        if key in expected.get("computed_styles",{}):
            styles[key]={k:style.get(k) for k in expected["computed_styles"][key]}
        for child in node: walk(child,style)
    walk(root,{})
    if page: styles["@page"]=page
    empty=sum(1 for node in root.iter() if local(node.tag)=="p" and inline_text(node)=="")
    return {"root":local(root.tag),"blocks":blocks,"headings":headings,"lists":lists,"tables":tables,
            "images":images,"links":links,"empty_paragraphs":empty,"normalized_text_blocks":reading,
            "normalized_text_sha256":hashlib.sha256("\n".join(reading).encode()).hexdigest(),
            "author_stylesheet":css_trace(css_text),"computed_styles":styles,"page_style":page}


def assert_subset(expected, actual, label):
    if isinstance(expected, dict):
        require(isinstance(actual, dict), f"{label}: expected object")
        for key, value in expected.items():
            require(key in actual, f"{label}: missing {key}")
            assert_subset(value, actual[key], f"{label}.{key}")
    elif isinstance(expected, list):
        require(isinstance(actual, list) and len(expected)==len(actual), f"{label}: list length")
        for i,(a,b) in enumerate(zip(expected,actual)):
            assert_subset(a,b,f"{label}[{i}]")
    else:
        require(expected==actual,f"{label}: expected {expected!r}, got {actual!r}")


def safe_env(evidence: Path, compiler: Path, private_bin: Path) -> dict:
    env = {k: os.environ[k] for k in ("LANG", "LC_ALL", "DOTNET_ROOT", "PYTHONUTF8") if k in os.environ}
    node = shutil.which("node")
    paths = [str(private_bin), str(compiler.parent), "/usr/bin", "/bin"]
    if node:
        paths.insert(2, str(Path(node).parent))
    env["PATH"] = os.pathsep.join(dict.fromkeys(paths))
    env["HOME"] = str(evidence / "private-home")
    env["XDG_CACHE_HOME"] = str(evidence / "xdg-cache")
    env["LMSCRIPT_TOOL_CACHE"] = str(evidence / "lmscript-tools")
    return env


def run_source(compiler, source, path, env, dry):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(source,encoding="utf-8")
    cmd=[str(compiler)]
    if dry: cmd += ["--dry-run","--plan-format","json"]
    cmd += [str(path)]
    if os.name=="nt" and str(compiler).lower().endswith((".cmd",".bat")):
        import subprocess as sp
        cmd=["cmd.exe","/d","/s","/c",sp.list2cmdline(cmd)]
    return subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)


def host_source(host, xml, css, output):
    return (
        "xml = " + json.dumps(xml, ensure_ascii=False) + ";\n"
        "css = " + json.dumps(css, ensure_ascii=False) + ";\n"
        f'p = _lmcode_ cli={json.dumps(host+" docx")} install={json.dumps(INSTALLS[host])};\n'
        f'let d = docx.create({json.dumps(str(output))});\n'
        f'd.html_xml({FIELD}xml}}, {FIELD}css}});\n'
        "d.save();\nend _lmcode_\nr=run_lmcode(p);\nprintln(json_stringify(r));\n"
    )


def parse_real_result(proc):
    for line in reversed(proc.stdout.splitlines()):
        try:
            value=json.loads(line)
            if isinstance(value,dict) and "ok" in value:
                return value
        except json.JSONDecodeError:
            continue
    return None


def parse_dry_plan(proc):
    try:
        plan=json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"dry run emitted no JSON plan: {proc.stdout}{proc.stderr}") from exc
    entry=next((e for e in plan.get("entries",[]) if e.get("kind")=="lmcode-host-dry"),None)
    require(entry is not None,f"no host dry entry in plan: {plan}")
    return plan,entry["envelope"]


def source_for(host, xml, css, output):
    xfield, cfield = FIELD+"xml}", FIELD+"css}"
    return (
        "xml = " + json.dumps(xml,ensure_ascii=False) + ";\n"
        "css = " + json.dumps(css,ensure_ascii=False) + ";\n"
        f'p = _lmcode_ cli={json.dumps(host+" docx")} install={json.dumps(INSTALLS[host])};\n'
        f'let d = docx.create({json.dumps(str(output))});\n'
        f'd.html_xml({xfield}, {cfield});\n'
        'd.save();\nend _lmcode_\nr=run_lmcode(p);\nprintln(json_stringify(r));\n'
    )


def parse_real_result(proc):
    for line in reversed(proc.stdout.splitlines()):
        try:
            value=json.loads(line)
            if isinstance(value,dict) and "ok" in value:
                return value
        except json.JSONDecodeError:
            pass
    return None


def parse_dry_plan(proc):
    try:
        plan=json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"dry run emitted no JSON plan: {proc.stdout}{proc.stderr}") from exc
    entry=next((e for e in plan.get("entries",[]) if e.get("kind")=="lmcode-host-dry"),None)
    require(entry is not None,f"no host dry entry in plan: {plan}")
    return plan,entry["envelope"]


def inspect_pdf(path, binary):
    info=subprocess.run(["pdfinfo",str(path)],text=True,capture_output=True)
    require(info.returncode==0,info.stderr)
    pages=int(re.search(r"^Pages:\s+(\d+)",info.stdout,re.M).group(1))
    size=re.search(r"^Page size:\s+(.+)$",info.stdout,re.M).group(1).strip()
    textproc=subprocess.run(["pdftotext","-layout",str(path),"-"],text=True,capture_output=True)
    require(textproc.returncode==0,textproc.stderr)
    fontproc=subprocess.run(["pdffonts",str(path)],text=True,capture_output=True)
    require(fontproc.returncode==0,fontproc.stderr)
    fonts=[line.split()[0] for line in fontproc.stdout.splitlines()[2:] if line.split()]
    bbox=subprocess.run(["pdftotext","-bbox",str(path),"-"],text=True,capture_output=True)
    require(bbox.returncode==0,bbox.stderr)
    tree=ET.fromstring(bbox.stdout); bounds=[]; pdf_pages=[x for x in tree.iter() if local(x.tag)=="page"]
    for number,page in enumerate(pdf_pages,1):
        w,h=float(page.get("width")),float(page.get("height"))
        for word in page.iter():
            if local(word.tag)=="word":
                box=[float(word.get(k)) for k in ("xMin","yMin","xMax","yMax")]
                require(0<=box[0]<=box[2]<=w+0.1 and 0<=box[1]<=box[3]<=h+0.1,f"PDF word outside page: {box}")
                bounds.append({"text":word.text or "","page":number,"box":[round(x,2) for x in box]})
    native=subprocess.run([str(binary),"inspect",str(path)],text=True,capture_output=True)
    require(native.returncode==0,native.stdout+native.stderr)
    info_json=json.loads(native.stdout).get("result",{})
    images=subprocess.run(["pdfimages","-list",str(path)],text=True,capture_output=True)
    require(images.returncode==0,images.stderr)
    return {"pages":pages,"page_size":size,"text":textproc.stdout,"fonts":fonts,"word_bounds":bounds,
            "links":info_json.get("links"),"images":info_json.get("images"),"tables":info_json.get("tables"),
            "headings":info_json.get("headings"),"pdfimages_list":images.stdout}


def inspect_docx(path):
    w="{"+W_NS+"}"
    with zipfile.ZipFile(path) as z:
        require(z.testzip() is None,"invalid DOCX ZIP")
        parts={n:ET.fromstring(z.read(n)) for n in z.namelist() if n.endswith(".xml") or n.endswith(".rels")}
        doc=parts["word/document.xml"];body=doc.find(".//"+w+"body")
        paragraphs=[];tables=[];blocks=[]
        for child in list(body):
            if local(child.tag)=="p":
                text="".join(x.text or "" for x in child.iter(w+"t"))
                ppr=child.find(w+"pPr");pstyle=None if ppr is None or ppr.find(w+"pStyle") is None else ppr.find(w+"pStyle").get(w+"val")
                runs=[]
                for run in child.findall(w+"r"):
                    rpr=run.find(w+"rPr")
                    fonts=None if rpr is None or rpr.find(w+"rFonts") is None else dict(rpr.find(w+"rFonts").attrib)
                    runs.append({"text":"".join(x.text or "" for x in run.iter(w+"t")),
                                 "bold":rpr is not None and rpr.find(w+"b") is not None,
                                 "italic":rpr is not None and rpr.find(w+"i") is not None,
                                 "color":None if rpr is None or rpr.find(w+"color") is None else rpr.find(w+"color").get(w+"val"),
                                 "size":None if rpr is None or rpr.find(w+"sz") is None else rpr.find(w+"sz").get(w+"val"),
                                 "fonts":fonts})
                numpr=None if ppr is None else ppr.find(w+"numPr")
                num_id=None if numpr is None or numpr.find(w+"numId") is None else numpr.find(w+"numId").get(w+"val")
                paragraphs.append({"text":text,"style":pstyle,"num_id":num_id,"runs":runs});blocks.append({"type":"p","text":text})
            elif local(child.tag)=="tbl":
                rows=[];header=0
                for tr in child.findall(w+"tr"):
                    if tr.find(w+"trPr") is not None and tr.find(w+"trPr").find(w+"tblHeader") is not None: header+=1
                    row=[]
                    for tc in tr.findall(w+"tc"):
                        cell_paragraphs=tc.findall(w+"p")
                        alignments=[]
                        for pnode in cell_paragraphs:
                            jc=pnode.find(w+"pPr/"+w+"jc")
                            alignments.append(None if jc is None else jc.get(w+"val"))
                        row.append({"text":"".join(x.text or "" for x in tc.iter(w+"t")),"alignments":alignments})
                    rows.append(row)
                tables.append({"rows":len(rows),"columns":len(rows[0]) if rows else 0,"cells":rows,"repeat_header_rows":header})
                blocks.append({"type":"table","rows":rows})
        sect=body.find(w+"sectPr")
        size=None if sect is None or sect.find(w+"pgSz") is None else dict(sect.find(w+"pgSz").attrib)
        margins=None if sect is None or sect.find(w+"pgMar") is None else dict(sect.find(w+"pgMar").attrib)
        list_style_num_ids={}
        styles=parts.get("word/styles.xml")
        if styles is not None:
            for style in styles.iter(w+"style"):
                style_id=style.get(w+"styleId")
                num_id=style.find(w+"pPr/"+w+"numPr/"+w+"numId")
                if style_id and num_id is not None:
                    list_style_num_ids[style_id]=num_id.get(w+"val")
        rels=parts.get("word/_rels/document.xml.rels");links=[];images=[]
        if rels is not None:
            for relation in rels:
                kind=relation.get("Type","")
                if kind.endswith("/hyperlink"): links.append(relation.get("Target"))
                if kind.endswith("/image"): images.append(relation.get("Target"))
        media=[n for n in z.namelist() if n.startswith("word/media/")]
    list_ids=[]
    for para in paragraphs:
        if para.get("style") in {"ListNumber","ListBullet"}:
            list_ids.append({"style":para["style"],"num_id":para.get("num_id")})
    return {"paragraphs":paragraphs,"tables":tables,"blocks":blocks,"list_paragraphs":list_ids,"page_size":size,"margins":margins,
            "list_style_num_ids":list_style_num_ids,"links":links,"image_relationships":images,"media":media}


def assert_release_red_controls(observations: list[dict], identity_text: str) -> list[dict]:
    by={(item["host"],item["case"]):item for item in observations}
    red=[]
    letter_pdf=by[("lmpdf","letter")]
    letter_docx=by[("lmoffice","letter")]
    require(letter_pdf["real_ok"] and letter_docx["real_ok"],"letter should render in both released hosts")
    require("Inc.across" in letter_pdf["metrics"]["text"],"PDF boundary-space loss baseline changed")
    docx_letter=" ".join(p["text"] for p in letter_docx["metrics"]["paragraphs"])
    require("Northwind Logistics, Inc. across the 2026 shipping cycle" in docx_letter,"DOCX letter text baseline changed")
    red.append({"id":"lost-run-boundary-space","host":"lmpdf","case":"letter","observed":"Inc.across"})

    report=by[("lmpdf","report-with-table-image")]
    require(not report["dry_ok"] and not report["real_ok"] and not report["output_exists"],"released PDF image rejection changed")
    require("unsupported element <img>" in report["dry_envelope"].get("message",""),"PDF image diagnostic changed")
    report_docx=by[("lmoffice","report-with-table-image")]
    require(not report_docx["dry_ok"] and not report_docx["real_ok"] and not report_docx["output_exists"],"released DOCX image rejection changed")
    require("unsupported element <img>" in report_docx["dry_envelope"].get("message",""),"DOCX image diagnostic changed")
    red.append({"id":"img-rejected","hosts":["lmpdf","lmoffice"],"case":"report-with-table-image"})
    for host in ("lmpdf","lmoffice"):
        link=by[(host,"link")]
        require(not link["dry_ok"] and not link["real_ok"] and not link["output_exists"],f"{host} hyperlink rejection changed")
        require("unsupported element <a>" in link["dry_envelope"].get("message",""),f"{host} hyperlink diagnostic changed")
    red.append({"id":"hyperlink-rejected","hosts":["lmpdf","lmoffice"],"case":"link"})

    ws_pdf=by[("lmpdf","whitespace-run-boundary")]["metrics"]["text"]
    ws_docx=" ".join(p["text"] for p in by[("lmoffice","whitespace-run-boundary")]["metrics"]["paragraphs"])
    require("boldand" in ws_pdf,"PDF run-boundary whitespace baseline changed")
    require("bold and" in ws_docx,"DOCX whitespace baseline changed")
    red.append({"id":"run-boundary-whitespace","lmpdf":"boundary space lost","lmoffice":"space preserved"})

    lists_pdf=by[("lmpdf","independent-list-restart")]["metrics"]["text"]
    lists_docx=by[("lmoffice","independent-list-restart")]["metrics"]
    require(lists_pdf.count("1.")==2,"PDF independent ordered-list restart baseline changed")
    require(len(lists_docx["list_paragraphs"])==4 and
            {lists_docx["list_style_num_ids"].get(p["style"]) for p in lists_docx["list_paragraphs"]}=={"2"},
            "DOCX shared numbering-instance baseline changed")
    red.append({"id":"independent-list-restart","lmpdf":"restarts at one","lmoffice":"both lists use numbering instance 2"})

    long_pdf=by[("lmpdf","long-table")]["metrics"]
    long_docx=by[("lmoffice","long-table")]["metrics"]
    require(long_pdf["pages"]>=2,"long PDF table should paginate")
    require(long_docx["tables"][0]["rows"]==101,"long DOCX table row count changed")
    require(long_docx["tables"][0]["repeat_header_rows"]==0,"missing DOCX table-header marker baseline changed")
    red.append({"id":"missing-header-repeat-marker","host":"lmoffice","case":"long-table","tblHeader":0})

    align_pdf=by[("lmpdf","column-alignment")]
    align_docx=by[("lmoffice","column-alignment")]
    require(not align_pdf["dry_ok"] and "text-align must be consistent" in align_pdf["dry_envelope"].get("message",""),"PDF mixed column alignment baseline changed")
    require(align_docx["dry_ok"] and align_docx["real_ok"],"DOCX per-cell alignment baseline changed")
    red.append({"id":"column-alignment-asymmetry","lmpdf":"mixed column alignment refused","lmoffice":"accepted per-cell alignment"})

    page_box=by[("lmpdf","page-box")]
    page_break=by[("lmpdf","page-break")]
    require(not page_box["dry_ok"] and "selector" in page_box["dry_envelope"].get("message",""),"PDF @page support baseline changed")
    require(not page_break["dry_ok"] and "page-break-before" in page_break["dry_envelope"].get("message",""),"PDF page-break support baseline changed")
    require(not by[("lmoffice","page-box")]["dry_ok"] and not by[("lmoffice","page-break")]["dry_ok"],"DOCX page CSS baseline changed")
    red.append({"id":"page-css-not-supported","cases":["page-box","page-break"]})

    require('unknown XML profile "html-doc@2"' in identity_text,"profile identity rejection changed")
    red.append({"id":"unmatched-profile-identity","profile":"html-doc@2","static-check":"unknown profile"})
    return red


def host_diagnostic(message: str | None) -> str | None:
    if not message:
        return None
    match=re.search(r"(html-subset|css-subset) line \d+ column \d+:.*",message)
    return match.group(0) if match else message


def baseline_view(compiler_name: str, hosts_version: dict, hosts: dict, frozen: dict,
                  identity_run, identity_expect: str, observations: list[dict]) -> dict:
    cases=[]
    for item in observations:
        metrics=item["metrics"]
        if item["host"]=="lmpdf" and metrics:
            words=metrics["word_bounds"]
            output={"pages":metrics["pages"],"page_size":metrics["page_size"],"text":metrics["text"],
                    "fonts":[re.sub(r"^[A-Z]{6}\+","",name) for name in metrics["fonts"]],
                    "word_count":len(words),"links":metrics["links"],"images":metrics["images"],
                    "tables":metrics["tables"],"headings":metrics["headings"],
                    "bounds":{"min_x":min((w["box"][0] for w in words),default=None),
                              "min_y":min((w["box"][1] for w in words),default=None),
                              "max_x":max((w["box"][2] for w in words),default=None),
                              "max_y":max((w["box"][3] for w in words),default=None)}}
        elif metrics:
            table_summary=[]
            for table in metrics["tables"]:
                cells=[[cell["text"] for cell in row] for row in table["cells"]]
                table_summary.append({"rows":table["rows"],"columns":table["columns"],
                                      "repeat_header_rows":table["repeat_header_rows"],
                                      "first_row":cells[0] if cells else [],
                                      "last_row":cells[-1] if cells else [],
                                      "cell_text_sha256":hashlib.sha256("\n".join("|".join(row) for row in cells).encode()).hexdigest()})
            output={"paragraphs":[{"text":p["text"],"style":p["style"],"num_id":p["num_id"],"runs":p["runs"]} for p in metrics["paragraphs"]],
                    "tables":table_summary,"page_size":metrics["page_size"],"margins":metrics["margins"],
                    "links":metrics["links"],"image_relationships":metrics["image_relationships"],
                    "media":metrics["media"],"list_paragraphs":metrics["list_paragraphs"],
                    "list_style_num_ids":metrics["list_style_num_ids"]}
        else:
            output=None
        result=item["real_result"] or {}
        cases.append({"host":item["host"],"case":item["case"],"dry_ok":item["dry_ok"],
                      "dry_message":host_diagnostic(item["dry_envelope"].get("message")),
                      "dry_code":item["dry_envelope"].get("code"),"dry_phase":item["dry_envelope"].get("phase"),
                      "real_ok":item["real_ok"],"real_message":host_diagnostic(result.get("message")),
                      "real_code":result.get("code"),"output_exists":item["output_exists"],
                      "dry_output_unchanged":item["dry_output_unchanged"],"output":output})
    return {"format":"html-doc-release-baseline/1","platform":"linux-x86_64",
            "corpus_sha256":sha256((ROOT/"corpus.json").read_bytes()),"compiler":compiler_name,
            "host_versions":hosts_version,"host_sha256":{n:sha256(p.read_bytes()) for n,p in hosts.items()},
            "frozen_profile_sha256":frozen,
            "profile_identity":{"exit":identity_run.returncode,"diagnostic":identity_expect,"line":2,"column":1},
            "cases":cases}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--compiler",required=True)
    parser.add_argument("--lmpdf",required=True)
    parser.add_argument("--lmoffice",required=True)
    parser.add_argument("--mono-root",required=True)
    parser.add_argument("--mono-source",required=True)
    parser.add_argument("--evidence",required=True)
    parser.add_argument("--record",action="store_true",help="record release behavior to evidence only")
    args=parser.parse_args()
    compiler=Path(args.compiler).resolve();hosts={"lmpdf":Path(args.lmpdf).resolve(),"lmoffice":Path(args.lmoffice).resolve()}
    mono_root=Path(args.mono_root).resolve();evidence=Path(args.evidence).resolve();evidence.mkdir(parents=True,exist_ok=True)
    # The binaries were installed by the release resolver into an owned tool cache.
    private_bin=evidence/"private-bin";private_bin.mkdir(exist_ok=True)
    for name,binary in hosts.items():
        link=private_bin/name
        if not link.exists(): os.link(binary,link)
        require(sha256(link.read_bytes())==sha256(binary.read_bytes()),f"private binary link mismatch: {name}")
    env=safe_env(evidence,compiler,private_bin)
    manifest=json.loads((ROOT/"corpus.json").read_text(encoding="utf-8"))
    require(manifest["profiles"]=={"html":"html-doc@1","css":"css-doc@1"},"profile identity mismatch")
    for asset in manifest["assets"]:
        asset_path=ROOT/asset["path"]
        require(asset_path.is_file() and sha256(asset_path.read_bytes())==asset["sha256"],f"asset digest mismatch: {asset['path']}")
    frozen=manifest["frozen_legacy_profiles"]
    for name,digest in frozen.items():
        require(sha256((mono_root/"lmscript/data-profiles"/name).read_bytes())==digest,f"legacy profile changed: {name}")
    lock=(mono_root/"lmscript/data-profiles/profiles.lock.json").read_text(encoding="utf-8")
    require("html-doc@1" not in lock and "css-doc@1" not in lock,"corpus pre-adapter release baseline should not yet include proposed profile identities")
    traces={}
    for case in manifest["cases"]:
        if case["kind"]=="dry-negative":
            continue
        xml=(ROOT/case["xml"]).read_text(encoding="utf-8");css=(ROOT/case["css"]).read_text(encoding="utf-8")
        validate_html(ET.fromstring(xml),case["id"],{a["path"]:a["sha256"] for a in manifest["assets"]})
        trace=source_trace(xml,css,case["expected"],manifest)
        assert_subset(case["expected"],trace,f"{case['id']} pinned source trace")
        traces[case["id"]]=trace
    compiler_name=subprocess.run([str(compiler),"--version"],env=env,cwd=ROOT,text=True,capture_output=True).stdout.strip()
    hosts_version={name:subprocess.run([str(binary),"--version"],env=env,cwd=ROOT,text=True,capture_output=True).stdout.strip() for name,binary in hosts.items()}
    require(hosts_version["lmpdf"]=="lmpdf "+RELEASES["lmpdf"],hosts_version["lmpdf"])
    require(hosts_version["lmoffice"]=="lmoffice "+RELEASES["lmoffice"],hosts_version["lmoffice"])
    identity_file=ROOT/"controls/unmatched-profile.lms"
    node=Path(shutil.which("node") or "/usr/bin/node")
    identity_run=subprocess.run([str(node),"--experimental-strip-types",str(Path(args.mono_source).resolve()),"--check",str(identity_file)],
                                env=env,cwd=mono_root,text=True,capture_output=True)
    identity_text=identity_run.stdout+identity_run.stderr
    identity_expect='unknown XML profile "html-doc@2"'
    require(identity_run.returncode==2 and identity_expect in identity_text,f"unmatched profile identity control did not fail as expected: {identity_text}")
    location=re.search(r"unmatched-profile\.lms:(\d+):(\d+):",identity_text)
    require(location is not None and location.groups()==("2","1"),f"profile identity diagnostic location changed: {identity_text}")
    observations=[]
    for case in manifest["cases"]:
        for host,binary in hosts.items():
            case_dir=evidence/"runs"/case["id"]/host;case_dir.mkdir(parents=True,exist_ok=True)
            output=case_dir/f"out.{ARTIFACTS[host]}"
            if output.exists(): output.unlink()
            xml=(ROOT/case["xml"]).read_text(encoding="utf-8");css=(ROOT/case["css"]).read_text(encoding="utf-8")
            source=host_source(host,xml,css,output)
            real_proc=run_source(compiler,source,case_dir/"real.lms",env,dry=False)
            real_result=parse_real_result(real_proc)
            real_ok=bool(real_result and real_result.get("ok") is True)
            exists=output.is_file()
            metrics=None;digest=None
            if exists:
                digest=sha256(output.read_bytes())
                metrics=inspect_pdf(output,binary) if host=="lmpdf" else inspect_docx(output)
            dry_proc=run_source(compiler,source,case_dir/"dry.lms",env,dry=True)
            plan,envelope=parse_dry_plan(dry_proc)
            dry_ok=envelope.get("ok") is True
            still=output.is_file()
            unchanged=(not exists and not still) or (exists and still and sha256(output.read_bytes())==digest)
            require(envelope.get("dry") is True,f"{host}/{case['id']}: dry marker missing: {envelope}")
            require(unchanged,f"{host}/{case['id']}: dry output modified/created")
            observations.append({"case":case["id"],"host":host,"real_exit":real_proc.returncode,"real_result":real_result,
                "real_ok":real_ok,"output_exists":exists,"output_sha256":digest,"metrics":metrics,
                "dry_exit":dry_proc.returncode,"dry_ok":dry_ok,"dry_envelope":envelope,
                "dry_output_unchanged":unchanged,"real_stderr":real_proc.stderr,"dry_stderr":dry_proc.stderr})
    red_controls=assert_release_red_controls(observations,identity_text)
    pinned_view=baseline_view(compiler_name,hosts_version,hosts,frozen,identity_run,identity_expect,observations)
    result={"format":"html-doc-release-observations/1","corpus_sha256":sha256((ROOT/"corpus.json").read_bytes()),
            "source_traces":traces,"observations":observations,"red_controls":red_controls,
            "profile_identity_control":{"exit":identity_run.returncode,"diagnostic":identity_expect,"text":identity_text},
            "baseline_view":pinned_view}
    observations_file=evidence/"release-observations.json"
    observations_file.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    candidate_file=evidence/"release-baseline-candidate.json"
    candidate_file.write_text(json.dumps(pinned_view,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    baseline=ROOT/"release-baseline.json"
    if not args.record:
        require(baseline.is_file(),"release-baseline.json missing; run once with --record and review observations")
        assert_subset(json.loads(baseline.read_text(encoding="utf-8")),pinned_view,"pinned release baseline")
    print(json.dumps({"compiler":compiler_name,"host_versions":hosts_version,"observations":len(observations),
                      "red_controls":red_controls,"profile_identity_control":identity_expect,
                      "evidence":str(observations_file),"baseline_candidate":str(candidate_file)},indent=2,ensure_ascii=False))


if __name__=="__main__":
    main()
