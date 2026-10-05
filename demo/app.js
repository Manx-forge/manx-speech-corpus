// The speech corpus demo: corpus.gaelg.im's Speech pages as a static site. The search runs here, over the index
// scripts/demo.py builds: phrase search in Manx or English, hits grouped by recording, each line linked to the
// recording at its source at the matched word less a second (D25).
"use strict"

const PLATFORMS = {
    youtube: "YouTube", manx_radio: "Manx Radio", learn_manx: "Learn Manx", clilstore: "Clilstore",
    common_voice: "Common Voice", saysomething: "Say Something in Manx",
}
const MAX_RECORDINGS = 100, LINES_SHOWN = 3
const REPO = "https://github.com/Manx-forge/manx-speech-corpus"
// works.json columns
const NAME = 0, PLATFORM = 1, ORIGIN = 2, SOURCE = 3, DEEP = 4, STATUS = 5, YEAR = 6, ALT = 7

const cache = new Map()
const getJSON = (path) => {
    if (!cache.has(path)) cache.set(path, fetch(path).then((r) => (r.ok ? r.json() : null)))
    return cache.get(path)
}
const works = () => getJSON("data/works.json")
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

// as scripts/demo.py's norm(): lowercase, accents off, apostrophes kept inside a word
const norm = (w) => w.toLowerCase().replace(/[’‘]/g, "'").normalize("NFD").replace(/\p{M}/gu, "")
    .replace(/^[^\p{L}\p{N}_]+|[^\p{L}\p{N}_]+$/gu, "")
const shard = (t) => { const k = t.slice(0, 2).replace(/[^a-z0-9]/g, "_"); return k.length == 2 ? k : k + "_" }

const formatTime = (s) => {
    s = Math.floor(s)
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), pad = (x) => String(x).padStart(2, "0")
    return h ? `${h}:${pad(m)}:${pad(s % 60)}` : `${m}:${pad(s % 60)}`
}
const band = (c) => (c >= 90 ? "green" : c >= 60 ? "amber" : "red")
const badge = (c) => c < 0
    ? `<span class="badge human" title="Transcribed by a person">Human</span>`
    : `<span class="badge ai ${band(c)}" title="AI-generated transcript, ${c}% confidence">AI ${c}%</span>`
const youTubeId = (url) => url?.match(/(?:watch\?(?:.*&)?v=|youtu\.be\/|\/embed\/)([\w-]{11})/)?.[1] ?? null

/** The link at `seconds` less a second, floored (YouTube's t= takes whole seconds); the source itself if it cannot seek */
function link(work, seconds) {
    const t = Math.max(0, Math.floor(seconds - 1))
    if (work[DEEP]) return { t, href: work[DEEP].replace("{t}", t), seek: true }
    return { t, href: work[STATUS] == "ok" ? work[SOURCE] : null, seek: false }
}

/** When word `pos` of a line starts: its own time, else the aligned word before it, else the line's start */
function wordStart(line, pos) {
    const starts = line[5]
    for (let i = Math.min(pos, starts.length - 1); i >= 0; i--) if (starts[i] >= 0) return starts[i] / 100
    return line[0]
}

function lineHtml(work, line, highlight, onSeek) {
    const [start, , manx, english, conf] = line
    const marks = new Set(highlight?.positions ?? [])
    const text = manx.split(/\s+/).map((w, i, all) => (marks.has(i)
        ? `${marks.has(i - 1) ? "" : "<mark>"}${esc(w)}${marks.has(i + 1) && i + 1 < all.length ? "" : "</mark>"}`
        : esc(w))).join(" ")
    const at = link(work, highlight ? wordStart(line, highlight.positions[0]) : start)
    const time = onSeek
        ? `<button class="time" data-seek="${at.t}">▶ ${formatTime(at.t)}</button>`
        : at.href
            ? `<a class="time" href="${esc(at.href)}" target="_blank" rel="noreferrer">${at.seek ? "▶ " : ""}${formatTime(at.t)}</a>`
            : `<span class="time plain">${formatTime(at.t)}</span>`
    const en = english && (highlight?.english || onSeek) ? `<span class="english">${esc(english)}</span>` : ""
    return `<li class="line"><span>${time}</span><span class="line-text"><span>${text}</span>${en}</span>` +
        `<span class="badge-cell">${badge(conf)}</span></li>`
}

