# One XML certificate for PDF and DOCX

`examples/education-certificate.lms` keeps the certificate body in checked `_xml_` blocks and sends the serialized XML to `Docx.html_xml(xml, css)`. The host parses the XML string itself; `_xml_ profile="html-subset@1"` checks well-formedness and the shared vocabulary before execution, while a host dry run checks its rendering rules without writing a DOCX.

The shared profile uses XHTML `div`/`article`, headings `h1`–`h3`, `p`, `ul`/`ol`/`li`, `table`/`tr`/`th`/`td`, and inline `span`/`strong`/`em`/`br`. Only `id` and `class` attributes are accepted. The CSS XML profile uses `*`, a single tag, `.class`, or `#id` selectors and `font-family`, `font-size`, `font-weight`, `font-style`, `color`, `text-align`, `margin-top`, and `margin-bottom`; lengths use `pt`. Links, images, inline style, browser recovery, external resources, and arbitrary CSS are outside this profile.

Run `lmscript --check examples/education-certificate.lms`, then `lmscript examples/education-certificate.lms [output.docx]`. To validate without writing the output, run `lmscript --dry-run --plan-format json examples/education-certificate.lms`; the plan includes the host's `dry:true` result envelope.

The legacy adapter remains the two-string `Docx.html_xml(string, string)` operation. New documents that need the expanded layout contract should use [`Docx.html_doc(string, string)`](html-doc-profile.md); it does not reinterpret or replace the legacy profile.
