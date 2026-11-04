#!/usr/bin/env python3
"""Real compiler/host checks, OOXML validation and optional independent readers."""
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
HOST = Path(os.environ["LMOFFICE_BIN"]).resolve()
COMPILER = os.environ.get("LMSCRIPT_BIN") or shutil.which("lmscript")
ENV = dict(os.environ, PATH=str(HOST.parent) + os.pathsep + os.environ.get("PATH", ""))
CHECKS = 0
RESULT_MARKER = "LMOFFICE_TEST_RESULT:"


def check(name, condition, detail=""):
    global CHECKS
    if not condition:
        raise AssertionError(f"{name}: {detail}")
    CHECKS += 1
    print(f"ok {CHECKS} - {name}")


def invoke(args, expected=0, cwd=None, env=None):
    result = subprocess.run([str(a) for a in args], cwd=cwd, env=env or ENV, capture_output=True)
    if result.returncode != expected:
        raise AssertionError(f"{args}: expected exit {expected}, got {result.returncode}\n{result.stdout.decode('utf-8', 'replace')}\n{result.stderr.decode('utf-8', 'replace')}")
    return result


def terminal_frame(response):
    lines = response.stdout.decode("utf-8", "replace").splitlines()
    if len(lines) != 3 or lines[0] != "LMCODE_RETURN_BEGIN" or lines[2] != "LMCODE_RETURN_END" or response.stderr:
        raise AssertionError(f"expected one terminal lmcode frame and empty stderr: {response}")
    return json.loads(lines[1])


def compiler(*args, cwd=None, expected=0):
    command = [COMPILER, *map(str, args)]
    if os.name == "nt" and str(COMPILER).lower().endswith((".cmd", ".bat")):
        command = ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(command)]
    return invoke(command, expected=expected, cwd=cwd)


def run_lmscript(source, *options, cwd=None):
    response = compiler(*options, source, cwd=cwd or Path(source).parent)
    rows = [line[len(RESULT_MARKER):] for line in response.stdout.decode("utf-8", "replace").splitlines() if line.startswith(RESULT_MARKER)]
    if len(rows) != 1:
        raise AssertionError(f"expected one run_lmcode result marker from {source}: {response.stdout.decode('utf-8', 'replace')}\n{response.stderr.decode('utf-8', 'replace')}")
    return json.loads(rows[0]), response


def result(args, expected=0):
    # Source fixtures exercise the public run_lmcode path. Corrupt-bytecode and
    # CLI controls pass a binary directly to --lmcode.
    wrapper = None
    format = None
    if len(args) == 3 and args[0] in SCHEMAS and args[1] == "--lmcode" and Path(args[2]).suffix == ".lms":
        format, wrapper = args[0], Path(args[2])
    elif len(args) == 2 and args[0] == "--lmcode" and Path(args[1]).suffix == ".lms":
        wrapper = Path(args[1])
    if wrapper is not None:
        payload, _ = run_lmscript(wrapper, cwd=wrapper.parent)
        status = 0 if payload.get("ok") else 2 if payload.get("code") == "CLI_USAGE" else 4 if payload.get("code") == "APP_FAIL" else 3
        if status != expected:
            raise AssertionError(f"{wrapper}: expected host result status {expected}, got {status}: {payload}")
        return payload
    response = invoke([HOST, *args], expected)
    stdout = response.stdout.decode("utf-8", "replace")
    if "LMCODE_RETURN_BEGIN\n" in stdout:
        return terminal_frame(response)
    lines = response.stdout.splitlines()
    if len(lines) != 1 or response.stderr:
        raise AssertionError(f"expected one JSON line and empty stderr: {response}")
    return json.loads(lines[0])


def literal(value):
    return json.dumps(str(value).replace("\\", "/"), ensure_ascii=False)


SCHEMAS = {name: ROOT / "schema" / f"{name}.dsl.json" for name in ("docx", "xlsx", "pptx")}


def _format_for_body(body, explicit=None):
    unquoted = re.sub(r'"(?:\\.|[^"\\])*"', '""', body)
    found = set(re.findall(r"\b(docx|xlsx|pptx)\s*\.", unquoted))
    if explicit:
        if found and found != {explicit}:
            raise AssertionError(f"mixed schema body: {found} (explicit {explicit})")
        return explicit
    if len(found) != 1:
        raise AssertionError(f"cannot infer one schema from body: {sorted(found)}")
    return found.pop()


