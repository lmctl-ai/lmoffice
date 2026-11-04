"""Exercise compiler-built-in std against every format's real native registry."""


def run(api, temp):
    for format in api.SCHEMAS:
        path = temp / (format + "-std.txt")
        body = f'''let upper = str_upper("lmoffice");
if (upper != "LMOFFICE" || str_len("é") != 2) {{ {format}.create("").save(); }}
let magnitude = math_abs(-37);
if (magnitude != 37 || math_sqrt(81) != 9 || math_abs(-2.5) != 2.5) {{ {format}.create("").save(); }}
let items = str_list();
items.add("é").add("日本");
if (items.len() != 2 || items.at(0) != "é" || items.join("|") != "é|日本") {{ {format}.create("").save(); }}
let values = str_map();
values.set("heading", upper).set("body", items.at(1));
if (values.len() != 2 || !values.has("body") || values.get("heading") != "LMOFFICE") {{ {format}.create("").save(); }}
file_write({api.literal(path)}, "é\\n");
file_append({api.literal(path)}, values.get("body"));
if (!file_exists({api.literal(path)}) || file_read({api.literal(path)}) != "é\\n日本") {{ {format}.create("").save(); }}
let lines = file_lines({api.literal(path)});
if (lines.len() != 2 || lines.at(0) != items.at(0) || lines.at(1) != values.get("body")) {{ {format}.create("").save(); }}'''
        bytecode = api.chunk(temp, "std-families-" + format, body, format)
        response = api.result([format, "--lmcode", bytecode])
        api.check(f"{format} executes string/math/StrList/StrMap/file std", response["ok"], response)
        api.check(f"{format} std file byte round trip", path.read_bytes() == "é\n日本".encode("utf-8"))
