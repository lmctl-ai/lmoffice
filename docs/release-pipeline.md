# Private draft → public qualification → immutable Latest

The private `lmctlhq/lmoffice` manual workflow is the producer. Public code verifies a GitHub-signed private provenance bundle, tests the frozen bytes without publication credentials, and only then publishes. A dispatch digest is a locator/checksum, never producer authorization. No private source or long-lived private API credential is copied to the public repository.

## Authority and artifact flow

| Job | Permissions | Candidate execution |
| --- | --- | --- |
| regression | contents:read | Synthetic offline controls only |
| candidate | contents:read | Never; trusted download and provenance validation |
| qualify-macos-arm64 | contents:read | Yes, without GH_TOKEN/GITHUB_TOKEN or persisted checkout credentials |
| integration | contents:read | Yes, four other native platforms, same credential boundary |
| deliberate-failure-test | contents:read | No; sealed throwaway control only |
| promote | contents:write | Never; trusted publication or sealed-throwaway cleanup only |

The private workflow builds the five NativeAOT binaries and runs its smoke gate. Its separate publisher verifies the ORIGINAL build attempt through the private Actions API using its own `GITHUB_TOKEN` with `actions:read`/`contents:read`. It requires the correct repository, workflow path, workflow_dispatch event, main branch, source SHA and all eight completed successful prerequisite jobs. It never executes a candidate while release/signing credentials are present.

The publisher's existing `RELEASE_TOKEN` uploads missing public draft assets and sends repository_dispatch; it is scoped to the intended public repository and never reaches native qualification jobs. `id-token:write`/`attestations:write` belong only to the trusted private publisher. No new secret is introduced. GitHub Enterprise Cloud is required for private attestations; this organization has that plan. Signing adds one attestation action and private API reads to the already existing publisher job, not another native build matrix. Public verification uses a bundled attestation, not a token with private-repository access.

The acyclic seal is explicit:

1. Upload seven payload assets once; record each actual GitHub asset ID, size and SHA-256 in `RELEASE-MANIFEST.json` v2.
2. That manifest also seals private repository/workflow/run/build-attempt/branch/ref/source SHA, the private API verification receipt and the boolean throwaway purpose. Upload it and `SHA256SUMS`, which covers the seven payloads and manifest.
3. `FROZEN-CANDIDATE.json` records the public release ID and IDs/digests/sizes of ALL nine preceding assets, including the checksum file itself. A seal cannot recursively contain its own asset ID; its own digest is signed instead.
4. `actions/attest-build-provenance`, pinned by full SHA, signs the frozen file. Upload its Sigstore bundle as `PROVENANCE.jsonl`. Dispatch only the tag, seal/bundle asset IDs and seal digest. There is no payload failure-control flag to override the signed purpose.
5. The public trusted handoff downloads by fixed asset IDs, verifies byte hashes and the private GitHub Sigstore signature with `gh attestation verify --bundle --repo ... --signer-workflow ... --source-ref refs/heads/main --source-digest ... --deny-self-hosted-runners --no-public-good`. The issuer-authenticated certificate's run invocation must match the sealed run/build-attempt relationship; an arbitrary provenance predicate is not trusted as proof of identity.
6. Each native job gets an immutable Actions artifact and an independently supplied checksum identity from the trusted job output. It validates local files, stages the exact binary, checks `lmscript install` selected that PATH binary, and runs the integration suite, profile corpus, gallery checks and representative sample. The installer and candidate subprocess environments strip GitHub/signing credentials. All checkouts use `persist-credentials:false`.
7. After ALL five platforms pass, the final writer verifies the attestation again, checks live revocation/Latest, downloads all live bytes, and rechecks the entire set of asset IDs/digests immediately before publication. Strong ETags are supplied as If-Match where available; weak ETags are not misrepresented as an asset-set CAS.
8. The repository must have GitHub release immutability enabled. The writer first publishes with `make_latest:false`, verifies GitHub locked the exact frozen asset set, then moves Latest. A failed post-publication identity/immutability check revokes and removes only that suspect release object without deleting its tag. Arbitrary repository administrators can bypass workflows; this protocol removes candidate credentials and coordinates all legitimate producer writes rather than claiming an unsupported atomic multi-asset API transaction.

Private producer retries NEVER use --clobber, delete assets, or repair a missing frozen payload. Existing IDs/bytes must match; otherwise use a new candidate. An unfinished initial upload can add missing files only before the freeze exists. A missing first provenance bundle can complete that same frozen seal. Once provenance exists, retries reuse and verify it rather than signing/replacing a new identity.

## Trigger, observe and recover

Normal release (all subsequent steps automatic):

```sh
gh workflow run ci.yml --repo lmctlhq/lmoffice --ref main
```

One throwaway failure control, selected BEFORE sealing:

```sh
gh workflow run ci.yml --repo lmctlhq/lmoffice --ref main -f deliberate_public_failure=true
```