def write_wrapper(temp, name, body, schema, command):
    source = temp / (name + ".lms")
    host_command = json.dumps([*map(str, command), "--lmcode", "$DSLFILE"], ensure_ascii=False)
    source.write_text(
        f's = load_schema(schema={literal(schema)});\n'
        f'p = _lmcode_ s;\n{body}\nend _lmcode_\n'
        f'r = run_lmcode(p, {{command:{host_command}}});\n'
        f'println({json.dumps(RESULT_MARKER)} + json_stringify(r));\n',
        encoding="utf-8",
    )
    return source


def chunk(temp, name, body, format=None):
    format = _format_for_body(body, format)
    return write_wrapper(temp, name, body, SCHEMAS[format], [HOST, format])


def capture_fixture(temp, name, body, format):
    target = temp / (name + ".bin")
    helper = ROOT / "tests/capture-lmcode.py"
    source = write_wrapper(temp, name + "-capture", body, SCHEMAS[format], [sys.executable, helper, target])
    result, _ = run_lmscript(source, cwd=temp)
    if not result.get("ok") or not target.is_file():
        raise AssertionError(f"compiler fixture capture failed for {name}: {result}")
    return target


def dry_controls(temp, report_path):
    image = literal(temp / "dry-image.png")
    document = literal(temp / "dry-document.docx")
    body = f'docx.sample_image({image}); let d=docx.create({document}); d.heading("Dry probe",1).bold(true); d.save();'
    source = chunk(temp, "dry-effects", body, "docx")
    plan = compiler("--dry-run", source, cwd=temp)
    check("dry invocation validates typed-null document chain", b'"dry":true' in plan.stdout)
    check("dry skips image acquisition and document save", not (temp / "dry-image.png").exists() and not (temp / "dry-document.docx").exists())

    before = report_path.read_bytes()
    inspect = f'$return = str_len(docx.inspect({literal(report_path)}));'
    source = chunk(temp, "dry-readonly-inspect", inspect, "docx")
    plan = compiler("--dry-run", source, cwd=temp)
    check("dry read-only inspect validates an existing document", b'"dry":true' in plan.stdout and b'"result":' in plan.stdout)
    check("dry read-only inspect leaves document bytes unchanged", report_path.read_bytes() == before)


def manifest_controls(temp):
    missing = temp / "must-not-load.lmcode"
    manifest = temp / "invocation.json"
    parts = [{"index": 0, "file": str(missing)}]
    invalid = [
        ("missing dry", {"version": 1, "mode": "single", "parts": parts}),
        ("string dry", {"version": 1, "mode": "single", "dry": "false", "parts": parts}),
        ("null dry", {"version": 1, "mode": "single", "dry": None, "parts": parts}),
        ("numeric dry", {"version": 1, "mode": "single", "dry": 0, "parts": parts}),
    ]
    for label, payload in invalid:
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        env = dict(ENV, LMCODE_INVOCATION_FILE=str(manifest))
        response = invoke([HOST, "docx", "--lmcode", missing], 2, cwd=temp, env=env)
        frame = terminal_frame(response)
        check(f"{label} rejected before dispatch", frame["phase"] == "cli" and frame["code"] == "CLI_USAGE" and "LOAD_BAD_BYTECODE" not in frame["message"])

    for dry, expected_marker in ((False, False), (True, True)):
        manifest.write_text(json.dumps({"version": 1, "mode": "single", "dry": dry, "parts": parts}), encoding="utf-8")
        env = dict(ENV, LMCODE_INVOCATION_FILE=str(manifest))
        response = invoke([HOST, "docx", "--lmcode", missing], 3, cwd=temp, env=env)
        frame = terminal_frame(response)
        check(f"valid dry={str(dry).lower()} manifest reaches loader", frame["phase"] == "load" and frame.get("dry", False) == expected_marker)

    first, second = temp / "part-0.lmcode", temp / "part-1.lmcode"
    manifest.write_text(json.dumps({"version": 1, "mode": "builder", "dry": False, "parts": [
        {"index": 0, "file": str(first)}, {"index": 1, "file": str(second)},
    ]}), encoding="utf-8")
    env = dict(ENV, LMCODE_INVOCATION_FILE=str(manifest))
    response = invoke([HOST, "docx", "--lmcode", second, "--lmcode", first], 3, cwd=temp, env=env)
    frame = terminal_frame(response)
    message = frame["message"].replace("\\", "/").casefold()
    check("builder dispatch follows manifest identity and reports part zero", frame["phase"] == "load" and frame.get("part") == 0 and first.name.casefold() in message, frame)


