#!/usr/bin/env python3
"""Tests for ORDER_024's "no link to an empty section" rule (site/_conditional.py, scripts/site/check_conditional.py).

  python3 scripts/site/test_conditional.py -v

Each test builds a tiny site in a temp directory: writing/ with 0, 1 draft or 1 published piece, a ledger with 0 or 1
entries, and pages whose navbar and footer are copied from real Quarto output. The real repo is never touched.
Negative controls: the checker must FAIL on a page that keeps the Writing link with 0 published pieces (and on the
ledger link with 0 entries), and on an empty build. Positive: it passes once one piece is published and the link stays."""
import json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'site'))
sys.path.insert(0, HERE)
import _conditional as c  # noqa: E402
import check_conditional as chk  # noqa: E402

# Navbar item and footer exactly as Quarto 1.x renders them on wknipe.com (copied from a render of 07aca2b).
NAV = '''<ul class="navbar-nav navbar-nav-scroll ms-auto">
  <li class="nav-item">
    <a class="nav-link" href="{p}writing/index.html">
<span class="menu-text">Writing</span></a>
  </li>
  <li class="nav-item">
    <a class="nav-link" href="{p}about.html">
<span class="menu-text">About</span></a>
  </li>
</ul>'''
FOOT = '<div class="nav-footer-left"><p><a href="{p}api/">API</a> · <a href="{p}index/">Index</a> · <a href="{p}feed.xml">RSS</a> · <a href="https://github.com/x">GitHub</a></p></div>'
PAGE = '<!DOCTYPE html><html><head><title>t</title></head><body><nav>' + NAV + '</nav><main>{main}</main><footer>' + FOOT + '</footer></body></html>'
def rd(p):
    with open(p, encoding='utf-8') as fh: return fh.read()


def wr(p, text):
    with open(p, 'w', encoding='utf-8') as fh: fh.write(text)


POST = '---\ntitle: "A piece"\ndate: 2026-10-05\n{draft}---\n\nText.\n'


class Site:
    """A temp site: src (with writing/), root (with predictions/ledger.json) and out (the built pages)."""
    def __init__(self, tc, posts=0, draft=False, ledger=0, home_main=''):
        self.d = tempfile.mkdtemp(); tc.addCleanup(shutil.rmtree, self.d)
        self.src, self.root, self.out = (os.path.join(self.d, x) for x in ('site', 'repo', 'out'))
        os.makedirs(os.path.join(self.src, 'writing')); os.makedirs(os.path.join(self.root, 'predictions'))
        wr(os.path.join(self.src, 'writing', 'index.qmd'), '---\ntitle: Writing\n---\n')
        for i in range(posts):
            wr(os.path.join(self.src, 'writing', f'p{i}.qmd'), POST.format(draft='draft: true\n' if draft else ''))
        wr(os.path.join(self.root, 'predictions', 'ledger.json'), json.dumps({'about': 'x', 'predictions': [{'id': f'P-{i}'} for i in range(ledger)]}))
        for rel, p, main in (('index.html', './', home_main), ('about.html', './', ''), ('x402/sellers/index.html', '../../', ''), ('writing/index.html', '../', '')):
            os.makedirs(os.path.dirname(os.path.join(self.out, rel)) or self.out, exist_ok=True)
            wr(os.path.join(self.out, rel), PAGE.format(p=p, main=main))

    def postrender(self):
        return c.apply(self.out, self.src)

    def check(self):
        info, bad = chk.check(self.out, self.src, self.root)
        return bad

    def page(self, rel='index.html'):
        return rd(os.path.join(self.out, rel))