/** Lines matching the phrase: {work: {line: [positions of the phrase's first word]}}, with the match count */
async function search(query, lang, filters) {
    const terms = query.split(/\s+/).map(norm).filter(Boolean)
    if (!terms.length) return null
    const all = await works()
    const postings = await Promise.all(terms.map(async (t) => (await getJSON(`data/${lang}/${shard(t)}.json`))?.[t] ?? []))
    const later = postings.slice(1).map((p) => {
        const s = new Set()
        for (let i = 0; i < p.length; i += 4) s.add(`${p[i]},${p[i + 1]},${p[i + 2]}`)
        return s
    })
    const hits = new Map()
    let matches = 0
    const first = postings[0]
    for (let i = 0; i < first.length; i += 4) {
        const [w, l, p, c] = [first[i], first[i + 1], first[i + 2], first[i + 3]]
        if (!later.every((s, k) => s.has(`${w},${l},${p + k + 1}`))) continue
        const work = all[w]
        if (filters.origin && work[ORIGIN] != filters.origin) continue
        if (filters.platform && work[PLATFORM] != filters.platform) continue
        if (filters.minConfidence && c >= 0 && c < filters.minConfidence) continue
        matches++
        if (!hits.has(w)) hits.set(w, new Map())
        const lines = hits.get(w)
        if (!lines.has(l)) lines.set(l, [])
        lines.get(l).push(p)
    }
    return { terms, matches, hits }
}

// ---------------------------------------------------------------- pages

const page = document.getElementById("page")
const params = () => new URLSearchParams(location.hash.split("?")[1] ?? "")
const setParams = (p) => history.replaceState(null, "", `#/?${p.toString()}`)

async function searchPage() {
    const p = params()
    page.innerHTML = `
        <div class="search-row">
            <input class="search-input" id="q" type="search" placeholder="Search in Manx…" value="${esc(p.get("q") ?? "")}" autofocus>
            <div class="seg"><button data-lang="gv">Gaelg</button><button data-lang="en">English</button></div>
        </div>
        <div class="filters">
            <label>Transcribed by <select id="origin"><option value="">Anyone</option><option value="human">People</option><option value="asr">AI</option></select></label>
            <label title="AI transcripts make mistakes: hide the less certain lines">AI lines <select id="minConfidence"><option value="">All</option><option value="60">Amber and green</option><option value="90">Green only</option></select></label>
            <label>Source <select id="platform"><option value="">All</option>${Object.entries(PLATFORMS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></label>
        </div>
        <div id="results"></div>`
    for (const id of ["origin", "minConfidence", "platform"]) page.querySelector(`#${id}`).value = p.get(id) ?? ""
    const lang = () => (params().get("lang") == "en" ? "en" : "gv")
    const paint = () => page.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("active", b.dataset.lang == lang()))
    paint()
    let timer
    const update = () => {
        const next = new URLSearchParams()
        const q = page.querySelector("#q").value
        if (q) next.set("q", q)
        if (lang() == "en") next.set("lang", "en")
        for (const id of ["origin", "minConfidence", "platform"]) if (page.querySelector(`#${id}`).value) next.set(id, page.querySelector(`#${id}`).value)
        setParams(next)
        clearTimeout(timer)
        timer = setTimeout(results, 200)
    }
    page.querySelector("#q").addEventListener("input", update)
    page.querySelectorAll("select").forEach((s) => s.addEventListener("change", update))
    page.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
        const next = params()
        b.dataset.lang == "en" ? next.set("lang", "en") : next.delete("lang")
        setParams(next)
        page.querySelector("#q").placeholder = b.dataset.lang == "en" ? "Search in English…" : "Search in Manx…"
        paint()
        results()
    }))
    results()
}

