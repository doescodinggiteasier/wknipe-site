#!/usr/bin/env python3
"""Seal a prediction: fingerprint it, time-stamp the fingerprint on Bitcoin, list it publicly. The text stays private.

  python3 scripts/predict/seal.py my-prediction.md [--resolves-by 2031-01-01] [--title "short public label"]

1. copies the file to local/predictions/<id><ext> (gitignored) and appends one line, `salt: <32 random hex chars>`, to
   that private copy (ORDER_022). Your original file is never changed. The salt (128 random bits) means a short or
   guessable text ("Yes.", a name, a number) can't be recovered by hashing guesses until one matches the public
   fingerprint. The salt line is part of the sealed file: share.py and reveal.py hand it out unchanged;
2. computes the private copy's SHA-256 and runs `ots stamp` (submits the hash, never the text, to public
   OpenTimestamps calendars);
3. copies the proof to predictions/ots/<id>.ots and appends {id, date, sha256, ots_file, status: sealed, salted: true}
   to predictions/ledger.json.
The proof is "pending" until a calendar's Bitcoin transaction confirms (a few hours); run
`python3 scripts/predict/seal.py --upgrade` later to embed the Bitcoin attestation in every pending proof.
Don't edit the private copy after sealing: any byte changed breaks the hash. The title (optional) is public; keep it
vague. Entries sealed before ORDER_022 have no salt line and no `salted` field; they are left as they are."""
import argparse, os, re, secrets, shutil, sys

sys.path.insert(0, os.path.dirname(__file__))
import ledger as L

SALT_LINE = re.compile(rb'salt: [0-9a-f]{32}\n\Z')


def with_newline(data):
    """The text as it sits in front of the salt line: a missing final newline is added."""
    return data if not data or data.endswith(b'\n') else data + b'\n'


def salted_copy(src, dst):
    """Copy src to dst and append `salt: <32 random hex chars>` as a new last line. src is only read. Returns the salt."""
    salt = secrets.token_hex(16)
    with open(src, 'rb') as fh: data = fh.read()
    with open(dst, 'wb') as fh: fh.write(with_newline(data) + f'salt: {salt}\n'.encode())
    return salt


def already_sealed(doc, src):
    """The id of an earlier prediction with this exact text, if any. A salted hash differs on every seal, so compare
    the private copies with their salt line removed (and the public hash, for entries sealed without a salt)."""
    data, digest = open(src, 'rb').read(), L.sha256(src)
    for p in doc['predictions']:
        if p['sha256'] == digest: return p['id']
        priv = os.path.join(L.PRIVATE, p['id'] + p.get('ext', '.txt'))
        if not os.path.exists(priv): continue
        old = open(priv, 'rb').read()
        m = SALT_LINE.search(old)
        if m and old[:m.start()] == with_newline(data): return p['id']


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
    dup = already_sealed(doc, a.file)
    if dup: raise SystemExit(f'this exact text is already sealed as {dup}')
    day = L.today()
    n = 1 + sum(1 for p in doc['predictions'] if p['date'] == day)
    pid = f'P-{day}-{n:02d}'
    ext = os.path.splitext(a.file)[1] or '.txt'
    os.makedirs(L.PRIVATE, exist_ok=True)
    priv = os.path.join(L.PRIVATE, pid + ext)
    salted_copy(a.file, priv)
    digest = L.sha256(priv)
    rc, out = L.ots('stamp', priv)
    if rc != 0 or not os.path.exists(priv + '.ots'): raise SystemExit(f'ots stamp failed: {out}')
    os.makedirs(os.path.join(L.PUB, 'ots'), exist_ok=True)
    rel = os.path.join('predictions', 'ots', pid + '.ots')
    shutil.move(priv + '.ots', os.path.join(L.ROOT, rel))
    entry = {'id': pid, 'date': day, 'sha256': digest, 'ots_file': rel, 'ext': ext, 'status': 'sealed', 'ots_complete': False,
             'salted': True}
    if a.title: entry['title'] = a.title
    if a.resolves_by: entry['resolves_by'] = a.resolves_by
    doc['predictions'].append(entry)
    L.save(doc)
    print(f'sealed {pid}: sha256 {digest}\n  private text (your original plus a salt line): {priv}\n'
          f'  public proof: {rel} (pending until Bitcoin confirms; run --upgrade later)')


if __name__ == '__main__':
    main()
