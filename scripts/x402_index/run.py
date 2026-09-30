#!/usr/bin/env python3
"""ORDER_010: one command for the x402 Clean Index.

  python3 scripts/x402_index/run.py            # rebuild every headline number and the page from cached data (no keys)
  python3 scripts/x402_index/run.py --weekly   # the weekly job: Bazaar snapshot, collect last full week,
                                               # classify new payees (OpenRouter), then rebuild
The weekly job needs OPENROUTER_API_KEY in the environment only if new listed payees appeared:
  export OPENROUTER_API_KEY=$(security find-generic-password -s openrouter -w) && python3 scripts/x402_index/run.py --weekly
CI (wknipe-site .github/workflows/weekly.yml) runs `--weekly --deadline 18000` with X402_STATE=state, X402_STRICT=1:
exit 75 = the week's collection is unfinished (progress kept for the next run); any other non-zero exit = do not deploy.
"""
import argparse, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = 'mistralai/mistral-small-3.2-24b-instruct'  # chosen by the ORDER_010 pilot (local/o10_classifier_pilot.json)
FALLBACK = 'google/gemini-2.5-flash-lite'  # pilot runner-up


def step(*args, ok=(0,)):
    print('>>', ' '.join(args), flush=True)
    rc = subprocess.run([sys.executable, *args]).returncode
    if rc not in ok: sys.exit(rc)
    return rc


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--weekly', action='store_true')
    ap.add_argument('--deadline', help='seconds of collection before stopping to resume later (CI)')
    a = ap.parse_args()
    if a.weekly:
        step(os.path.join(HERE, 'bazaar_snapshot.py'))
        if step(os.path.join(HERE, 'collect.py'), '--latest', *(['--deadline', a.deadline] if a.deadline else []), ok=(0, 75)) == 75:
            print('collection unfinished: stopping before build (exit 75)', flush=True); sys.exit(75)
        if os.environ.get('OPENROUTER_API_KEY'):
            step(os.path.join(HERE, 'classify.py'), '--model', MODEL)
            step(os.path.join(HERE, 'classify.py'), '--model', FALLBACK,  # payees MODEL returned malformed JSON for
                 *(['--strict'] if os.environ.get('X402_STRICT') == '1' else []))
        else:
            print('OPENROUTER_API_KEY not set: new payees stay unclassed this run', flush=True)
    step(os.path.join(HERE, 'build.py'))
    step(os.path.join(HERE, 'review_unlisted.py'))  # top unlisted sellers until unclassed < 25% of clean USD
    step(os.path.join(HERE, 'build.py'))
    step(os.path.join(HERE, 'site.py'))
    # ORDER_013: market / buyer / seller-quality stats (cached per week while the raw week is still on disk), then the
    # listing classes (new listing texts only; OR_CAP applies) and the posted-price / Price comps data.
    step(os.path.join(HERE, '..', 'x402_market', 'build.py'))
    if a.weekly and os.environ.get('OPENROUTER_API_KEY'):
        step(os.path.join(HERE, '..', 'x402_prices', 'classify_listings.py'), '--model', 'google/gemini-2.5-flash-lite')
    step(os.path.join(HERE, '..', 'x402_prices', 'build.py'))