class Writing(unittest.TestCase):
    def test_negative_control_link_with_zero_published_fails(self):
        s = Site(self, posts=0)  # not post-rendered: the Writing link is still on every page
        bad = s.check()
        self.assertTrue(any('Writing link with 0 published' in b for b in bad), bad)
        self.assertEqual(sum('Writing link' in b for b in bad), 4, 'all four pages carry the link')

    def test_draft_only_counts_as_zero(self):
        s = Site(self, posts=1, draft=True)
        self.assertEqual(c.published_posts(s.src), [])
        self.assertTrue(s.check(), 'a draft is not a published piece: the unstripped link must fail')
        s.postrender()
        self.assertEqual(s.check(), [])

    def test_zero_published_after_postrender_passes(self):
        s = Site(self, posts=0)
        self.assertEqual(s.postrender(), 4)
        self.assertEqual(s.check(), [])
        for rel in ('index.html', 'about.html', 'x402/sellers/index.html', 'writing/index.html'):
            p = s.page(rel)
            self.assertFalse(c.has_writing_link(p), rel)
            self.assertIn('menu-text">About<', p, 'the other navbar items stay')
            self.assertIn('>Index</a> · <a href="https://github.com/x">GitHub</a>', p, 'the footer closes up around the removed link')

    def test_one_published_keeps_link_and_passes(self):
        s = Site(self, posts=1)
        self.assertEqual(len(c.published_posts(s.src)), 1)
        self.assertEqual(s.postrender(), 0, 'nothing is stripped once a piece is published')
        self.assertTrue(c.has_writing_link(s.page()))
        self.assertEqual(s.check(), [])

    def test_one_published_but_link_removed_fails(self):
        s = Site(self, posts=1)
        wr(os.path.join(s.out, 'index.html'), c.strip_writing_links(s.page()))
        self.assertTrue(any('no Writing navbar item' in b for b in s.check()))

    def test_home_section_link_with_zero_published_fails(self):
        s = Site(self, posts=0, home_main='<h2>Writing</h2><p class="more"><a href="/writing/">All writing →</a></p>')
        s.postrender()
        self.assertTrue(any('home-page link to /writing/' in b for b in s.check()))

    def test_empty_build_fails(self):
        s = Site(self, posts=0); shutil.rmtree(s.out); os.makedirs(s.out)
        info, bad = chk.check(s.out, s.src, s.root)
        self.assertIsNone(info); self.assertTrue(bad)


class IndexPage(unittest.TestCase):
    def test_empty_index_fails_and_listed_index_passes(self):
        s = Site(self); s.postrender(); os.makedirs(os.path.join(s.out, 'index'))
        wr(os.path.join(s.out, 'index', 'index.html'), '<p class="meta ix-head"><span id="ix-count">0</span> entries</p>')
        self.assertTrue(any('lists no entries' in b for b in s.check()), 'negative control: an empty Index must fail')
        wr(os.path.join(s.out, 'index', 'index.html'), '<p class="meta ix-head"><span id="ix-count">23</span> entries</p>')
        self.assertEqual(s.check(), [])


class Ledger(unittest.TestCase):
    ROW = '<li><a href="./predictions/"><span class="t">Prediction ledger</span></a></li>'

    def test_show_rule(self):
        self.assertFalse(c.show('/predictions/', Site(self, ledger=0).root))
        self.assertTrue(c.show('/predictions/', Site(self, ledger=1).root))
        self.assertTrue(c.show('/x402/', Site(self, ledger=0).root), 'other links are never hidden')
        self.assertEqual(c.ledger_entries(tempfile.gettempdir() + '/no-such-repo'), 0)

    def test_negative_control_ledger_link_with_zero_entries_fails(self):
        s = Site(self, posts=0, ledger=0, home_main=self.ROW); s.postrender()
        self.assertTrue(any('prediction ledger with 0 entries' in b for b in s.check()))

    def test_ledger_link_with_one_entry_passes(self):
        s = Site(self, posts=0, ledger=1, home_main=self.ROW); s.postrender()
        self.assertEqual(s.check(), [])

    def test_llms_txt_listing_with_zero_entries_fails(self):
        s = Site(self, ledger=0); s.postrender()
        wr(os.path.join(s.out, 'llms.txt'), '- [Prediction ledger](https://wknipe.com/predictions/): x\n')
        self.assertTrue(any('llms.txt' in b for b in s.check()))


class Cli(unittest.TestCase):
    def run_cli(self, s):
        return subprocess.run([sys.executable, os.path.join(HERE, 'check_conditional.py'), '--site', s.out, '--src', s.src, '--root', s.root],
                              capture_output=True, text=True).returncode

    def test_exit_codes(self):
        self.assertEqual(self.run_cli(Site(self, posts=0)), 1, 'violations exit 1')
        s = Site(self, posts=0); s.postrender()
        self.assertEqual(self.run_cli(s), 0, 'clean build exits 0')
        e = Site(self); shutil.rmtree(e.out)
        self.assertEqual(self.run_cli(e), 3, 'no build exits 3, never 0')


if __name__ == '__main__':
    unittest.main()