let searchId = 0
async function results() {
    const id = ++searchId
    const box = document.getElementById("results")
    const p = params(), q = (p.get("q") ?? "").trim()
    const all = await works()
    if (!q) {
        const ai = all.filter((w) => w[ORIGIN] == "asr").length
        box.innerHTML = `<div class="intro">Search what was said in <b>${all.length.toLocaleString()} recordings</b> of Manx<br>and listen at the source.
            <div class="intro-note">${(all.length - ai).toLocaleString()} are transcribed by people and ${ai.toLocaleString()} by AI.
            Lines marked <b>AI</b> contain mistakes: the percentage is how sure it was. Missing a recording? <a href="#/contribute">Contribute it</a>.</div></div>`
        return
    }
    box.innerHTML = `<div class="message">Searching…</div>`
    const lang = p.get("lang") == "en" ? "en" : "gv"
    const found = await search(q, lang, {
        origin: p.get("origin"), platform: p.get("platform"), minConfidence: Number(p.get("minConfidence")) || 0,
    })
    if (id != searchId) return
    if (!found || found.hits.size == 0) {
        box.innerHTML = `<div class="message">No matches for “${esc(q)}”. Try another spelling: AI transcripts may spell a word differently.</div>`
        return
    }
    const ranked = [...found.hits].map(([w, lines]) => ({ w, lines, count: [...lines.values()].reduce((a, x) => a + x.length, 0) }))
        .sort((a, b) => b.count - a.count || all[a.w][NAME].localeCompare(all[b.w][NAME])).slice(0, MAX_RECORDINGS)
    const files = await Promise.all(ranked.map((r) => getJSON(`data/lines/${r.w}.json`)))
    if (id != searchId) return
    const n = found.terms.length
    const cards = ranked.map((r, i) => {
        const work = all[r.w], lines = files[i]
        const shown = [...r.lines.keys()].sort((a, b) => a - b).slice(0, LINES_SHOWN)
        const lis = shown.map((l) => {
            const firsts = r.lines.get(l)
            const positions = lang == "gv" ? firsts.flatMap((p) => Array.from({ length: n }, (_, k) => p + k)) : null
            return lineHtml(work, lines[l], positions ? { positions } : { positions: [0], english: true })
        }).join("")
        const more = r.lines.size - shown.length
        return `<li class="recording"><div class="recording-head"><a class="recording-name" href="#/rec/${r.w}">${esc(work[NAME])}</a>
            <span class="meta">${PLATFORMS[work[PLATFORM]] ?? esc(work[PLATFORM])}${work[YEAR] ? ` · ${work[YEAR]}` : ""}${work[STATUS] != "ok" ? " · no public link" : ""}</span></div>
            <ul class="lines">${lis}</ul>${more > 0 ? `<a class="more" href="#/rec/${r.w}">${more} more matching line${more == 1 ? "" : "s"}</a>` : ""}</li>`
    }).join("")
    box.innerHTML = `<div class="results-header"><div class="results-count">Found <b class="n">${found.matches.toLocaleString()}</b> matches in <b>${found.hits.size.toLocaleString()}</b> recordings</div>
        ${found.hits.size > ranked.length ? `<div class="results-note">Showing the ${ranked.length} with the most matches</div>` : ""}</div><ol class="results">${cards}</ol>`
}