def error_case(temp, name, body, status, code, message):
    format = _format_for_body(body)
    bytecode = chunk(temp, name, body)
    failure = result([format, "--lmcode", bytecode], status)
    check(name, failure.get("ok") is False and failure.get("code") == code
          and message.lower() in failure.get("message", "").lower() and failure.get("line", 0) > 0, failure)


def consumers(outputs):
    if importlib.util.find_spec("docx"):
        from docx import Document
        doc = Document(outputs["report.lms"])
        check("python-docx report table and image", doc.tables[0].cell(1, 0).text == "Revenue" and len(doc.inline_shapes) == 1)
        picture = doc.inline_shapes[0]._inline.graphic.graphicData.pic
        check("python-docx recognizes Word picture namespace", picture is not None)
        image_part = doc.part.related_parts[picture.blipFill.blip.embed]
        check("python-docx resolves embedded PNG", image_part.image.px_width == 64 and image_part.image.px_height == 64)
        check("python-docx headings and properties", doc.paragraphs[0].style.name == "Heading 1" and doc.core_properties.title == "Quarterly report")
        check("python-docx header and footer", "Lattice" in doc.sections[0].header.paragraphs[0].text and "Confidential" in doc.sections[0].footer.paragraphs[0].text)
        for name in ("invoice.lms", "meetingminutes.lms"):
            other = Document(outputs[name])
            check("python-docx opens " + name, bool(other.paragraphs))
        for name, path in outputs.items():
            if path.suffix == ".docx":
                other = Document(path)
                check("python-docx opens " + name, bool(other.paragraphs or other.tables))
    else:
        print("SKIP independent DOCX reader: python-docx not installed")
    if importlib.util.find_spec("openpyxl"):
        import openpyxl
        book = openpyxl.load_workbook(outputs["budgetxlsx.lms"])
        sheet = book["Budget"]
        check("openpyxl values and formulas", sheet["B2"].value == 80000 and sheet["D2"].value == "=B2-C2")
        check("openpyxl styles and format", sheet["A1"].font.bold and sheet["A1"].fill.fgColor.rgb == "FFD9EAF7" and sheet["B2"].number_format == "$#,##0.00")
        check("openpyxl merge and freeze", "A7:D7" in sheet.merged_cells and sheet.freeze_panes == "A2")
        check("openpyxl column width", sheet.column_dimensions["A"].width == 22)
        other = openpyxl.load_workbook(outputs["multisheet.lms"])
        check("openpyxl multi-sheet typed values", other.sheetnames == ["Assumptions", "Data", "Summary"] and other["Data"]["B6"].value is True and other["Data"]["B7"].value == 3)
        
        # New feature checks on XLSX
        inv_book = openpyxl.load_workbook(outputs["invoice_tracker.lms"])
        inv_sheet = inv_book["Invoices"]
        check("openpyxl data validation list", len(inv_sheet.data_validations.dataValidation) >= 1)
        check("openpyxl conditional formatting", len(inv_sheet.conditional_formatting) >= 1)
        check("openpyxl autofilter ref", inv_sheet.auto_filter.ref == "A4:G10")
        check("openpyxl tab color", inv_sheet.sheet_properties.tabColor.rgb == "FF4472C4")
        
        gantt_book = openpyxl.load_workbook(outputs["project_gantt.lms"])
        check("openpyxl gantt conditional rules", len(gantt_book["Gantt Schedule"].conditional_formatting) >= 2)
        
        cap_book = openpyxl.load_workbook(outputs["cap_table.lms"])
        check("openpyxl named ranges", "TotalShares" in cap_book.defined_names)
        
        exp_book = openpyxl.load_workbook(outputs["expense_report.lms"])
        check("openpyxl comment readback", exp_book["Expense Report"]["D10"].comment is not None and "Receipt" in exp_book["Expense Report"]["D10"].comment.text)

        for name, path in outputs.items():
            if str(path).endswith(".xlsx"):
                wb = openpyxl.load_workbook(path)
                check(f"openpyxl opens {name}", len(wb.sheetnames) >= 1)
    else:
        print("SKIP independent XLSX reader: openpyxl not installed")
    if importlib.util.find_spec("pptx"):
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
        deck = Presentation(outputs["5slidedeck.lms"])
        check("python-pptx five slides and title", len(deck.slides) == 5 and deck.slides[0].shapes.title.text == "Project briefing")
        check("python-pptx slide dimensions", deck.slide_width == 12192000 and deck.slide_height == 6858000)
        check("python-pptx speaker notes", "Opening context" in deck.slides[0].notes_slide.notes_text_frame.text)
        images = [shape for slide in deck.slides for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE]
        check("python-pptx image readback", len(images) == 1 and images[0].image.size == (64, 64))
        
        # New feature checks on PPTX
        qbr = Presentation(outputs["quarterly_business_review.lms"])
        check("python-pptx qbr slides", len(qbr.slides) == 5)
        qbr_tables = [s for s in qbr.slides[2].shapes if s.has_table]
        check("python-pptx qbr table", len(qbr_tables) == 1 and len(qbr_tables[0].table.rows) == 5 and len(qbr_tables[0].table.columns) == 4)
        
        pitch = Presentation(outputs["pitch_deck.lms"])
        check("python-pptx pitch deck slides", len(pitch.slides) == 6)
        
        launch = Presentation(outputs["product_launch.lms"])
        launch_tables = [s for s in launch.slides[3].shapes if s.has_table]
        check("python-pptx launch table", len(launch_tables) == 1 and launch_tables[0].table.cell(0, 1).text == "Vanguard 3.0")

        for name, path in outputs.items():
            if str(path).endswith(".pptx"):
                p_deck = Presentation(path)
                check(f"python-pptx opens {name}", len(p_deck.slides) >= 1)
    else:
        print("SKIP independent PPTX reader: python-pptx not installed")


