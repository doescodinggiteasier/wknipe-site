"""ORDER_024: links that appear only when there is something behind them.

- Writing: the navbar item, the footer RSS link and the home-page section appear only when at least one piece in
  writing/ is published (no `draft: true`). With none, they are absent. /writing/ itself stays reachable by URL.
- Prediction ledger: the home-page row, the Index entry and the llms.txt line appear only when the ledger has at least
  one entry. /predictions/ stays reachable by URL.

Used by _pages.py (home), _index_pages.py (the Index), _seo.py (llms.txt) and _postrender.py (navbar and footer).
Tested in scripts/site/test_conditional.py (negative controls included); a built site is checked with
scripts/site/check_conditional.py."""
import glob, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
PREDICTIONS = '/predictions/'


def published_posts(site=HERE):
    """(date, title, url) for every published piece in writing/, newest first."""
    posts = []
    for p in sorted(glob.glob(os.path.join(site, 'writing', '*.qmd'))):
        if p.endswith('index.qmd'): continue
        with open(p, encoding='utf-8') as fh: text = fh.read()
        fm = text.split('---')[1] if text.startswith('---') else ''
        if re.search(r'^draft:\s*true', fm, re.M): continue
        t = re.search(r'^title:\s*"?(.*?)"?\s*$', fm, re.M); dd = re.search(r'^date:\s*"?([\d-]+)', fm, re.M)
        posts.append((dd.group(1) if dd else '', t.group(1) if t else os.path.basename(p), '/writing/' + os.path.basename(p)[:-4]))
    return sorted(posts, reverse=True)


def ledger_entries(root=ROOT):
    """Number of entries in the prediction ledger (0 when there is no ledger)."""
    p = os.path.join(root, 'predictions', 'ledger.json')
    if not os.path.exists(p): return 0
    with open(p, encoding='utf-8') as fh: return len(json.load(fh).get('predictions') or [])


def show(href, root=ROOT):
    """False for a link that should be hidden right now (only the empty ledger, for now)."""
    return not (href.rstrip('/') + '/' == PREDICTIONS and ledger_entries(root) == 0)


# Quarto renders the navbar item as <li class="nav-item"><a class="nav-link" href="../writing/index.html">…Writing…</a></li>
# (the relative prefix depends on the page's depth), the footer link as <a href="./feed.xml">RSS</a> (relative too), and
# the writing listing's feed as <link rel="alternate" type="application/rss+xml" title="Wes Knipe: writing" href="index.xml">.
NAV_WRITING = re.compile(r'\s*<li class="nav-item">\s*<a class="nav-link[^"]*" href="(?:\.\./|\./|/)*writing/(?:index\.html)?"[^>]*>.*?</a>\s*</li>', re.S)
FOOTER_RSS = re.compile(r'\s*·\s*<a href="(?:\.\./|\./|/)*feed\.xml"[^>]*>RSS</a>')
FEED_HEAD = re.compile(r'\s*<link rel="alternate" type="application/rss\+xml" title="Wes Knipe: writing"[^>]*>')


def has_writing_link(html):
    """True if a page still links to the Writing section from its navbar or footer."""
    return bool(NAV_WRITING.search(html) or FOOTER_RSS.search(html))


def strip_writing_links(html):
    return FEED_HEAD.sub('', FOOTER_RSS.sub('', NAV_WRITING.sub('', html)))


def apply(site_out, site=HERE):
    """Post-render: with no published writing, remove the Writing navbar item and RSS links from every page."""
    if published_posts(site): return 0
    n = 0
    for p in glob.glob(os.path.join(site_out, '**', '*.html'), recursive=True):
        with open(p, encoding='utf-8') as fh: s = fh.read()
        t = strip_writing_links(s)
        if t != s:
            with open(p, 'w', encoding='utf-8') as fh: fh.write(t)
            n += 1
    return n
