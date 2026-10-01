/* wknipe.com components (ORDER_013). No framework. Loaded on every page (defer).
   - Tooltips: .info[data-tip] buttons and .term[data-term] spans (glossary from /assets/glossary.json)
   - Chart frames: .chart-frame[data-chart] render with Observable Plot (loaded only when a page has charts)
   - Data tables: .wk-table with a <script type="application/json"> config: sort, filter, facets, pages, CSV
   - ⌘K / Ctrl-K search over pages, sellers and Bazaar listings (MiniSearch, lazy)
   Colours are read from the CSS tokens at render time, so charts follow light/dark and the /design/ panels. */
(function () {
  "use strict";
  const WK = (window.WK = window.WK || {});
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const CATS = ["content", "data", "search", "compute", "other", "large_ticket", "unclassed"];
  const CAT_LABEL = { content: "Content", data: "Data", search: "Search", compute: "Compute & tools", other: "Other", large_ticket: "Large ticket", unclassed: "Unclassed", all: "All" };
  WK.CATS = CATS; WK.CAT_LABEL = CAT_LABEL; WK.esc = esc;

  // ---------- formatting ----------
  const fmt = (WK.fmt = {
    usd(x) { if (x == null || x === "" || isNaN(x)) return "–"; const a = Math.abs(x); return (x < 0 ? "−$" : "$") + (a >= 1e6 ? (a / 1e6).toFixed(2) + "M" : a >= 1e4 ? Math.round(a / 1e3).toLocaleString("en-US") + "k" : a >= 100 ? Math.round(a).toLocaleString("en-US") : a >= 1 ? a.toFixed(2) : a === 0 ? "0" : a.toPrecision(2)); },
    usdFull(x) { if (x == null || x === "" || isNaN(x)) return "–"; const a = Math.abs(x); return (x < 0 ? "−$" : "$") + (a >= 100 ? Math.round(a).toLocaleString("en-US") : a >= 1 ? a.toFixed(2) : a === 0 ? "0" : (+a.toPrecision(3)).toString()); },
    int(x) { return x == null || x === "" ? "–" : Math.round(+x).toLocaleString("en-US"); },
    pct(x, d = 0) { return x == null || x === "" || isNaN(x) ? "–" : (x * 100).toFixed(d) + "%"; },
    week(w) { const d = new Date(String(w).slice(0, 10) + "T00:00:00Z"); return d.getUTCDate() + " " + "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ")[d.getUTCMonth()]; },
  });

  // ---------- theme tokens ----------
  WK.theme = function (el) {
    const cs = getComputedStyle(el || document.body), v = (n) => cs.getPropertyValue("--" + n).trim();
    const cat = {}; CATS.forEach((c) => (cat[c] = v("c-" + c)));
    return { ink: v("ink"), muted: v("muted"), line: v("line"), grid: v("grid"), surface: v("surface"), bg: v("bg"), purple: v("purple"), gold: v("gold"), goldText: v("gold-text"),
      primary: v("series-primary"), clean: v("series-clean"), raw: v("series-raw"), faint: v("series-muted"), pos: v("pos"), neg: v("neg"), cat };
  };

  // ---------- tooltips ----------
  let tipEl = null, tipFor = null;
  function hideTip() { if (tipEl) { tipEl.remove(); tipEl = null; } if (tipFor) tipFor.removeAttribute("aria-describedby"); tipFor = null; }
  function showTip(target, html) {
    hideTip();
    tipEl = document.createElement("div"); tipEl.className = "wk-tip"; tipEl.id = "wk-tip"; tipEl.setAttribute("role", "tooltip"); tipEl.innerHTML = html;
    (target.closest(".wk-light, .wk-dark") || document.body).appendChild(tipEl);
    const r = target.getBoundingClientRect(), t = tipEl.getBoundingClientRect(), host = tipEl.offsetParent ? tipEl.offsetParent.getBoundingClientRect() : { left: 0, top: 0 };
    let left = Math.min(Math.max(8, r.left + r.width / 2 - t.width / 2), window.innerWidth - t.width - 8);
    let top = r.bottom + 8; if (top + t.height > window.innerHeight - 8 && r.top - t.height - 8 > 0) top = r.top - t.height - 8;
    tipEl.style.left = left - host.left + (tipEl.offsetParent === document.body ? window.scrollX : 0) + "px";
    tipEl.style.top = top - host.top + (tipEl.offsetParent === document.body ? window.scrollY : 0) + "px";
    tipFor = target; target.setAttribute("aria-describedby", "wk-tip");
  }
  let glossary = null;
  async function loadGlossary() { if (!glossary) glossary = fetch("/assets/glossary.json").then((r) => r.json()).catch(() => ({})); return glossary; }
  async function tipHtml(el) {
    if (el.dataset.tip) return el.dataset.tip;
    const g = await loadGlossary(), k = (el.dataset.term || el.textContent).trim().toLowerCase(), e = g[k];
    return e ? `<b>${esc(e.term)}</b>: ${esc(e.def)}${e.href ? ` <a href="${e.href}">Method →</a>` : ""}` : esc(k);
  }
  function initTips(root = document) {
    $$(".term", root).forEach((el) => { if (!el.hasAttribute("tabindex")) el.tabIndex = 0; el.setAttribute("role", "button"); });
    if (WK._tips) return; WK._tips = true;
    const on = async (e) => { const el = e.target.closest && e.target.closest(".info, .term"); if (!el) return; showTip(el, await tipHtml(el)); };
    document.addEventListener("mouseover", on); document.addEventListener("focusin", on);
    document.addEventListener("click", (e) => { const el = e.target.closest(".info, .term"); if (el) { e.preventDefault(); on(e); } else if (!e.target.closest(".wk-tip")) hideTip(); });
    document.addEventListener("mouseout", (e) => { const el = e.target.closest && e.target.closest(".info, .term"); if (el && !el.contains(e.relatedTarget) && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest(".wk-tip"))) setTimeout(() => { if (tipEl && !tipEl.matches(":hover")) hideTip(); }, 120); });
    document.addEventListener("focusout", (e) => { if (e.target.closest && e.target.closest(".info, .term")) hideTip(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
  }

  // ---------- lazy script loading ----------
  const loaded = {};
  WK.load = (src) => (loaded[src] ||= new Promise((res, rej) => { const s = document.createElement("script"); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); }));
  WK.plotReady = () => WK.load("/assets/vendor/d3-7.min.js").then(() => WK.load("/assets/vendor/plot-0.6.17.min.js")).then(() => WK.load("/assets/wk-charts.js?v=19"));
  const jsonCache = {};
  WK.json = (url) => (jsonCache[url] ||= fetch(url).then((r) => { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); }));

  // ---------- CSV ----------
  WK.toCSV = (cols, rows) => [cols.map((c) => c.label).join(","), ...rows.map((r) => cols.map((c) => { let v = c.csv ? c.csv(r) : r[c.k]; v = v == null ? "" : String(v); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; }).join(","))].join("\n");
  WK.download = (name, text, type = "text/csv") => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); };
  const copy = async (text, btn) => { try { await navigator.clipboard.writeText(text); const o = btn.textContent; btn.textContent = "Copied"; setTimeout(() => (btn.textContent = o), 1400); } catch { prompt("Copy:", text); } };

  // ---------- chart frames ----------
  WK.charts = WK.charts || {};
  function tableHtml(cols, rows) {
    return `<table class="table"><thead><tr>${cols.map((c) => `<th${c.r ? ' style="text-align:right"' : ""}>${esc(c.label)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${cols.map((c) => `<td${c.r ? ' style="text-align:right"' : ""}>${esc(c.f ? c.f(r[c.k], r) : r[c.k])}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }
  async function renderFrame(fr) {
    const kind = fr.dataset.chart, body = $(".plot", fr);
    try {
      await WK.plotReady();
      if (!WK.charts[kind]) throw new Error("unknown chart " + kind);
      const data = fr.dataset.src ? await WK.json(fr.dataset.src) : null;
      const opts = fr.dataset.opts ? JSON.parse(fr.dataset.opts) : {};
      const draw = () => {
        const state = fr._state || (fr._state = { ...opts });
        const w = Math.max(280, body.clientWidth || fr.clientWidth - 40);
        const out = WK.charts[kind]({ el: fr, body, data, opts: state, width: w, t: WK.theme(fr), redraw: draw });
        if (out && out.node) { out.node.querySelectorAll("g[aria-label]:not([role])").forEach((g) => g.setAttribute("role", "group")); body.replaceChildren(out.node); }
        if (out && out.legend) { let lg = $(".legend", fr); if (!lg) { lg = document.createElement("div"); lg.className = "legend"; body.before(lg); } lg.innerHTML = out.legend; }
        if (out && out.table) { let tb = $(".tbl", fr); if (!tb) { tb = document.createElement("div"); tb.className = "tbl"; body.after(tb); } tb.innerHTML = tableHtml(out.table.cols, out.table.rows); fr._table = out.table; }
      };
      fr._draw = draw; draw();
    } catch (e) { body.innerHTML = `<p class="meta">Chart failed to load (${esc(e.message)}). The data is in the CSV link below.</p>`; console.error(e); }
  }
  function initFrames(root = document) {
    const frames = $$(".chart-frame", root);
    frames.forEach((fr) => {
      fr.addEventListener("click", (e) => {
        const b = e.target.closest("[data-act]"); if (!b) return;
        const act = b.dataset.act;
        if (act === "table") { fr.classList.toggle("show-table"); b.textContent = fr.classList.contains("show-table") ? "Hide table" : "Table"; b.setAttribute("aria-expanded", fr.classList.contains("show-table")); }
        if (act === "cite") copy(b.dataset.cite, b);
        if (act === "link") copy(location.origin + location.pathname + "#" + fr.id, b);
        if (act === "csv" && fr._table) WK.download((fr.id || "chart") + ".csv", WK.toCSV(fr._table.cols, fr._table.rows));
        if (act === "opt") { fr._state = { ...(fr._state || {}), [b.dataset.k]: b.dataset.v }; $$(`[data-act="opt"][data-k="${b.dataset.k}"]`, fr).forEach((x) => x.setAttribute("aria-pressed", x === b)); fr._draw && fr._draw(); }
      });
    });
    const charted = frames.filter((f) => f.dataset.chart);
    if (!charted.length) return;
    const io = "IntersectionObserver" in window ? new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { io.unobserve(e.target); renderFrame(e.target); } }), { rootMargin: "300px" }) : null;
    // ORDER_014: chart libraries (~170 KB) and chart data are fetched only after the page has loaded
    const start = () => charted.forEach((f) => (io ? io.observe(f) : renderFrame(f)));
    document.readyState === "complete" ? start() : window.addEventListener("load", start, { once: true });
    let rw = 0; window.addEventListener("resize", () => { clearTimeout(rw); rw = setTimeout(() => charted.forEach((f) => f._draw && f._draw()), 200); });
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => setTimeout(() => charted.forEach((f) => f._draw && f._draw()), 50));
  }
  WK.renderFrame = renderFrame;

  // ---------- data tables ----------
  const cellFmt = { usd: fmt.usdFull, int: fmt.int, pct: (x) => fmt.pct(x, 0), pct1: (x) => fmt.pct(x, 1), price: fmt.usdFull, text: (x) => esc(x) };
  function initTable(box) {
    const cfg = JSON.parse($('script[type="application/json"]', box).textContent);
    const st = { q: "", facet: {}, sort: cfg.sort || null, dir: cfg.dir || "desc", page: 0, rows: null };
    const cols = cfg.cols;
    box.insertAdjacentHTML("beforeend", `<div class="bar"><input type="search" placeholder="${esc(cfg.placeholder || "Filter")}" aria-label="${esc(cfg.placeholder || "Filter rows")}">${cfg.csv !== false ? '<button class="wk-btn ghost sm" data-t="csv">Download CSV</button>' : ""}</div><div class="facets"></div><div class="scroll"><table><thead><tr></tr></thead><tbody></tbody></table></div><div class="pager"><span class="cnt" aria-live="polite"></span><span class="btns"><button class="wk-btn ghost sm" data-t="prev">← Prev</button><button class="wk-btn ghost sm" data-t="next">Next →</button></span></div>`);
    const input = $("input", box), tbody = $("tbody", box), thr = $("thead tr", box), facets = $(".facets", box), cnt = $(".cnt", box);
    thr.innerHTML = cols.map((c) => `<th class="${c.r ? "r" : ""}" scope="col"${st.sort === c.k ? ` aria-sort="${st.dir === "asc" ? "ascending" : "descending"}"` : ""}><button data-k="${c.k}">${esc(c.label)}</button></th>`).join("");
    const load = cfg.src ? WK.json(cfg.src).then((d) => (cfg.path ? cfg.path.split(".").reduce((o, k) => o[k], d) : d)) : Promise.resolve(cfg.rows);
    load.then((rows) => {
      st.rows = rows;
      (cfg.facets || []).forEach((f) => {
        const counts = {}; rows.forEach((r) => (counts[r[f.k]] = (counts[r[f.k]] || 0) + 1));
        const vals = (f.order || Object.keys(counts)).filter((v) => counts[v]);
        facets.insertAdjacentHTML("beforeend", vals.map((v) => `<button class="chip" aria-pressed="false" data-f="${f.k}" data-v="${esc(v)}">${f.dot ? `<i style="background:var(--c-${esc(v)})"></i>` : ""}${esc((f.labels || CAT_LABEL)[v] || v)} <span class="n">${counts[v]}</span></button>`).join(""));
      });
      const q0 = new URLSearchParams(location.search).get(cfg.qparam || "filter"); if (q0 && cfg.qparam !== false) { input.value = q0; st.q = q0.toLowerCase(); }
      draw();
    }).catch((e) => (tbody.innerHTML = `<tr><td>Failed to load data: ${esc(e.message)}</td></tr>`));
    function filtered() {
      const words = st.q.split(/\s+/).filter(Boolean);
      let rs = st.rows.filter((r) => Object.entries(st.facet).every(([k, set]) => !set.size || set.has(String(r[k]))) &&
        (!words.length || words.every((w) => (r._s ||= (cfg.search || cols.map((c) => c.k)).map((k) => r[k + "_t"] ?? r[k] ?? "").join(" ").toLowerCase()).includes(w))));
      if (st.sort) { const k = st.sort, sk = st.rows[0] && (k + "_s") in st.rows[0] ? k + "_s" : k, m = st.dir === "asc" ? 1 : -1;
        rs = rs.slice().sort((a, b) => { const x = a[sk], y = b[sk]; if (x == null || x === "") return 1; if (y == null || y === "") return -1; return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y))) * m; }); }
      return rs;
    }
    function draw() {
      const rs = filtered(), ps = cfg.pageSize || 25, pages = Math.max(1, Math.ceil(rs.length / ps)); st.page = Math.min(st.page, pages - 1);
      const view = rs.slice(st.page * ps, st.page * ps + ps);
      tbody.innerHTML = view.map((r) => `<tr>${cols.map((c) => `<td class="${c.r ? "r" : ""}" data-label="${esc(c.label)}">${c.t === "html" ? r[c.k] ?? "" : (cellFmt[c.t] || cellFmt.text)(r[c.k])}</td>`).join("")}</tr>`).join("") || `<tr><td colspan="${cols.length}">No rows match.</td></tr>`;
      cnt.textContent = rs.length ? `${st.page * ps + 1}–${Math.min(rs.length, st.page * ps + ps)} of ${rs.length.toLocaleString("en-US")}${rs.length !== st.rows.length ? ` (filtered from ${st.rows.length.toLocaleString("en-US")})` : ""}` : "0 rows";
      $('[data-t="prev"]', box).disabled = st.page === 0; $('[data-t="next"]', box).disabled = st.page >= pages - 1;
      $(".pager .btns", box).style.display = pages > 1 ? "" : "none";
      initTips(box);
    }
    input.addEventListener("input", () => { st.q = input.value.toLowerCase().trim(); st.page = 0; draw(); });
    box.addEventListener("click", (e) => {
      const th = e.target.closest("th button"), ch = e.target.closest(".chip[data-f]"), t = e.target.closest("[data-t]");
      if (th) { const k = th.dataset.k; st.dir = st.sort === k && st.dir === "desc" ? "asc" : "desc"; st.sort = k; $$("th", box).forEach((x) => x.removeAttribute("aria-sort")); th.parentElement.setAttribute("aria-sort", st.dir === "asc" ? "ascending" : "descending"); draw(); }
      if (ch) { const set = (st.facet[ch.dataset.f] ||= new Set()), v = ch.dataset.v; set.has(v) ? set.delete(v) : set.add(v); ch.setAttribute("aria-pressed", set.has(v)); st.page = 0; draw(); }
      if (t && t.dataset.t === "prev") { st.page--; draw(); } if (t && t.dataset.t === "next") { st.page++; draw(); }
      if (t && t.dataset.t === "csv") WK.download(cfg.csvName || "table.csv", WK.toCSV(cols.map((c) => ({ ...c, csv: (r) => r[c.k + "_t"] ?? r[c.k] })), filtered()));
    });
    box._wk = { st, draw };
  }
  // ORDER_014: tables whose rows come from a file (cfg.src) load when they scroll near the viewport
  WK.initTables = (root = document) => $$(".wk-table", root).forEach((b) => {
    if (b._wk || b._lazy) return;
    const cfgText = ($('script[type="application/json"]', b) || {}).textContent || "";
    if (!/"src":/.test(cfgText) || !("IntersectionObserver" in window)) return initTable(b);
    b._lazy = true;
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) { io.disconnect(); initTable(b); } }, { rootMargin: "400px" });
    io.observe(b);
  });

  // ---------- ⌘K search ----------
  let dlg = null, mini = null, loadingIdx = null;
  async function searchIndex() {
    if (mini) return mini;
    if (!loadingIdx) loadingIdx = (async () => {
      await WK.load("/assets/vendor/minisearch-7.min.js");
      const core = await WK.json("/assets/search-core.json");
      const ms = new MiniSearch({ fields: ["t", "s", "x"], storeFields: ["t", "s", "u", "ty"], searchOptions: { boost: { t: 3, x: 1.5 }, prefix: true, fuzzy: 0.15, combineWith: "AND" } });
      ms.addAll(core.map((d, i) => ({ id: "c" + i, ...d })));
      mini = ms;
      WK.json("/assets/search-listings.json").then((ls) => ms.addAllAsync(ls.map((d, i) => ({ id: "l" + i, ty: "listing", ...d })), { chunkSize: 500 })).catch(() => {});
      return ms;
    })();
    return loadingIdx;
  }
  function openSearch() {
    if (!dlg) {
      dlg = document.createElement("dialog"); dlg.className = "wk-k"; dlg.setAttribute("aria-label", "Search the site");
      dlg.innerHTML = `<div class="in"><span aria-hidden="true">⌕</span><input type="search" placeholder="Search sellers, listings, pages…" aria-label="Search" autocomplete="off"></div><ul role="listbox"></ul><div class="ft">↑↓ to move · Enter to open · Esc to close · <span class="n"></span></div>`;
      document.body.appendChild(dlg);
      const inp = $("input", dlg), ul = $("ul", dlg); let sel = 0, res = [];
      const draw = () => { ul.innerHTML = res.map((r, i) => `<li role="option" aria-selected="${i === sel}"><a href="${esc(r.u)}"><span class="ty">${esc(r.ty)}</span><span>${esc(r.t)}<span class="sb">${esc(r.s || "")}</span></span></a></li>`).join("") || (inp.value ? '<li class="meta" style="padding:10px">No matches.</li>' : '<li class="meta" style="padding:10px">Try "token price", "scrape", a seller name or an address.</li>'); };
      inp.addEventListener("input", async () => { const ms = await searchIndex(); const q = inp.value.trim(); res = q ? ms.search(q).slice(0, 30) : []; if (q && !res.length) res = ms.search(q, { combineWith: "OR" }).slice(0, 30); sel = 0; draw(); $(".n", dlg).textContent = ms.documentCount.toLocaleString("en-US") + " items indexed"; });
      inp.addEventListener("keydown", (e) => {
        if (e.key === "ArrowDown") { sel = Math.min(sel + 1, res.length - 1); draw(); e.preventDefault(); $$("li", ul)[sel]?.scrollIntoView({ block: "nearest" }); }
        if (e.key === "ArrowUp") { sel = Math.max(sel - 1, 0); draw(); e.preventDefault(); $$("li", ul)[sel]?.scrollIntoView({ block: "nearest" }); }
        if (e.key === "Enter" && res[sel]) location.href = res[sel].u;
      });
      dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
      draw();
    }
    dlg.showModal(); $("input", dlg).focus(); searchIndex();
  }
  WK.openSearch = openSearch;
  document.addEventListener("keydown", (e) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); } else if (e.key === "/" && !/input|textarea|select/i.test(document.activeElement.tagName) && !document.activeElement.isContentEditable) { e.preventDefault(); openSearch(); } });
  document.addEventListener("click", (e) => { const a = e.target.closest && e.target.closest('a[href$="#k"]'); if (a) { e.preventDefault(); openSearch(); } });
  function addSearchButton() {
    const a = $('.navbar a[href$="#k"]');
    if (a) { a.classList.add("wk-search-btn"); a.setAttribute("role", "button"); a.setAttribute("aria-label", "Search the site"); const mac = /Mac|iPhone|iPad/.test(navigator.platform); a.innerHTML = `<span aria-hidden="true">⌕</span><span class="lbl">Search</span><kbd>${mac ? "⌘" : "Ctrl "}K</kbd>`; return; }
    return addSearchButtonOld();
  }
  function addSearchButtonOld() {
    const nav = $(".navbar .navbar-nav.ms-auto") || $(".navbar-nav"); if (!nav || $(".wk-search-btn")) return;
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    const b = document.createElement("button"); b.className = "wk-search-btn"; b.type = "button"; b.setAttribute("aria-label", "Search the site");
    b.innerHTML = `<span aria-hidden="true">⌕</span><span class="lbl">Search</span><kbd>${mac ? "⌘" : "Ctrl "}K</kbd>`; b.addEventListener("click", openSearch);
    nav.after(b);
  }

  function init() { addSearchButton(); initTips(); initFrames(); WK.initTables(); }
  document.readyState === "loading" ? document.addEventListener("DOMContentLoaded", init) : init();
})();
