#!/usr/bin/env python3
"""Check canonical fixture bytes and source-derived expectations, without a host."""
import hashlib,json,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('html_doc_source',ROOT/'run.py');source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
def main():
 base=json.loads((ROOT/'corpus.json').read_text(encoding='utf8'));extra=json.loads((ROOT/'regressions.json').read_text(encoding='utf8'));cases=[dict(c,**extra.get('case_overrides',{}).get(c['id'],{})) for c in base['cases']]+extra['cases'];seen=set()
 for a in base['assets']:assert hashlib.sha256((ROOT/a['path']).read_bytes()).hexdigest()==a['sha256'],a['path']
 for c in cases:
  assert c['id'] not in seen,c['id'];seen.add(c['id'])
  for path in [c['xml'],c['css']]:assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==c['input_sha256'][Path(path).name],path
  if c['kind']!='dry-negative':source.assert_subset(c['expected'],source.source_trace((ROOT/c['xml']).read_text(encoding='utf8'),(ROOT/c['css']).read_text(encoding='utf8'),c['expected'],base),c['id'])
 print(f'html-doc canonical source/byte checks: {len(cases)} cases PASS')
if __name__=='__main__':main()
