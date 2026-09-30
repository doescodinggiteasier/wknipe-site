#!/usr/bin/env python3
"""Machine-readable AI terms census over Common Crawl robots.txt WARCs.

Stdlib only. Subcommands:
  plan   CRAWL                 estimate download size and run time
  run    CRAWL --frac F        process a seeded random fraction of robots.txt WARC files
  agg    OUTDIR                aggregate per-file results into domain-level counts

Counts, per distinct host:
  - RSL `License:` lines in robots.txt (RSL 1.0 robots extension)
  - `Content-Signal:` lines (Cloudflare content signals)
  - AI-crawler blocks: a user-agent group naming a known AI crawler with `Disallow: /`
"""
import argparse, gzip, hashlib, io, json, os, random, sys, time, urllib.request, zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit

UA = "ai-price-index-research/0.1 (github.com/doescodinggiteasier/ai-price-index)"
BASE = "https://data.commoncrawl.org/"
AI_BOTS = {
    "gptbot", "chatgpt-user", "oai-searchbot", "claudebot", "claude-web", "claude-user",
    "claude-searchbot", "anthropic-ai", "ccbot", "google-extended", "perplexitybot",
    "perplexity-user", "bytespider", "applebot-extended", "meta-externalagent",
    "meta-externalfetcher", "facebookbot", "cohere-ai", "cohere-training-data-crawler",
    "amazonbot", "diffbot", "omgili", "omgilibot", "timpibot", "youbot", "ai2bot",
    "mistralai-user", "duckassistbot", "imagesiftbot", "petalbot", "gemini-deep-research",
    "google-cloudvertexbot", "novellum", "panscient", "velenpublicwebcrawler",
}


def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:  # retry with backoff
            if i == tries - 1:
                raise
            time.sleep(2 ** i * 3)


def paths(crawl):
    return gzip.decompress(get(f"{BASE}crawl-data/{crawl}/robotstxt.paths.gz")).decode().split()


def iter_records(raw):
    """Yield (target_uri, http_payload_bytes) for WARC response records in a .warc.gz."""
    data = raw
    while data:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        rec = d.decompress(data)
        data = d.unused_data
        head, _, rest = rec.partition(b"\r\n\r\n")
        hdrs = {}
        for line in head.split(b"\r\n")[1:]:
            k, _, v = line.partition(b":")
            hdrs[k.strip().lower()] = v.strip()
        if hdrs.get(b"warc-type") != b"response":
            continue
        _, _, body = rest.partition(b"\r\n\r\n")  # strip HTTP headers
        status = rest[:12]
        if b" 200" not in status:
            continue
        yield hdrs.get(b"warc-target-uri", b"").decode("utf-8", "replace"), body


def analyse(text):
    lic, sig, ai_blocked = [], [], set()
    agents, in_rules = [], False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip().lower(), v.strip()
        if k == "license":
            lic.append(v)
        elif k == "content-signal":
            sig.append(v)
        elif k == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(v.lower())
        elif k in ("disallow", "allow", "crawl-delay"):
            in_rules = True
            if k == "disallow" and v == "/":
                for a in agents:
                    if a in AI_BOTS:
                        ai_blocked.add(a)
    return lic, sig, ai_blocked


def process(path):
    raw = get(BASE + path)
    out = {"path": path, "bytes": len(raw), "records": 0, "hosts": 0,
           "rsl": {}, "sig": {}, "ai_block": {}, "tdm_sample": []}
    seen = set()
    for uri, body in iter_records(raw):
        out["records"] += 1
        host = (urlsplit(uri).hostname or "").lower()
        if not host or host in seen:
            continue
        seen.add(host)
        if hashlib.md5(host.encode()).digest()[0] < 3:  # ~1.2% deterministic host sample for tdmrep
            out["tdm_sample"].append(host)
        lic, sig, blocked = analyse(body[:500_000].decode("utf-8", "replace"))
        if lic:
            out["rsl"][host] = lic[:5]
        if sig:
            out["sig"][host] = sig[:5]
        if blocked:
            out["ai_block"][host] = sorted(blocked)
    out["hosts"] = len(seen)
    return out


