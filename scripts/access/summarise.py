#!/usr/bin/env python3
"""ORDER_013 Phase 4: summarise the AI-access census runs (scripts/access/census.mjs) into the /access/ page data.

Per run: share of checked Tranco domains whose robots.txt blocks each named AI crawler (fully; partial blocks counted
separately), share blocking any / all training crawlers, and adoption of Content-Signal, RSL, TDMRep, llms.txt, plus
domains answering our identified crawler with HTTP 402 or a machine-readable price.
History is seeded with the ORDER_004 Common Crawl census (CC-MAIN-2026-39, 5% robots.txt sample, 2.67M hosts) for the
metrics measured the same way; it is a different population (all crawled hosts, not the top sites), marked as a
method break on the page.
Writes data/ai_access/{access_weekly.csv, access_latest.csv, access.json}.
"""
import collections, csv, glob, gzip, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
STATE = os.path.join(ROOT, os.environ['X402_STATE']) if os.environ.get('X402_STATE') else os.path.join(ROOT, 'local')
OUT = os.path.join(ROOT, 'data', 'ai_access')
TRAINING = ['GPTBot', 'ClaudeBot', 'Google-Extended', 'Applebot-Extended', 'Meta-ExternalAgent', 'CCBot', 'Bytespider']


def seed():
    """CC-MAIN-2026-39 5% sample (ORDER_004): hosts with a robots.txt (HTTP 200)."""
    h = json.load(open(os.path.join(ROOT, 'data', 'a_census_sample5_hosts_summary.json')))
    n = h['records_200']
    rows = [{'date': '2026-09-27', 'population': 'CC-MAIN-2026-39 5% sample (hosts with robots.txt)', 'metric': 'content_signal', 'value': round(h['hosts_with_content_signal'] / n, 5), 'n': n},
            {'date': '2026-09-27', 'population': 'CC-MAIN-2026-39 5% sample (hosts with robots.txt)', 'metric': 'rsl', 'value': round(h['hosts_with_rsl_license'] / n, 5), 'n': n},
            {'date': '2026-09-27', 'population': 'CC-MAIN-2026-39 5% sample (hosts with robots.txt)', 'metric': 'any_ai_bot_blocked', 'value': round(h['hosts_with_ai_crawler_block'] / n, 5), 'n': n}]
    for bot, k in h['ai_block_by_bot'].items():
        rows.append({'date': '2026-09-27', 'population': 'CC-MAIN-2026-39 5% sample (hosts with robots.txt)', 'metric': 'named_block:' + bot.lower(), 'value': round(k / n, 5), 'n': n})
    return rows


