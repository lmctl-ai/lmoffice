# Public release qualification harness

This directory contains the lmoffice integration tests and the pinned html-doc@1/css-doc@1 corpus. The public qualification workflow executes the 536-check integration suite and the document-profile corpus against the exact candidate installed through lmscript. These tests are MIT-licensed under `../LICENSE-examples` so the public workflow does not need private source access.

The upstream XML/CSS corpus is pinned by `html-doc-conformance/UPSTREAM_COMMIT`. Adapter-specific regression assertions are maintained in the same pinned test directory without changing the upstream release baseline.