Public failure does not retroactively fail the private producer. Watch both runs:

```sh
gh run list --repo lmctlhq/lmoffice --workflow ci.yml --limit 5
gh run view PRIVATE_RUN --repo lmctlhq/lmoffice
gh run list --repo lmctl-ai/lmoffice --workflow qualify-private-draft.yml --limit 10
gh run view PUBLIC_RUN --repo lmctl-ai/lmoffice
gh release list --repo lmctl-ai/lmoffice --limit 10
```

After fixing a public test/runner failure, redrive the ORIGINAL successful or failed publisher job; do not ask a successful private workflow to rerun nonexistent failed jobs:

```sh
gh run view PRIVATE_RUN --repo lmctlhq/lmoffice --json jobs --jq '.jobs[] | select(.name=="publish-draft") | .databaseId'
gh run rerun PRIVATE_RUN --repo lmctlhq/lmoffice --job PUBLISH_JOB_ID
```

That path reuses the original source/build attempt and frozen asset IDs. A source/build change requires a NEW private manual run/version. A full rerun changes build-attempt identity at the same version and is refused if a conflicting frozen candidate already exists.

The public manual input is only a recorded-candidate replay, never authorization for an unrecorded release:

```sh
gh workflow run qualify-private-draft.yml --repo lmctl-ai/lmoffice --ref main -f tag=RECORDED_TAG
```

An older-than-Latest or revoked tag is refused before download. An identical CURRENT published candidate is an idempotent no-op after verification. A real native failure keeps the draft unpublished and skips the writer. The sealed throwaway control fails only after all native jobs pass; the writer then records durable revocation and its replay record before deleting only that owned draft object, never a tag. Failure/rejection reasons are written to the run summary.

## Queue and cancellation semantics

Private workflows group by original run ID; distinct candidate runs do not replace each other. Public workflows group by candidate tag. Multiple pending redrives of the SAME candidate can replace each other; they represent identical frozen bytes and can be redriven using the publisher job above. Different candidate versions cannot cancel one another's pending qualification.

Only the final public mutation job has a product-wide group, using `queue:max` and `cancel-in-progress:false`. GitHub currently permits up to 100 pending entries in that queue; excess/cancelled jobs remain visible in Actions and can be redriven. This is a documented platform queue bound, not a tool work budget. Bare `cancel-in-progress:false` does NOT mean pending runs are lossless: the default single pending slot is replaced by a newer run. No polling sweep, notification service or feature deadline is introduced.

Every always()-based release-mutation predicate also requires !cancelled() and explicit success of ALL native gates. Operator cancellation must stop a running publisher; always() alone would keep it alive.

## Version and durable rollback

The candidate version is the committed VERSION floor plus that workflow's run number in PATCH. Keep the floor nondecreasing and preserve the workflow counter. Freshness is additionally checked against the live published Latest, so a lowered floor, out-of-order completion or stale retry cannot silently move Latest backward. A same-version conflicting seal is refused.

Rollback is a revocation operation FIRST. Do not merely make a bad release a draft: a delayed old event could otherwise republish it.

1. Record the bad tag, known-good tag, checksum and run URLs. Append `BAD_TAG reason-and-incident-link` to the public repo's `REVOKED` file, commit/push normally to main, and verify the append landed. Never remove old entries. Publication checks this file live before fetching and immediately before mutation.
2. Mark the bad immutable release as a prerelease and move Latest to an already-published known-good release, with operator approval:

   ```sh
   gh release edit BAD_TAG --repo lmctl-ai/lmoffice --prerelease --latest=false
   gh release edit GOOD_TAG --repo lmctl-ai/lmoffice --latest
   ```

3. If a release object must be removed, `gh release delete BAD_TAG --repo lmctl-ai/lmoffice --yes` intentionally omits --cleanup-tag. GitHub immutability has tag-name reuse restrictions: do not reuse that tag. Dispatch a NEW corrected private candidate and update downstream pins. Already-installed copies and caches do not roll back automatically.

These are operator incident commands, not actions for a development agent to execute by hand. New publication remains CI-only. Existing mutable releases can be unpublished if incident policy requires, but REVOKED still comes first.

REST tag lookup/browser downloads do not expose an unpublished draft normally. The gh release commands can resolve pending draft tags through their authenticated GraphQL fallback. Public qualification stages files by verified asset IDs; its source:PATH install assertion does not claim to test the GitHub tag-download/cache path.

## Tests, cost and applicability

`python3 -B -m unittest discover -s tests -p 'test_release*.py'` and `python3 tests/mutate-release-pipeline.py` are committed, offline and use only synthetic credentials/candidates/stubbed APIs. They gate authority scopes, actual candidate subprocess inheritance, private provenance policy, sealed cleanup, older/revoked replay, late asset replacement, cancellation, queue configuration, action pins and this permission table.

