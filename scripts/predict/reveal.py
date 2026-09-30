#!/usr/bin/env python3
"""Reveal a sealed prediction, and later record how it resolved.

  python3 scripts/predict/reveal.py P-2026-10-01-01                     # publish the text after checking its hash
  python3 scripts/predict/reveal.py P-2026-10-01-01 --resolve true|false|partial --note "what happened, with a source"

Reveal checks the private file's SHA-256 against the ledger (refuses on mismatch), copies it to
predictions/revealed/<id><ext>, stores the text in the ledger, upgrades the OpenTimestamps proof, and records the
`ots verify` output. Resolution never edits the sealed text; it adds {resolved, resolved_date, note}."""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(__file__))
import ledger as L


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('id'); ap.add_argument('--resolve', choices=['true', 'false', 'partial'])
    ap.add_argument('--note')
    a = ap.parse_args()
    doc = L.load(); p = L.find(doc, a.id)
    if a.resolve:
        if p['status'] != 'revealed': raise SystemExit('reveal it before resolving it')
        if not a.note: raise SystemExit('--note is required: say what happened and cite a source')
        p.update({'resolved': a.resolve, 'resolved_date': L.today(), 'note': a.note})
        L.save(doc); print(a.id, 'resolved', a.resolve); return
    priv = os.path.join(L.PRIVATE, a.id + p.get('ext', '.txt'))
    if not os.path.exists(priv): raise SystemExit(f'private text not found: {priv}')
    digest = L.sha256(priv)
    if digest != p['sha256']: raise SystemExit(f'hash mismatch: ledger {p["sha256"]}, file {digest}. Not revealing.')
    os.makedirs(os.path.join(L.PUB, 'revealed'), exist_ok=True)
    rel = os.path.join('predictions', 'revealed', a.id + p.get('ext', '.txt'))
    shutil.copyfile(priv, os.path.join(L.ROOT, rel))
    proof = os.path.join(L.ROOT, p['ots_file'])
    L.ots('upgrade', proof)
    if os.path.exists(proof + '.bak'): os.remove(proof + '.bak')
    rc, out = L.ots('verify', '-f', os.path.join(L.ROOT, rel), proof)
    p.update({'status': 'revealed', 'revealed_date': L.today(), 'text_file': rel,
              'text': open(priv, encoding='utf-8', errors='replace').read(), 'ots_verify': out.splitlines()[-1] if out else None})
    L.save(doc)
    print(f'revealed {a.id} (hash ok). ots verify: {p["ots_verify"]}')


if __name__ == '__main__':
    main()
