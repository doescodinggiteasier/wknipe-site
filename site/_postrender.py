#!/usr/bin/env python3
"""Quarto post-render (ORDER_014, mobile performance): rewrite each page's <head> so less of it blocks first paint.

- The dark Bootstrap stylesheets get media="(prefers-color-scheme: dark)": readers in light mode no longer wait for
  ~80 KB of dark CSS. A reader who picks dark with the toggle (or has picked it before) gets the media removed, so the
  toggle still works (inline script below).
- bootstrap-icons.css loads without blocking (icons appear a moment later; none are needed for the first paint).
- Quarto's head scripts (nav, headroom, clipboard, popper, tippy, bootstrap) get defer. Everything that uses them runs
  on DOMContentLoaded, which fires after deferred scripts have run.
Then _seo.apply(): canonical links, JSON-LD, sitemap, robots.txt, llms.txt (ORDER_014 addendum I).
Idempotent. Runs on every render after Quarto has written _site/.
"""
import glob, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SITE = os.path.join(HERE, '_site')
DEFER = ('quarto-nav/quarto-nav.js', 'quarto-nav/headroom.min.js', 'clipboard/clipboard.min.js', 'quarto-html/popper.min.js',
         'quarto-html/tippy.umd.min.js', 'bootstrap/bootstrap.min.js')
UNMEDIA = ('<script>(function(){var u=function(){document.querySelectorAll("link.quarto-color-alternate[media]").forEach(function(l){l.removeAttribute("media")})};'
           'try{if(localStorage.getItem("quarto-color-scheme")==="alternate")u()}catch(e){}'
           'document.addEventListener("click",function(e){if(e.target.closest(".quarto-color-scheme-toggle"))u()},true)})();</script>')


def fix(html):
    if 'data-wk-post="1"' in html: return html
    head, sep, rest = html.partition('</head>')
    if not sep: return html
    head = re.sub(r'<link ([^>]*class="[^"]*quarto-color-alternate[^"]*"[^>]*)>', lambda m: m.group(0) if 'media=' in m.group(1) else f'<link media="(prefers-color-scheme: dark)" {m.group(1)}>', head)
    head = re.sub(r'<link href="([^"]*bootstrap-icons\.css)" rel="stylesheet">', r"""<link href="\1" rel="stylesheet" media="print" onload="this.media='all'"><noscript><link href="\1" rel="stylesheet"></noscript>""", head)
    for s in DEFER:
        head = re.sub(r'<script src="([^"]*' + re.escape(s) + r')"></script>', r'<script defer src="\1"></script>', head)
    head += UNMEDIA + '<meta name="wk-post" data-wk-post="1">'
    return head + sep + rest


if __name__ == '__main__':
    n = 0
    for p in glob.glob(os.path.join(SITE, '**', '*.html'), recursive=True):
        s = open(p, encoding='utf-8').read(); t = fix(s)
        if t != s: open(p, 'w', encoding='utf-8').write(t); n += 1
    print(f'post-render: {n} pages')
    import _seo
    print('seo: sitemap urls', _seo.apply(SITE))