def summarise_run(run):
    """Denominators: block shares are of domains with a robots.txt (explicit rules); file/header signals are of domains
    that serve a website (robots.txt reachable, found or not). Domains whose robots.txt is unreachable (CDN, API and
    infrastructure hostnames in the Tranco list) are excluded and counted: RFC 9309 tells crawlers to treat them as fully
    disallowed, but that is not a policy choice."""
    res = [r for r in run['results'] if r and 'summary' in r]
    web = [r for r in res if r['robots']['state'] != 'unreachable']
    found = [r for r in res if r['robots']['state'] == 'found']
    pop = f"Tranco top {run['top']} ({run['tranco_list_id']})"
    rows = []
    add = lambda metric, k, denom: rows.append({'date': run['date'], 'population': pop, 'metric': metric, 'value': round(k / denom, 5) if denom else None, 'n': denom})
    st = lambda r, tok: next(b for b in r['robots']['bots'] if b['token'] == tok)
    bots = collections.OrderedDict((b['token'], b) for b in res[0]['robots']['bots']) if res else {}
    for tok in bots:
        add('named_block:' + tok.lower(), sum(1 for r in found if st(r, tok)['status'] == 'blocked' and st(r, tok).get('via') == 'named'), len(found))
        add('blocked:' + tok.lower(), sum(1 for r in found if st(r, tok)['status'] == 'blocked'), len(found))
        add('partial:' + tok.lower(), sum(1 for r in found if st(r, tok)['status'] == 'partial'), len(found))
    add('robots_found', len(found), len(web))
    add('any_ai_bot_blocked', sum(1 for r in found if any(b['status'] == 'blocked' and b.get('via') == 'named' for b in r['robots']['bots'])), len(found))
    add('all_training_bots_blocked', sum(1 for r in found if all(st(r, t)['status'] == 'blocked' for t in TRAINING)), len(found))
    add('content_signal', sum(1 for r in web if r['summary']['content_signal']), len(web))
    add('rsl', sum(1 for r in web if r['summary']['rsl']), len(web))
    add('tdmrep', sum(1 for r in web if r['summary']['tdmrep']), len(web))
    add('llms_txt', sum(1 for r in web if r['summary']['llms_txt']), len(web))
    add('http_402', sum(1 for r in web if r['homepage'].get('http_402')), len(web))
    add('machine_readable_price', sum(1 for r in web if r['summary']['machine_readable_price']), len(web))
    latest = [{'rank': r['rank'], 'domain': r['domain'], 'robots': r['robots']['state'], 'ai_bots_blocked_by_name': sum(1 for b in r['robots']['bots'] if b['status'] == 'blocked' and b.get('via') == 'named'),
               'ai_bots_blocked': r['summary']['blocked'], 'ai_bots_checked': r['summary']['ai_bots_checked'], 'default_other_bots': r['summary']['default_for_other_bots'],
               'content_signal': r['summary']['content_signal'], 'rsl': r['summary']['rsl'], 'tdmrep': r['summary']['tdmrep'], 'llms_txt': r['summary']['llms_txt'],
               'http_402': bool(r['homepage'].get('http_402')), 'machine_readable_price': r['summary']['machine_readable_price'],
               'blocked_bots': ' '.join(b['token'] for b in r['robots']['bots'] if b['status'] == 'blocked' and r['robots']['state'] == 'found')} for r in res]
    errors = [r for r in run['results'] if r and 'summary' not in r]
    return rows, latest, {'date': run['date'], 'population': pop, 'checked': len(res), 'serves_website': len(web), 'robots_found': len(found),
                          'robots_unreachable': len(res) - len(web), 'not_checkable': len(errors), 'requests_approx': run.get('requests_approx'),
                          'seconds': run.get('seconds'), 'tranco_list_id': run['tranco_list_id'], 'tranco_created_on': run['tranco_created_on'], 'bots': list(bots),
                          'bot_meta': {t: {'operator': b['operator'], 'purpose': b['purpose']} for t, b in bots.items()}}


def main():
    runs = sorted(glob.glob(os.path.join(STATE, 'ai_access', 'run_*.json.gz')))
    if not runs: sys.exit('no census runs')
    rows = seed(); meta = []; latest = None
    for p in runs:
        run = json.load(gzip.open(p, 'rt'))
        r, latest, m = summarise_run(run); rows += r; meta.append(m)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'access_weekly.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['date', 'population', 'metric', 'value', 'n']); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, 'access_latest.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(latest[0])); w.writeheader(); w.writerows(latest)
    last = meta[-1]
    lr = {r['metric']: r for r in rows if r['date'] == last['date'] and r['population'] == last['population']}
    nf = last['robots_found']
    bots = [{'bot': t, 'operator': last['bot_meta'][t]['operator'], 'purpose': last['bot_meta'][t]['purpose'], 'named_block': lr['named_block:' + t.lower()]['value'],
             'blocked': lr['blocked:' + t.lower()]['value'], 'partial': lr['partial:' + t.lower()]['value'], 'n': nf, 'k': round(lr['named_block:' + t.lower()]['value'] * nf)} for t in last['bots']]
    cc = {r['metric']: r['value'] for r in rows if r['population'].startswith('CC-MAIN')}
    for b in bots: b['cc_sample'] = cc.get('named_block:' + b['bot'].lower())
    bots.sort(key=lambda b: -b['named_block'])
    signals = [{'signal': lab, 'share': lr[k]['value'], 'n': lr[k]['n'], 'k': round(lr[k]['value'] * lr[k]['n']), 'cc_sample': cc.get(k)} for k, lab in
               (('robots_found', 'Has a robots.txt'), ('any_ai_bot_blocked', 'Blocks at least one AI crawler by name'), ('all_training_bots_blocked', 'Blocks all 7 major training crawlers'),
                ('content_signal', 'Content-Signal in robots.txt'), ('llms_txt', 'Publishes /llms.txt'), ('tdmrep', 'TDMRep (/.well-known/tdmrep.json)'),
                ('rsl', 'RSL licence link'), ('machine_readable_price', 'States a machine-readable price'), ('http_402', 'Answers our crawler with HTTP 402'))]
    json.dump({'runs': meta, 'latest': last, 'bots': bots, 'signals': signals, 'history': rows}, open(os.path.join(OUT, 'access.json'), 'w'))
    print(json.dumps({'latest': last, 'top_bots': bots[:5], 'signals': signals}, indent=1))


if __name__ == '__main__':
    main()
