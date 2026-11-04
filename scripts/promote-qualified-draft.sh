#!/usr/bin/env bash
# Only the public qualification workflow may publish a candidate as Latest.
set -euo pipefail
TAG="${1:?usage: promote-qualified-draft.sh TAG SHA256SUMS_SHA256 CANDIDATE_DIR}"
EXPECTED="${2:?usage: promote-qualified-draft.sh TAG SHA256SUMS_SHA256 CANDIDATE_DIR}"
CANDIDATE="${3:?usage: promote-qualified-draft.sh TAG SHA256SUMS_SHA256 CANDIDATE_DIR}"
REPO="${GITHUB_REPOSITORY:?public repo identity is required}"
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]
[[ "$EXPECTED" =~ ^[0-9a-f]{64}$ ]]
LOCAL_SHA="$(sha256sum "$CANDIDATE/SHA256SUMS" | awk '{print $1}')"
test "$LOCAL_SHA" = "$EXPECTED" || { echo "candidate checksum differs from event identity" >&2; exit 1; }
(cd "$CANDIDATE" && sha256sum -c SHA256SUMS)
WORK="$(mktemp -d "${RUNNER_TEMP:-/tmp}/lmoffice-promote-XXXXXX")"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT
release="$(gh release view "$TAG" -R "$REPO" --json tagName,isDraft)"
test "$(jq -r .tagName <<<"$release")" = "$TAG"
mkdir -p "$WORK/current"
gh release download "$TAG" -R "$REPO" --dir "$WORK/current"
REMOTE_SHA="$(sha256sum "$WORK/current/SHA256SUMS" | awk '{print $1}')"
test "$REMOTE_SHA" = "$EXPECTED" || { echo "live release no longer matches the qualified candidate" >&2; exit 1; }
cmp -s "$CANDIDATE/SHA256SUMS" "$WORK/current/SHA256SUMS" || { echo "release checksum file changed after qualification" >&2; exit 1; }
(cd "$WORK/current" && sha256sum -c SHA256SUMS)
if [[ "$(jq -r .isDraft <<<"$release")" == true ]]; then
  gh release edit "$TAG" -R "$REPO" --draft=false --latest
  echo "Promoted qualified draft $TAG and marked it Latest" >> "$GITHUB_STEP_SUMMARY"
else
  # A replay of the same event is idempotent only for the identical published candidate.
  echo "Candidate $TAG is already published with the same SHA256SUMS; no promotion needed" >> "$GITHUB_STEP_SUMMARY"
fi
