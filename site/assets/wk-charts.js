/* wknipe.com chart renderers (ORDER_013). Each takes {data, opts, width, t} and returns {node, legend, table}.
   t = colour tokens read from CSS (WK.theme). Categorical colours are fixed per category site-wide. */
(function () {
  "use strict";
  const WK = window.WK, C = (WK.charts = WK.charts || {}), fmt = WK.fmt, esc = WK.esc, CATS = WK.CATS, L = WK.CAT_LABEL;
  const utc = (w) => new Date(w + "T00:00:00Z");
  const base = (t, width, o = {}) => ({ width, style: { fontFamily: "'IBM Plex Sans', system-ui, sans-serif", fontSize: "12px", color: t.muted, background: "transparent", overflow: "visible" }, ...o });
  const legend = (items) => items.map(([lab, col, dash]) => `<span><i style="background:${col}${dash ? ";height:2px;border-radius:0" : ""}"></i>${esc(lab)}</span>`).join("");
  const wkTicks = (weeks) => ({ type: "utc", ticks: weeks.map(utc), tickFormat: (d) => d3.utcFormat("%-d %b")(d), label: null });
  const pct0 = (x) => fmt.pct(x, 0);
  const latest = (data, opts) => opts.week || data.latest_week;
  const weeksOf = (rows, k = "week_start") => [...new Set(rows.map((r) => r[k]))].sort();
  const decades = (lo, hi) => { const out = []; for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) out.push(10 ** e); return out; };

  // 1. Raw -> clean waterfall (horizontal; labels above bars so it reads the same on a phone)
  C.waterfall = ({ data, opts, width, t }) => {
    const w = latest(data, opts), rows = data.waterfall.filter((r) => r.week_start === w);
    const total = d3.sum(rows, (r) => r.usd), pays = d3.sum(rows, (r) => r.payments);
    let run = total;
    const bars = [{ label: "All facilitator settlements", x1: 0, x2: total, usd: total, payments: pays, kind: "raw" }];
    for (const r of rows) if (r.step !== "clean") { bars.push({ label: "− " + r.label, x1: run - r.usd, x2: run, usd: -r.usd, payments: -r.payments, kind: "cut" }); run -= r.usd; }
    const cl = rows.find((r) => r.step === "clean");
    bars.push({ label: "= Demand-cleaned", x1: 0, x2: cl.usd, usd: cl.usd, payments: cl.payments, kind: "clean" });
    const col = (d) => (d.kind === "raw" ? t.primary : d.kind === "clean" ? t.clean : t.raw);
    const node = Plot.plot(base(t, width, {
      height: bars.length * 50 + 30, marginLeft: 4, marginRight: 70, marginTop: 18,
      x: { grid: true, tickFormat: fmt.usd, label: null, domain: [0, total] }, y: { domain: bars.map((b) => b.label), axis: null, padding: 0.55 },
      marks: [
        Plot.barX(bars, { y: "label", x1: "x1", x2: "x2", fill: col, rx: 3, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d.label.replace(/^[−=] /, "")}\n${fmt.usdFull(Math.abs(d.usd))} (${fmt.pct(Math.abs(d.usd) / total, 1)} of settled $)\n${fmt.int(Math.abs(d.payments))} payments` }),
        Plot.text(bars, { y: "label", x: 0, text: "label", textAnchor: "start", dy: -17, fill: t.ink, fontSize: 13 }),
        Plot.text(bars, { y: "label", x: "x2", text: (d) => (d.kind === "cut" ? "−" : "") + fmt.usd(Math.abs(d.usd)), textAnchor: "start", dx: 6, fill: t.ink, fontWeight: 600 }),
      ],
    }));
    return { node, table: { cols: [{ k: "label", label: "Step" }, { k: "usd", label: "USD", r: 1, f: fmt.usdFull }, { k: "payments", label: "Payments", r: 1, f: fmt.int }, { k: "share", label: "Share of settled USD", r: 1, f: (x) => fmt.pct(x, 1) }],
      rows: bars.map((b) => ({ ...b, share: Math.abs(b.usd) / total })) } };
  };

  // 2. Category mix over time (stacked area), USD or payments
  C.mix = ({ data, opts, width, t }) => {
    const m = opts.metric || "usd", weeks = data.weeks;
    const rows = data.category_mix.map((r) => ({ week: utc(r.week_start), w: r.week_start, category: r.category, v: +r[m] }));
    const tot = d3.rollups(rows, (v) => ({ total: d3.sum(v, (d) => d.v), parts: v }), (d) => d.w).map(([w, o]) => ({ week: utc(w), w, ...o }));
    const f = m === "usd" ? fmt.usd : (x) => d3.format("~s")(x);
    const node = Plot.plot(base(t, width, {
      height: 300, marginLeft: 52, marginRight: 24, x: wkTicks(weeks), y: { grid: true, label: null, tickFormat: f },
      color: { domain: CATS, range: CATS.map((c) => t.cat[c]) },
      marks: [
        Plot.areaY(rows, Plot.stackY({ x: "week", y: "v", fill: "category", order: CATS, stroke: t.surface, strokeWidth: 1.5, })),
        Plot.ruleY([0], { stroke: t.line }),
        Plot.ruleX(tot, Plot.pointerX({ x: "week", stroke: t.muted, strokeDasharray: "2,3" })),
        Plot.tip(tot, Plot.pointerX({ x: "week", y: "total", fill: t.surface, stroke: t.line, title: (d) => `Week of ${fmt.week(d.w)} · total ${m === "usd" ? fmt.usdFull(d.total) : fmt.int(d.total)}\n` + CATS.slice().reverse().map((c) => { const p = d.parts.find((x) => x.category === c); return p ? `${L[c]}: ${m === "usd" ? fmt.usdFull(p.v) : fmt.int(p.v)} (${fmt.pct(p.v / d.total, 0)})` : ""; }).filter(Boolean).join("\n") })),
      ],
    }));
    return { node, legend: legend(CATS.map((c) => [L[c], t.cat[c]])),
      table: { cols: [{ k: "w", label: "Week of" }, { k: "category", label: "Category", f: (c) => L[c] }, { k: "v", label: m === "usd" ? "Clean USD" : "Clean payments", r: 1, f: m === "usd" ? fmt.usdFull : fmt.int }], rows } };
  };

  // 3. Concentration: top-1 and top-10 seller share for a category
  C.concentration = ({ data, opts, width, t }) => {
    const c = opts.cat || "all", rows = data.concentration.filter((r) => r.category === c), weeks = weeksOf(data.concentration);
    const long = rows.flatMap((r) => [{ week: utc(r.week_start), s: "Top seller", v: r.top1_share, r }, { week: utc(r.week_start), s: "Top 10 sellers", v: r.top10_share, r }]);
    const col = { "Top seller": t.primary, "Top 10 sellers": t.clean };
    const last = weeks[weeks.length - 1];
    const node = Plot.plot(base(t, width, {
      height: 260, marginLeft: 44, marginRight: width < 520 ? 16 : 140, x: wkTicks(weeks), y: { grid: true, domain: [0, 1], tickFormat: pct0, label: null },
      marks: [
        Plot.line(long, { x: "week", y: "v", stroke: (d) => col[d.s], strokeWidth: 2, z: "s" }),
        Plot.dot(long, { x: "week", y: "v", fill: (d) => col[d.s], r: 4, stroke: t.surface, strokeWidth: 1.5, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d.s}: ${fmt.pct(d.v, 1)} of ${fmt.usdFull(d.r.usd)}\n${d.r.sellers} sellers · HHI ${fmt.int(d.r.hhi)} · ${d.r.effective_sellers} effective sellers` }),
        width < 520 ? null : Plot.text(long.filter((d) => d.r.week_start === last), { x: "week", y: "v", text: (d) => `${d.s} ${fmt.pct(d.v, 0)}`, textAnchor: "start", dx: 8, fill: t.ink }),
      ],
    }));
    return { node, legend: legend(Object.entries(col)), table: { cols: [{ k: "week_start", label: "Week of" }, { k: "sellers", label: "Sellers", r: 1, f: fmt.int }, { k: "usd", label: "Clean USD", r: 1, f: fmt.usdFull }, { k: "top1_share", label: "Top-1 share", r: 1, f: (x) => fmt.pct(x, 1) }, { k: "top10_share", label: "Top-10 share", r: 1, f: (x) => fmt.pct(x, 1) }, { k: "hhi", label: "HHI", r: 1, f: fmt.int }, { k: "effective_sellers", label: "Effective sellers", r: 1 }], rows } };
  };

  // 4a. Active genuine buyers per week: new / returning / reactivated
  C.buyers = ({ data, width, t }) => {
    const rows = data.buyers_weekly, weeks = rows.map((r) => r.week_start);
    const parts = [["Returning from last week", "returning_buyers", t.primary], ["Came back after a gap", "reactivated_buyers", t.cat.other], ["New this week", "new_buyers", t.clean]];
    const long = rows.flatMap((r) => (r.new_buyers === "" ? [{ w: r.week_start, s: "First week (no history)", v: r.active_buyers, col: t.raw }] : parts.map(([s, k, col]) => ({ w: r.week_start, s, v: +r[k], col }))));
    const node = Plot.plot(base(t, width, {
      height: 260, marginLeft: 48, x: { domain: weeks, tickFormat: fmt.week, label: null, padding: 0.35 }, y: { grid: true, label: null, tickFormat: "~s" },
      marks: [Plot.barY(long, Plot.stackY({ x: "w", y: "v", fill: (d) => d.col, order: ["Returning from last week", "Came back after a gap", "New this week", "First week (no history)"].reverse(), z: "s", rx: 2, insetLeft: 0.5, insetRight: 0.5, tip: { fill: t.surface, stroke: t.line }, title: (d) => `Week of ${fmt.week(d.w)}\n${d.s}: ${fmt.int(d.v)}` })),
        Plot.text(rows, { x: "week_start", y: "active_buyers", text: (d) => fmt.int(d.active_buyers), dy: -8, fill: t.ink }), Plot.ruleY([0], { stroke: t.line })],
    }));
    return { node, legend: legend([...parts.map(([s, , c]) => [s, c]), ["First week (no history)", t.raw]]),
      table: { cols: [{ k: "week_start", label: "Week of" }, { k: "active_buyers", label: "Active", r: 1, f: fmt.int }, { k: "new_buyers", label: "New", r: 1, f: fmt.int }, { k: "returning_buyers", label: "Returning", r: 1, f: fmt.int }, { k: "reactivated_buyers", label: "Reactivated", r: 1, f: fmt.int }, { k: "median_spend_usd", label: "Median spend", r: 1, f: fmt.usdFull }, { k: "multi_homing_share", label: "Pay 2+ sellers", r: 1, f: (x) => fmt.pct(x, 1) }], rows } };
  };

  // 4b/5. Log histograms (spend per buyer, payment size)
  const binLabel = (lo) => fmt.usdFull(lo);
  C.hist = ({ data, opts, width, t }) => {
    const w = latest(data, opts), src = opts.src || "buyer_spend_histogram", cat = opts.cat;
    let rows = data[src].filter((r) => r.week_start === w && (!cat || r.category === cat));
    const yk = opts.y || (src === "buyer_spend_histogram" ? "buyers" : "payments");
    const col = cat && cat !== "all" ? t.cat[cat] : t.primary;
    const node = Plot.plot(base(t, width, {
      height: 240, marginLeft: 48, marginBottom: 36, x: { domain: rows.map((r) => r.bin_lo_usd), tickFormat: binLabel, label: opts.xlabel || "USD (log bins, each ~3.2×)", labelAnchor: "center", labelArrow: false, tickRotate: width < 520 ? -45 : 0 },
      y: { grid: true, label: null, tickFormat: "~s" },
      marks: [Plot.barY(rows, { x: "bin_lo_usd", y: yk, fill: col, rx: 2, insetLeft: 1, insetRight: 1, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${fmt.usdFull(d.bin_lo_usd)}–${fmt.usdFull(d.bin_hi_usd)}\n${fmt.int(d[yk])} ${yk} · ${fmt.usdFull(d.usd)} total` }), Plot.ruleY([0], { stroke: t.line })],
    }));
    return { node, table: { cols: [{ k: "bin_lo_usd", label: "From", f: fmt.usdFull }, { k: "bin_hi_usd", label: "To", f: fmt.usdFull }, { k: yk, label: yk[0].toUpperCase() + yk.slice(1), r: 1, f: fmt.int }, { k: "usd", label: "USD", r: 1, f: fmt.usdFull }], rows } };
  };

  // 4c. Sellers per buyer (multi-homing)
  C.spb = ({ data, opts, width, t }) => {
    const w = latest(data, opts), rows = data.sellers_per_buyer.filter((r) => r.week_start === w), tot = d3.sum(rows, (r) => r.buyers);
    const node = Plot.plot(base(t, width, {
      height: 220, marginLeft: 48, x: { domain: rows.map((r) => r.sellers), label: "Distinct sellers paid in the week", labelAnchor: "center", labelArrow: false }, y: { grid: true, label: null, tickFormat: "~s" },
      marks: [Plot.barY(rows, { x: "sellers", y: "buyers", fill: (d) => (d.sellers === "1" ? t.raw : t.primary), rx: 2, insetLeft: 4, insetRight: 4, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d.sellers} seller(s): ${fmt.int(d.buyers)} buyers (${fmt.pct(d.buyers / tot, 1)})` }),
        Plot.text(rows, { x: "sellers", y: "buyers", text: (d) => fmt.pct(d.buyers / tot, 0), dy: -8, fill: t.ink }), Plot.ruleY([0], { stroke: t.line })],
    }));
    return { node, table: { cols: [{ k: "sellers", label: "Sellers paid" }, { k: "buyers", label: "Buyers", r: 1, f: fmt.int }], rows } };
  };

  // 5. Payment size by category: p10–p90 range and median, log scale
  C.tickets = ({ data, opts, width, t }) => {
    const w = latest(data, opts), order = ["all", ...CATS];
    const rows = data.tickets.filter((r) => r.week_start === w && r.payments >= 20).sort((a, b) => order.indexOf(a.category) - order.indexOf(b.category));
    const col = (d) => (d.category === "all" ? t.ink : t.cat[d.category]);
    const node = Plot.plot(base(t, width, {
      height: rows.length * 40 + 40, marginLeft: width < 520 ? 96 : 130, marginRight: 24, x: { type: "log", grid: true, ticks: decades(d3.min(rows, (r) => r.p10_usd), d3.max(rows, (r) => r.p90_usd)), tickFormat: fmt.usd, label: "USD per payment (log scale)", labelAnchor: "center", labelArrow: false },
      y: { domain: rows.map((r) => r.category), tickFormat: (c) => L[c], label: null },
      marks: [Plot.ruleY(rows, { y: "category", x1: "p10_usd", x2: "p90_usd", stroke: col, strokeWidth: 4, strokeLinecap: "round" }),
        Plot.dot(rows, { y: "category", x: "median_usd", fill: col, r: 6.5, stroke: t.surface, strokeWidth: 2, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${L[d.category]} · ${fmt.int(d.payments)} clean payments\np10 ${fmt.usdFull(d.p10_usd)} · median ${fmt.usdFull(d.median_usd)} · p90 ${fmt.usdFull(d.p90_usd)}` }),
        Plot.text(rows, { y: "category", x: "median_usd", text: (d) => fmt.usdFull(d.median_usd), dy: -13, fill: t.ink, fontSize: 11 })],
    }));
    return { node, table: { cols: [{ k: "category", label: "Category", f: (c) => L[c] }, { k: "payments", label: "Payments", r: 1, f: fmt.int }, { k: "p10_usd", label: "p10", r: 1, f: fmt.usdFull }, { k: "median_usd", label: "Median", r: 1, f: fmt.usdFull }, { k: "p90_usd", label: "p90", r: 1, f: fmt.usdFull }], rows } };
  };

  // 6. Facilitator share, raw vs clean (grouped by facilitator name)
  C.facilitators = ({ data, opts, width, t }) => {
    const w = latest(data, opts), m = opts.metric || "usd";
    const g = d3.rollups(data.facilitators.filter((r) => r.week_start === w), (v) => ({ raw: d3.sum(v, (d) => d["raw_" + (m === "usd" ? "usd" : "payments")]), clean: d3.sum(v, (d) => d["clean_" + (m === "usd" ? "usd" : "payments")]), addrs: v.length }), (d) => d.name)
      .map(([name, o]) => ({ name, ...o }));
    const R = d3.sum(g, (d) => d.raw), K = d3.sum(g, (d) => d.clean);
    g.forEach((d) => { d.rawShare = d.raw / R; d.cleanShare = d.clean / K; });
    g.sort((a, b) => b.rawShare + b.cleanShare - a.rawShare - a.cleanShare);
    const top = g.slice(0, 9), rest = g.slice(9);
    if (rest.length) top.push({ name: `${rest.length} others`, raw: d3.sum(rest, (d) => d.raw), clean: d3.sum(rest, (d) => d.clean), rawShare: d3.sum(rest, (d) => d.rawShare), cleanShare: d3.sum(rest, (d) => d.cleanShare), addrs: d3.sum(rest, (d) => d.addrs) });
    const long = top.flatMap((d) => [{ ...d, s: "Raw", v: d.rawShare }, { ...d, s: "Clean", v: d.cleanShare }]);
    const col = { Raw: t.raw, Clean: t.clean };
    const node = Plot.plot(base(t, width, {
      height: top.length * 34 + 40, marginLeft: width < 520 ? 90 : 120, marginRight: 40, x: { grid: true, tickFormat: pct0, label: null, domain: [0, Math.min(1, d3.max(long, (d) => d.v) * 1.1)] }, y: { domain: top.map((d) => d.name), label: null },
      marks: [Plot.ruleY(top, { y: "name", x1: "rawShare", x2: "cleanShare", stroke: t.line, strokeWidth: 2 }),
        Plot.dot(long, { y: "name", x: "v", fill: (d) => col[d.s], r: 6, stroke: t.surface, strokeWidth: 1.5, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d.name} (${d.addrs} address${d.addrs > 1 ? "es" : ""})\nRaw: ${fmt.pct(d.rawShare, 1)} (${m === "usd" ? fmt.usdFull(d.raw) : fmt.int(d.raw)})\nClean: ${fmt.pct(d.cleanShare, 1)} (${m === "usd" ? fmt.usdFull(d.clean) : fmt.int(d.clean)})` })],
    }));
    return { node, legend: legend([["Share of raw " + (m === "usd" ? "USD" : "payments"), t.raw], ["Share of demand-cleaned", t.clean]]),
      table: { cols: [{ k: "name", label: "Facilitator" }, { k: "raw", label: "Raw", r: 1, f: m === "usd" ? fmt.usdFull : fmt.int }, { k: "rawShare", label: "Raw share", r: 1, f: (x) => fmt.pct(x, 1) }, { k: "clean", label: "Clean", r: 1, f: m === "usd" ? fmt.usdFull : fmt.int }, { k: "cleanShare", label: "Clean share", r: 1, f: (x) => fmt.pct(x, 1) }], rows: g } };
  };

  // 7. Tripwire: content + data clean USD vs the reopen threshold (+20%/month)
  C.tripwire = ({ data, width, t }) => {
    const rows = data.tripwire.map((r) => ({ ...r, week: utc(r.week_start) })), weeks = rows.map((r) => r.week_start);
    const node = Plot.plot(base(t, width, {
      height: 260, marginLeft: 52, marginRight: width < 520 ? 16 : 170, x: wkTicks(weeks), y: { grid: true, label: null, tickFormat: fmt.usd, domain: [0, d3.max(rows, (d) => Math.max(d.content_plus_data_usd, d.threshold_usd)) * 1.1] },
      marks: [
        Plot.line(rows, { x: "week", y: "threshold_usd", stroke: t.muted, strokeDasharray: "5,4", strokeWidth: 1.5 }),
        Plot.line(rows, { x: "week", y: "content_plus_data_usd", stroke: t.clean, strokeWidth: 2.5 }),
        Plot.dot(rows, { x: "week", y: "content_plus_data_usd", fill: t.clean, r: 4.5, stroke: t.surface, strokeWidth: 1.5, tip: { fill: t.surface, stroke: t.line }, title: (d) => `Week of ${fmt.week(d.week_start)}\nContent + data: ${fmt.usdFull(d.content_plus_data_usd)} (content ${fmt.usdFull(d.content_usd)}, data ${fmt.usdFull(d.data_usd)})\nThreshold path: ${fmt.usdFull(d.threshold_usd)}` }),
        width < 520 ? null : Plot.text(rows.slice(-1), { x: "week", y: "threshold_usd", text: () => "Reopen path (+20%/mo)", textAnchor: "start", dx: 8, fill: t.muted }),
        width < 520 ? null : Plot.text(rows.slice(-1), { x: "week", y: "content_plus_data_usd", text: (d) => "Content + data " + fmt.usd(d.content_plus_data_usd), textAnchor: "start", dx: 8, fill: t.ink }),
        Plot.ruleY([0], { stroke: t.line }),
      ],
    }));
    return { node, legend: legend([["Content + data, demand-cleaned", t.clean], ["+20%/month path from the first week", t.muted, 1]]),
      table: { cols: [{ k: "week_start", label: "Week of" }, { k: "content_usd", label: "Content", r: 1, f: fmt.usdFull }, { k: "data_usd", label: "Data", r: 1, f: fmt.usdFull }, { k: "content_plus_data_usd", label: "Content + data", r: 1, f: fmt.usdFull }, { k: "threshold_usd", label: "Threshold path", r: 1, f: fmt.usdFull }], rows } };
  };

  // Prices: chain-linked Jevons index, posted vs transacted (category from opts)
  C.jevons = ({ data, opts, width, t }) => {
    const c = opts.cat || "all", rows = data.prices_weekly.filter((r) => r.category === c && r.index_jevons !== "" && r.index_jevons != null).map((r) => ({ ...r, week: utc(r.week_start) }));
    const col = { transacted: t.clean, posted: t.primary }, weeks = weeksOf(data.prices_weekly);
    const node = Plot.plot(base(t, width, {
      height: 240, marginLeft: 44, marginRight: width < 520 ? 16 : 120, x: wkTicks(weeks), y: { grid: true, label: null, nice: true },
      marks: [Plot.ruleY([100], { stroke: t.line }), Plot.line(rows, { x: "week", y: "index_jevons", stroke: (d) => col[d.measure], z: "measure", strokeWidth: 2 }),
        Plot.dot(rows, { x: "week", y: "index_jevons", fill: (d) => col[d.measure], r: 4, stroke: t.surface, strokeWidth: 1.5, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d.measure} · week of ${fmt.week(d.week_start)}\nindex ${(+d.index_jevons).toFixed(1)} · ${fmt.int(d.basket_items)} items in both weeks\nmedian ${fmt.usdFull(+d.median_usd)}` }),
        width < 520 ? null : Plot.text(d3.groups(rows, (d) => d.measure).map(([, v]) => v[v.length - 1]), { x: "week", y: "index_jevons", text: (d) => d.measure + " " + (+d.index_jevons).toFixed(1), textAnchor: "start", dx: 8, fill: t.ink })],
    }));
    return { node, legend: legend([["Paid (transacted, seller median)", t.clean], ["Posted (Bazaar listings)", t.primary]]),
      table: { cols: [{ k: "week_start", label: "Week of" }, { k: "measure", label: "Measure" }, { k: "index_jevons", label: "Index", r: 1 }, { k: "basket_items", label: "Items in both weeks", r: 1, f: fmt.int }, { k: "median_usd", label: "Median", r: 1, f: (x) => fmt.usdFull(+x) }], rows } };
  };

  // Prices: posted vs paid by category (dot pair on a log axis)
  C.postedPaid = ({ data, width, t }) => {
    const rows = data.posted_vs_paid.filter((r) => r.posted_median_usd && r.paid_median_usd);
    const long = rows.flatMap((r) => [{ ...r, s: "Posted (median listing)", v: r.posted_median_usd }, { ...r, s: "Paid (median clean payment)", v: r.paid_median_usd }]);
    const col = { "Posted (median listing)": t.primary, "Paid (median clean payment)": t.clean };
    const node = Plot.plot(base(t, width, {
      height: rows.length * 40 + 40, marginLeft: width < 520 ? 96 : 130, marginRight: 30, x: { type: "log", grid: true, ticks: decades(d3.min(long, (r) => r.v), d3.max(long, (r) => r.v)), tickFormat: fmt.usd, label: "USD per call (log scale)", labelAnchor: "center", labelArrow: false }, y: { domain: rows.map((r) => r.category), tickFormat: (c) => L[c] || c, label: null },
      marks: [Plot.ruleY(rows, { y: "category", x1: "posted_median_usd", x2: "paid_median_usd", stroke: t.line, strokeWidth: 2 }),
        Plot.dot(long, { y: "category", x: "v", fill: (d) => col[d.s], r: 6, stroke: t.surface, strokeWidth: 1.5, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${L[d.category] || d.category}\nPosted median ${fmt.usdFull(d.posted_median_usd)} over ${fmt.int(d.listings)} listings\nPaid median ${fmt.usdFull(d.paid_median_usd)} over ${fmt.int(d.payments)} clean payments` })],
    }));
    return { node, legend: legend(Object.entries(col)), table: { cols: [{ k: "category", label: "Category", f: (c) => L[c] || c }, { k: "listings", label: "Listings", r: 1, f: fmt.int }, { k: "posted_median_usd", label: "Posted median", r: 1, f: fmt.usdFull }, { k: "payments", label: "Clean payments", r: 1, f: fmt.int }, { k: "paid_median_usd", label: "Paid median", r: 1, f: fmt.usdFull }, { k: "ratio", label: "Paid ÷ posted", r: 1, f: (x) => (x == null ? "–" : x.toFixed(2) + "×") }], rows } };
  };

  // Seller page: one weekly series as bars (USD or buyers)
  C.sellerWeekly = ({ data, opts, width, t }) => {
    const s = opts.history ? opts : data.sellers.find((x) => x.address === opts.address) || { history: [] };
    const weeks = opts.weeks || data.weeks;
    const k = opts.metric || "usd", byW = Object.fromEntries(s.history.map((h) => [h.week, h]));
    const rows = weeks.map((w) => ({ w, v: byW[w] ? byW[w][k] : 0, h: byW[w] }));
    const node = Plot.plot(base(t, width, {
      height: 200, marginLeft: 48, x: { domain: weeks, tickFormat: fmt.week, label: null, padding: 0.3 }, y: { grid: true, label: null, tickFormat: k === "usd" ? fmt.usd : "~s" },
      marks: [Plot.barY(rows, { x: "w", y: "v", fill: k === "usd" ? t.clean : t.primary, rx: 2, tip: { fill: t.surface, stroke: t.line }, title: (d) => `Week of ${fmt.week(d.w)}\n${k === "usd" ? fmt.usdFull(d.v) + " clean" : fmt.int(d.v) + " distinct buyers"}` }), Plot.ruleY([0], { stroke: t.line })],
    }));
    return { node, table: { cols: [{ k: "w", label: "Week of" }, { k: "v", label: k === "usd" ? "Clean USD" : "Buyers", r: 1, f: k === "usd" ? fmt.usdFull : fmt.int }], rows } };
  };

  // Generic daily/weekly line for monitor series: opts.x, opts.y, opts.pct
  C.line = ({ data, opts, width, t }) => {
    const rows = (opts.path ? opts.path.split(".").reduce((o, k) => o[k], data) : data).map((r) => ({ ...r, _x: utc(r[opts.x]) }));
    const f = opts.pct ? pct0 : (x) => d3.format("~s")(x);
    const node = Plot.plot(base(t, width, {
      height: 220, marginLeft: 44, x: { type: "utc", label: null, tickFormat: (d) => d3.utcFormat("%-d %b")(d), ticks: Math.min(rows.length, 8) }, y: { grid: true, label: null, tickFormat: f, domain: opts.pct ? [0, 1] : undefined },
      marks: [Plot.line(rows, { x: "_x", y: opts.y, stroke: t.primary, strokeWidth: 2 }), Plot.dot(rows, { x: "_x", y: opts.y, fill: t.primary, r: 3.5, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d[opts.x]}: ${opts.pct ? fmt.pct(d[opts.y], 1) : fmt.int(d[opts.y])}` })],
    }));
    return { node, table: { cols: [{ k: opts.x, label: "Date" }, { k: opts.y, label: opts.label || opts.y, r: 1, f: opts.pct ? (x) => fmt.pct(x, 1) : fmt.int }], rows } };
  };

  // Horizontal share bars (AI access census: % of domains blocking each bot, etc.). opts.path, opts.label, opts.value
  C.bars = ({ data, opts, width, t }) => {
    const rows = (opts.path ? opts.path.split(".").reduce((o, k) => o[k], data) : data).slice(0, opts.top || 40);
    const node = Plot.plot(base(t, width, {
      height: rows.length * 26 + 40, marginLeft: width < 520 ? 110 : 170, marginRight: 50, x: { grid: true, tickFormat: opts.pct ? pct0 : "~s", label: null, domain: opts.pct ? [0, Math.min(1, d3.max(rows, (d) => d[opts.value]) * 1.15 || 1)] : undefined }, y: { domain: rows.map((d) => d[opts.label]), label: null },
      marks: [Plot.barX(rows, { y: opts.label, x: opts.value, fill: (d) => (opts.hi && d[opts.hi] ? t.clean : t.primary), rx: 2, insetTop: 3, insetBottom: 3, tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d[opts.label]}: ${opts.pct ? fmt.pct(d[opts.value], 1) : fmt.int(d[opts.value])}${d.n != null ? ` (${fmt.int(d.k ?? Math.round(d[opts.value] * d.n))} of ${fmt.int(d.n)})` : ""}` }),
        Plot.text(rows, { y: opts.label, x: opts.value, text: (d) => (opts.pct ? fmt.pct(d[opts.value], opts.dp ?? 0) : fmt.int(d[opts.value])), textAnchor: "start", dx: 5, fill: t.ink, fontSize: 11 })],
    }));
    return { node, table: { cols: [{ k: opts.label, label: opts.labelName || "Item" }, { k: opts.value, label: opts.valueName || "Value", r: 1, f: opts.pct ? (x) => fmt.pct(x, 1) : fmt.int }, ...(rows[0] && rows[0].n != null ? [{ k: "n", label: "Of", r: 1, f: fmt.int }] : [])], rows } };
  };

  // Gap map (/x402/gaps/): topics by competition (sellers, log x) and conversion (share with 5+ genuine buyers, y)
  C.gapmap = ({ data, width, t }) => {
    const rows = data.topics.filter((r) => r.hit_rate != null && r.topic !== "other").map((r) => ({ ...r, short: r.label.split(/ & |, /)[0] }));
    const base_ = data.base_rate, narrow = width < 560, xmax = d3.max(rows, (d) => d.sellers);
    const node = Plot.plot(base(t, width, {
      height: narrow ? 380 : 440, marginLeft: 46, marginRight: narrow ? 16 : 30, marginBottom: 40,
      x: { type: "log", label: "Sellers competing (log scale) →", grid: true, tickFormat: "~s", domain: [d3.min(rows, (d) => d.sellers) * 0.85, d3.max(rows, (d) => d.sellers) * 1.25] },
      y: { label: `↑ Share with ${data.min_buyers}+ genuine buyers`, grid: true, tickFormat: pct0, domain: [0, Math.max(0.5, d3.max(rows, (d) => d.hit_rate) * 1.12)] },
      r: { range: [4, narrow ? 16 : 22] },
      marks: [
        Plot.ruleY([base_], { stroke: t.muted, strokeDasharray: "4,4" }),
        Plot.text([base_], { frameAnchor: "right", y: (d) => d, text: () => `all sellers ${fmt.pct(base_, 0)}`, textAnchor: "end", dy: -7, fill: t.muted, fontSize: 11 }),
        Plot.dot(rows, { x: "sellers", y: "hit_rate", r: "buyer_seller_pairs", fill: (d) => (d.hit_rate >= base_ ? t.clean : t.primary), fillOpacity: 0.75, stroke: t.surface, strokeWidth: 1,
          tip: { fill: t.surface, stroke: t.line }, title: (d) => `${d.label}\n${fmt.int(d.sellers)} sellers · ${fmt.pct(d.hit_rate, 0)} get ${data.min_buyers}+ buyers\n${fmt.int(d.buyer_seller_pairs)} genuine buyers (sum) · ${fmt.usdFull(d.clean_usd)} clean/wk\nMedian ask ${fmt.usdFull(d.posted_median_usd)} · ${fmt.int(d.listings)} listings` }),
        ...[[(d) => d.sellers < xmax / 3, "middle"], [(d) => d.sellers >= xmax / 3, "end"]].map(([keep, anchor]) =>
          Plot.text((narrow ? rows.filter((d) => d.hit_rate >= base_) : rows).filter(keep), { x: "sellers", y: "hit_rate", text: "short", dy: -13, dx: anchor === "end" ? 8 : 0, textAnchor: anchor, fill: t.ink, fontSize: narrow ? 10 : 11, fontWeight: 500, stroke: t.surface, strokeWidth: 3, paintOrder: "stroke" })),
      ],
    }));
    return { node, legend: legend([["Above the base rate", t.clean], ["Below it", t.primary]]) + `<span>Dot size = genuine buyers</span>`,
      table: { cols: [{ k: "label", label: "Topic" }, { k: "sellers", label: "Sellers", r: 1, f: fmt.int }, { k: "hit_rate", label: `Share with ${data.min_buyers}+ buyers`, r: 1, f: (x) => fmt.pct(x, 0) }, { k: "buyer_seller_pairs", label: "Genuine buyers (sum)", r: 1, f: fmt.int }], rows } };
  };
})();
