"""Rate-limit-aware Blockscout (base.blockscout.com) getter shared by the ORDER_010 scripts.

Blockscout publishes its limits in response headers (x-ratelimit-limit / -remaining / -reset in ms). Observed
2026-09-30: v2 REST 150 requests per ~5 min; v1 (Etherscan-style) 10 requests per ~40 min, 10,000 rows per call.
We never exceed them: when `remaining` reaches 0, or on 429, we sleep until the reset.
"""
import json, threading, time, urllib.error, urllib.request

UA = "wknipe-x402-index/0.1 (github.com/doescodinggiteasier/wknipe-site)"
BASE = "https://base.blockscout.com"
_locks = {'v1': threading.Lock(), 'v2': threading.Lock()}
_state = {'v1': {'remaining': 1, 'reset_at': 0.0, 'gap': 1.0, 'last': 0.0},
          'v2': {'remaining': 1, 'reset_at': 0.0, 'gap': 2.0, 'last': 0.0}}
STATS = {'v1': 0, 'v2': 0, '429': 0, 'errors': 0}


def _wait(bucket):
    s = _state[bucket]
    while True:
        with _locks[bucket]:
            now = time.time()
            if s['remaining'] <= 0 and now < s['reset_at']:
                pause = s['reset_at'] - now + 1
            elif now - s['last'] < s['gap']:
                pause = s['gap'] - (now - s['last'])
            else:
                s['last'] = now; s['remaining'] -= 1  # optimistic; corrected from headers
                return
        time.sleep(min(pause, 60))


def _update(bucket, headers):
    s = _state[bucket]
    try:
        rem, reset = headers.get('x-ratelimit-remaining'), headers.get('x-ratelimit-reset')
        with _locks[bucket]:
            if rem is not None: s['remaining'] = int(rem)
            if reset is not None: s['reset_at'] = time.time() + int(reset) / 1000
    except (TypeError, ValueError):
        pass


def get(path, bucket=None, tries=10, timeout=90):
    """GET BASE+path, JSON-decoded. bucket: 'v1' for /api?module=..., else 'v2'."""
    bucket = bucket or ('v1' if path.startswith('/api?') else 'v2')
    for i in range(tries):
        _wait(bucket)
        try:
            req = urllib.request.Request(BASE + path, headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                _update(bucket, r.headers); STATS[bucket] += 1
                return json.load(r)
        except urllib.error.HTTPError as e:
            _update(bucket, e.headers)
            if e.code == 429:
                STATS['429'] += 1
                with _locks[bucket]: _state[bucket]['remaining'] = 0
                if _state[bucket]['reset_at'] < time.time(): _state[bucket]['reset_at'] = time.time() + 60
                continue
            STATS['errors'] += 1
            if i == tries - 1: raise
            time.sleep(min(5 * 2 ** i, 120))
        except Exception:
            STATS['errors'] += 1
            if i == tries - 1: raise
            time.sleep(min(5 * 2 ** i, 120))
    raise RuntimeError(f'gave up on {path}')
