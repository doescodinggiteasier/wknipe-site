#!/usr/bin/env python3
"""ORDER_010: snapshot the public CDP Bazaar x402 discovery listing (no key, free).
Writes STATE/bazaar/<date>.json.gz: the compact form (common.compact_listing: text fields and Base offers only, ~10x
smaller), which the index reads exactly as it read the full ORDER_001/010 snapshots (STATE/bazaar_all_<date>.json).
Usage: python3 scripts/x402_index/bazaar_snapshot.py [--date YYYY-MM-DD]"""
import argparse, datetime as dt, json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
import common

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UA = "wknipe-x402-index/0.1 (github.com/doescodinggiteasier/wknipe-site)"
API = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"


def get(url, tries=6):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=60) as r:
                return json.load(r)
        except Exception as e:
            if i == tries - 1: raise
            time.sleep(5 * 2 ** i)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--date', default=str(dt.datetime.now(dt.timezone.utc).date()))
    a = ap.parse_args()
    out = os.path.join(common.STATE, 'bazaar', f'{a.date}.json.gz')
    items, off = [], 0
    while True:
        d = get(f'{API}?limit=1000&offset={off}')
        page = d.get('items') or []
        items += page
        total = (d.get('pagination') or {}).get('total')
        print(off, len(page), total, flush=True)
        if len(page) < 1000: break
        off += 1000; time.sleep(1)
    if len(items) < 1000: raise SystemExit(f'only {len(items)} resources listed; refusing to save a partial snapshot')
    small = common.compact_listing(items)
    common.jdump(small, out)
    print(f'{len(items)} resources ({len(small)} with a Base offer) -> {out}')


if __name__ == '__main__':
    main()
