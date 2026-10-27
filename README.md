# lmoffice

> The public README, docs, images, and examples for `lmoffice` are MIT under `LICENSE-examples`. Binary releases use `LICENSE`; implementation source and its history are maintained privately in `lmctlhq/lmoffice`.

`lmoffice` is a self-contained .NET 8 NativeAOT host for the lmscript `_dsl_` statement. It creates and inspects Word, Excel, and PowerPoint Open XML documents through Microsoft's Open XML SDK. The executable embeds three format-specific DSL schemas and has no Office installation or network requirement at runtime.

The host writes one JSON result line for each bytecode file. Exit status `0` means success, `2` means command usage, `3` means bytecode load or VM run failure, and `4` means an application or document failure. The generated files are validated with `OpenXmlValidator` before `inspect` returns their summary.

## Install lmctl

Everything in this repository runs through [lmctl](https://lmctl.com), the core tool of the lmctl family. Install it once, then run any `.lms` file or raw URL:

```bash
npm install -g @lmctl-ai/lmctl
lmctl autorun path/to/example.lms
lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/example.lms
```

## Commands

```sh
private implementation detail
private implementation detail
./test.sh
```

Requires the .NET 8 SDK, git, Python 3, and `lmscript` (npm `@lmctl-ai/lmctl@0.2.420`) on PATH. Native publishing also needs a platform C toolchain; Linux needs clang and zlib development headers.

The SDK checkout in ignored `private implementation detail` is pinned by `private build metadata`; the application uses `DocumentFormat.OpenXml` 3.5.1 and its locked `System.IO.Packaging` 8.0.1 dependency. `private implementation detail` publishes one self-contained NativeAOT executable for the selected runtime identifier. The current release lane publishes Linux x64 and arm64, dynamically linked to the platform C, math, and zlib libraries (and using platform cryptography). Earlier releases may contain macOS and Windows assets; those platforms are not produced by the current lane. Each Linux binary is a single deployable file, but it is not a statically linked libc binary.

```sh
lmoffice --version
lmoffice docx --help
lmoffice docx --dsl-schema --json
lmoffice docx --dsl-signatures
lmoffice docx --dsl report.dslb
lmoffice inspect report.docx
```

The `docx`, `xlsx`, and `pptx` subcommands each embed and expose their own schema (`private implementation detail`, `private implementation detail`, and `private implementation detail`). Every DSL flag follows its format word. `inspect` is the shared top-level command: it validates a `.docx`, `.xlsx`, or `.pptx` and returns a JSON summary containing format-specific counts and extracted text. Add `--markdown` to extract the supported Markdown subset. The schema's strings are UTF-8 DSL strings; the host converts them at the document boundary.

The context factories are `docx.create(path)`, `xlsx.create(path)`, and `pptx.create(path)`. Their types are `DocxHost`, `XlsxHost`, and `PptxHost`; document methods belong to the returned handles. All three registries include the SDK’s built-in string, math, collection and file catalogs; compiler 0.2.420 resolves them without host schema declarations. See the subcommand layout.

Coordinates and indices are deliberately small and predictable: Word table cells and spreadsheet rows/columns are 1-based; spreadsheet formulas are stored in the workbook and are not evaluated by lmoffice; slide coordinates are pixels on a 1280×720 canvas at 96 DPI. Paragraph styles use boolean bold/italic, point sizes, six-digit hex colors, and named alignment values. The format contexts expose the shared sample-image helper for examples that need a self-contained 64×64 PNG.

## Documents as code

Write the document in one outer-lmscript triple-quoted body, then pass it into the
host. These examples work with the published compiler; triple quotes inside the
DSL block are not required.

```text
body = """# Weekly brief

- **Shipped:** the pilot workflow
- **Next:** customer feedback

{{sign: Avery Chen}}
""";
p = _lmcode_ cli="lmoffice docx" install="github:lmctl-ai/lmoffice@latest";
docx.create("brief.docx").markdown(${body}).save();
end _lmcode_
savedsl(p, "brief.dslb");
r = system(concat(dsl_cli(p), ["--dsl", "brief.dslb"]), 120000); assert(r.code == 0);
```

Use `Docx.markdown_file(path)` to read a UTF-8 Markdown file, `Pptx.markdown(text)`
for slide-separated text, and `Xlsx.sheet_from_markdown_table(name,text)` or
`Xlsx.sheet_from_csv(name,text)` for typed worksheets. The format adapters'
`to_markdown` operations read actual Office packages back into Markdown. From the command line:

```sh
lmoffice inspect brief.docx --markdown
```

The command returns one JSON result with the text in `result.markdown`. The
strict grammar documents fields, directives,
image sizing, tables, and line-numbered errors. DOCX extraction reaches a canonical
fixed point for the supported subset. Unsupported Office objects are reported in
the extracted text; exact visual reconstruction of arbitrary files is not promised.
Image references use portable data URIs. CSV values beginning with `=` remain
literal strings.

Thirteen examples below pair the rendered document with up to ten lines from its
body. Physical line counts include blank lines; the API originals often compress
many calls onto one line. These are comparable tasks, not identical documents or
a blanket claim that Markdown always uses fewer lines. Regenerate this comparison
with `python3 private implementation detail`.

| Task | API version: lines | Text version: lines | Body lines |
| --- | ---: | ---: | ---: |
| NDA | [19](examples/legal-nda.lms) | [32](examples/markdown-nda.lms) | 26 |
| Services agreement | [20](examples/legal-services-agreement.lms) | [41](examples/markdown-services-agreement.lms) | 35 |
| Resume | [21](examples/resume-classic.lms) | [41](examples/markdown-resume.lms) | 35 |
| Business letter | [16](examples/business-letter.lms) | [30](examples/markdown-business-letter.lms) | 24 |
| Report with TOC | [22](examples/business-report-with-toc.lms) | [40](examples/markdown-report-toc.lms) | 34 |
| Meeting minutes | [18](examples/meetingminutes.lms) | [42](examples/markdown-meeting-minutes.lms) | 36 |
| Project deck | [54](examples/project_status.lms) | [34](examples/markdown-project-deck.lms) | 28 |
| Training deck | [65](examples/training_workshop.lms) | [34](examples/markdown-training-deck.lms) | 28 |
| Budget workbook | [19](examples/budgetxlsx.lms) | [13](examples/markdown-budget-table.lms) | 7 |
| Gradebook | [56](examples/education-gradebook-advanced.lms) | [14](examples/markdown-gradebook-csv.lms) | 7 |

## Example gallery

Click any preview to view it at full size. Every image is rendered from its offline `.lms` example with LibreOffice and PyMuPDF. Run the command in a caption to create the document; inspect it with `lmoffice inspect <output-file>`.

### Word documents by genre

#### Legal

| [`legal-nda`](examples/legal-nda.lms) | [`legal-services-agreement`](examples/legal-services-agreement.lms) | [`legal-lease`](examples/legal-lease.lms) |
| --- | --- | --- |
| <a href="docs/images/legal-nda.png"><img src="docs/images/legal-nda.png" alt="Mutual NDA with three-level clauses and signature lines" width="290"></a> | <a href="docs/images/legal-services-agreement.png"><img src="docs/images/legal-services-agreement.png" alt="Outside counsel engagement scope, fees and signatures" width="290"></a> | <a href="docs/images/legal-lease.png"><img src="docs/images/legal-lease.png" alt="Office lease with premises, rent and handover terms" width="290"></a> |
| Mutual NDA with three-level clauses and signature lines<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/legal-nda.lms` | Outside counsel engagement scope, fees and signatures<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/legal-services-agreement.lms` | Office lease with premises, rent and handover terms<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/legal-lease.lms` |

| [`legal-terms-of-service`](examples/legal-terms-of-service.lms) | [`legal-power-of-attorney`](examples/legal-power-of-attorney.lms) | [`legal-demand-letter`](examples/legal-demand-letter.lms) |
| --- | --- | --- |
| <a href="docs/images/legal-terms-of-service.png"><img src="docs/images/legal-terms-of-service.png" alt="Service terms with numbered obligations" width="290"></a> | <a href="docs/images/legal-power-of-attorney.png"><img src="docs/images/legal-power-of-attorney.png" alt="Limited transaction authority and signature blocks" width="290"></a> | <a href="docs/images/legal-demand-letter.png"><img src="docs/images/legal-demand-letter.png" alt="Delivery-dispute demand for replacement goods or credit" width="290"></a> |
| Service terms with numbered obligations<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/legal-terms-of-service.lms` | Limited transaction authority and signature blocks<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/legal-power-of-attorney.lms` | Delivery-dispute demand for replacement goods or credit<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/legal-demand-letter.lms` |

#### Resume and career

| [`resume-classic`](examples/resume-classic.lms) | [`resume-two-column`](examples/resume-two-column.lms) | [`resume-academic-cv`](examples/resume-academic-cv.lms) |
| --- | --- | --- |
| <a href="docs/images/resume-classic.png"><img src="docs/images/resume-classic.png" alt="Chronological resume with right-aligned employment dates" width="290"></a> | <a href="docs/images/resume-two-column.png"><img src="docs/images/resume-two-column.png" alt="Borderless two-column skills and experience layout" width="290"></a> | <a href="docs/images/resume-academic-cv.png"><img src="docs/images/resume-academic-cv.png" alt="Academic appointments, publications, link and footnote" width="290"></a> |
| Chronological resume with right-aligned employment dates<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/resume-classic.lms` | Borderless two-column skills and experience layout<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/resume-two-column.lms` | Academic appointments, publications, link and footnote<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/resume-academic-cv.lms` |

| [`resume-cover-letter`](examples/resume-cover-letter.lms) | [`resume-reference-sheet`](examples/resume-reference-sheet.lms) |
| --- | --- |
| <a href="docs/images/resume-cover-letter.png"><img src="docs/images/resume-cover-letter.png" alt="Targeted application letter with contact details" width="290"></a> | <a href="docs/images/resume-reference-sheet.png"><img src="docs/images/resume-reference-sheet.png" alt="Professional references with role and contact information" width="290"></a> |
| Targeted application letter with contact details<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/resume-cover-letter.lms` | Professional references with role and contact information<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/resume-reference-sheet.lms` |

#### Business

| [`business-memo`](examples/business-memo.lms) | [`business-proposal`](examples/business-proposal.lms) | [`business-letter`](examples/business-letter.lms) |
| --- | --- | --- |
| <a href="docs/images/business-memo.png"><img src="docs/images/business-memo.png" alt="Decision memo with owner, actions and indented request" width="290"></a> | <a href="docs/images/business-proposal.png"><img src="docs/images/business-proposal.png" alt="Project proposal with scope, delivery and commercial terms" width="290"></a> | <a href="docs/images/business-letter.png"><img src="docs/images/business-letter.png" alt="Formal customer correspondence and signature" width="290"></a> |
| Decision memo with owner, actions and indented request<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-memo.lms` | Project proposal with scope, delivery and commercial terms<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-proposal.lms` | Formal customer correspondence and signature<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-letter.lms` |

| [`business-press-release`](examples/business-press-release.lms) | [`business-report-with-toc`](examples/business-report-with-toc.lms) | [`business-purchase-order`](examples/business-purchase-order.lms) |
| --- | --- | --- |
| <a href="docs/images/business-press-release.png"><img src="docs/images/business-press-release.png" alt="Two-column launch announcement and media contact" width="290"></a> | <a href="docs/images/business-report-with-toc.png"><img src="docs/images/business-report-with-toc.png" alt="Operating review with linked TOC and page fields" width="290"></a> | <a href="docs/images/business-purchase-order.png"><img src="docs/images/business-purchase-order.png" alt="Landscape PO with fixed widths and shaded header cells" width="290"></a> |
| Two-column launch announcement and media contact<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-press-release.lms` | Operating review with linked TOC and page fields<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-report-with-toc.lms` | Landscape PO with fixed widths and shaded header cells<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-purchase-order.lms` |

| [`business-job-offer`](examples/business-job-offer.lms) | [`business-agenda`](examples/business-agenda.lms) | [`report`](examples/report.lms) |
| --- | --- | --- |
| <a href="docs/images/business-job-offer.png"><img src="docs/images/business-job-offer.png" alt="Offer letter with compensation, start date and acceptance" width="290"></a> | <a href="docs/images/business-agenda.png"><img src="docs/images/business-agenda.png" alt="Planning workshop agenda with timed sessions and owners" width="290"></a> | <a href="docs/images/report.png"><img src="docs/images/report.png" alt="Report with generated image, table, headers and footers" width="290"></a> |
| Offer letter with compensation, start date and acceptance<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-job-offer.lms` | Planning workshop agenda with timed sessions and owners<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/business-agenda.lms` | Report with generated image, table, headers and footers<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/report.lms` |

| [`invoice`](examples/invoice.lms) | [`meetingminutes`](examples/meetingminutes.lms) |
| --- | --- |
| <a href="docs/images/invoice.png"><img src="docs/images/invoice.png" alt="Invoice with line-item table and totals" width="290"></a> | <a href="docs/images/meetingminutes.png"><img src="docs/images/meetingminutes.png" alt="Meeting decisions and action items" width="290"></a> |
| Invoice with line-item table and totals<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/invoice.lms` | Meeting decisions and action items<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/meetingminutes.lms` |

#### Education

| [`education-lesson-plan`](examples/education-lesson-plan.lms) | [`education-syllabus`](examples/education-syllabus.lms) | [`education-certificate`](examples/education-certificate.lms) |
| --- | --- | --- |
| <a href="docs/images/education-lesson-plan.png"><img src="docs/images/education-lesson-plan.png" alt="Science lesson plan, learning targets and landscape teacher notes" width="290"></a> | <a href="docs/images/education-syllabus.png"><img src="docs/images/education-syllabus.png" alt="Course syllabus with outcomes, assessment and weekly topics" width="290"></a> | <a href="docs/images/education-certificate.png"><img src="docs/images/education-certificate.png" alt="Landscape completion certificate and signature lines" width="290"></a> |
| Science lesson plan, learning targets and landscape teacher notes<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-lesson-plan.lms` | Course syllabus with outcomes, assessment and weekly topics<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-syllabus.lms` | Landscape completion certificate and signature lines<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-certificate.lms` |

| [`education-assessment-rubric`](examples/education-assessment-rubric.lms) |
| --- |
| <a href="docs/images/education-assessment-rubric.png"><img src="docs/images/education-assessment-rubric.png" alt="Merged rubric headers, shaded criteria and scoring bands" width="290"></a> |
| Merged rubric headers, shaded criteria and scoring bands<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-assessment-rubric.lms` |

#### HR

| [`hr-offer-letter`](examples/hr-offer-letter.lms) | [`hr-performance-review`](examples/hr-performance-review.lms) | [`hr-org-chart`](examples/hr-org-chart.lms) |
| --- | --- | --- |
| <a href="docs/images/hr-offer-letter.png"><img src="docs/images/hr-offer-letter.png" alt="Fictional employment offer, compensation and acceptance" width="290"></a> | <a href="docs/images/hr-performance-review.png"><img src="docs/images/hr-performance-review.png" alt="Performance review with comments and tracked wording changes" width="290"></a> | <a href="docs/images/hr-org-chart.png"><img src="docs/images/hr-org-chart.png" alt="Team reporting structure with merged cells and role ownership" width="290"></a> |
| Fictional employment offer, compensation and acceptance<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/hr-offer-letter.lms` | Performance review with comments and tracked wording changes<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/hr-performance-review.lms` | Team reporting structure with merged cells and role ownership<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/hr-org-chart.lms` |

| [`hr-onboarding-checklist`](examples/hr-onboarding-checklist.lms) |
| --- |
| <a href="docs/images/hr-onboarding-checklist.png"><img src="docs/images/hr-onboarding-checklist.png" alt="First-week onboarding checklist with owners and completion evidence" width="290"></a> |
| First-week onboarding checklist with owners and completion evidence<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/hr-onboarding-checklist.lms` |

#### Real estate and operations

| [`operations-lease-abstract`](examples/operations-lease-abstract.lms) | [`operations-inspection-checklist`](examples/operations-inspection-checklist.lms) |
| --- | --- |
| <a href="docs/images/operations-lease-abstract.png"><img src="docs/images/operations-lease-abstract.png" alt="Lease summary with a landscape premises appendix" width="290"></a> | <a href="docs/images/operations-inspection-checklist.png"><img src="docs/images/operations-inspection-checklist.png" alt="Property inspection checklist with condition notes and actions" width="290"></a> |
| Lease summary with a landscape premises appendix<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/operations-lease-abstract.lms` | Property inspection checklist with condition notes and actions<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/operations-inspection-checklist.lms` |

#### Marketing

| [`marketing-content-plan`](examples/marketing-content-plan.lms) | [`marketing-case-study`](examples/marketing-case-study.lms) |
| --- | --- |
| <a href="docs/images/marketing-content-plan.png"><img src="docs/images/marketing-content-plan.png" alt="Editorial plan with content owners, channels and review dates" width="290"></a> | <a href="docs/images/marketing-case-study.png"><img src="docs/images/marketing-case-study.png" alt="Customer case study with outcomes and measurement table" width="290"></a> |
| Editorial plan with content owners, channels and review dates<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/marketing-content-plan.lms` | Customer case study with outcomes and measurement table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/marketing-case-study.lms` |

#### Document as code

| [`markdown-nda`](examples/markdown-nda.lms) |
| --- |
| <a href="docs/images/markdown-nda.png"><img src="docs/images/markdown-nda.png" alt="NDA written as clauses, signatures and a Markdown body" width="900"></a> |
| NDA written as clauses, signatures and a Markdown body<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-nda.lms` |

| [`markdown-services-agreement`](examples/markdown-services-agreement.lms) |
| --- |
| <a href="docs/images/markdown-services-agreement.png"><img src="docs/images/markdown-services-agreement.png" alt="Services agreement with scope, fees and numbered clauses" width="900"></a> |
| Services agreement with scope, fees and numbered clauses<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-services-agreement.lms` |

| [`markdown-resume`](examples/markdown-resume.lms) |
| --- |
| <a href="docs/images/markdown-resume.png"><img src="docs/images/markdown-resume.png" alt="Resume with rich text, a right-aligned date and list achievements" width="900"></a> |
| Resume with rich text, a right-aligned date and list achievements<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-resume.lms` |

| [`markdown-business-letter`](examples/markdown-business-letter.lms) |
| --- |
| <a href="docs/images/markdown-business-letter.png"><img src="docs/images/markdown-business-letter.png" alt="Business letter with fields, emphasis and signature" width="900"></a> |
| Business letter with fields, emphasis and signature<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-business-letter.lms` |

| [`markdown-report-toc`](examples/markdown-report-toc.lms) |
| --- |
| <a href="docs/images/markdown-report-toc.png"><img src="docs/images/markdown-report-toc.png" alt="Report with a generated table of contents and table" width="900"></a> |
| Report with a generated table of contents and table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-report-toc.lms` |

| [`markdown-meeting-minutes`](examples/markdown-meeting-minutes.lms) |
| --- |
| <a href="docs/images/markdown-meeting-minutes.png"><img src="docs/images/markdown-meeting-minutes.png" alt="Meeting minutes with attendees, decisions and action table" width="900"></a> |
| Meeting minutes with attendees, decisions and action table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-meeting-minutes.lms` |

| [`markdown-lesson-plan`](examples/markdown-lesson-plan.lms) |
| --- |
| <a href="docs/images/markdown-lesson-plan.png"><img src="docs/images/markdown-lesson-plan.png" alt="Lesson plan with learning goals, schedule and teacher notes" width="900"></a> |
| Lesson plan with learning goals, schedule and teacher notes<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-lesson-plan.lms` |

| [`markdown-review-notes`](examples/markdown-review-notes.lms) |
| --- |
| <a href="docs/images/markdown-review-notes.png"><img src="docs/images/markdown-review-notes.png" alt="Counsel review notes with questions, quotation and proposed clause" width="900"></a> |
| Counsel review notes with questions, quotation and proposed clause<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-review-notes.lms` |

#### Cross-format

| [`cross-workbook-memo`](examples/cross-workbook-memo.lms) |
| --- |
| <a href="docs/images/cross-workbook-memo.png"><img src="docs/images/cross-workbook-memo.png" alt="Memo fed by a shared total from a companion quarterly workbook" width="290"></a> |
| Memo fed by a shared total from a companion quarterly workbook<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/cross-workbook-memo.lms` |

### Excel workbooks by task

#### Finance

| [`monthly_budget`](examples/monthly_budget.lms) | [`expense_report`](examples/expense_report.lms) | [`invoice_tracker`](examples/invoice_tracker.lms) |
| --- | --- | --- |
| <a href="docs/images/monthly_budget.png"><img src="docs/images/monthly_budget.png" alt="Monthly budget with variance formulas and budgeted-expense chart" width="290"></a> | <a href="docs/images/expense_report.png"><img src="docs/images/expense_report.png" alt="Travel expense reimbursement with categories and receipt comments" width="290"></a> | <a href="docs/images/invoice_tracker.png"><img src="docs/images/invoice_tracker.png" alt="Accounts receivable tracker with validation lists and KPI cards" width="290"></a> |
| Monthly budget with variance formulas and budgeted-expense chart<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/monthly_budget.lms` | Travel expense reimbursement with categories and receipt comments<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/expense_report.lms` | Accounts receivable tracker with validation lists and KPI cards<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/invoice_tracker.lms` |

| [`loan_amortization`](examples/loan_amortization.lms) | [`cap_table`](examples/cap_table.lms) | [`budgetxlsx`](examples/budgetxlsx.lms) |
| --- | --- | --- |
| <a href="docs/images/loan_amortization.png"><img src="docs/images/loan_amortization.png" alt="15-year fixed loan assumptions and first-year amortization schedule" width="290"></a> | <a href="docs/images/cap_table.png"><img src="docs/images/cap_table.png" alt="Startup capitalization table with equity tiers and pie chart" width="290"></a> | <a href="docs/images/budgetxlsx.png"><img src="docs/images/budgetxlsx.png" alt="Simple departmental budget with formulas and frozen headers" width="290"></a> |
| 15-year fixed loan assumptions and first-year amortization schedule<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/loan_amortization.lms` | Startup capitalization table with equity tiers and pie chart<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/cap_table.lms` | Simple departmental budget with formulas and frozen headers<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/budgetxlsx.lms` |

| [`finance-profit-loss`](examples/finance-profit-loss.lms) | [`finance-cash-flow`](examples/finance-cash-flow.lms) | [`finance-balance-sheet`](examples/finance-balance-sheet.lms) |
| --- | --- | --- |
| <a href="docs/images/finance-profit-loss.png"><img src="docs/images/finance-profit-loss.png" alt="Quarterly P&amp;L with formulas, native chart and an embedded image" width="290"></a> | <a href="docs/images/finance-cash-flow.png"><img src="docs/images/finance-cash-flow.png" alt="Rolling cash balances with six months of receipt and payment assumptions" width="290"></a> | <a href="docs/images/finance-balance-sheet.png"><img src="docs/images/finance-balance-sheet.png" alt="Detailed assets, liabilities and equity with a zero-balance control" width="290"></a> |
| Quarterly P&L with formulas, native chart and an embedded image<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/finance-profit-loss.lms` | Rolling cash balances with six months of receipt and payment assumptions<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/finance-cash-flow.lms` | Detailed assets, liabilities and equity with a zero-balance control<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/finance-balance-sheet.lms` |

| [`finance-cap-table`](examples/finance-cap-table.lms) | [`finance-tax-worksheet`](examples/finance-tax-worksheet.lms) |
| --- | --- |
| <a href="docs/images/finance-cap-table.png"><img src="docs/images/finance-cap-table.png" alt="Pre- and post-round capitalization with ownership formulas" width="290"></a> | <a href="docs/images/finance-tax-worksheet.png"><img src="docs/images/finance-tax-worksheet.png" alt="Illustrative deduction worksheet with evidence and fictional allowance assumptions" width="290"></a> |
| Pre- and post-round capitalization with ownership formulas<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/finance-cap-table.lms` | Illustrative deduction worksheet with evidence and fictional allowance assumptions<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/finance-tax-worksheet.lms` |

#### Operations

| [`project_gantt`](examples/project_gantt.lms) | [`sales_dashboard`](examples/sales_dashboard.lms) | [`inventory_tracker`](examples/inventory_tracker.lms) |
| --- | --- | --- |
| <a href="docs/images/project_gantt.png"><img src="docs/images/project_gantt.png" alt="Project schedule tracker with phase highlights and bars" width="290"></a> | <a href="docs/images/sales_dashboard.png"><img src="docs/images/sales_dashboard.png" alt="Multi-sheet sales KPI dashboard with summary formulas and chart" width="290"></a> | <a href="docs/images/inventory_tracker.png"><img src="docs/images/inventory_tracker.png" alt="Warehouse inventory ledger with stock valuations and reorder highlights" width="290"></a> |
| Project schedule tracker with phase highlights and bars<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/project_gantt.lms` | Multi-sheet sales KPI dashboard with summary formulas and chart<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/sales_dashboard.lms` | Warehouse inventory ledger with stock valuations and reorder highlights<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/inventory_tracker.lms` |

| [`timesheet`](examples/timesheet.lms) | [`kpi_scorecard`](examples/kpi_scorecard.lms) | [`multisheet`](examples/multisheet.lms) |
| --- | --- | --- |
| <a href="docs/images/timesheet.png"><img src="docs/images/timesheet.png" alt="Weekly engineering timesheet with daily totals and project billing" width="290"></a> | <a href="docs/images/kpi_scorecard.png"><img src="docs/images/kpi_scorecard.png" alt="Balanced scorecard across financial, customer and internal KPIs" width="290"></a> | <a href="docs/images/multisheet.png"><img src="docs/images/multisheet.png" alt="Assumptions, data and summary multi-sheet workbook" width="290"></a> |
| Weekly engineering timesheet with daily totals and project billing<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/timesheet.lms` | Balanced scorecard across financial, customer and internal KPIs<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/kpi_scorecard.lms` | Assumptions, data and summary multi-sheet workbook<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/multisheet.lms` |

| [`operations-maintenance-log`](examples/operations-maintenance-log.lms) |
| --- |
| <a href="docs/images/operations-maintenance-log.png"><img src="docs/images/operations-maintenance-log.png" alt="Asset service history, next due dates and priority icons" width="290"></a> |
| Asset service history, next due dates and priority icons<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/operations-maintenance-log.lms` |

#### Personal and learning

| [`gradebook`](examples/gradebook.lms) | [`habit_tracker`](examples/habit_tracker.lms) | [`shopping_list`](examples/shopping_list.lms) |
| --- | --- | --- |
| <a href="docs/images/gradebook.png"><img src="docs/images/gradebook.png" alt="Course gradebook with weighted scoring and class statistics" width="290"></a> | <a href="docs/images/habit_tracker.png"><img src="docs/images/habit_tracker.png" alt="Fourteen-day habit grid with completion totals and success rates" width="290"></a> | <a href="docs/images/shopping_list.png"><img src="docs/images/shopping_list.png" alt="Event shopping list grouped by store aisle with cost variance" width="290"></a> |
| Course gradebook with weighted scoring and class statistics<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/gradebook.lms` | Fourteen-day habit grid with completion totals and success rates<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/habit_tracker.lms` | Event shopping list grouped by store aisle with cost variance<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/shopping_list.lms` |

| [`travel_itinerary`](examples/travel_itinerary.lms) |
| --- |
| <a href="docs/images/travel_itinerary.png"><img src="docs/images/travel_itinerary.png" alt="Multi-day trip itinerary with flight, hotel and daily details" width="290"></a> |
| Multi-day trip itinerary with flight, hotel and daily details<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/travel_itinerary.lms` |

#### Education

| [`education-gradebook-advanced`](examples/education-gradebook-advanced.lms) | [`education-class-schedule`](examples/education-class-schedule.lms) | [`education-rubric`](examples/education-rubric.lms) |
| --- | --- | --- |
| <a href="docs/images/education-gradebook-advanced.png"><img src="docs/images/education-gradebook-advanced.png" alt="Weighted gradebook with native progress icons" width="290"></a> | <a href="docs/images/education-class-schedule.png"><img src="docs/images/education-class-schedule.png" alt="Printable weekly timetable with rooms and study periods" width="290"></a> | <a href="docs/images/education-rubric.png"><img src="docs/images/education-rubric.png" alt="Assessment register with score formulas and icon bands" width="290"></a> |
| Weighted gradebook with native progress icons<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-gradebook-advanced.lms` | Printable weekly timetable with rooms and study periods<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-class-schedule.lms` | Assessment register with score formulas and icon bands<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-rubric.lms` |

#### HR

| [`hr-leave-tracker`](examples/hr-leave-tracker.lms) |
| --- |
| <a href="docs/images/hr-leave-tracker.png"><img src="docs/images/hr-leave-tracker.png" alt="Leave allowance, bookings and remaining-balance formulas" width="290"></a> |
| Leave allowance, bookings and remaining-balance formulas<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/hr-leave-tracker.lms` |

#### Marketing

| [`marketing-campaign-calendar`](examples/marketing-campaign-calendar.lms) |
| --- |
| <a href="docs/images/marketing-campaign-calendar.png"><img src="docs/images/marketing-campaign-calendar.png" alt="Campaign launch calendar with channels, owners and planned spend" width="290"></a> |
| Campaign launch calendar with channels, owners and planned spend<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/marketing-campaign-calendar.lms` |

#### Document as code

| [`markdown-budget-table`](examples/markdown-budget-table.lms) |
| --- |
| <a href="docs/images/markdown-budget-table.png"><img src="docs/images/markdown-budget-table.png" alt="Typed budget worksheet imported from a Markdown table" width="900"></a> |
| Typed budget worksheet imported from a Markdown table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-budget-table.lms` |

| [`markdown-contacts-csv`](examples/markdown-contacts-csv.lms) |
| --- |
| <a href="docs/images/markdown-contacts-csv.png"><img src="docs/images/markdown-contacts-csv.png" alt="Contact workbook imported from a quoted CSV body" width="900"></a> |
| Contact workbook imported from a quoted CSV body<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-contacts-csv.lms` |

| [`markdown-gradebook-csv`](examples/markdown-gradebook-csv.lms) |
| --- |
| <a href="docs/images/markdown-gradebook-csv.png"><img src="docs/images/markdown-gradebook-csv.png" alt="Typed grade register with weighted scores supplied as CSV data" width="900"></a> |
| Typed grade register with weighted scores supplied as CSV data<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-gradebook-csv.lms` |

### PowerPoint presentations by task

#### Briefings

| [`quarterly_business_review`](examples/quarterly_business_review.lms) | [`project_status`](examples/project_status.lms) | [`annual_report`](examples/annual_report.lms) |
| --- | --- | --- |
| <a href="docs/images/quarterly_business_review.png"><img src="docs/images/quarterly_business_review.png" alt="Executive QBR with KPI cards, revenue table and growth chart" width="290"></a> | <a href="docs/images/project_status.png"><img src="docs/images/project_status.png" alt="Weekly status deck with RAG health cards and milestone table" width="290"></a> | <a href="docs/images/annual_report.png"><img src="docs/images/annual_report.png" alt="Annual report deck with performance table and multi-year chart" width="290"></a> |
| Executive QBR with KPI cards, revenue table and growth chart<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/quarterly_business_review.lms` | Weekly status deck with RAG health cards and milestone table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/project_status.lms` | Annual report deck with performance table and multi-year chart<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/annual_report.lms` |

#### Sales

| [`pitch_deck`](examples/pitch_deck.lms) | [`product_launch`](examples/product_launch.lms) | [`sales_proposal`](examples/sales_proposal.lms) |
| --- | --- | --- |
| <a href="docs/images/pitch_deck.png"><img src="docs/images/pitch_deck.png" alt="Investor pitch with problem, solution and market sizing" width="290"></a> | <a href="docs/images/product_launch.png"><img src="docs/images/product_launch.png" alt="Product launch deck with pillars, architecture and competitor table" width="290"></a> | <a href="docs/images/sales_proposal.png"><img src="docs/images/sales_proposal.png" alt="Enterprise commercial proposal with solution and pricing table" width="290"></a> |
| Investor pitch with problem, solution and market sizing<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/pitch_deck.lms` | Product launch deck with pillars, architecture and competitor table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/product_launch.lms` | Enterprise commercial proposal with solution and pricing table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/sales_proposal.lms` |

#### People and training

| [`conference_talk`](examples/conference_talk.lms) | [`team_intro`](examples/team_intro.lms) | [`onboarding`](examples/onboarding.lms) |
| --- | --- | --- |
| <a href="docs/images/conference_talk.png"><img src="docs/images/conference_talk.png" alt="Technical keynote with speaker bio and architecture diagram" width="290"></a> | <a href="docs/images/team_intro.png"><img src="docs/images/team_intro.png" alt="Team briefing with values, leadership table and global team chart" width="290"></a> | <a href="docs/images/onboarding.png"><img src="docs/images/onboarding.png" alt="Engineering onboarding plan with milestones and mentor support" width="290"></a> |
| Technical keynote with speaker bio and architecture diagram<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/conference_talk.lms` | Team briefing with values, leadership table and global team chart<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/team_intro.lms` | Engineering onboarding plan with milestones and mentor support<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/onboarding.lms` |

| [`training_workshop`](examples/training_workshop.lms) | [`5slidedeck`](examples/5slidedeck.lms) |
| --- | --- |
| <a href="docs/images/training_workshop.png"><img src="docs/images/training_workshop.png" alt="Technical training deck with modules, lab flow and schedule" width="290"></a> | <a href="docs/images/5slidedeck.png"><img src="docs/images/5slidedeck.png" alt="Five-slide project briefing with image, bullets and notes" width="290"></a> |
| Technical training deck with modules, lab flow and schedule<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/training_workshop.lms` | Five-slide project briefing with image, bullets and notes<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/5slidedeck.lms` |

#### Education

| [`education-lesson-deck`](examples/education-lesson-deck.lms) |
| --- |
| <a href="docs/images/education-lesson-deck.png"><img src="docs/images/education-lesson-deck.png" alt="Data-literacy lesson with chart discussion and activity table" width="290"></a> |
| Data-literacy lesson with chart discussion and activity table<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/education-lesson-deck.lms` |

#### Marketing

| [`marketing-brand-guidelines`](examples/marketing-brand-guidelines.lms) |
| --- |
| <a href="docs/images/marketing-brand-guidelines.png"><img src="docs/images/marketing-brand-guidelines.png" alt="Brand voice, channel chart, campaign table and content-mix pie" width="290"></a> |
| Brand voice, channel chart, campaign table and content-mix pie<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/marketing-brand-guidelines.lms` |

#### HR

| [`hr-onboarding-review`](examples/hr-onboarding-review.lms) |
| --- |
| <a href="docs/images/hr-onboarding-review.png"><img src="docs/images/hr-onboarding-review.png" alt="Onboarding progress, role table and completion trend" width="290"></a> |
| Onboarding progress, role table and completion trend<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/hr-onboarding-review.lms` |

#### Document as code

| [`markdown-project-deck`](examples/markdown-project-deck.lms) |
| --- |
| <a href="docs/images/markdown-project-deck.png"><img src="docs/images/markdown-project-deck.png" alt="Project update deck from slide-separated Markdown" width="900"></a> |
| Project update deck from slide-separated Markdown<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-project-deck.lms` |

| [`markdown-training-deck`](examples/markdown-training-deck.lms) |
| --- |
| <a href="docs/images/markdown-training-deck.png"><img src="docs/images/markdown-training-deck.png" alt="Training deck with nested bullets, notes and layout hints" width="900"></a> |
| Training deck with nested bullets, notes and layout hints<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/markdown-training-deck.lms` |

#### Cross-format

| [`cross-workbook-briefing`](examples/cross-workbook-briefing.lms) |
| --- |
| <a href="docs/images/cross-workbook-briefing.png"><img src="docs/images/cross-workbook-briefing.png" alt="Briefing deck fed by a shared revenue forecast workbook" width="290"></a> |
| Briefing deck fed by a shared revenue forecast workbook<br>`lmctl autorun https://raw.githubusercontent.com/lmctl-ai/lmoffice/main/examples/cross-workbook-briefing.lms` |

## DSL shape

Each format subcommand exposes a small context rooted at its format: `docx.create(path)`/`docx.open(path)`, `xlsx.create(path)`/`xlsx.open(path)`, and `pptx.create(path)`/`pptx.open(path)`. Word exposes headings, styled paragraphs, bullets, numbered paragraphs, tables, images, page breaks, headers, footers, fields, titles, authors, and `save()`. Excel exposes typed cell values, formulas, rich formatting, borders, number formats, column widths, row heights, freeze panes, merges, auto-filters, tables, data validation lists, cell comments, conditional formatting (cell-is, color scales, and icon sets), named ranges, images, and charts (bar, line, pie). PowerPoint exposes slides, themes, title/content/section layouts, styled text, bullets, rectangles, shapes (ellipse, line, arrow, rounded rectangle), hyperlinks, footers, slide numbers, transitions, tables, charts (bar, line, pie), images, notes, and `save()`.

The schema is the source of truth for exact signatures:

```sh
lmoffice docx --dsl-signatures
lmscript --dsl-signatures private implementation detail
lmoffice xlsx --dsl-signatures
lmscript --dsl-signatures private implementation detail
lmoffice pptx --dsl-signatures
lmscript --dsl-signatures private implementation detail
# Compare just the host declarations (repeat for xlsx/pptx):
lmoffice docx --dsl-signatures --without-std
lmscript --dsl-signatures private implementation detail --without-std
```

The integration suite requires those two outputs to match. See `durable-memory/` for technical decisions, build facts, test behavior, and known limits.

## Images and document review

Place an external PNG or JPEG next to worksheet data with
`sheet.image(path, row, col, width_px, height_px)`. `book.image(...)` targets the
most recently created sheet. Images and native charts can share a worksheet;
`conditional_icon_set(r1,c1,r2,c2,"3TrafficLights1")` adds native status icons.

Word supports `table.merge(row,col,row_span,col_span)`, per-cell `shade` and
`cell_border`, `text_box(text,width_pt,height_pt)`, text columns, and
`section_break("landscape")`. `heading_numbering(true)` links heading styles to
multilevel numbering. Paragraphs support `comment(text,author)`,
`inserted(text,author)` and `deleted(text,author)` for editable review markup.
See the API details for units, supported
icon names, section behavior and deterministic metadata conventions.

PowerPoint charts are native editable bar/line/pie chart parts; tables are native
editable slide tables. The education, marketing and HR decks demonstrate both.

## License


Releases up to and including v0.1.27 were published under the MIT License (see the LICENSE asset of that release). Releases after v0.1.27 are published under the Lattice Systems Binary License 1.0 (this file).
The README, docs, images, and `examples/*.lms` are MIT-licensed under `LICENSE-examples`.
Binary releases are licensed under `LICENSE`. Third-party components remain under their own licenses and notices.

## CI and releases

Every push to `main` builds and tests five native executables, then publishes a
`vMAJOR.MINOR.<workflow run number>` GitHub release with the executables,
`SHA256SUMS`, `LICENSE`, and third-party notices. `VERSION` supplies MAJOR.MINOR;
CI stamps the full version into the binary. Pull requests and manual runs test
without releasing. Current assets are named `lmoffice-linux-x64` and
`lmoffice-linux-arm64`; earlier releases may contain macOS and Windows assets.

`test.sh` publishes a native executable unless `LMOFFICE_BIN` selects one to test.
It requires the compiler and runs the example gallery including every Word genre document, the SDK's OpenXmlValidator,
signature parity, readback, and error cases. Independent Python readers are used
when installed (all three are installed in CI); choose a virtual environment with
`PYTHON=/path/to/venv/bin/python`. Format-specific inspection and Markdown
extraction are also available inside their DSL subcommands.
Document text must be valid UTF-8 and XML 1.0; the host rejects invalid bytes and
NUL text instead of silently replacing them. `Docx.title` and `Docx.author` set
core properties; use `heading` for visible headings. `freeze(rows, columns)` takes
counts of frozen rows/columns, and `col_width` uses Excel character widths.

## Regenerating the demo page

All gallery preview PNGs are committed in `docs/images/`; GitHub displays them directly.
The renderer uses LibreOffice to refresh Word fields/TOCs and spreadsheet formulas,
then PyMuPDF and Pillow produce compact PNGs. Slides are contact sheets; spreadsheet
previews include every selected print page and its charts. Page selection lives in
`docs/gallery.json`.

```sh
private implementation detail
# Rendering tools only; not runtime dependencies of lmoffice:
python3 -m pip install --user pymupdf pillow
python3 private implementation detail
python3 private implementation detail --only report monthly_budget pitch_deck
python3 private implementation detail
python3 private implementation detail
python3 private implementation detail
```

Set `SOFFICE` (or `LMOFFICE_SOFFICE`) and `UNO_PYTHON` for a custom LibreOffice
installation. The default search also finds an official DEB extraction under
`~/tools/libreoffice`. Each run has an isolated profile and leaves the source
Office documents unchanged. The image-link check needs only Python and Git,
not LibreOffice, the compiler, or CI; it verifies that every README image resolves
to a committed file and that every example has a preview below 300 KB.
See gallery rendering for details.