def cmd_plan(a):
    ps = paths(a.crawl)
    rnd = random.Random(1)
    sample = rnd.sample(ps, 20)
    sizes, secs = [], []
    for p in sample:
        req = urllib.request.Request(BASE + p, method="HEAD", headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            sizes.append(int(r.headers["Content-Length"]))
    t = time.time(); raw = get(BASE + sample[0]); secs = time.time() - t
    mean = sum(sizes) / len(sizes)
    total = mean * len(ps)
    bps = len(raw) / secs
    print(json.dumps({
        "crawl": a.crawl, "files": len(ps), "mean_file_mb": round(mean / 1e6, 2),
        "est_total_gb": round(total / 1e9, 1),
        "single_stream_mb_s": round(bps / 1e6, 2),
        "est_hours_1_stream": round(total / bps / 3600, 1),
        "est_hours_4_streams_inferred": round(total / bps / 4 / 3600, 1),
        "method": "HEAD on 20 seeded-random files; one timed GET",
    }, indent=1))


def cmd_run(a):
    ps = paths(a.crawl)
    rnd = random.Random(a.seed)
    chosen = sorted(rnd.sample(ps, int(len(ps) * a.frac)))
    os.makedirs(a.out, exist_ok=True)
    res_path = os.path.join(a.out, "files.jsonl")
    done = set()
    if os.path.exists(res_path):
        with open(res_path) as f:
            done = {json.loads(l)["path"] for l in f}
    todo = [p for p in chosen if p not in done]
    print(f"{len(chosen)} chosen, {len(done)} done, {len(todo)} to go", flush=True)
    errs = open(os.path.join(a.out, "errors.log"), "a")
    with open(res_path, "a") as f, ThreadPoolExecutor(a.workers) as ex:
        futs = {ex.submit(process, p): p for p in todo}
        for i, fu in enumerate(as_completed(futs), 1):
            try:
                f.write(json.dumps(fu.result()) + "\n"); f.flush()
            except Exception as e:
                errs.write(f"{futs[fu]}\t{e!r}\n"); errs.flush()
            if i % 100 == 0:
                print(f"{i}/{len(todo)}", flush=True)


def cmd_agg(a):
    rsl, sig, ai = {}, {}, {}
    files = recs = total_hosts = 0
    with open(os.path.join(a.out, "files.jsonl")) as f:
        for l in f:
            r = json.loads(l); files += 1; recs += r["records"]
            rsl.update(r["rsl"]); sig.update(r["sig"]); ai.update(r["ai_block"])
            total_hosts += r["hosts"]
    terms = set(rsl) | set(sig)
    bot_counts = {}
    for bl in ai.values():
        for b in bl:
            bot_counts[b] = bot_counts.get(b, 0) + 1
    summary = {
        "files": files, "records_200": recs,
        "hosts_sum_per_file": total_hosts,
        "hosts_with_rsl_license": len(rsl),
        "hosts_with_content_signal": len(sig),
        "hosts_with_rsl_or_content_signal": len(terms),
        "hosts_with_ai_crawler_block": len(ai),
        "ai_block_by_bot": dict(sorted(bot_counts.items(), key=lambda x: -x[1])),
    }
    json.dump(summary, open(os.path.join(a.out, "summary.json"), "w"), indent=1)
    with open(os.path.join(a.out, "rsl_hosts.tsv"), "w") as f:
        for h, v in sorted(rsl.items()):
            for u in v:
                f.write(f"{h}\t{u}\n")
    with open(os.path.join(a.out, "content_signal_hosts.tsv"), "w") as f:
        for h, v in sorted(sig.items()):
            for u in v:
                f.write(f"{h}\t{u}\n")
    with open(os.path.join(a.out, "ai_block_hosts.tsv"), "w") as f:
        for h, v in sorted(ai.items()):
            f.write(f"{h}\t{','.join(v)}\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("plan"); p.add_argument("crawl"); p.set_defaults(fn=cmd_plan)
    p = sp.add_parser("run"); p.add_argument("crawl"); p.add_argument("--frac", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=42); p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out", required=True); p.set_defaults(fn=cmd_run)
    p = sp.add_parser("agg"); p.add_argument("out"); p.set_defaults(fn=cmd_agg)
    a = ap.parse_args(); a.fn(a)
