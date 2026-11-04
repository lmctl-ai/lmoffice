#!/usr/bin/env python3
"""End-to-end shared XML sample and host dry validation through lmscript."""
import argparse
import atexit
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile
import xml.etree.ElementTree as ET


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def transformed(source):
    def take(name, profile):
        nonlocal source
        pattern = rf'{name} = _xml_ profile="{profile}";\n(.*?)\nend _xml_'
        match = re.search(pattern, source, re.S)
        require(match is not None, f"missing {name} {profile} block")
        value = match.group(1)
        replacement = f'{name} = {json.dumps(value)};'
        source = re.sub(pattern, lambda _: replacement, source, count=1, flags=re.S)
        return value

    take("content", "html-subset@1")
    take("styles", "css-subset@1")
    source = source.replace("let xml = content.toString();", "let xml = content;")
    source = source.replace("let css = styles.toString();", "let css = styles;")
    return source


def invoke(compiler, source, args=(), options=(), env=None):
    with tempfile.TemporaryDirectory(prefix="shared-xml-lmscript-") as folder:
        path = Path(folder) / "sample.lms"
        path.write_text(source, encoding="utf-8")
        command = [compiler, *options, str(path), *args]
        if os.name == "nt" and compiler.lower().endswith((".cmd", ".bat")):
            import subprocess as sp
            command = ["cmd.exe", "/d", "/s", "/c", sp.list2cmdline(command)]
        return subprocess.run(command, env=env, text=True, capture_output=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--binary", required=True, help="built host executable")
    parser.add_argument("--example", required=True)
    parser.add_argument("--kind", choices=("pdf", "docx"), required=True)
    args = parser.parse_args()
    source = transformed(Path(args.example).read_text(encoding="utf-8"))
    schema = (Path(args.example).resolve().parents[1] / "schema" / "docx.dsl.json").as_posix()
    source = source.replace(
        'load_schema(schema="../schema/docx.dsl.json")',
        f"load_schema(schema={json.dumps(schema)})",
    )
    binary = Path(args.binary).resolve()
    bind_dir = tempfile.TemporaryDirectory(prefix="shared-xml-bin-", dir=binary.parent)
    atexit.register(bind_dir.cleanup)
    command_name = ("lmpdf" if args.kind == "pdf" else "lmoffice") + (".exe" if os.name == "nt" else "")
    os.link(binary, Path(bind_dir.name) / command_name)
    env = dict(os.environ)
    env["PATH"] = bind_dir.name + os.pathsep + env.get("PATH", "")
    host = str(binary)
    with tempfile.TemporaryDirectory(prefix="shared-xml-output-") as folder:
        output = Path(folder) / ("certificate." + args.kind)
        real = invoke(args.compiler, source, [str(output)], env=env)
        require(real.returncode == 0, real.stdout + real.stderr)
        require(output.is_file() and output.stat().st_size > 0, "real run did not create the document")
        if args.kind == "docx":
            with zipfile.ZipFile(output) as package:
                bad = package.testzip()
                require(bad is None, f"bad docx ZIP member {bad}")
                document = ET.fromstring(package.read("word/document.xml"))
                text = "".join(node.text or "" for node in document.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"))
                for expected in ("Jordan Rivera", "Community Data Studio", "NS-2027-041"):
                    require(expected in text, f"DOCX missing {expected!r}")
        else:
            inspect = subprocess.run([host, "inspect", str(output)], text=True, capture_output=True)
            require(inspect.returncode == 0 and not inspect.stderr, inspect.stdout + inspect.stderr)
            detail = json.loads(inspect.stdout)["result"]
            require(detail.get("pages") == 1, str(detail))
            extraction = subprocess.run([host, "docx", "--to-markdown", str(output)], text=True, capture_output=True)
            require(extraction.returncode == 0 and not extraction.stderr, extraction.stdout + extraction.stderr)
            text = detail["text"]
            for expected in ("Jordan Rivera", "Community Data Studio", "NS-2027-041"):
                require(expected in text, f"PDF missing {expected!r}: {text}")

        dry = invoke(args.compiler, source, [str(output)], ["--dry-run", "--plan-format", "json"], env)
        require(dry.returncode == 0, dry.stdout + dry.stderr)
        plan = json.loads(dry.stdout)
        envelope = plan["entries"][0]["envelope"]
        require(envelope.get("dry") is True and envelope.get("ok") is True, str(plan))

        for label, bad_xml, error in (
            ("unknown element", '<div xmlns="http://www.w3.org/1999/xhtml"><script/></div>', "unsupported element <script>"),
            ("bad attribute", '<div xmlns="http://www.w3.org/1999/xhtml"><p onclick="x">x</p></div>', "unsupported attribute 'onclick'"),
            ("bad nesting", '<div xmlns="http://www.w3.org/1999/xhtml"><ul><p>x</p></ul></div>', "not allowed in <ul>"),
        ):
            markup = json.dumps(bad_xml)
            schema = (Path(args.example).resolve().parents[1] / "schema" / "docx.dsl.json").as_posix()
            probe = f'''markup = {markup};
p = _lmcode_ schema={json.dumps(schema)};
let d = docx.create("unused.{args.kind}");
d.html_xml(${{markup}}, "");
end _lmcode_
r = run_lmcode(p, {{command:["lmoffice","docx","--lmcode","$DSLFILE"]}});
'''
            result = invoke(args.compiler, probe, options=["--dry-run", "--plan-format", "json"], env=env)
            require(result.returncode == 0, f"{label}: {result.stdout}{result.stderr}")
            plan = json.loads(result.stdout)
            envelope = plan["entries"][0]["envelope"]
            require(envelope.get("dry") is True and envelope.get("ok") is False, f"{label}: {plan}")
            require(error in envelope.get("message", ""), f"{label}: {envelope}")
            require("line 1 column" in envelope.get("message", ""), f"{label} missing location: {envelope}")
    print(f"shared XML {args.kind}: real render, dry validation and 3 located controls PASS")


if __name__ == "__main__":
    main()
