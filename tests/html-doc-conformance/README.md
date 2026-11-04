# HTML document profile cross-host corpus

This is the canonical pre-adapter corpus for html-doc@1 / css-doc@1. The corpus home is the public lmctl-ai/lmcode specification repository, under tests/, alongside its language-neutral conformance assets. The suggested lmctl-ai/lmcode-style repository does not exist. lmpdf, lmoffice, and mono test jobs can sync this directory from a pinned lmcode commit; do not regenerate expected traces from a host run.

corpus.json pins the profile IDs, asset digest, immutable legacy profile digests, and normalized expected document structure, text blocks, styles, and table grids. release-baseline.json pins the measured Linux x64 behavior of lmpdf v0.2.6 and lmoffice v0.1.31, including locations and messages from dry failures. That release baseline is deliberately red where today’s adapters do not implement the proposed profile. The oracle files are reviewed source data; run.py never rewrites them.

## Decisions compared with the second design

The Lead chose the smaller WP285 proposal as the normative v1 boundary and WP286 only for CSS and document examples that fit inside it:

| Topic | Adopted from WP285 | Smaller-scope choice over WP286 |
|---|---|---|
| Element set | article, div, h1–h3, p, span, strong, em, br, ul, ol, li, table, tr, th, td, img, a (19 elements) | Omit section, header, footer, h4, blockquote, pre, hr, colgroup, col, thead, tbody, u, s, and code. |
| Nesting/lists | Flat lists, no nested tables; table rows form a rectangular grid | Omit depth-three nested lists, nested content models, colgroups, colspan, and rowspan. |
| Image input | Local relative PNG/JPEG path; required alt, width and height in pt/mm; reject traversal and symlink escapes | Omit data URIs, absolute paths, inferred intrinsic dimensions, and optional alt/dimensions. |
| Links | Required href, absolute http/https/mailto only; validate but never fetch | Omit link targets or browser navigation behavior. |
| CSS selectors | *, one tag, .class, or #id | Omit tag.class, descendant selectors, selector lists, and combinators. |
| CSS properties | font-family, font-size, font-weight, font-style, color, text-align, margin-top/bottom, page-break-before/after | Omit background, border, padding, widths, text-decoration, line-height, indents, page-break-inside, and other layout knobs. |
| Values/units | Four font families; opaque #RRGGBB; left/center/right; pt/mm only | Omit em, %, px, unitless zero, extra font families, justify, and shorthand values. |
| Page model | Letter or A4 portrait, 54pt default margins; optional @page size and four margins; explicit before/after page breaks | Omit landscape, legal/custom sizes, running headers/footers, page-number fields, keep-together, and an exact natural page-count promise. |
| Fidelity/diagnostics | Same normalized text/styles/explicit constraints; automatic wrapping and pagination may vary. Unmatched selectors and unmeasured DOCX font availability are dry warnings. | Do not adopt WP286’s stricter no-warning rule or its 92% page-height/page-count contract. |
| Whitespace | Collapse XML ASCII whitespace across the inline stream, preserving style runs and one separator; trim paragraph edges and spaces around br; preserve NBSP. | Use the WP285 stream-level rule; hosts must not collapse each run independently. |

The letter, report, and invoice carry WP286’s concrete business content, pared back to the WP285 profile (for example, no running header/footer, merged cells, column groups, shading, or selector combinations). The carrier-portal link is isolated in its own refusal case; the report retains a pinned local PNG. Additional probes cover whitespace/run boundaries, empty paragraphs, independent ordered-list restart, adjacent list kinds, styled headings, per-cell alignment, long tables/repeated headers, page breaks, and malformed/profile-negative controls. The job report lists the narrower choices by category.

## Run against the released hosts

Use private prefixes/cache locations. Do not link or install lmctl globally:

    EVIDENCE=/home/mma/repos/lmcode-team/wp288-evidence
    npm install --prefix "$EVIDENCE/compiler" --no-save --package-lock=false @lmctl-ai/lmctl@0.2.458
    PATH=/usr/bin:/bin LMSCRIPT_TOOL_CACHE="$EVIDENCE/lmscript-tools" node --experimental-strip-types /home/mma/repos/lmctl-mono-wp288/lmscript/lmscript.ts install github:lmctl-ai/lmpdf@v0.2.6
    PATH=/usr/bin:/bin LMSCRIPT_TOOL_CACHE="$EVIDENCE/lmscript-tools" node --experimental-strip-types /home/mma/repos/lmctl-mono-wp288/lmscript/lmscript.ts install github:lmctl-ai/lmoffice@v0.1.31

    python3 tests/html-doc-conformance/run.py       --compiler "$EVIDENCE/compiler/node_modules/.bin/lmscript"       --lmpdf "$EVIDENCE/lmscript-tools/github/lmctl-ai/lmpdf/v0.2.6/lmpdf"       --lmoffice "$EVIDENCE/lmscript-tools/github/lmctl-ai/lmoffice/v0.1.31/lmoffice"       --mono-root /home/mma/repos/lmctl-mono-wp288       --mono-source /home/mma/repos/lmctl-mono-wp288/lmscript/lmscript.ts       --evidence "$EVIDENCE/run"

The runner checks pair and asset SHA-256 values, computes the normative source trace/styles, confirms html-subset@1/css-subset@1 remain unchanged, asserts the profile-identity negative control, invokes both released hosts in real and dry mode, and checks dry results/side effects. Successful PDF outputs are inspected for extracted text, page geometry, word bounds, font names, links, and images. Successful DOCX packages are parsed for paragraph/run styles, tables/cells, header-repeat markers, section geometry, links, relationships, and media. release-baseline.json pins the measured Linux x64 release behavior; a fixed host is a baseline change for review, not a reason to regenerate the normative source trace.

The current release compiler does not ship _xml_ or these new profile IDs, so corpus XML is sent to the current host through the existing String API in the real/dry runner. The mono-main source check separately verifies that an unmatched profile ID is rejected. This is expected for a before-adapter slice, not a new lmcode or std protocol.

## Adapter-fix regression vectors

`regressions.json` adds vectors without changing the frozen pre-adapter corpus or
release baseline. Current adapter runners load both manifests. Expected traces
come from the source oracle, never from a renderer; `render_assertions` additionally
checks final PDF operators or DOCX run/paragraph properties. This covers regular
weight resets, default link color, inherited list fonts, full word sequences,
authored spacing, exact decimal rounding, half-point text and strict refusals.
Deep-tree and allocation-pressure probes are host tests: they generate inputs and
apply explicit caller memory limits, rather than adding an implicit profile quota.

The historical page-box CSS spells `letter` lowercase. WP285 requires exact
`Letter` or `A4`, so the current adapter overlay requires refusal of that old
input and adds page-box-Letter with the same physical geometry, plus A4 coverage.
The original corpus and historical release baseline bytes are retained. The
source-trace validator recognizes both historical and canonical spellings;
current-host rejection is tested independently by the explicit negative case.

Font quantization does not override format capacity: Open XML requires font
half-point values of at least2 (1pt). The positive half-point vector therefore
uses1.25pt ->1.5pt;0.25pt ->0.5pt is an explicit format-refusal vector.
