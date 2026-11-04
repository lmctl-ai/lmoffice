# html_doc profile for DOCX

`Docx.html_doc(xml, css)` parses ordinary lmcode string values under the fixed
`html-doc@1` / `css-doc@1` contract and appends the resulting content to the
current document. It is additive: `Docx.html_xml(xml, css)` remains available
for the older `html-subset@1` / `css-subset@1` certificate examples.

The profile supports XHTML `article` and `div` containers; `h1`–`h3`, `p`,
`span`, `strong`, `em`, `br`, flat `ul` / `ol` lists, rectangular tables,
local PNG/JPEG images, and absolute HTTP, HTTPS, or mailto links. It uses
single-element, class, id, and universal CSS selectors. Supported properties
are `font-family`, `font-size`, `font-weight`, `font-style`, `color`,
`text-align`, paragraph margins, `page-break-before`, and `page-break-after`.
`@page` accepts Letter or A4 and four margins. Unknown elements, attributes,
properties, malformed values, unsafe image paths, and unsupported structure
are errors with source locations.

The DOCX writer sets page geometry (defaulting to Letter with 54pt margins on a
fresh document, or preserving prior document page geometry on additive calls
when `@page` is omitted), text styles, list instances, fixed table grids and
insets, repeatable first header rows, image extents/alt text, and hyperlink
relationships directly in OOXML. Dry execution parses the profile and reads and
decodes image data in memory; `save()` is skipped, so no output document is
created or replaced. Automatic pagination remains under Word's layout engine,
and font substitution can vary by viewer.

```lmscript
content = "<article xmlns=\"http://www.w3.org/1999/xhtml\"><h1>Quarterly update</h1><p>Capacity is <strong>stable</strong>.</p></article>";
styles = "<style xmlns=\"urn:lmctl:css:1\"><rule select=\"p\"><set name=\"margin-bottom\" value=\"6pt\"/></rule></style>";
s = load_schema(cli="lmoffice docx" install="github:lmctl-ai/lmoffice@v0.1.33");
p = _lmcode_ s;
let d = docx.create("update.docx");
d.html_doc(${content}, ${styles});
d.save();
end _lmcode_
r = run_lmcode(p);
require(r.ok, json_stringify(r));
```

The pinned shared corpus is in [`lmctl-ai/lmcode/tests/html-doc-conformance`](https://github.com/lmctl-ai/lmcode/tree/main/tests/html-doc-conformance).
