#!/usr/bin/env bash
set -euo pipefail
shopt -s globstar nullglob

if [[ ! -d examples ]]; then
  echo "install-hosts: no examples directory; nothing to install"
  exit 0
fi

host_bin="${LMCTL_HOST_BIN_DIR:-${RUNNER_TEMP:-/tmp}/lmctl-example-hosts}"
mkdir -p "$host_bin"
skip_file="${RUNNER_TEMP:-/tmp}/lmctl-unavailable-examples.tsv"
: > "$skip_file"

declare -A tags_by_repo=()
declare -A owner_by_repo=()
declare -A cli_names=()
declare -A cli_repo=()
declare -A unavailable_reason=()
declare -A resolved_latest=()
declare -A PINNED_HOST_SHA256=(
  ["lmctl-ai/lmoffice@v0.1.58/lmoffice-linux-arm64"]="72d50e524d179ea5549f3cd5870d3b7e8b05bc8ad6bfe1e52b94403253ebf12c"
  ["lmctl-ai/lmoffice@v0.1.58/lmoffice-linux-x64"]="b1bb094b110456f11784064492074a5e9636787dd8965c93d02f99ea4fb4c478"
  ["lmctl-ai/lmoffice@v0.1.58/lmoffice-macos-arm64"]="ab212d3e6c435d27947015b7558ff6549945f447ee39331e1be4e91793a8023c"
  ["lmctl-ai/lmoffice@v0.1.58/lmoffice-macos-x64"]="7f79c90f131656bb27ab9fe40e6f9c8e87056ea6e8af1619d37b22cdcedc09d2"
  ["lmctl-ai/lmoffice@v0.1.58/lmoffice-windows-x64.exe"]="36bc61d36ea211b230b81e4fdc646d3853192c4f1e4915a4f6a31127ea379057"
  ["lmctl-ai/lmoffice@v0.1.60/lmoffice-linux-arm64"]="942f6924ac60c30db4fb7e83738704df97ba2960452168a72bbc640b1eab0ff5"
  ["lmctl-ai/lmoffice@v0.1.60/lmoffice-linux-x64"]="638c8c1c95b8fb433b0be44c66d46bad7bbe19d55c99bc52680fab1ad375611f"
  ["lmctl-ai/lmoffice@v0.1.60/lmoffice-macos-arm64"]="571dc587cf2fb4f8d01b8ec40f521d3e92d9e690d93533cd74772f6398254590"
  ["lmctl-ai/lmoffice@v0.1.60/lmoffice-macos-x64"]="a3b05dc71fbb05ecbc5b30e908b5f7bfdad141b7ac976ee168ce4c6bbfd27b89"
  ["lmctl-ai/lmoffice@v0.1.60/lmoffice-windows-x64.exe"]="39265f2389e6a2fcbd84c3139856c4bfd8dcab44cd1853f812ad09ca3ef3fc96"
)
verify_sha256() {
  local expected="$1" file="$2" actual=""
  if command -v sha256sum >/dev/null 2>&1; then
    actual="$(sha256sum "$file" | awk '{print $1}')"
  else
    actual="$(shasum -a 256 "$file" | awk '{print $1}')"
  fi
  if [[ "$actual" != "$expected" ]]; then
    echo "install-hosts: SHA-256 mismatch for $file: expected $expected, got $actual" >&2
    return 1
  fi
}
install_re="install[[:space:]]*=[[:space:]]*[\"'](github:[^\"']+)[\"']"
cli_re="cli[[:space:]]*=[[:space:]]*[\"']([^\"']+)[\"']"
examples=(examples/**/*.lms)

for example in "${examples[@]}"; do
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ $install_re ]]; then
      spec="${BASH_REMATCH[1]#github:}"
      if [[ "$spec" != *@* ]]; then
        echo "install-hosts: unsupported GitHub install (missing @TAG) in $example: $spec" >&2
        exit 1
      fi
      full_repo="${spec%@*}"
      tag="${spec##*@}"
      if [[ ! "$full_repo" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ || ! "$tag" =~ ^[A-Za-z0-9_.-]+$ ]]; then
        echo "install-hosts: invalid GitHub install in $example: $spec" >&2
        exit 1
      fi
      repo="${full_repo##*/}"
      case " ${tags_by_repo[$full_repo]-} " in
        *" $tag "*) ;;
        *) tags_by_repo["$full_repo"]="${tags_by_repo[$full_repo]-}${tags_by_repo[$full_repo]:+ }$tag" ;;
      esac
      owner_by_repo["$full_repo"]="$repo"
    fi
    if [[ "$line" =~ $cli_re ]]; then
      cli="${BASH_REMATCH[1]}"
      cli="${cli%%[[:space:]]*}"
      [[ -z "$cli" ]] || cli_names["$cli"]=1
    fi
  done < "$example"
done

