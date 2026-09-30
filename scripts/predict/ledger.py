"""Shared helpers for the prediction ledger (ORDER_012 Build 4).

Public:  predictions/ledger.json          every sealed prediction: id, date, sha256, ots_file, status (+ text once revealed)
         predictions/ots/<id>.ots         the OpenTimestamps proof that the sha256 existed on the sealing date
Private: local/predictions/<id>.<ext>     the plaintext, gitignored, until reveal.py publishes it
PREDICT_HOME overrides the repo root (used by the self-test)."""
import datetime as dt, hashlib, json, os, shutil, subprocess

ROOT = os.path.abspath(os.environ.get('PREDICT_HOME') or os.path.join(os.path.dirname(__file__), '..', '..'))
PUB = os.path.join(ROOT, 'predictions')
LEDGER = os.path.join(PUB, 'ledger.json')
PRIVATE = os.path.join(ROOT, 'local', 'predictions')
OTS = shutil.which('ots') or os.path.expanduser('~/.local/bin/ots')


def load():
    return json.load(open(LEDGER)) if os.path.exists(LEDGER) else {'about': 'Sealed predictions by Wes Knipe. Each entry is '
            'the SHA-256 of a prediction written before its date, time-stamped on Bitcoin with OpenTimestamps. Every sealed '
            'fingerprint is listed, so none can be quietly dropped; the text is published when revealed.', 'predictions': []}


def save(doc):
    os.makedirs(PUB, exist_ok=True)
    json.dump(doc, open(LEDGER, 'w'), indent=1, ensure_ascii=False)
    open(LEDGER, 'a').write('\n')


def sha256(path):
    return hashlib.sha256(open(path, 'rb').read()).hexdigest()


def ots(*args):
    if not os.path.exists(OTS): raise SystemExit('ots not found: python3 -m pip install --user opentimestamps-client')
    r = subprocess.run([OTS, *args], capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def today():
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def find(doc, pid):
    for p in doc['predictions']:
        if p['id'] == pid: return p
    raise SystemExit(f'no prediction {pid} in {LEDGER}')