def rendering(outputs, temp, summaries):
    soffice = None
    for cand in ([] if os.environ.get("LMOFFICE_DISABLE_RENDER") == "1" else [
        os.environ.get("LMOFFICE_SOFFICE") or os.environ.get("SOFFICE"),
        shutil.which("soffice"),
        *map(str, sorted((Path.home() / "tools/libreoffice").glob("opt/libreoffice*/program/soffice"))),
    ]):
        if cand and os.path.exists(cand) and os.access(cand, os.X_OK):
            soffice = cand
            break
    if not soffice:
        # Preserve two deterministic checks on runners without a renderer. The
        # reader validations still exercise the completed package in both formats.
        workbook = summaries["monthly_budget.lms"]
        deck = summaries["quarterly_business_review.lms"]
        check("renderer-free workbook package remains valid", workbook["valid"] and workbook["sheets"] == 1 and "Monthly" in workbook["text"])
        check("renderer-free deck package remains valid", deck["valid"] and deck["slides"] == 5 and "Quarterly Business Review" in deck["text"])
        return
    for sample in ["monthly_budget.lms", "quarterly_business_review.lms"]:
        in_path = outputs[sample]
        cmd = [soffice, "-env:UserInstallation=" + (temp / "lo-profile").as_uri(), "--headless", "--convert-to", "pdf", "--outdir", str(temp), str(in_path)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        pdf_name = in_path.stem + ".pdf"
        out_pdf = temp / pdf_name
        check(f"soffice render {sample} to pdf", res.returncode == 0 and out_pdf.exists() and out_pdf.stat().st_size > 0)


def check_readme_images():
    completed = subprocess.run([sys.executable, str(ROOT / "scripts/check-gallery.py")], capture_output=True, text=True)
    check("README images resolve to committed, bounded previews", completed.returncode == 0, completed.stdout + completed.stderr)


def main():
    if not COMPILER:
        raise AssertionError("lmscript is required; install @lmctl-ai/lmctl or set LMSCRIPT_BIN")
    version_text = compiler("--version").stdout.decode()
    version = re.search(r"(\d+)\.(\d+)\.(\d+)", version_text)
    check("compiler supports built-in std", version is not None and tuple(map(int, version.groups())) >= (0, 2, 420), version_text)
    expected_types = {"docx": {"DocxHost", "Docx", "Paragraph", "Table"}, "xlsx": {"XlsxHost", "Xlsx", "Sheet"}, "pptx": {"PptxHost", "Pptx", "Slide", "PptxTable"}}
    check("combined schema is removed", not (ROOT / "schema/lmoffice.dsl.json").exists())
    standard_signatures = None
    for format in SCHEMAS:
        parsed = json.loads(SCHEMAS[format].read_text())
        check(f"{format} exposes only its own types and context", set(parsed["types"]) == expected_types[format] and parsed["context"] == {format: format.capitalize() + "Host"})
        check(f"embedded {format} schema byte identity", invoke([HOST, format, "--lmcode-schema", "--json"]).stdout == SCHEMAS[format].read_bytes())
        compiler_signatures = compiler("--lmcode-signatures", SCHEMAS[format]).stdout.splitlines()
        host_signatures = invoke([HOST, format, "--lmcode-signatures"]).stdout.splitlines()
        check(f"{format} compiler/registry signature parity", compiler_signatures == host_signatures)
        check(f"{format} schema omits built-in std", not parsed.get("functions"))
        host_only = invoke([HOST, format, "--lmcode-signatures", "--without-std"]).stdout.splitlines()
        check(f"{format} host-only signature parity", compiler("--lmcode-signatures", SCHEMAS[format], "--without-std").stdout.splitlines() == host_only)
        check(f"{format} host signatures are retained in full output", set(host_only) <= set(host_signatures))
        current_std = set(host_signatures) - set(host_only)
        if standard_signatures is None:
            standard_signatures = current_std
        check(f"{format} has the same complete std catalog", current_std == standard_signatures and {
            b"fn str_upper(string) -> string", b"fn math_abs(int) -> int",
            b"fn str_list() -> StrList", b"fn str_map() -> StrMap",
            b"method StrList.add(string) -> StrList", b"method StrMap.get(string) -> string",
            b"fn file_read(string) -> string", b"fn file_write(string, string) -> void"
        } <= current_std, sorted(current_std))
        check(f"{format} registers str_len", b"fn str_len(string) -> int" in host_signatures)
        summary = invoke([HOST, format, "--lmcode-schema"]).stdout.decode().replace("\r\n", "\n")
        check(f"{format} schema summary convention", summary.startswith(f"context {format}:") and format.capitalize() in summary)
    # Exercise the shared byte-length function through every real subcommand.
    with tempfile.TemporaryDirectory(prefix="lmoffice-stdlib-") as directory:
        temp = Path(directory)
        import std_families
        std_families.run(sys.modules[__name__], temp)
        for format in SCHEMAS:
            body = 'let empty = str_len(""); let ascii = str_len("aXb"); let utf8 = str_len("é");' + f' if (empty != 0 || ascii != 3 || utf8 != 2) {{ {format}.create("wrong-length").save(); }}'
            probe = chunk(temp, f"stdlib-{format}", body, format)
            check(f"{format} str_len UTF-8/NUL byte counts", result([format, "--lmcode", probe])["ok"])
        raw_fixture = capture_fixture(temp, "docx-strlen-v6", 'if (str_len("aXb") != 3) { docx.create("wrong-len.docx").save(); }', "docx")
        raw = raw_fixture.read_bytes()
        raw_nul = temp / "strlen-nul.bin"
        raw_nul.write_bytes(raw.replace(b"aXb", b"a\x00b", 1))
        check("str_len preserves embedded NUL bytes", result(["docx", "--lmcode", raw_nul])["ok"] and not (temp / "wrong-len.docx").exists())
        check("cross-format bytecode schema mismatch", result(["xlsx", "--lmcode", raw_fixture], 3)["code"] == "LOAD_SCHEMA_MISMATCH")
        wrong = temp / "wrong-format.lms"
        wrong.write_text('s = load_schema(schema=' + literal(SCHEMAS["docx"]) + ');\np = _lmcode_ s;\nlet foreign = xlsx.create("wrong.xlsx");\nend _lmcode_\n', encoding="utf-8")
        refused = compiler(wrong, expected=2)
        check("compiler refuses foreign context", b"xlsx" in refused.stderr)
    check("embedded version", invoke([HOST, "--version"]).stdout.decode().strip() == "lmoffice " + (ROOT / "VERSION").read_text().strip())
    check_readme_images()
    unified_schema = json.loads(invoke([HOST, "--lmcode-schema", "--json"]).stdout)
    check("root schema exposes all office formats", unified_schema["context"] == {"docx": "DocxHost", "xlsx": "XlsxHost", "pptx": "PptxHost", "office": "OfficeFacade"})
    check("root schema contains each format host type", all(name in unified_schema["types"] for name in ("DocxHost", "XlsxHost", "PptxHost", "OfficeFacade")))
    root_summary = invoke([HOST, "--lmcode-schema"]).stdout.decode()
    check("root schema summary includes the office facade", "context office: OfficeFacade" in root_summary)
    root_signatures = invoke([HOST, "--lmcode-signatures"]).stdout.decode()
    check("root signatures include office facade methods", "context office: OfficeFacade" in root_signatures and "OfficeFacade.docx" in root_signatures)
    for args in [[], ["--lmcode"], ["--lmcode-schema", "--json", "extra"], ["--lmcode-signatures", "extra"], ["--lmcode", "--schema"], ["--inspect", "--bad"], ["--to-markdown"], ["--to-markdown", "--bad"]]:
        response = invoke([HOST, *args], 2)
        frame = terminal_frame(response)
        check("top-level invalid usage " + " ".join(args), frame["phase"] == "cli" and frame["code"] == "CLI_USAGE")
    with tempfile.TemporaryDirectory(prefix="lmoffice-retired-flags-") as directory:
        missing = Path(directory) / "must-not-open.lmcode"
        routes = [[], ["docx"], ["xlsx"], ["pptx"]]
        for route in routes:
            for flag, extra in (("--first", [str(missing)]), ("--last", [str(missing)]), ("--dsl", [str(missing)]), ("--dsl-schema", ["--json"]), ("--dsl-signatures", [])):
                response = invoke([HOST, *route, flag, *extra], 2)
                frame = terminal_frame(response)
                check("retired route refused before dispatch " + " ".join([*route, flag]), frame["phase"] == "cli" and frame["code"] == "CLI_USAGE" and str(missing) not in frame["message"])
    with tempfile.TemporaryDirectory(prefix="lmoffice-root-cli-") as directory:
        temp = Path(directory)
        document = temp / "root-cli.docx"
        root_schema = temp / "lmoffice.json"
        root_schema.write_bytes(invoke([HOST, "--lmcode-schema", "--json"]).stdout)
        source = write_wrapper(temp, "root-cli", f'let d = office.docx({literal(document)}); d.paragraph("root CLI"); d.save();', root_schema, [HOST])
        result(["--lmcode", source])
        check("root lmoffice CLI executes the office facade", document.is_file() and result(["inspect", document])["result"]["valid"])
        builder = temp / "builder.lms"
        builder.write_text(
            f's = load_schema(schema={literal(SCHEMAS["docx"])});\n'
            'p1 = _lmcode_ s;\n$return = 11;\nend _lmcode_\n'
            'p2 = _lmcode_ s;\n$return = 22;\nend _lmcode_\n'
            f'b = lmcode_build({json.dumps([str(HOST), "docx"])});\n'
            'b.add(p1); b.add(p2);\n'
            'r = run_lmcode(b);\n'
            f'println({json.dumps(RESULT_MARKER)} + json_stringify(r));\n',
            encoding="utf-8",
        )
        built, _ = run_lmscript(builder, cwd=temp)
        check("builder manifest preserves part order and result sinks", built.get("ok") and built.get("parts") == 2 and built.get("result") == [11, 22], built)
    for format in SCHEMAS:
        response = invoke([HOST, format, "--help"])
        check(f"{format} help", response.stdout and f"lmoffice {format}".encode() in response.stdout)
    unknown = invoke([HOST, "unknown"], 2)
    unknown_frame = terminal_frame(unknown)
    check("unknown subcommand lists formats", unknown_frame["phase"] == "cli" and all(name in unknown_frame["message"] for name in ("docx", "xlsx", "pptx")))
    with tempfile.TemporaryDirectory(prefix="lmoffice-test-") as directory:
        temp = Path(directory)
        manifest_controls(temp)
        gallery = json.loads((ROOT / "docs/gallery.json").read_text(encoding="utf-8"))["examples"]
        outputs = {entry["name"] + ".lms": temp / entry["output"] for entry in gallery}
        summaries = {}
        for name, output in outputs.items():
            if name == "education-certificate.lms":
                source = (ROOT / "examples" / name).read_text(encoding="utf-8")
                xml_match = re.search(r'content = _xml_ profile="html-subset@1";\n(.*?)\nend _xml_', source, re.S)
                css_match = re.search(r'styles = _xml_ profile="css-subset@1";\n(.*?)\nend _xml_', source, re.S)
                if xml_match and css_match:
                    xml, css = xml_match.group(1), css_match.group(1)
                else:
                    # Public examples use local lmcode schema values; probe the legacy adapter with raw strings.
                    xml = '<article xmlns="http://www.w3.org/1999/xhtml"><h1>Certificate of Completion</h1><p>Jordan Rivera</p><table><tr><th>Program</th><td>Community Data Studio</td></tr><tr><th>Certificate</th><td>NS-2027-041</td></tr></table></article>'
                    css = '<style xmlns="urn:lmctl:css:1"><rule select="p"><set name="margin-bottom" value="6pt"/></rule></style>'
                body = f'docx.create({literal(output)}).title("Certificate of Completion").html_xml({literal(xml)}, {literal(css)}).save();'
                compiled = chunk(temp, "education-certificate-host", body, "docx")
                result(["docx", "--lmcode", compiled])
                data = result(["inspect", output])
                check("example validated " + name, data["ok"] and data["result"]["valid"] and "Jordan Rivera" in data["result"]["text"])
                summaries[name] = data["result"]
                continue
            compiler(ROOT / "examples" / name, output, cwd=temp)
            format = next(entry["kind"] for entry in gallery if entry["name"] == name[:-4])
            data = result(["inspect", output])
            check("example validated " + name, data["ok"] and data["result"]["valid"])
            summaries[name] = data["result"]
        dry_controls(temp, outputs["report.lms"])
        # Format-specific Markdown extraction refuses a package from another format.
        check("docx rejects xlsx Markdown extraction", result(["docx", "--to-markdown", outputs["budgetxlsx.lms"]], 3)["ok"] is False)
        check("xlsx rejects docx Markdown extraction", result(["xlsx", "--to-markdown", outputs["report.lms"]], 3)["ok"] is False)
        check("pptx rejects docx Markdown extraction", result(["pptx", "--to-markdown", outputs["report.lms"]], 3)["ok"] is False)
        check("report structure", summaries["report.lms"]["tables"] == 1 and summaries["report.lms"]["images"] == 1 and "Revenue" in summaries["report.lms"]["text"])
        check("invoice content", "INV-1042" in summaries["invoice.lms"]["text"] and summaries["invoice.lms"]["tables"] == 1)
        check("minutes content", "Action items" in summaries["meetingminutes.lms"]["text"] and summaries["meetingminutes.lms"]["paragraphs"] >= 7)
        check("workbook summaries", summaries["budgetxlsx.lms"]["sheets"] == 1 and summaries["multisheet.lms"]["sheets"] == 3 and "=SUM(B2:B4)" in summaries["budgetxlsx.lms"]["text"])
        check("deck summary", summaries["5slidedeck.lms"]["slides"] == 5 and "Project briefing" in summaries["5slidedeck.lms"]["text"])
        check("task xlsx summaries", summaries["sales_dashboard.lms"]["sheets"] == 2 and summaries["monthly_budget.lms"]["sheets"] == 1 and summaries["cap_table.lms"]["sheets"] == 1)
        check("task pptx summaries", summaries["quarterly_business_review.lms"]["slides"] == 5 and summaries["pitch_deck.lms"]["slides"] == 6 and summaries["annual_report.lms"]["slides"] == 5)
        for name, total in (("cross-workbook-memo.lms", "155000"), ("cross-workbook-briefing.lms", "414000")):
            companion = Path(str(outputs[name]) + ".xlsx")
            check("cross-format workbook validates " + name, result(["inspect", companion])["result"]["valid"])
            check("cross-format outer readback reaches document " + name, total in summaries[name]["text"] and "=SUM(B2:B4)" in summaries[name]["text"])
        for format in ("docx", "pptx"):
            failure = result([format, "--to-markdown", outputs["budgetxlsx.lms"]], 3)
            check(f"{format} extraction refuses a workbook", failure["code"] == "RUN_HOST" and f".{format}" in failure["message"], failure)
        consumers(outputs)
        import docx_round3, xlsx_round3, pptx_round3, markdown_syntax, markdown_docx, markdown_office, markdown_export, markdown_io
        for suite in (docx_round3, xlsx_round3, pptx_round3, markdown_syntax, markdown_docx, markdown_office, markdown_export, markdown_io):
            suite.run(sys.modules[__name__], temp, outputs)
        # Regenerate image/chart/comment-rich packages and compare actual bytes.
        for name in ("report.lms", "finance-profit-loss.lms", "marketing-brand-guidelines.lms"):
            output = outputs[name]
            original = output.read_bytes()
            compiler(ROOT / "examples" / name, output, cwd=temp)
            check("deterministic package " + name, original == output.read_bytes())
        rendering(outputs, temp, summaries)
        import docx_genres
        docx_genres.run(sys.modules[__name__], temp)
        inspected = chunk(temp, "inspect-in-lmcode", f'let summary = docx.inspect({literal(outputs["report.lms"])}); if (summary == "") {{ docx.create("").save(); }}')
        check("Docx.inspect through run_lmcode", result(["docx", "--lmcode", inspected])["ok"])
        # Ensure fluent style replacement, UTF-8 boundaries, and every document's lifecycle are exercised.
        doc = literal(temp / "error.docx")
        sheet = 'let d = xlsx.create(' + literal(temp / "error.xlsx") + '); let s = d.sheet("Data"); '
        deck = 'let d = pptx.create(' + literal(temp / "error.pptx") + '); let s = d.slide(); '
        cases = [
            ("bad-color", f'docx.create({doc}).paragraph("x").color("#12345");', 3, "RUN_HOST", "#RRGGBB"),
            ("table-row", f'docx.create({doc}).table(1, 1).cell(2, 1, "x");', 3, "RUN_HOST", "range"),
            ("table-col", f'docx.create({doc}).table(1, 1).cell(1, 2, "x");', 3, "RUN_HOST", "range"),
            ("sheet-row", sheet + 's.set(0, 1, "x");', 3, "RUN_HOST", "row"),
            ("sheet-col", sheet + 's.set(1, 16385, "x");', 3, "RUN_HOST", "column"),
            ("overlap-merge", sheet + 's.merge(1,1,2,2).merge(2,2,3,3);', 3, "RUN_HOST", "overlap"),
            ("docx-save-twice", f'let d=docx.create({doc}); d.save(); d.save();', 3, "RUN_HOST", "already"),
            ("xlsx-save-twice", sheet + 'd.save(); d.save();', 3, "RUN_HOST", "already"),
            ("pptx-save-twice", deck + 'd.save(); d.save();', 3, "RUN_HOST", "already"),
            ("post-save-paragraph", f'let d=docx.create({doc}); let p=d.paragraph("x"); d.save(); p.bold(true);', 3, "RUN_HOST", "saved"),
            ("post-save-sheet", sheet + 'd.save(); s.set(1,1,"late");', 3, "RUN_HOST", "saved"),
            ("post-save-slide", deck + 'd.save(); s.title("late");', 3, "RUN_HOST", "saved"),
            ("unwritable", f'docx.create({literal(temp / "missing-parent" / "no.docx")}).save();', 4, "APP_FAIL", ""),
            ("bad-image-size", f'docx.create({doc}).image({literal(str(outputs["report.lms"]) + ".png")},0,1);', 3, "RUN_HOST", "positive"),
            ("bad-slide-size", deck + 's.rect(0.0,0.0,0.0,10.0,"#112233");', 3, "RUN_HOST", "positive"),
        ]
        for name, body, status, code, message in cases:
            error_case(temp, name, body, status, code, message)
        unicode_doc = temp / "unicode.docx"
        success = chunk(temp, "unicode", f'let d=docx.create({literal(unicode_doc)}); d.paragraph("café 日本").size(14.0).bold(true).italic(true).align("center"); d.save();')
        result(["docx", "--lmcode", success])
        check("UTF-8 document boundary", "café 日本" in result(["inspect", unicode_doc])["result"]["text"])
        original_raw = capture_fixture(temp, "docx-sentinel-v6", 'let d = docx.create("unused.docx"); d.paragraph("BYTE_SENTINEL_937");', "docx").read_bytes()
        for name, byte, message in [("invalid-utf8", 255, "valid UTF-8"), ("nul-text", 0, "XML 1.0")]:
            data = bytearray(original_raw)
            data[data.index(b"BYTE_SENTINEL_937")] = byte
            mutated = temp / (name + ".bin")
            mutated.write_bytes(data)
            failure = result(["docx", "--lmcode", mutated], 3)
            check(name + " rejected at host boundary", failure["code"] == "RUN_HOST" and message in failure["message"])
        malformed = temp / "malformed.bin"
        malformed.write_bytes(b"DSLB\x00\x05")
        check("truncated bytecode", result(["docx", "--lmcode", malformed], 3)["code"] == "LOAD_BAD_BYTECODE")
        original = bytearray(original_raw)
        original[6] ^= 1
        malformed.write_bytes(original)
        check("schema hash mismatch", result(["docx", "--lmcode", malformed], 3)["code"] == "LOAD_SCHEMA_MISMATCH")
        schema_fixture = capture_fixture(temp, "docx-schema-v6", 'let d = docx.create("unused.docx"); d.paragraph("schema");', "docx")
        check("cross-format schema hash refusal", result(["xlsx", "--lmcode", schema_fixture], 3)["code"] == "LOAD_SCHEMA_MISMATCH")
        check("missing inspect file", result(["inspect", temp / "absent.docx"], 4)["code"] == "APP_FAIL")
        invalid = temp / "invalid.docx"
        invalid.write_bytes(b"invalid package")
        check("invalid document reports JSON", result(["inspect", invalid], 4)["code"] == "APP_FAIL")
    print(f"PASS {CHECKS} integration checks")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, OSError, subprocess.SubprocessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        sys.exit(1)
