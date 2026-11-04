#!/usr/bin/env python3
"""Exercise lmoffice html_doc against the frozen language-neutral corpus."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import struct
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
spec = importlib.util.spec_from_file_location("html_doc_corpus", ROOT / "run.py")
corpus = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = corpus
spec.loader.exec_module(corpus)
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
DRAW = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def fail(message):
    raise AssertionError(message)


def invocation(xml, css, out):
    schema = (REPO / "schema" / "docx.dsl.json").as_posix()
    return (
        f"xml = {json.dumps(xml, ensure_ascii=False)};\n"
        f"css = {json.dumps(css, ensure_ascii=False)};\n"
        f"s = load_schema(schema={json.dumps(schema)});\n"
        "p = _lmcode_ s;\n"
        f"let d = docx.create({json.dumps(str(out))});\n"
        "d.html_doc(${xml}, ${css});\n"
        "d.save();\n"
        "end _lmcode_\n"
        'r = run_lmcode(p, {command:["lmoffice","docx","--lmcode","$DSLFILE"]});\n'
        "println(json_stringify(r));\n"
    )


def invoke(compiler, source, path, env, dry=False, check=False, cwd=ROOT):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    args=[str(compiler)]
    if dry: args += ["--dry-run", "--plan-format", "json"]
    if check: args += ["--check"]
    args += [str(path)]
    if os.name=="nt" and str(compiler).lower().endswith((".cmd",".bat")):
        args=["cmd.exe","/d","/s","/c",subprocess.list2cmdline(args)]
    return subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)


def result_from(proc):
    for line in reversed(proc.stdout.splitlines()):
        try:
            value=json.loads(line)
            if isinstance(value,dict) and "ok" in value: return value
        except json.JSONDecodeError:
            pass
    return None


def dry_result(proc):
    plan=json.loads(proc.stdout)
    entry=next((x for x in plan.get("entries",[]) if x.get("kind")=="lmcode-host-dry"),None)
    if entry is None: fail(f"missing host dry envelope: {plan}")
    return entry["envelope"]


def paragraph_text(paragraph):
    parts=[]
    for node in paragraph.iter():
        if node.tag == W+"t": parts.append(node.text or "")
        elif node.tag == W+"br": parts.append("\n")
    return "".join(parts)


def xml_bool(node):
    return node is not None and node.get(W+"val") not in ("0","false","off")


def paragraph_for(metrics,text):
    return next((p for p,value in metrics["paragraphs"] if value==text),None)


def runs_for(paragraph,text=None):
    if paragraph is None:return []
    runs=[]
    for run in paragraph.iter(W+"r"):
        value="".join(t.text or "" for t in run.iter(W+"t"))
        if text is None or text in value:
            rpr=run.find(W+"rPr")
            if rpr is None:continue
            fonts=rpr.find(W+"rFonts");size=rpr.find(W+"sz");color=rpr.find(W+"color")
            runs.append({"text":value,"font":None if fonts is None else fonts.get(W+"ascii"),
                         "size":None if size is None else size.get(W+"val"),"bold":xml_bool(rpr.find(W+"b")),
                         "italic":xml_bool(rpr.find(W+"i")),"color":None if color is None else color.get(W+"val"),
                         "underline":None if rpr.find(W+"u") is None else rpr.find(W+"u").get(W+"val")})
    return runs


def inspect_docx(path):
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None: fail("DOCX package has a bad member")
        document=ET.fromstring(archive.read("word/document.xml"))
        styles=ET.fromstring(archive.read("word/styles.xml"))
        settings=ET.fromstring(archive.read("word/settings.xml")) if "word/settings.xml" in archive.namelist() else None
        relationships=ET.fromstring(archive.read("word/_rels/document.xml.rels"))
        numbering=ET.fromstring(archive.read("word/numbering.xml"))
        body=document.find(".//"+W+"body")
        blocks=[]; paragraphs=[]; tables=[]; breaks=0; page_breaks=0; links=[]; link_text=[]; images=[]; image_boxes=[]; image_shapes=[]; image_hashes=[]; list_num_ids=[]
        relmap={rel.get("Id"):rel for rel in relationships}
        for child in list(body):
            if child.tag == W+"p":
                text=paragraph_text(child); paragraphs.append((child,text)); blocks.append(("p",(text,child)))
                for br in child.iter(W+"br"):
                    if br.get(W+"type")=="page": breaks+=1
                num=child.find(W+"pPr/"+W+"numPr/"+W+"numId")
                if num is not None:list_num_ids.append(num.get(W+"val"))
                if child.find(W+"pPr/"+W+"pageBreakBefore") is not None:page_breaks+=1
                for link in child.iter(W+"hyperlink"):
                    rel=relmap.get(link.get(R+"id"))
                    links.append(None if rel is None else rel.get("Target"))
                    link_text.append("".join(t.text or "" for t in link.iter(W+"t")))
                for drawing in child.iter(W+"drawing"):
                    images.append(drawing)
                    description=drawing.find(".//"+WP+"docPr")
                    extent=drawing.find(".//"+WP+"extent")
                    box=None if extent is None else (int(extent.get("cx")),int(extent.get("cy")))
                    image_boxes.append({"alt":None if description is None else description.get("descr"),"box":box})
                    transform=drawing.find(".//"+DRAW+"xfrm");offset=None if transform is None or transform.find(DRAW+"off") is None else (int(transform.find(DRAW+"off").get("x")),int(transform.find(DRAW+"off").get("y")))
                    shape_extent=None if transform is None or transform.find(DRAW+"ext") is None else (int(transform.find(DRAW+"ext").get("cx")),int(transform.find(DRAW+"ext").get("cy")))
                    image_shapes.append({"offset":offset,"extent":shape_extent})
                    blip=drawing.find(".//"+DRAW+"blip")
                    relation=relmap.get(None if blip is None else blip.get(R+"embed"))
                    raw_target="" if relation is None else relation.get("Target","")
                    target=None if relation is None else raw_target.lstrip("/") if raw_target.startswith("/") else "word/"+raw_target
                    image_hashes.append(None if target is None or target not in archive.namelist() else hashlib.sha256(archive.read(target)).hexdigest())
            elif child.tag == W+"tbl":
                rows=[]
                for row in child.findall(W+"tr"):
                    cells=[]
                    for cell in row.findall(W+"tc"):
                        cells.append("\n".join(paragraph_text(p) for p in cell.findall(W+"p")))
                        for p in cell.findall(W+"p"):
                            if p.find(W+"pPr/"+W+"pageBreakBefore") is not None:page_breaks+=1
                    rows.append(cells)
                props=child.find(W+"tblPr")
                layout=None if props is None or props.find(W+"tblLayout") is None else props.find(W+"tblLayout").get(W+"type")
                grid=[int(c.get(W+"w")) for c in child.findall(W+"tblGrid/"+W+"gridCol")]
                table_width=None if props is None or props.find(W+"tblW") is None else int(props.find(W+"tblW").get(W+"w"))
                margins=None if props is None or props.find(W+"tblCellMar") is None else {m.tag.rsplit("}",1)[-1]:m.get(W+"w") for m in props.find(W+"tblCellMar")}
                borders=[] if props is None or props.find(W+"tblBorders") is None else [b.get(W+"sz") for b in props.find(W+"tblBorders")]
                alignments=[];cell_widths=[]
                for row in child.findall(W+"tr"):
                    row_widths=[]
                    for cell in row.findall(W+"tc"):
                        tcw=cell.find(W+"tcPr/"+W+"tcW");row_widths.append(None if tcw is None else int(tcw.get(W+"w")))
                        for p in cell.findall(W+"p"):
                            jc=p.find(W+"pPr/"+W+"jc");alignments.append(None if jc is None else jc.get(W+"val"))
                    cell_widths.append(row_widths)
                headers=sum(1 for row in child.findall(W+"tr") if row.find(W+"trPr/"+W+"tblHeader") is not None)
                tables.append((child,rows,{"layout":layout,"grid":grid,"width":table_width,"cell_widths":cell_widths,"margins":margins,"borders":borders,"alignments":alignments,"headers":headers})); blocks.append(("table",rows))
        psize=body.find(W+"sectPr/"+W+"pgSz")
        margins=body.find(W+"sectPr/"+W+"pgMar")
        relitems=[(r.get("Id"),r.get("Type"),r.get("Target"),r.get("TargetMode")) for r in relationships]
        num_instances={n.get(W+"numId"):n.find(W+"abstractNumId").get(W+"val") for n in numbering.findall(W+"num")}
        num_start_overrides={n.get(W+"numId"):n.find(W+"lvlOverride/"+W+"startOverride").get(W+"val") for n in numbering.findall(W+"num") if n.find(W+"lvlOverride/"+W+"startOverride") is not None}
        num_formats={n.get(W+"abstractNumId"):n.find(W+"lvl/"+W+"numFmt").get(W+"val") for n in numbering.findall(W+"abstractNum")}
        num_indents={n.get(W+"abstractNumId"):(n.find(W+"lvl/"+W+"pPr/"+W+"ind").get(W+"left"),n.find(W+"lvl/"+W+"pPr/"+W+"ind").get(W+"hanging")) for n in numbering.findall(W+"abstractNum") if n.find(W+"lvl/"+W+"pPr/"+W+"ind") is not None}
        auto_hyphen=None if settings is None or settings.find(W+"autoHyphenation") is None else xml_bool(settings.find(W+"autoHyphenation"))
        return {"blocks":blocks,"paragraphs":paragraphs,"tables":tables,"page_size":psize,"margins":margins,
                "relationships":relitems,"numbering":num_instances,"num_start_overrides":num_start_overrides,"number_formats":num_formats,"num_indents":num_indents,"list_num_ids":list_num_ids,
                "archive_names":archive.namelist(),"breaks":breaks,"page_breaks":page_breaks,"links":links,"link_text":link_text,
                "images":images,"image_boxes":image_boxes,"image_shapes":image_shapes,"image_hashes":image_hashes,"parts":set(archive.namelist()),"auto_hyphenation":auto_hyphen}


def run_profile_unit_controls(compiler,host,evidence,env):
    work=evidence/"profile-unit-controls";work.mkdir(parents=True,exist_ok=True)
    results=[]
    xml='<article xmlns="http://www.w3.org/1999/xhtml"><p>Normalized units</p></article>'
    css='<style xmlns="urn:lmctl:css:1"><rule select="@page"><set name="size" value="A4"/><set name="margin-top" value="10mm"/><set name="margin-right" value="5.4pt"/><set name="margin-bottom" value="6pt"/><set name="margin-left" value="2mm"/></rule><rule select="p"><set name="font-size" value="14.25pt"/></rule></style>'
    output=(work/"a4.docx").resolve();source=invocation(xml,css,output)
    checked=invoke(compiler,source,work/"a4-check.lms",env,check=True)
    if checked.returncode:fail(f"A4 profile unit static check failed: {checked.stdout}{checked.stderr}")
    real=invoke(compiler,source,work/"a4-real.lms",env,cwd=work);result=result_from(real)
    if real.returncode or result is None or result.get("ok") is not True:fail(f"A4 profile unit real control failed: {real.stdout}{real.stderr}")
    metrics=inspect_docx(output)
    if int(metrics["page_size"].get(W+"w"))!=11906 or int(metrics["page_size"].get(W+"h"))!=16838:fail("A4 dimensions did not normalize to 595.3 x 841.9pt")
    if [metrics["margins"].get(W+side) for side in ("top","right","bottom","left")]!=["567","108","120","113"]:fail("A4 physical margins did not normalize to 1/20pt twips")
    paragraph=paragraph_for(metrics,"Normalized units");run=runs_for(paragraph)
    if not run or run[0]["size"]!="29":fail("14.25pt font size did not round ties-away to 14.5pt")
    before=hashlib.sha256(output.read_bytes()).hexdigest()
    dry=invoke(compiler,source,work/"a4-dry.lms",env,dry=True,cwd=work)
    if dry.returncode or dry_result(dry).get("ok") is not True:fail(f"A4 dry normalization failed: {dry.stdout}{dry.stderr}")
    if hashlib.sha256(output.read_bytes()).hexdigest()!=before:fail("A4 dry run changed the output file")
    results.append({"case":"a4-unit-normalization","result":"pass"})

    breaks='<article xmlns="http://www.w3.org/1999/xhtml"><p class="first">Alpha</p><p class="next">Beta</p></article>'
    break_css='<style xmlns="urn:lmctl:css:1"><rule select="p"><set name="margin-top" value="10pt"/><set name="margin-bottom" value="20pt"/></rule><rule select=".first"><set name="page-break-after" value="always"/></rule><rule select=".next"><set name="page-break-before" value="always"/></rule></style>'
    break_out=(work/"page-break-after.docx").resolve();break_source=invocation(breaks,break_css,break_out)
    break_real=invoke(compiler,break_source,work/"break-real.lms",env,cwd=work);break_result=result_from(break_real)
    if break_real.returncode or break_result is None or break_result.get("ok") is not True:fail(f"page-break-after unit control failed: {break_real.stdout}{break_real.stderr}")
    break_metrics=inspect_docx(break_out)
    if break_metrics["page_breaks"]!=1:fail("coalesced before/after requests did not emit exactly one page break")
    alpha=paragraph_for(break_metrics,"Alpha");beta=paragraph_for(break_metrics,"Beta")
    if alpha.find(W+"pPr/"+W+"spacing").get(W+"after")!="0" or beta.find(W+"pPr/"+W+"spacing").get(W+"before")!="0":fail("page-break spacing was not discarded")
    results.append({"case":"page-break-after-coalescing","result":"pass"})

    corrupt=bytearray((ROOT/"assets/chart.png").read_bytes());corrupt[-1]^=0x01
    bad_asset=work/"corrupt.png";bad_asset.write_bytes(corrupt)
    image='<article xmlns="http://www.w3.org/1999/xhtml"><img src="corrupt.png" alt="broken" width="20pt" height="10pt"/></article>'
    image_source=invocation(image,"",(work/"must-not-exist.docx").resolve())
    dry_bad=invoke(compiler,image_source,work/"corrupt-dry.lms",env,dry=True,cwd=work)
    if dry_bad.returncode:fail(f"corrupt-image dry runner failed: {dry_bad.stdout}{dry_bad.stderr}")
    bad_envelope=dry_result(dry_bad)
    if bad_envelope.get("ok") is not False or "PNG chunk checksum" not in bad_envelope.get("message",""):fail(f"dry callback did not decode/reject corrupt PNG: {bad_envelope}")
    if (work/"must-not-exist.docx").exists():fail("corrupt-image dry validation created an output file")
    results.append({"case":"dry-decodes-image-bytes","result":"pass"})

    # F1: <br/> inside <td> and <th>
    cell_br_xml='<article xmlns="http://www.w3.org/1999/xhtml"><table><tr><th>Col<br/>One</th></tr><tr><td>Line 1<br/>Line 2</td></tr></table></article>'
    cell_br_out=(work/"cell-br.docx").resolve();cell_br_src=invocation(cell_br_xml,"",cell_br_out)
    cell_br_real=invoke(compiler,cell_br_src,work/"cell-br.lms",env,cwd=work);cell_br_res=result_from(cell_br_real)
    if cell_br_real.returncode or cell_br_res is None or cell_br_res.get("ok") is not True:fail(f"F1 cell <br/> control failed: {cell_br_real.stdout}{cell_br_real.stderr}")
    cell_br_metrics=inspect_docx(cell_br_out)
    if cell_br_metrics["tables"][0][1]!=[["Col\nOne"],["Line 1\nLine 2"]]:fail(f"F1 cell <br/> text mismatch: {cell_br_metrics['tables'][0][1]}")
    results.append({"case":"f1-table-cell-br","result":"pass"})

    # F2: CDATA and non-ASCII whitespace directly inside container elements rejected
    for idx,bad_container in enumerate([
        '<article xmlns="http://www.w3.org/1999/xhtml"><![CDATA[Dropped text]]><p>Kept</p></article>',
        '<article xmlns="http://www.w3.org/1999/xhtml"><div><![CDATA[In div]]><p>Kept</p></div></article>',
        '<article xmlns="http://www.w3.org/1999/xhtml">&#160;<p>Kept</p></article>',
    ]):
        cdata_dry=invoke(compiler,invocation(bad_container,"",(work/f"cdata-{idx}.docx").resolve()),work/f"cdata-{idx}.lms",env,dry=True,cwd=work)
        cdata_env=dry_result(cdata_dry)
        if cdata_dry.returncode or cdata_env.get("ok") is not False or "text is not allowed directly inside" not in cdata_env.get("message",""):
            fail(f"F2 container CDATA/NBSP {idx} was not rejected: {cdata_env}")
    results.append({"case":"f2-container-cdata-rejected","result":"pass"})

    # F3: <th> cascade bold override and empty <th></th> underline
    th_xml='<article xmlns="http://www.w3.org/1999/xhtml"><table><tr><th>Plain Header</th><th></th></tr><tr><td>A</td><td>B</td></tr></table></article>'
    th_css='<style xmlns="urn:lmctl:css:1"><rule select="th"><set name="font-weight" value="normal"/></rule></style>'
    th_out=(work/"th-cascade.docx").resolve()
    th_real=invoke(compiler,invocation(th_xml,th_css,th_out),work/"th-cascade.lms",env,cwd=work)
    if th_real.returncode or (result_from(th_real) or {}).get("ok") is not True:fail(f"F3 th cascade control failed: {th_real.stdout}{th_real.stderr}")
    th_metrics=inspect_docx(th_out)
    th_cells=th_metrics["tables"][0][0].findall(W+"tr")[0].findall(W+"tc")
    for tc_idx,tc in enumerate(th_cells):
        tc_runs=runs_for(tc.find(W+"p"))
        if not tc_runs or tc_runs[0]["bold"] is not False or tc_runs[0]["underline"]!="none":
            fail(f"F3 th cell {tc_idx} expected bold=False, underline='none', got {tc_runs}")
    th_def_out=(work/"th-default.docx").resolve()
    th_def_real=invoke(compiler,invocation(th_xml,"",th_def_out),work/"th-default.lms",env,cwd=work)
    if th_def_real.returncode or (result_from(th_def_real) or {}).get("ok") is not True:fail("F3 default th failed")
    th_def_cells=inspect_docx(th_def_out)["tables"][0][0].findall(W+"tr")[0].findall(W+"tc")
    for tc_idx,tc in enumerate(th_def_cells):
        tc_runs=runs_for(tc.find(W+"p"))
        if not tc_runs or tc_runs[0]["bold"] is not True or tc_runs[0]["underline"]!="none":
            fail(f"F3 default th cell {tc_idx} expected bold=True, underline='none', got {tc_runs}")
    results.append({"case":"f3-th-cascade-and-empty-th","result":"pass"})

    # F4: <a> default #0563C1 color, child color inside <a>, and no spurious empty <w:r>
    a_xml='<article xmlns="http://www.w3.org/1999/xhtml"><p><a href="https://example.com"><span class="accent">Colored</span> plain</a></p></article>'
    a_css='<style xmlns="urn:lmctl:css:1"><rule select="article"><set name="color" value="#334155"/></rule><rule select=".accent"><set name="color" value="#FF0000"/></rule></style>'
    a_out=(work/"a-color.docx").resolve()
    a_real=invoke(compiler,invocation(a_xml,a_css,a_out),work/"a-color.lms",env,cwd=work)
    if a_real.returncode or (result_from(a_real) or {}).get("ok") is not True:fail(f"F4 link child color failed: {a_real.stdout}{a_real.stderr}")
    a_metrics=inspect_docx(a_out)
    a_p=a_metrics["paragraphs"][0][0]
    if len(a_p.findall(W+"r"))!=0:fail(f"F4 link-only paragraph emitted spurious direct <w:r>: {len(a_p.findall(W+'r'))}")
    a_runs=runs_for(a_p)
    if len(a_runs)!=2 or a_runs[0]["color"]!="FF0000" or a_runs[0]["underline"]!="single" or a_runs[1]["color"]!="0563C1" or a_runs[1]["underline"]!="single":
        fail(f"F4 link child runs mismatch: {a_runs}")
    results.append({"case":"f4-link-color-and-runs","result":"pass"})

    # F5: TryDocLink credentials, hostless mailto:, whitespace in href, and whitespace-only <a>
    for idx,(bad_a,expected_msg) in enumerate([
        ('<article xmlns="http://www.w3.org/1999/xhtml"><p><a href="https://user:pass@example.com/path">Link</a></p></article>',"href must be an absolute http, https, or mailto URI"),
        ('<article xmlns="http://www.w3.org/1999/xhtml"><p><a href="mailto:just-a-path">Link</a></p></article>',"href must be an absolute http, https, or mailto URI"),
        ('<article xmlns="http://www.w3.org/1999/xhtml"><p><a href="https://example.com/a b">Link</a></p></article>',"href must be an absolute http, https, or mailto URI"),
        ('<article xmlns="http://www.w3.org/1999/xhtml"><p><a href="https://example.com">   </a></p></article>',"a requires nonempty text"),
    ]):
        bad_a_dry=invoke(compiler,invocation(bad_a,"",(work/f"bad-a-{idx}.docx").resolve()),work/f"bad-a-{idx}.lms",env,dry=True,cwd=work)
        bad_a_env=dry_result(bad_a_dry)
        if bad_a_dry.returncode or bad_a_env.get("ok") is not False or expected_msg not in bad_a_env.get("message",""):
            fail(f"F5 invalid link {idx} was not rejected with {expected_msg!r}: {bad_a_env}")
    results.append({"case":"f5-link-validation","result":"pass"})

    # F6: Universal selector * with <br/> and <img/>, and css-doc line/column provenance on applicability errors
    shutil.copyfile(ROOT/"assets/chart.png",work/"logo.png")
    star_xml='<article xmlns="http://www.w3.org/1999/xhtml"><p>Line 1<br/>Line 2</p><img src="logo.png" alt="Logo" width="40pt" height="20pt"/></article>'
    star_css='<style xmlns="urn:lmctl:css:1"><rule select="*"><set name="font-family" value="Arial"/><set name="font-size" value="10pt"/><set name="color" value="#112233"/></rule></style>'
    star_out=(work/"star.docx").resolve()
    star_real=invoke(compiler,invocation(star_xml,star_css,star_out),work/"star.lms",env,cwd=work)
    if star_real.returncode or (result_from(star_real) or {}).get("ok") is not True:fail(f"F6 universal selector * failed: {star_real.stdout}{star_real.stderr}")
    star_runs=runs_for(inspect_docx(star_out)["paragraphs"][0][0])
    if not star_runs or any(r["font"]!="Liberation Sans" or r["size"]!="20" or r["color"]!="112233" for r in star_runs):
        fail(f"F6 universal selector * did not apply to paragraph runs: {star_runs}")
    loc_xml='<article xmlns="http://www.w3.org/1999/xhtml">\n  <p>\n    \n    \n    <span>Inline</span>\n  </p>\n</article>'
    loc_css='<style xmlns="urn:lmctl:css:1">\n  <rule select="span">\n    <set name="text-align" value="center"/>\n  </rule>\n</style>'
    loc_dry=invoke(compiler,invocation(loc_xml,loc_css,(work/"loc.docx").resolve()),work/"loc.lms",env,dry=True,cwd=work)
    loc_env=dry_result(loc_dry)
    if loc_dry.returncode or loc_env.get("ok") is not False or "css-doc line 3" not in loc_env.get("message",""):
        fail(f"F6 applicability error did not report css-doc line 3: {loc_env}")
    results.append({"case":"f6-universal-selector-and-css-loc","result":"pass"})

    # F7: 58-byte huge-IHDR PNG, grayscale PLTE PNG, and malformed JPEG rejection
    import zlib
    def png_chunk(ctype,data):
        return struct.pack(">I",len(data))+ctype+data+struct.pack(">I",zlib.crc32(ctype+data)&0xffffffff)
    ihdr_huge=struct.pack(">IIBBBBB",268435455,1,16,6,0,0,0)
    (work/"huge-ihdr.png").write_bytes(b"\x89PNG\r\n\x1a\n"+png_chunk(b"IHDR",ihdr_huge)+png_chunk(b"IDAT",b"")+png_chunk(b"IEND",b""))
    ihdr_gray_plte=struct.pack(">IIBBBBB",1,1,8,0,0,0,0)
    (work/"gray-plte.png").write_bytes(b"\x89PNG\r\n\x1a\n"+png_chunk(b"IHDR",ihdr_gray_plte)+png_chunk(b"PLTE",b"\x00\x00\x00")+png_chunk(b"IDAT",zlib.compress(b"\x00\x00"))+png_chunk(b"IEND",b""))
    (work/"empty-scan.jpg").write_bytes(bytes([0xFF,0xD8,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xDA,0x00,0x08,0x01,0x01,0x00,0x00,0x3F,0x00,0xFF,0xD9]))
    (work/"trailing-eoi.jpg").write_bytes(bytes([0xFF,0xD8,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xDA,0x00,0x08,0x01,0x01,0x00,0x00,0x3F,0x00,0xAA,0xFF,0xD9,0x00,0x11]))
    for bad_img,expected_err in (
        ("huge-ihdr.png","PNG compressed data cannot satisfy declared dimensions"),
        ("gray-plte.png","invalid PNG palette"),
        ("empty-scan.jpg","empty JPEG scan data"),
        ("trailing-eoi.jpg","trailing bytes after JPEG EOI"),
    ):
        img_xml=f'<article xmlns="http://www.w3.org/1999/xhtml"><img src="{bad_img}" alt="x" width="10pt" height="10pt"/></article>'
        img_dry=invoke(compiler,invocation(img_xml,"",(work/f"{bad_img}.docx").resolve()),work/f"{bad_img}.lms",env,dry=True,cwd=work)
        img_env=dry_result(img_dry)
        if img_dry.returncode or img_env.get("ok") is not False or "html-doc line 1" not in img_env.get("message","") or expected_err not in img_env.get("message",""):
            fail(f"F7 malformed image {bad_img} was not cleanly rejected with {expected_err!r}: {img_env}")
    results.append({"case":"f7-png-jpeg-validation","result":"pass"})

    # F9: <table> page-break-before without phantom <w:p> and trailing page-break-after preserving after margin
    tbl_pb_xml='<article xmlns="http://www.w3.org/1999/xhtml"><p>Before</p><table><tr><td>Cell</td></tr></table></article>'
    tbl_pb_css='<style xmlns="urn:lmctl:css:1"><rule select="table"><set name="page-break-before" value="always"/></rule></style>'
    tbl_pb_out=(work/"tbl-pb.docx").resolve()
    tbl_pb_real=invoke(compiler,invocation(tbl_pb_xml,tbl_pb_css,tbl_pb_out),work/"tbl-pb.lms",env,cwd=work)
    if tbl_pb_real.returncode or (result_from(tbl_pb_real) or {}).get("ok") is not True:fail(f"F9 table page-break-before failed: {tbl_pb_real.stdout}{tbl_pb_real.stderr}")
    tbl_pb_metrics=inspect_docx(tbl_pb_out)
    if len(tbl_pb_metrics["paragraphs"])!=1 or tbl_pb_metrics["page_breaks"]!=1:
        fail(f"F9 table page-break-before emitted phantom body paragraph or wrong break count: paragraphs={len(tbl_pb_metrics['paragraphs'])}, page_breaks={tbl_pb_metrics['page_breaks']}")
    trail_xml='<article xmlns="http://www.w3.org/1999/xhtml"><p>Final</p></article>'
    trail_css='<style xmlns="urn:lmctl:css:1"><rule select="p"><set name="margin-bottom" value="10pt"/><set name="page-break-after" value="always"/></rule></style>'
    trail_out=(work/"trail-pb.docx").resolve()
    trail_real=invoke(compiler,invocation(trail_xml,trail_css,trail_out),work/"trail-pb.lms",env,cwd=work)
    if trail_real.returncode or (result_from(trail_real) or {}).get("ok") is not True:fail("F9 trailing page-break-after failed")
    trail_metrics=inspect_docx(trail_out)
    if trail_metrics["page_breaks"]!=0 or trail_metrics["paragraphs"][0][0].find(W+"pPr/"+W+"spacing").get(W+"after")!="200":
        fail("F9 trailing page-break-after clobbered final paragraph after margin")
    results.append({"case":"f9-table-and-trailing-page-breaks","result":"pass"})

    # F10: Inter-run whitespace at <a> boundaries not absorbed into <w:hyperlink>
    ws_xml='<article xmlns="http://www.w3.org/1999/xhtml"><p><a href="https://example.com">Link </a>After</p><p>Before<a href="https://example.com"> Link</a></p></article>'
    ws_out=(work/"ws-link.docx").resolve()
    ws_real=invoke(compiler,invocation(ws_xml,"",ws_out),work/"ws-link.lms",env,cwd=work)
    if ws_real.returncode or (result_from(ws_real) or {}).get("ok") is not True:fail("F10 link boundary whitespace failed")
    ws_metrics=inspect_docx(ws_out)
    if ws_metrics["link_text"]!=["Link","Link"] or [t for _,t in ws_metrics["paragraphs"]]!=["Link After","Before Link"]:
        fail(f"F10 link boundary whitespace absorbed into hyperlink: link_text={ws_metrics['link_text']}")
    results.append({"case":"f10-link-boundary-whitespace","result":"pass"})

    # F11: Additive html_doc without @page preserves existing page size, and strong/em normal reset works
    schema=(REPO/"schema"/"docx.dsl.json").as_posix()
    add_out=(work/"additive-a4.docx").resolve()
    add_src=(
        f's = load_schema(schema={json.dumps(schema)});\n'
        'p = _lmcode_ s;\n'
        f'let d = docx.create({json.dumps(str(add_out))});\n'
        'd.page_size(595.3, 841.9);\n'
        'd.paragraph("Native paragraph");\n'
        'd.html_doc("<article xmlns=\\"http://www.w3.org/1999/xhtml\\"><p><strong>ResetStrong</strong> <em>ResetEm</em></p></article>", "<style xmlns=\\"urn:lmctl:css:1\\"><rule select=\\"strong\\"><set name=\\"font-weight\\" value=\\"normal\\"/></rule><rule select=\\"em\\"><set name=\\"font-style\\" value=\\"normal\\"/></rule></style>");\n'
        'd.save();\n'
        'end _lmcode_\n'
        'r = run_lmcode(p, {command:["lmoffice","docx","--lmcode","$DSLFILE"]});\n'
        'println(json_stringify(r));\n'
    )
    add_real=invoke(compiler,add_src,work/"additive.lms",env,cwd=work)
    if add_real.returncode or (result_from(add_real) or {}).get("ok") is not True:fail(f"F11 additive A4 failed: {add_real.stdout}{add_real.stderr}")
    add_metrics=inspect_docx(add_out)
    if int(add_metrics["page_size"].get(W+"w"))!=11906 or int(add_metrics["page_size"].get(W+"h"))!=16838:
        fail(f"F11 additive html_doc without @page clobbered A4 page size: {add_metrics['page_size'].attrib}")
    reset_p=paragraph_for(add_metrics,"ResetStrong ResetEm")
    reset_runs=runs_for(reset_p)
    if not reset_runs or any(r["bold"] or r["italic"] for r in reset_runs):
        fail(f"F11 strong/em normal reset failed: {reset_runs}")
    results.append({"case":"f11-additive-page-and-normal-reset","result":"pass"})

    # F12: Invalid font-family diagnostic
    ff_css='<style xmlns="urn:lmctl:css:1"><rule select="p"><set name="font-family" value="Comic Sans MS"/></rule></style>'
    ff_dry=invoke(compiler,invocation(xml,ff_css,(work/"ff.docx").resolve()),work/"ff.lms",env,dry=True,cwd=work)
    ff_env=dry_result(ff_dry)
    if ff_dry.returncode or ff_env.get("ok") is not False or "invalid font-family value 'Comic Sans MS'" not in ff_env.get("message",""):
        fail(f"F12 invalid font-family diagnostic mismatch: {ff_env}")
    results.append({"case":"f12-font-family-diagnostic","result":"pass"})
    return results


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--case", action="append")
    args=parser.parse_args()
    compiler=Path(args.compiler).resolve(); host=Path(args.host).resolve(); evidence=Path(args.evidence).resolve()
    evidence.mkdir(parents=True,exist_ok=True)
    keep=("LANG","LC_ALL","DOTNET_ROOT","PYTHONUTF8")
    env={k:os.environ[k] for k in keep if k in os.environ}
    if os.name=="nt":
        windows_runtime=("PATH","SYSTEMROOT","WINDIR","TEMP","TMP","COMSPEC","PATHEXT",
                         "PROCESSOR_ARCHITECTURE","PROCESSOR_IDENTIFIER","PROGRAMFILES","PROGRAMFILES(X86)",
                         "LOCALAPPDATA","APPDATA","HOMEDRIVE","HOMEPATH","USERPROFILE","NUMBER_OF_PROCESSORS")
        env.update({k:os.environ[k] for k in windows_runtime if k in os.environ})
    host_bin=evidence/"bin";host_bin.mkdir(parents=True,exist_ok=True)
    link=host_bin/("lmoffice.exe" if os.name=="nt" else "lmoffice")
    if link.exists() or link.is_symlink(): link.unlink()
    try: os.link(host,link)
    except OSError: link.symlink_to(host)
    env["PATH"]=os.pathsep.join([str(host_bin),str(compiler.parent),os.environ.get("PATH","")])
    env["HOME"]=str(evidence/"home");env["XDG_CACHE_HOME"]=str(evidence/"cache")
    manifest=json.loads((ROOT/"corpus.json").read_text(encoding="utf-8"))
    upstream=(ROOT/"UPSTREAM_COMMIT").read_text().strip()
    if len(upstream)!=40 or any(c not in "0123456789abcdef" for c in upstream): fail(f"corpus source pin changed: {upstream}")
    for asset in manifest["assets"]:
        path=ROOT/asset["path"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=asset["sha256"]: fail(f"corpus asset hash changed: {path}")
    extra=json.loads((ROOT/"regressions.json").read_text(encoding="utf-8")) if (ROOT/"regressions.json").exists() else {}
    all_cases=[dict(c,**extra.get("case_overrides",{}).get(c["id"],{})) for c in manifest["cases"]]+extra.get("cases",[])
    cases=[c for c in all_cases if not args.case or c["id"] in args.case]
    if args.case and {c["id"] for c in cases}!=set(args.case): fail("unknown corpus case requested")
    subprocess.run([sys.executable,str(ROOT/"check.py")],check=True)
    records=[]
    for case in cases:
        xml=(ROOT/case["xml"]).read_text(encoding="utf-8");css=(ROOT/case["css"]).read_text(encoding="utf-8")
        output=(evidence/"outputs"/case["id"]/"result.docx").resolve()
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.exists(): output.unlink()
        source=invocation(xml,css,output)
        case_dir=evidence/"cases"/case["id"]
        checked=invoke(compiler,source,case_dir/"program.lms",env,check=True)
        if checked.returncode!=0: fail(f"{case['id']}: static control failed ({checked.returncode})\n{checked.stdout}{checked.stderr}")
        if case["kind"]=="dry-negative":
            dry=invoke(compiler,source,case_dir/"dry.lms",env,dry=True)
            if dry.returncode!=0: fail(f"{case['id']}: dry runner failed\n{dry.stdout}{dry.stderr}")
            envelope=dry_result(dry)
            expected=case["controls"]["expected_message"]
            if case["controls"].get("expected_code") and envelope.get("code")!=case["controls"]["expected_code"]:fail(f"{case['id']}: wrong error code {envelope}")
            if envelope.get("ok") is not False or envelope.get("dry") is not True or expected not in envelope.get("message",""):
                fail(f"{case['id']}: expected dry error {expected!r}, got {envelope}")
            if output.exists(): fail(f"{case['id']}: dry-negative created {output}")
            records.append({"case":case["id"],"dry":"expected error","message":envelope.get("message")})
            continue
        real=invoke(compiler,source,case_dir/"real.lms",env)
        result=result_from(real)
        if real.returncode!=0 or result is None or result.get("ok") is not True:
            fail(f"{case['id']}: real call failed\n{real.stdout}{real.stderr}")
        if not output.is_file(): fail(f"{case['id']}: real call did not create output")
        inspected=subprocess.run([str(host),"inspect",str(output)],cwd=ROOT,env=env,text=True,capture_output=True)
        if inspected.returncode!=0:fail(f"{case['id']}: lmoffice round-trip inspection failed: {inspected.stdout}{inspected.stderr}")
        inspection=json.loads(inspected.stdout)
        if inspection.get("ok") is not True or inspection.get("result",{}).get("valid") is not True:
            fail(f"{case['id']}: generated DOCX failed Open XML round-trip validation: {inspection}")
        metrics=inspect_docx(output)
        text_blocks=[]
        for kind,block in metrics["blocks"]:
            if kind=="p":
                text,paragraph=block
                if not text and (paragraph.find(".//"+W+"drawing") is not None or paragraph.find(".//"+W+"br") is not None or paragraph.find(W+"pPr/"+W+"pageBreakBefore") is not None): continue
                text_blocks.append(text)
            else:
                for row in block: text_blocks.extend(row)
        if "normalized_text_blocks" in case["expected"] and text_blocks!=case["expected"]["normalized_text_blocks"]:
            fail(f"{case['id']}: normalized text mismatch\nexpected={case['expected']['normalized_text_blocks']!r}\nactual={text_blocks!r}")
        if "normalized_text_sha256" in case["expected"] and hashlib.sha256("\n".join(text_blocks).encode()).hexdigest()!=case["expected"]["normalized_text_sha256"]:
            fail(f"{case['id']}: normalized text digest mismatch")
        if len(metrics["tables"])!=len(case["expected"]["tables"]): fail(f"{case['id']}: table count mismatch")
        for expected_table,(table_xml,rows,table_info) in zip(case["expected"]["tables"],metrics["tables"]):
            if len(rows)!=expected_table["rows"] or len(rows[0])!=expected_table["columns"]: fail(f"{case['id']}: table geometry mismatch")
            if "cells" in expected_table and rows!=expected_table["cells"]: fail(f"{case['id']}: table cell mismatch")
            if len(rows)>5:
                if rows[0]!=expected_table.get("first_row") or rows[-1]!=expected_table.get("last_row"): fail(f"{case['id']}: long-table boundary mismatch")
                digest=hashlib.sha256("\n".join("|".join(row) for row in rows).encode()).hexdigest()
                if digest!=expected_table.get("cell_text_sha256"): fail(f"{case['id']}: long-table cell digest mismatch")
            if expected_table.get("repeat_header") and table_info["headers"]!=1: fail(f"{case['id']}: tblHeader missing or duplicated")
            if table_info["layout"]!="fixed" or not table_info["grid"] or table_info["width"]!=sum(table_info["grid"]): fail(f"{case['id']}: table grid is not fixed to its declared width")
            if max(table_info["grid"])-min(table_info["grid"])>1: fail(f"{case['id']}: table columns are not equal width")
            if any(row!=table_info["grid"] for row in table_info["cell_widths"]): fail(f"{case['id']}: cell widths do not match the fixed table grid")
            if table_info["borders"]!=["4"]*6: fail(f"{case['id']}: fixed 0.5pt black table borders changed")
            if table_info["margins"]!={"top":"10","left":"108","bottom":"120","right":"108"}: fail(f"{case['id']}: fixed table cell insets changed: {table_info['margins']}")
            if "cell_alignments" in expected_table:
                actual=[table_info["alignments"][i:i+expected_table["columns"]] for i in range(0,len(table_info["alignments"]),expected_table["columns"])]
                if actual!=expected_table["cell_alignments"]: fail(f"{case['id']}: per-cell alignment mismatch {actual}")
        expected_images=case["expected"].get("images",[])
        if len(metrics["images"])!=len(expected_images): fail(f"{case['id']}: image mapping count mismatch")
        for image_index,image in enumerate(expected_images):
            if metrics["image_boxes"][image_index]["alt"]!=image["alt"]: fail(f"{case['id']}: image alt text mismatch")
            asset_path=ROOT/image["src"]
            if metrics["image_hashes"][image_index]!=hashlib.sha256(asset_path.read_bytes()).hexdigest(): fail(f"{case['id']}: embedded image bytes differ from source")
            png=asset_path.read_bytes();pixel_width,pixel_height=struct.unpack(">II",png[16:24])
            outer_w,outer_h=metrics["image_boxes"][image_index]["box"]
            inner_w,inner_h=metrics["image_shapes"][image_index]["extent"]
            offset_x,offset_y=metrics["image_shapes"][image_index]["offset"]
            if inner_w>outer_w or inner_h>outer_h or abs(inner_w/inner_h-pixel_width/pixel_height)>0.005: fail(f"{case['id']}: image was stretched or cropped")
            if offset_x!=(outer_w-inner_w)//2 or offset_y!=(outer_h-inner_h)//2: fail(f"{case['id']}: contained image is not centered in its physical box")
            def emu(value):
                import re
                match=re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(pt|mm)",value)
                points=float(match.group(1))*(72/25.4 if match.group(2)=="mm" else 1)
                return round(points*12700)
            if metrics["image_boxes"][image_index]["box"]!=(emu(image["width"]),emu(image["height"])): fail(f"{case['id']}: image physical box mismatch")
        expected_links=case["expected"].get("links",[])
        if len(metrics["links"])!=len(expected_links): fail(f"{case['id']}: hyperlink relationship count mismatch")
        for index,link in enumerate(expected_links):
            if metrics["links"][index]!=link["href"] or metrics["link_text"][index]!=link["text"]: fail(f"{case['id']}: hyperlink mapping mismatch")
        assertions=case.get("render_assertions",{})
        page=assertions.get("page",{"width_pt":612,"height_pt":792})
        if int(metrics["page_size"].get(W+"w"))!=round(page['width_pt']*20) or int(metrics["page_size"].get(W+"h"))!=round(page['height_pt']*20):fail(f"{case['id']}: wrong page geometry")
        wanted_left=next((check['x'] for check in assertions.get('spans',[]) if 'x' in check),54)
        for side in ['top','right','bottom','left']:
            if int(metrics['margins'].get(W+side))!=round((wanted_left if side=='left' else 54)*20):fail(f"{case['id']}: wrong page margin {side}")
        for check in assertions.get('spans',[]):
            observed=[run for paragraph,_ in metrics['paragraphs'] for run in runs_for(paragraph,check['text'])]
            if not observed:fail(f"{case['id']}: missing final run {check['text']!r}")
            if 'bold' in check and any(r['bold']!=check['bold'] for r in observed):fail(f"{case['id']}: wrong final run weight")
            if 'rgb' in check and any(r['color'].upper()!=check['rgb'].upper() for r in observed):fail(f"{case['id']}: wrong final run color")
            if 'size_pt' in check and any(int(r['size'])!=round(check['size_pt']*2) for r in observed):fail(f"{case['id']}: wrong final run size")
        for check in assertions.get('paragraph_spacing',[]):
            paragraph=paragraph_for(metrics,check['text']);spacing=paragraph.find(W+'pPr/'+W+'spacing') if paragraph is not None else None
            if spacing is None or int(spacing.get(W+'after'))!=round(check['after_pt']*20):fail(f"{case['id']}: authored paragraph spacing lost")
        if metrics["auto_hyphenation"] is not False: fail(f"{case['id']}: autoHyphenation must be explicitly false in word/settings.xml")
        if metrics["page_breaks"]!=(1 if case["id"]=="page-break" else 0): fail(f"{case['id']}: explicit page-break boundary mismatch")
        if expected_images:
            img_paragraphs=[p for p,_ in metrics["paragraphs"] if p.find(".//"+W+"drawing") is not None]
            if not img_paragraphs or any(p.find(W+"pPr/"+W+"spacing").get(W+"after")!="120" for p in img_paragraphs):
                fail(f"{case['id']}: default 6pt bottom margin on img missing")
        if case["id"]=="independent-list-restart":
            first=metrics["list_num_ids"][:2];second=metrics["list_num_ids"][2:]
            if len(first)!=2 or len(second)!=2 or len(set(first+second))!=2 or metrics["number_formats"]!={"1":"bullet","2":"decimal"}:
                # Number IDs can be allocated in either order, but the two source lists need separate decimal instances.
                if len(first)!=2 or len(second)!=2 or first[0]!=first[1] or second[0]!=second[1] or first[0]==second[0]: fail(f"{case['id']}: ordered-list numbering instances did not restart")
            if metrics["num_start_overrides"].get(first[0])!="1" or metrics["num_start_overrides"].get(second[0])!="1":
                fail(f"{case['id']}: ordered-list numbering instances missing explicit startOverride=1: {metrics['num_start_overrides']}")
            if metrics["num_indents"].get("1")!=("360","360") or metrics["num_indents"].get("2")!=("360","360"):
                fail(f"{case['id']}: abstractNum 18pt hanging indent missing: {metrics['num_indents']}")
        if case["id"]=="adjacent-different-lists":
            ids=metrics["list_num_ids"]
            if len(ids)!=2 or ids[0]==ids[1] or metrics["number_formats"].get(metrics["numbering"].get(ids[0]))!="bullet" or metrics["number_formats"].get(metrics["numbering"].get(ids[1]))!="decimal":
                fail(f"{case['id']}: bullet and decimal list identities were not preserved")
        if case["id"]=="letter":
            sender=paragraph_for(metrics,"Northwind Logistics, Inc.\n450 Harborview Boulevard, Suite 800\nSeattle, WA 98104")
            sender_runs=runs_for(sender)
            if sender is None or sender.find(W+"pPr/"+W+"jc").get(W+"val")!="right" or sender.find(W+"pPr/"+W+"spacing").get(W+"after")!="240":
                fail("letter: sender paragraph alignment/spacing did not resolve")
            if not sender_runs or any(r["font"]!="Carlito" or r["size"]!="22" or r["color"]!="334155" for r in sender_runs):
                fail("letter: sender run styles did not inherit/resolve correctly")
            subject=paragraph_for(metrics,"Subject: Q4 Dedicated Freight Corridor Renewal (Ref: NWL-2026-Q4-089)")
            subject_runs=runs_for(subject)
            if subject is None or subject.find(W+"pPr/"+W+"outlineLvl").get(W+"val")!="1" or subject.find(W+"pPr/"+W+"spacing").get(W+"before")!="0":
                fail("letter: semantic heading level or collapsed spacing missing")
            if not subject_runs or any(r["size"]!="24" or not r["bold"] or r["color"]!="0F172A" for r in subject_runs):
                fail("letter: h2 computed text style mismatch")
            closing=paragraph_for(metrics,"Sincerely,")
            if closing is None or closing.find(W+"pPr/"+W+"spacing").get(W+"before")!="120":
                fail("letter: closing paragraph collapsed before-margin expected 120 twips (max(160, 280) - 160)")
        if case["id"]=="link":
            paragraph=paragraph_for(metrics,"Reference")
            linked=runs_for(paragraph,"Reference")
            if not linked or linked[0]["underline"]!="single" or linked[0]["color"]!="0563C1" or len(paragraph.findall(W+"r"))!=0:
                fail("link: default clickable link style #0563C1 missing or spurious empty run emitted")
        if case["id"]=="styled-headings":
            checks={"Primary heading":{"font":"Carlito","size":"48","bold":True,"italic":False,"color":"123456","align":"center","outline":"0"},
                    "Secondary heading":{"font":"Carlito","size":"28","bold":True,"italic":True,"outline":"1"},
                    "Third heading":{"font":"Carlito","size":"22","bold":True,"italic":False,"color":"654321","outline":"2"}}
            for text,check in checks.items():
                paragraph=next(p for p,t in metrics["paragraphs"] if t==text)
                ppr=paragraph.find(W+"pPr");run=paragraph.find(W+"r");rpr=run.find(W+"rPr")
                fonts=rpr.find(W+"rFonts");sz=rpr.find(W+"sz");bold=rpr.find(W+"b");italic=rpr.find(W+"i");color=rpr.find(W+"color")
                actual={"font":fonts.get(W+"ascii"),"size":sz.get(W+"val"),"bold":bold is not None and bold.get(W+"val") not in ("0","false"),"italic":italic is not None and italic.get(W+"val") not in ("0","false"),"color":None if color is None else color.get(W+"val"),"align":None if ppr.find(W+"jc") is None else ppr.find(W+"jc").get(W+"val"),"outline":None if ppr.find(W+"outlineLvl") is None else ppr.find(W+"outlineLvl").get(W+"val")}
                for key,value in check.items():
                    if actual.get(key)!=value:fail(f"styled-headings: {text} {key} expected {value!r}, got {actual.get(key)!r}")
        for paragraph,text in metrics["paragraphs"]:
            ppr=paragraph.find(W+"pPr");spacing=None if ppr is None else ppr.find(W+"spacing")
            if spacing is None or spacing.get(W+"line")!="240" or spacing.get(W+"lineRule")!="auto":fail(f"{case['id']}: paragraph must explicitly use single line spacing")
        before=hashlib.sha256(output.read_bytes()).hexdigest()
        dry=invoke(compiler,source,case_dir/"dry.lms",env,dry=True)
        if dry.returncode!=0: fail(f"{case['id']}: dry runner failed\n{dry.stdout}{dry.stderr}")
        envelope=dry_result(dry)
        if envelope.get("ok") is not True or envelope.get("dry") is not True: fail(f"{case['id']}: dry result not successful: {envelope}")
        if hashlib.sha256(output.read_bytes()).hexdigest()!=before: fail(f"{case['id']}: dry changed output")
        records.append({"case":case["id"],"real":"ok","dry":"ok","paragraphs":len(metrics["paragraphs"]),"tables":len(metrics["tables"]),"images":len(metrics["images"]),"links":len(metrics["links"])})
    records.extend(run_profile_unit_controls(compiler,host,evidence,env))
    (evidence/"results.json").write_text(json.dumps(records,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"cases":len(records),"results":records,"evidence":str(evidence/"results.json")},indent=2,ensure_ascii=False))

if __name__=="__main__": main()