The private side still pays for five NativeAOT builds; public standard-runner integration minutes are free. The original successful pilot used nine private jobs, 740 summed runner-seconds, 359 elapsed seconds and 18 per-job-rounded minutes. Attestation/API work adds a small trusted publisher overhead; record actual run times rather than calling the private work free. Current runner prices and plan allowances determine charges; a timing API zero is not an invoice.

This pilot publishes GitHub assets/Latest only. npm latest needs its own tested immutable-byte/provenance gate; it is not implemented by copying these workflows.

## Exact porting checklist for wp312 copies (lmpdf and lmvideo)

Apply this file-by-file; preserve each host's actual native/platform/test requirements. Do not copy private host implementation into a public repo.

- BOTH repos: add the same `release-policy.json`, adapting product, public/private repos, exact private workflow path/main branch, payload names and required private job names. This is the main product-specific configuration; do not guess missing platforms.
- BOTH repos: copy `scripts/release_policy.py` byte-for-byte. It owns token-free execution environments, strict version/provenance/asset validation, revocation and bundled GitHub verification. Keep its copies synchronized.
- PRIVATE: update `scripts/prepare-release-candidate.py` to emit core v2 producer/run/ref/source/throwaway fields and complete checksums. Add the sealed boolean from the workflow input BEFORE upload.
- BOTH repos: copy `scripts/verify-private-build.py` and `scripts/stage-frozen-draft.py`; the public copies are generic admin code covered by offline controls. Verify the private API receipt before signing. Upload missing assets once, refuse changes/frozen repairs, create the acyclic identity seal, attest it, upload provenance once, dispatch only fixed IDs/digest. Remove the old --clobber path from `scripts/release-to-public.sh`.
- PRIVATE `.github/workflows/ci.yml`: keep manual/main-only; group by run ID, retain that host's builders/smoke, then add API verification, freeze, pinned attest-build-provenance and final dispatch steps. Only its trusted publisher gets id-token/attestations write; existing RELEASE_TOKEN is step-scoped for public staging/dispatch. Verify Enterprise attestation availability.
- PUBLIC `scripts/download-draft-candidate.py` and `verify-draft-candidate.py`: replace listing/self-asserted-digest trust with fixed asset-ID download, complete byte validation and private GitHub attestation/run-certificate validation. No private API secret is copied.
- PUBLIC `scripts/check-local-candidate.py` and `install-draft-host.py`: validate the trusted checksum identity, stage exact PATH bytes and strip GitHub/OIDC credentials from candidate subprocesses. Never put GH_TOKEN in candidate-executing steps.
- PUBLIC `scripts/manage-qualified-draft.py`: recheck attestation, live revocation/Latest and ALL frozen IDs/digests; publish non-Latest, require immutable tested identities, then set Latest. Only sealed throwaways can be revoked/cleaned. Record replay identity/outcome in `release-state.json`; append revocations in `REVOKED` before destructive cleanup.
- PUBLIC `.github/workflows/qualify-private-draft.yml`: add offline regression/mutation gate; make trusted fetch and ALL native jobs read-only with non-persisted checkout credentials; consume verified artifacts. Group qualification per candidate tag. Only final writer has contents write, ALL native needs, !cancelled(), global queue:max, and both promotion/cleanup modes derived from the sealed manifest. Adapt the genuine platform matrix; retain failure visibility and recorded-tag replay input.
- PUBLIC `.github/actions/qualify-platform/action.yml`: add trusted sums identity, remove token env, pin every external action by its resolved full SHA. Retain that host's corpus/gallery/user example and Windows launcher handling.
- PUBLIC `.github/workflows/public-ci.yml`: pin its existing actions and disable checkout credential persistence too. Add no automatic private push release trigger.
- PUBLIC: initialize `REVOKED` and `release-state.json`; copy/adapt `tests/test_release_pipeline.py`, `tests/test_release_security.py`, `tests/release_fixtures.py`, `tests/mutate-release-pipeline.py` and this guide. Update product-specific expected private gates, not the security invariants. Run the actual candidate-credential probe and mutations, not missing-import failures.
- Repository setting: enable immutable releases before the proof through the repository admin API/UI; do not give Actions administration permission. Verify the CI-published candidate reports immutable:true. Older releases remain governed by their existing state.
- Prove one sealed throwaway failure, one five-platform success and an older/revoked replay refusal through the repositories' OWN workflows. Record source SHAs, action pins, run IDs, release tag, checksum/seal IDs and signer identity. No manual tags/promotions, secret copying or registry login.

## Primary references

- [Private artifact attestations require Enterprise Cloud](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations).
- [Bundled/offline verification and private Sigstore roots](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/verify-attestations-offline); [gh verification flags and certificate-versus-predicate distinction](https://cli.github.com/manual/gh_attestation_verify).
- [Actual concurrency/pending queue behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
- [Immutable release protections and tag reuse restrictions](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases).
