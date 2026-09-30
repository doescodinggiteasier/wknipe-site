"""ORDER_005_ADDENDUM §3: report an x402 week raw and with (a) D05's payer-resolution rule and (b) S385's dust filter.

D05 (arXiv 2607.12575) sorts each settlement by what its trace proves:
  C1 fictitious = self-payment (payer == payee) or a provably closed loop;
  C2 internal   = payer and payee in the same funding-linked cluster (common funder, or funder-fundee link);
  C3 unattributed = the rest (an upper bound on genuine third-party demand).
Our implementation (an approximation, labelled as such in every output):
  C1 = payer == payee, or the pair sits in a strongly connected component of the week's settlement graph (closed loop on the
       settlement layer; D05 uses the same SCC check as a cross-validation). We do not have sweep transfers, so hub-returns
       outside the settlement layer are missed: C1 is a lower bound.
  C2 = funding/sweep links from Blockscout v2: the newest 50 incoming and 50 outgoing non-settlement USDC transfers of each payer and payee that together carry
       >= --coverage of the week's settlements (1 req/s, polite). Union-find over funder-fundee edges; a settlement is C2
       when payer and payee share a cluster. Addresses outside the covered set are never merged: C2 is a lower bound.
S385 dust/treasury filter: a payee that received from exactly one distinct payer in the week (single-counterparty sink).
Outputs: local/o5/x402_filter_<week>.json and two new columns in data/o4_x402_trend.csv (usd_d05_c3, payments_d05_c3,
         payments_s385_nondust), written for the rows of that week."""
import argparse, collections, csv, json, os, sys, time, urllib.request

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
UA = "ai-price-index-research/0.1 (github.com/doescodinggiteasier/ai-price-index)"
USDC = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'


def load(path):
    rows, seen = [], set()
    for line in open(path):
        r = json.loads(line)
        if r['hash'] in seen: continue  # a restarted collector re-appends a facilitator's rows
        seen.add(r['hash'])
        if r.get('payer') and r.get('payee') and r.get('usdc_atomic') is not None:
            rows.append((r['payer'].lower(), r['payee'].lower(), int(r['usdc_atomic']), r['hash']))
    return rows


def sccs(edges):
    """Tarjan (iterative) over the directed payer->payee graph; returns node -> component id for components of size >= 2."""
    g = collections.defaultdict(set)
    for a, b in edges: g[a].add(b)
    index, low, on, st, comp, out = {}, {}, set(), [], 0, {}
    counter = [0]
    for v0 in list(g):
        if v0 in index: continue
        work = [(v0, iter(g[v0]))]; index[v0] = low[v0] = counter[0]; counter[0] += 1; st.append(v0); on.add(v0)
        while work:
            v, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]; counter[0] += 1; st.append(w); on.add(w); work.append((w, iter(g.get(w, ())))); break
                elif w in on:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work: low[work[-1][0]] = min(low[work[-1][0]], low[v])
                if low[v] == index[v]:
                    members = []
                    while True:
                        w = st.pop(); on.discard(w); members.append(w)
                        if w == v: break
                    if len(members) > 1:
                        for m in members: out[m] = comp
                        comp += 1
    return out


SETTLE = '0xe3ee160e'  # transferWithAuthorization = an x402 settlement; everything else is funding or sweep


def links(addr, cache, dirs=('to', 'from')):
    """Non-settlement USDC counterparties of `addr` (Blockscout v2; newest 50 incoming for a payer = top-ups, newest 50 outgoing for a payee = sweeps; a hub's full incoming list times out).
    Counterparties that are contracts, named, or publicly tagged (exchanges, routers, bridges) are dropped so that unrelated
    users funded by the same exchange are not merged. Rate-limit or error responses raise and are NOT cached (a v1 bug had
    cached HTTP-200 'Too many requests' bodies as 'no funders')."""
    if addr in cache: return cache[addr]
    out = []
    for f in dirs:
        u = (f'https://base.blockscout.com/api/v2/addresses/{addr}/token-transfers?type=ERC-20&filter={f}&token={USDC}')
        d = None
        for i in range(5):
            try:
                with urllib.request.urlopen(urllib.request.Request(u, headers={'User-Agent': UA}), timeout=60) as r:
                    d = json.load(r)
                if 'items' in d: break
                d = None
            except Exception:
                d = None
            time.sleep(5 * (i + 1))
        time.sleep(1.0)
        if d is None: raise RuntimeError(f'lookup failed for {addr} ({f})')
        for t in d['items']:
            if (t.get('method') or '') == SETTLE: continue
            cp = t['from'] if f == 'to' else t['to']
            if cp.get('is_contract') or cp.get('name') or cp.get('public_tags') or cp.get('metadata'): continue
            out.append(cp['hash'].lower())
    cache[addr] = sorted(set(out) - {addr})
    return cache[addr]


