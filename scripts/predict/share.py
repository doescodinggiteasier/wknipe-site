#!/usr/bin/env python3
"""Show one person a sealed prediction before it is revealed, in a form they can check without trusting me.

  python3 scripts/predict/share.py P-2026-10-01-01 --to alice

Writes share/<id>_<name>.zip (gitignored) with the private salted text exactly as sealed, its OpenTimestamps proof and
a README.txt telling the recipient how to verify it: the file's SHA-256 must equal the fingerprint on the public
ledger, and `ots verify` ties that fingerprint to a Bitcoin block. The proof in the zip is upgraded on a copy when
the public one is still pending, so the recipient gets the Bitcoin attestation if it exists by now.
Nothing is published: predictions/ (ledger and proofs) is only read, and the entry stays "sealed". Each share is
logged locally, one tab-separated line in local/predictions/shares.log (gitignored): time, id, name, zip, sha256.
Refuses if the private file no longer matches the ledger fingerprint, or if the prediction is already revealed.
(ORDER_022)"""
import argparse, datetime as dt, os, re, shutil, sys, tempfile, zipfile

sys.path.insert(0, os.path.dirname(__file__))
import ledger as L

SHARE = os.path.join(L.ROOT, 'share')
LOG = os.path.join(L.PRIVATE, 'shares.log')
LEDGER_URL = 'https://github.com/doescodinggiteasier/wknipe-site/blob/main/predictions/ledger.json'

README = """{id}: a sealed prediction, shared with {name} on {today}

I sealed this prediction on {date}. Only its fingerprint (SHA-256) is public, at https://wknipe.com/predictions/;
the text itself hasn't been published. I'm showing it to you before it is revealed, so please keep it to yourself
until then.

Files
  {fname:<{w}}  the prediction, byte for byte as sealed. Its last line ("salt: " and 32 random
  {blank:<{w}}  characters) was added before sealing, so nobody can work out a short text by guessing
  {blank:<{w}}  and hashing. It is part of the sealed file; leave it in.
  {ots:<{w}}  the OpenTimestamps proof that the fingerprint existed on {date}{pending}
  {readme:<{w}}  this note

How to check it (you don't have to trust me)

1. The text is the one I sealed. Compute the file's SHA-256:
     macOS / Linux:  shasum -a 256 {fname}
     Windows:        certutil -hashfile {fname} SHA256
   It must print
     {sha}
   and that must be the fingerprint listed for {id} on https://wknipe.com/predictions/ (the same list is in
   {ledger_url}).
   Change a single character of the file and the fingerprint comes out completely different.

2. It existed on that date. Drop both files on https://opentimestamps.org, or run
     pip install opentimestamps-client
     ots --no-bitcoin verify -f {fname} {ots}
   "check that Bitcoin block N has merkleroot ..." names the block that commits to the fingerprint; look the block
   up on any block explorer: the text existed no later than that block's time.
   "Pending confirmation" means Bitcoin hasn't confirmed it yet (that takes a few hours): run
   `ots upgrade {ots}` later and verify again.
   "File does not match original!" means the file was changed.
"""


def safe_name(name):
    s = re.sub(r'[^A-Za-z0-9._-]+', '-', name).strip('-.')
    if not s: raise SystemExit(f'--to {name!r}: use letters or digits, it becomes part of the file name')
    return s


def proof_for_recipient(p, tmp):
    """A copy of the public proof, upgraded if it is still pending. The public file is never written."""
    src = os.path.join(L.ROOT, p['ots_file'])
    dst = os.path.join(tmp, p['id'] + '.ots')
    shutil.copyfile(src, dst)
    if p.get('ots_complete'): return dst, True
    rc, out = L.ots('upgrade', dst)
    return dst, rc == 0 and 'Success' in out or 'already complete' in out.lower()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('id'); ap.add_argument('--to', required=True, help="recipient's name")
    a = ap.parse_args()
    doc = L.load(); p = L.find(doc, a.id)
    if p['status'] != 'sealed': raise SystemExit(f'{a.id} is already {p["status"]}: send https://wknipe.com/predictions/ instead')
    fname = a.id + p.get('ext', '.txt')
    priv = os.path.join(L.PRIVATE, fname)
    if not os.path.exists(priv): raise SystemExit(f'private text not found: {priv}')
    digest = L.sha256(priv)
    if digest != p['sha256']: raise SystemExit(f'hash mismatch: ledger {p["sha256"]}, file {digest}. Not sharing.')
    name = safe_name(a.to)
    now = dt.datetime.now(dt.timezone.utc)
    os.makedirs(SHARE, exist_ok=True)
    out = os.path.join(SHARE, f'{a.id}_{name}.zip')
    with tempfile.TemporaryDirectory() as tmp:
        proof, complete = proof_for_recipient(p, tmp)
        ots_name = os.path.basename(proof)
        w = max(len(fname), len(ots_name), len('README.txt'))
        readme = README.format(id=a.id, name=a.to, today=now.date().isoformat(), date=p['date'], fname=fname, ots=ots_name,
                               readme='README.txt', blank='', w=w,
                               sha=digest, ledger_url=LEDGER_URL,
                               pending='' if complete else '\n  ' + ' ' * w + '  (still waiting for Bitcoin when I sent it; see step 2)')
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(priv, fname)
            z.write(proof, ots_name)
            z.writestr('README.txt', readme)
    with open(LOG, 'a') as fh:
        fh.write('\t'.join([now.isoformat(timespec='seconds'), a.id, ' '.join(a.to.split()), os.path.relpath(out, L.ROOT), digest]) + '\n')
    print(f'shared {a.id} with {a.to}: {out}\n  proof {"complete" if complete else "still pending"}; nothing published; '
          f'logged in {os.path.relpath(LOG, L.ROOT)}')


if __name__ == '__main__':
    main()
