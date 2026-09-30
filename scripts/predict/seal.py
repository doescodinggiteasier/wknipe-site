#!/usr/bin/env python3
"""Seal a prediction: fingerprint it, time-stamp the fingerprint on Bitcoin, list it publicly. The text stays private.

  python3 scripts/predict/seal.py my-prediction.md [--resolves-by 2031-01-01] [--title "short public label"]

1. copies the file to local/predictions/<id><ext> (gitignored), byte for byte;
2. computes its SHA-256 and runs `ots stamp` (submits the hash, never the text, to public OpenTimestamps calendars);
3. copies the proof to predictions/ots/<id>.ots and appends {id, date, sha256, ots_file, status: sealed} to
   predictions/ledger.json.
The proof is "pending" until a calendar's Bitcoin transaction confirms (a few hours); run
`python3 scripts/predict/seal.py --upgrade` later to embed the Bitcoin attestation in every pending proof.
Don't edit the file after sealing: any byte changed breaks the hash. The title (optional) is public; keep it vague."""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(__file__))
import ledger as L


def upgrade():
    doc = L.load()
    for p in doc['predictions']:
        f = os.path.join(L.ROOT, p['ots_file'])
        rc, out = L.ots('upgrade', f)
        p['ots_complete'] = rc == 0 and 'Success' in out or 'already complete' in out.lower()
        print(p['id'], 'complete' if p['ots_complete'] else 'still pending', '|', out.splitlines()[-1] if out else '')
        for bak in (f + '.bak',):
            if os.path.exists(bak): os.remove(bak)
    L.save(doc)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('file', nargs='?'); ap.add_argument('--resolves-by'); ap.add_argument('--title')
    ap.add_argument('--upgrade', action='store_true')
    a = ap.parse_args()
    if a.upgrade: return upgrade()
    if not a.file: ap.error('give the prediction file to seal')
    doc = L.load()
    day = L.today()
    n = 1 + sum(1 for p in doc['predictions'] if p['date'] == day)
    pid = f'P-{day}-{n:02d}'
    ext = os.path.splitext(a.file)[1] or '.txt'
    os.makedirs(L.PRIVATE, exist_ok=True)
    priv = os.path.join(L.PRIVATE, pid + ext)
    shutil.copyfile(a.file, priv)
    digest = L.sha256(priv)
    if any(p['sha256'] == digest for p in doc['predictions']): raise SystemExit('this exact text is already sealed')
    rc, out = L.ots('stamp', priv)
    if rc != 0 or not os.path.exists(priv + '.ots'): raise SystemExit(f'ots stamp failed: {out}')
    os.makedirs(os.path.join(L.PUB, 'ots'), exist_ok=True)
    rel = os.path.join('predictions', 'ots', pid + '.ots')
    shutil.move(priv + '.ots', os.path.join(L.ROOT, rel))
    entry = {'id': pid, 'date': day, 'sha256': digest, 'ots_file': rel, 'ext': ext, 'status': 'sealed', 'ots_complete': False}
    if a.title: entry['title'] = a.title
    if a.resolves_by: entry['resolves_by'] = a.resolves_by
    doc['predictions'].append(entry)
    L.save(doc)
    print(f'sealed {pid}: sha256 {digest}\n  private text: {priv}\n  public proof: {rel} (pending until Bitcoin confirms; run --upgrade later)')


if __name__ == '__main__':
    main()
