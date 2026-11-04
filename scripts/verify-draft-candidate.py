#!/usr/bin/env python3
"""Revalidate a local frozen candidate and its private GitHub attestation."""
import sys
from pathlib import Path
from release_policy import verify_attestation
if __name__=='__main__':
 if len(sys.argv)!=2:raise SystemExit('usage: verify-draft-candidate.py DIRECTORY')
 try:
  manifest,seal=verify_attestation(Path(sys.argv[1]));print(manifest['version'])
 except (ValueError,KeyError,OSError) as error:raise SystemExit(str(error))
