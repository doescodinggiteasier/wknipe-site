#!/usr/bin/env python3
"""ORDER_024: check a built site against the "no link to an empty section" rule (site/_conditional.py).

  python3 scripts/site/check_conditional.py [--site site/_site] [--src site] [--root .]

Violations:
- No published writing, yet a page has the Writing navbar item or the footer RSS link, or the home page links to /writing/.
- At least one published piece, yet the home page has no Writing navbar item.
- An empty prediction ledger, yet the home page, the Index page or llms.txt links to /predictions/.
- The Index page lists no entries (hiding one entry must not empty the list).
Exit 0 when there are none, 1 when there are any, 3 when the build is missing or has no pages (so a check run on
nothing cannot pass) or the check itself errors."""
import argparse, glob, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


sys.path.insert(0, os.path.join(ROOT, 'site'))
import _conditional as c  # noqa: E402  (the rule lives with the site; --src only says where the writing/ folder is)


def check(site_out, src, root):
    pages = sorted(glob.glob(os.path.join(site_out, '**', '*.html'), recursive=True))
    home = os.path.join(site_out, 'index.html')
    if not pages or not os.path.exists(home):
        return None, [f'no built pages under {site_out}']
    posts, ledger = c.published_posts(src), c.ledger_entries(root)
    def rd(p):
        with open(p, encoding='utf-8') as fh: return fh.read()
    bad = []
    if not posts:
        bad += [f'{os.path.relpath(p, site_out)}: Writing link with 0 published pieces' for p in pages if c.has_writing_link(rd(p))]
        if re.search(r'href="(?:\./|/)?writing/"', rd(home)): bad.append('index.html: home-page link to /writing/ with 0 published pieces')
    elif not c.NAV_WRITING.search(rd(home)):
        bad.append(f'index.html: no Writing navbar item with {len(posts)} published piece(s)')
    if ledger == 0:
        link = re.compile(r'href="(?:\.\./|\./|/)*predictions/"|/index/prediction-ledger|href="(?:\./)?prediction-ledger(?:\.html)?"')
        for rel in ('index.html', os.path.join('index', 'index.html')):
            p = os.path.join(site_out, rel)
            if os.path.exists(p) and link.search(rd(p)): bad.append(f'{rel}: link to the prediction ledger with 0 entries')
        llms = os.path.join(site_out, 'llms.txt')
        if os.path.exists(llms) and '/predictions/' in rd(llms): bad.append('llms.txt: prediction ledger listed with 0 entries')
    ix = os.path.join(site_out, 'index', 'index.html')
    if os.path.exists(ix):
        m = re.search(r'id="ix-count">(\d+)<', rd(ix))
        if not m or int(m.group(1)) == 0: bad.append('index/index.html: the Index lists no entries')
    return {'pages': len(pages), 'published': len(posts), 'ledger': ledger}, bad


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--site', default=os.path.join(ROOT, 'site', '_site'))
    ap.add_argument('--src', default=os.path.join(ROOT, 'site'))
    ap.add_argument('--root', default=ROOT)
    a = ap.parse_args()
    try:
        info, bad = check(os.path.abspath(a.site), os.path.abspath(a.src), os.path.abspath(a.root))
    except Exception as e:  # an error is not a verdict
        print('ERROR:', repr(e)); sys.exit(3)
    if info is None:
        print('FAIL:', bad[0]); sys.exit(3)
    print(f"{info['pages']} pages, {info['published']} published piece(s), {info['ledger']} ledger entries")
    for b in bad[:20]: print('VIOLATION', b)
    if len(bad) > 20: print(f'... and {len(bad) - 20} more')
    print('OK' if not bad else f'{len(bad)} violation(s)')
    sys.exit(1 if bad else 0)