async function recordingPage(w) {
    const all = await works(), work = all[w], lines = await getJSON(`data/lines/${w}.json`)
    if (!work || !lines) {
        page.innerHTML = `<div class="message">No such recording.</div>`
        return
    }
    document.title = `${work[NAME]} | Manx Corpus Search (demo)`
    const video = work[DEEP] ? youTubeId(work[SOURCE]) : null
    const platform = PLATFORMS[work[PLATFORM]] ?? work[PLATFORM]
    const source = work[SOURCE] && work[STATUS] == "ok"
        ? `<a href="${esc(work[SOURCE])}" target="_blank" rel="noreferrer">${esc(platform)}</a>` : `${esc(platform)}${work[STATUS] != "ok" ? ` (no public link: ${esc(work[STATUS])})` : ""}`
    page.innerHTML = `<h1>${esc(work[NAME])}</h1>
        <dl class="work-meta">
            <dt>Source</dt><dd>${source}${work[ALT].map((u) => ` · <a href="${esc(u)}" target="_blank" rel="noreferrer">also here</a>`).join("")}</dd>
            ${work[YEAR] ? `<dt>Date</dt><dd>${work[YEAR]}</dd>` : ""}
            <dt>Transcript</dt><dd>${work[ORIGIN] == "asr"
                ? `<span class="badge ai">AI</span> AI-generated (fine-tuned Whisper). It contains mistakes; each line shows how confident the model was.`
                : `<span class="badge human">Human</span> Transcribed by a person.`} Word timings by forced alignment.</dd>
        </dl>
        ${video ? `<div class="player"><iframe id="player" src="https://www.youtube.com/embed/${video}" allow="autoplay; encrypted-media" allowfullscreen></iframe></div>` : ""}
        ${!work[DEEP] && work[STATUS] == "ok" && work[SOURCE] ? `<p class="meta">This source cannot be linked to a moment: open it and go to the time shown.</p>` : ""}
        <ul class="lines">${lines.map((l) => lineHtml(work, l, null, video)).join("")}</ul>`
    if (video) page.querySelectorAll("[data-seek]").forEach((b) => b.addEventListener("click", () => {
        document.getElementById("player").src = `https://www.youtube.com/embed/${video}?start=${b.dataset.seek}&autoplay=1`
    }))
}

function urlKey(url) {
    const v = youTubeId(url)
    if (v) return "youtube:" + v
    const m = url.trim().match(/^https?:\/\/(?:www\.)?(\S+)$/i)
    return m ? m[1].replace(/\/+$/, "").toLowerCase() : null
}

async function contributePage() {
    page.innerHTML = `<div class="contribute"><h1>Contribute a recording</h1>
        <p>The speech corpus aims to hold every recording of Manx on the web. Know one we're missing? Three steps:</p>
        <ol>
            <li><b>Check we don't have it.</b> Paste its link, or type words of its title:
                <input class="search-input" id="lookup" type="search" placeholder="https://www.youtube.com/watch?v=… or a title"><div id="found" class="meta"></div></li>
            <li><b>Timestamp it (optional).</b> If you have a transcript, the <a href="https://gaelgai.im/#timestamp" target="_blank" rel="noreferrer">Manx timestamper</a>
                lines it up with the audio. Without one, we transcribe it with speech recognition.</li>
            <li><b>Send it to us</b> on <a id="issue" href="${REPO}/issues/new?template=recording.yml" target="_blank" rel="noreferrer">GitHub</a>:
                the form asks for the link, and any transcript or timestamps you have.</li>
        </ol></div>`
    const all = await works()
    page.querySelector("#lookup").addEventListener("input", (e) => {
        const q = e.target.value.trim(), out = page.querySelector("#found")
        page.querySelector("#issue").href = `${REPO}/issues/new?${new URLSearchParams({ template: "recording.yml", url: q })}`
        if (q.length < 3) return (out.innerHTML = "")
        const key = urlKey(q)
        const hits = all.map((w, i) => [w, i]).filter(([w]) => key
            ? [w[SOURCE], ...w[ALT]].some((u) => u && urlKey(u) == key)
            : w[NAME].toLowerCase().includes(q.toLowerCase())).slice(0, 20)
        out.innerHTML = hits.length
            ? hits.map(([w, i]) => `We have <a href="#/rec/${i}">${esc(w[NAME])}</a> (${PLATFORMS[w[PLATFORM]] ?? esc(w[PLATFORM])}, ${w[ORIGIN] == "asr" ? "AI" : "human"} transcript)`).join("<br>")
            : `We don't have “${esc(q)}” yet. Please send it in.`
    })
}

function route() {
    const path = location.hash.replace(/^#/, "").split("?")[0] || "/"
    document.querySelectorAll("[data-nav]").forEach((a) => a.classList.toggle("active",
        (a.dataset.nav == "contribute") == (path == "/contribute")))
    document.title = "Speech | Manx Corpus Search (demo)"
    window.scrollTo(0, 0)
    const rec = path.match(/^\/rec\/(\d+)$/)
    if (rec) recordingPage(Number(rec[1]))
    else if (path == "/contribute") contributePage()
    else searchPage()
}
window.addEventListener("hashchange", route)
route()