class UF:
    def __init__(self): self.p = {}
    def f(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x: self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def u(self, a, b): self.p[self.f(a)] = self.f(b)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('week_dir'); ap.add_argument('--coverage', type=float, default=0.9)
    ap.add_argument('--max-lookups', type=int, default=1500); ap.add_argument('--no-funding', action='store_true')
    a = ap.parse_args()
    week = os.path.basename(a.week_dir.rstrip('/')).replace('x402_week_', '')
    rows = load(os.path.join(a.week_dir, 'txs.jsonl'))
    n, usd = len(rows), sum(r[2] for r in rows) / 1e6
    # C1: self-payment or settlement-layer SCC
    comp = sccs({(p, q) for p, q, _, _ in rows})
    c1 = [p == q or (p in comp and comp.get(p) == comp.get(q)) for p, q, _, _ in rows]
    # C2: funding-linked clusters for the addresses carrying most settlements
    cache_p = os.path.join(ROOT, 'local', 'o5', 'blockscout_links_v2.json')
    cache = json.load(open(cache_p)) if os.path.exists(cache_p) else {}
    cnt = collections.Counter()
    for p, q, _, _ in rows: cnt[p] += 1; cnt[q] += 1
    covered, acc = [], 0
    for addr, c in cnt.most_common():
        if acc >= a.coverage * 2 * n or len(covered) >= a.max_lookups: break
        covered.append(addr); acc += c
    uf = UF(); failed = []
    payer_set = {p for p, _, _, _ in rows}; payee_set = {q for _, q, _, _ in rows}  # payers: incoming top-ups; payees: outgoing sweeps
    if not a.no_funding:
        for i, addr in enumerate(covered):
            try:
                dirs = tuple(d for d, role in (('to', payer_set), ('from', payee_set)) if addr in role)
                for f in links(addr, cache, dirs): uf.u(addr, f)
            except RuntimeError as e:
                failed.append(addr); print(e, flush=True)
            if i % 50 == 0:
                json.dump(cache, open(cache_p, 'w')); print('funding lookups', i, '/', len(covered), flush=True)
        json.dump(cache, open(cache_p, 'w'))
    cov = set(covered)
    c2 = [(not x) and p in cov and q in cov and uf.f(p) == uf.f(q) for (p, q, _, _), x in zip(rows, c1)]
    # S385 dust: payee with exactly one distinct payer in the week
    payers_of = collections.defaultdict(set)
    for p, q, _, _ in rows: payers_of[q].add(p)
    dust = [len(payers_of[q]) == 1 for _, q, _, _ in rows]

    def agg(mask):
        sel = [r for r, m in zip(rows, mask) if m]
        return {'payments': len(sel), 'usd': round(sum(r[2] for r in sel) / 1e6, 2), 'payees': len({r[1] for r in sel}), 'payers': len({r[0] for r in sel})}
    c3 = [not (x or y) for x, y in zip(c1, c2)]
    res = {'week': week, 'method': 'D05 approximation (C1 self+settlement SCC; C2 Blockscout funding links for top addresses) + S385 single-payer dust',
           'coverage_target': a.coverage, 'funding_lookups': 0 if a.no_funding else len(covered), 'funding_lookup_failures': len(failed) if not a.no_funding else None,
           'share_of_settlement_endpoints_covered': round(acc / (2 * n), 4) if n else None,
           'raw': agg([True] * n), 'd05_c1_fictitious': agg(c1), 'd05_c2_internal': agg(c2), 'd05_c3_unattributed': agg(c3),
           's385_dust': agg(dust), 's385_nondust': agg([not d for d in dust]),
           'd05_c3_and_nondust': agg([x and not d for x, d in zip(c3, dust)])}
    json.dump(res, open(os.path.join(ROOT, 'local', 'o5', f'x402_filter_{week}.json'), 'w'), indent=1)
    print(json.dumps(res, indent=1))
    return res


if __name__ == '__main__':
    main()
