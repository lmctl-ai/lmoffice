# Public release qualification harness

This directory contains the lmoffice integration suite and the pinned html-doc@1/css-doc@1 corpus. The public qualification workflow executes the 536-check suite and profile corpus against the exact candidate asset. These tests are MIT-licensed under `../LICENSE-examples` so public Actions do not need private source access.

Draft releases are intentionally unavailable through the public tag-download URL. The workflow fetches assets by authenticated public release-asset ID, verifies `SHA256SUMS`, stages the platform executable under the `lmoffice` name in an isolated `PATH`, then runs the normal `lmscript install github:lmctl-ai/lmoffice@TAG` resolver and verifies it selected those exact bytes. After promotion, ordinary users install the same tag from the public release URL.

`html-doc-conformance/UPSTREAM_COMMIT` pins the canonical lmcode fixtures. Adapter-specific regression assertions are maintained alongside the frozen corpus without rewriting its source oracle or release baseline.