for full_repo in "${!tags_by_repo[@]}"; do
  repo="${owner_by_repo[$full_repo]}"
  if [[ -n "${cli_names[$repo]+set}" ]]; then cli_repo["$repo"]="$full_repo"; fi

  if ! gh repo view "$full_repo" --json name >/dev/null 2>&1; then
    echo "install-hosts: cannot verify public repository $full_repo" >&2
    exit 1
  fi

  if ! release_tags="$(gh release list -R "$full_repo" -L 1000 --json tagName --jq '.[].tagName')"; then
    echo "install-hosts: release lookup failed for $full_repo" >&2
    exit 1
  fi
  # `gh release list` includes prereleases and is used only to validate exact
  # pins. Resolve `@latest` through GitHub's dedicated endpoint, which excludes
  # prereleases and drafts by contract. A staging prerelease must never replace
  # the host selected for an @latest public example.
  latest_tag=""
  if latest_tag="$(gh api "repos/$full_repo/releases/latest" --jq '.tag_name' 2>/dev/null)" && [[ -n "$latest_tag" ]]; then
    resolved_latest["$full_repo"]="$latest_tag"
  else
    latest_tag=""
  fi

  available_tags=()
  for requested_tag in ${tags_by_repo[$full_repo]}; do
    resolved_tag="$requested_tag"
    [[ "$requested_tag" == latest ]] && resolved_tag="$latest_tag"
    found=false
    if [[ "$full_repo" == lmctl-ai/lmoffice && -n "${LMOFFICE_QUALIFY_TAG:-}" && "$requested_tag" == "$LMOFFICE_QUALIFY_TAG" ]]; then
      found=true
    elif [[ -n "$resolved_tag" ]]; then
      while IFS= read -r listed_tag; do
        [[ "$listed_tag" == "$resolved_tag" ]] && found=true
      done <<< "$release_tags"
    fi
    if [[ "$found" != true ]]; then
      reason="$full_repo@$requested_tag has no published release; dependent examples are not checkable"
      echo "install-hosts: SKIP $full_repo@$requested_tag: $reason"
      unavailable_reason["$full_repo@$requested_tag"]="$reason"
    else
      available_tags+=("$resolved_tag")
    fi
  done

  # Install the declared pin so a newer Latest never replaces the pinned binary.
  tag=""
  for candidate in "${available_tags[@]}"; do
    if [[ -n "$tag" && "$tag" != "$candidate" ]]; then
      echo "install-hosts: conflicting pins for $full_repo: $tag and $candidate" >&2
      exit 1
    fi
    tag="$candidate"
  done
  if [[ -z "$tag" ]]; then
    echo "install-hosts: no released binary is available for $full_repo"
    continue
  fi
  if [[ "$full_repo" == lmctl-ai/lmoffice && -n "${LMOFFICE_QUALIFY_TAG:-}" ]]; then
    echo "install-hosts: deferring $full_repo@$tag to the verified candidate staged on PATH"
    continue
  fi

  asset_name="$repo-linux-x64"
  tmp="$(mktemp -d "${RUNNER_TEMP:-/tmp}/lmctl-host-download.XXXXXX")"
  if ! gh release download "$tag" -R "$full_repo" --pattern "$asset_name" --pattern SHA256SUMS --dir "$tmp"; then
    rm -rf "$tmp"
    echo "install-hosts: release exists but $asset_name or SHA256SUMS could not be downloaded from $full_repo@$tag" >&2
    exit 1
  fi
  asset="$tmp/$asset_name"
  if [[ ! -s "$asset" || ! -s "$tmp/SHA256SUMS" ]]; then
    rm -rf "$tmp"
    echo "install-hosts: release exists but has no non-empty $asset_name or SHA256SUMS: $full_repo@$tag" >&2
    exit 1
  fi
  expected_sha="$(awk -v name="$asset_name" '$2 == name || $2 == ("*" name) {print $1; exit}' "$tmp/SHA256SUMS")"
  pinned_key="$full_repo@$tag/$asset_name"
  if [[ -n "${PINNED_HOST_SHA256[$pinned_key]-}" && "$expected_sha" != "${PINNED_HOST_SHA256[$pinned_key]}" ]]; then
    rm -rf "$tmp"
    echo "install-hosts: SHA256SUMS digest for $pinned_key ($expected_sha) does not match repo-pinned digest (${PINNED_HOST_SHA256[$pinned_key]})" >&2
    exit 1
  fi
  if [[ -z "$expected_sha" ]] || ! verify_sha256 "$expected_sha" "$asset"; then
    rm -rf "$tmp"
    exit 1
  fi
  cp "$asset" "$host_bin/$repo"
  chmod +x "$host_bin/$repo"
  rm -rf "$tmp"
  echo "install-hosts: installed $repo from $full_repo@$tag for declared pins: ${tags_by_repo[$full_repo]}"
done

for cli in "${!cli_names[@]}"; do
  if [[ -z "${cli_repo[$cli]+set}" ]]; then
    echo "install-hosts: cli=\"$cli\" has no matching GitHub install declaration" >&2
    exit 1
  fi
done

for example in "${examples[@]}"; do
  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" =~ $install_re ]]; then
      spec="${BASH_REMATCH[1]#github:}"
      full_repo="${spec%@*}"
      requested_tag="${spec##*@}"
      if [[ "$requested_tag" == latest ]]; then
        requested_tag="${resolved_latest[$full_repo]-latest}"
      fi
      ref_key="$full_repo@$requested_tag"
      if [[ -n "${unavailable_reason[$ref_key]+set}" ]]; then
        printf '%s\t%s\n' "$example" "${unavailable_reason[$ref_key]}" >> "$skip_file"
        break
      fi
    fi
  done < "$example"
done

if [[ -n "${GITHUB_ENV:-}" ]]; then
  printf 'LMCTL_UNAVAILABLE_EXAMPLES_FILE=%s\n' "$skip_file" >> "$GITHUB_ENV"
fi
export PATH="$host_bin:$PATH"
if [[ -n "${GITHUB_PATH:-}" ]]; then printf '%s\n' "$host_bin" >> "$GITHUB_PATH"; fi
echo "install-hosts: host directory prepended to PATH: $host_bin"
