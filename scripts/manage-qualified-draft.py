#!/usr/bin/env python3
"""Verify the sealed public release before promotion or throwaway cleanup."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys


def gh(args, *, data=None):
    result = subprocess.run(["gh", "api", *args], input=data, text=data is not None,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise SystemExit(f"gh api failed ({result.returncode}): {result.stderr.strip()}")
    return result.stdout


def main():
    if len(sys.argv) != 5 or sys.argv[1] not in {"promote", "cleanup"}:
        raise SystemExit("usage: manage-qualified-draft.py promote|cleanup TAG SHA256SUMS_SHA256 CANDIDATE_DIR")
    mode, tag, expected, directory = sys.argv[1:]
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SystemExit("invalid candidate tag or SHA256SUMS digest")
    root = Path(directory)
    local_sums = (root / "SHA256SUMS").read_bytes()
    if hashlib.sha256(local_sums).hexdigest() != expected:
        raise SystemExit("candidate SHA256SUMS differs from repository_dispatch identity")
    releases = json.loads(gh(["--paginate", "--slurp", f"repos/{os.environ['GITHUB_REPOSITORY']}/releases?per_page=100"]))
    if releases and isinstance(releases[0], list):
        releases = [item for page in releases for item in page]
    matches = [item for item in releases if item.get("tag_name") == tag]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one public release object for {tag}; found {len(matches)}")
    release = matches[0]
    if release.get("target_commitish") != "main":
        raise SystemExit("release target is not main")
    assets = {item.get("name"): item for item in release.get("assets", [])}
    prefix = "https://api.github.com/repos/lmctl-ai/lmoffice/releases/assets/"
    if set(assets) != {"lmoffice-linux-x64", "lmoffice-linux-arm64", "lmoffice-macos-arm64", "lmoffice-macos-x64", "lmoffice-windows-x64.exe", "LICENSE", "THIRD_PARTY_NOTICES.md", "RELEASE-MANIFEST.json", "SHA256SUMS"}:
        raise SystemExit("release asset list differs from the sealed candidate contract")
    remote_bytes = {}
    for name, asset in assets.items():
        asset_url = asset.get("url", "")
        if not asset_url.startswith(prefix):
            raise SystemExit(f"unexpected asset API URL for {name}")
        content = gh([asset_url, "-H", "Accept: application/octet-stream"])
        if len(content) != asset.get("size"):
            raise SystemExit(f"release asset size changed after qualification: {name}")
        remote_bytes[name] = content
    remote_sums = remote_bytes["SHA256SUMS"]
    if hashlib.sha256(remote_sums).hexdigest() != expected or remote_sums != local_sums:
        raise SystemExit("public release checksum file differs from the sealed and qualified candidate")
    for line in local_sums.decode("ascii").splitlines():
        digest, name = line.split("  ", 1)
        if hashlib.sha256(remote_bytes[name]).hexdigest() != digest:
            raise SystemExit(f"release asset differs from SHA256SUMS: {name}")
    if mode == "cleanup":
        if not release.get("draft"):
            raise SystemExit("refusing cleanup: throwaway release is already published")
        gh(["--method", "DELETE", f"repos/lmctl-ai/lmoffice/releases/{release['id']}"])
        print(f"Verified and removed only draft release {tag}; its git tag was left untouched.")
        return
    if release.get("draft") is False:
        print(f"{tag} is already published with the identical qualified SHA256SUMS; promotion is idempotently complete.")
        return
    if release.get("draft") is not True:
        raise SystemExit("release draft state is not boolean")
    payload = json.dumps({"draft": False, "make_latest": "true"})
    promoted = json.loads(gh(["--method", "PATCH", f"repos/lmctl-ai/lmoffice/releases/{release['id']}", "--input", "-"], data=payload))
    if promoted.get("draft") is not False or promoted.get("tag_name") != tag:
        raise SystemExit("GitHub did not confirm promotion of the qualified draft")
    print(f"Promoted qualified draft {tag} and marked it Latest.")


if __name__ == "__main__":
    main()
