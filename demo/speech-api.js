// The demo's server: the site's own client runs unchanged on GitHub Pages, and this answers its api/Speech calls
// (Search, Work, Lookup, Statistics) from the static index scripts/demo.py builds, in the shapes SpeechService returns.
// Its search is phrase search over normalised words, not the site's query language. Every page of the site outside
// Speech and Contribute (Text, Dictionary, Browse, documents) opens on corpus.gaelg.im.
"use strict"
;(() => {
    const BASE = new URL(document.currentScript.src).pathname.replace(/[^/]*$/, "") // "/manx-speech-corpus/"
    const LIVE = "https://corpus.gaelg.im"
    const REPO = "https://github.com/Manx-forge/manx-speech-corpus"
    const MAX_RECORDINGS = 100, LINES_SHOWN = 3
    // works.json columns
    const IDENT = 0, NAME = 1, PLATFORM = 2, ORIGIN = 3, SOURCE = 4, DEEP = 5, STATUS = 6, DATE = 7, ALT = 8, DURATION = 9

    // the Text home page needs the server: the demo opens on Speech
    if (location.pathname == BASE || location.pathname + "/" == BASE) {
        history.replaceState(null, "", BASE + "speech" + location.search + location.hash)
    }
    document.addEventListener("click", (e) => {
        const a = e.target.closest?.("a[href]")
        if (!a || a.target == "_blank" || e.button != 0 || e.metaKey || e.ctrlKey) return
        const url = new URL(a.href, location.href)
        if (url.origin != location.origin) return
        const path = url.pathname.startsWith(BASE) ? "/" + url.pathname.slice(BASE.length) : url.pathname
        if (/^\/(speech|contribute)(\/|$)/i.test(path)) return
        e.preventDefault()
        e.stopImmediatePropagation()
        location.href = LIVE + path + url.search
    }, true)

    const cache = new Map()
    const getJSON = (path) => {
        if (!cache.has(path)) cache.set(path, fetch(BASE + "data/" + path).then((r) => (r.ok ? r.json() : null)))
        return cache.get(path)
    }
    const works = () => getJSON("works.json")

    // as scripts/demo.py's norm(): lowercase, accents off, apostrophes kept inside a word
    const norm = (w) => w.toLowerCase().replace(/[’‘]/g, "'").normalize("NFD").replace(/\p{M}/gu, "")
        .replace(/^[^\p{L}\p{N}_]+|[^\p{L}\p{N}_]+$/gu, "")
    const shard = (t) => { const k = t.slice(0, 2).replace(/[^a-z0-9]/g, "_"); return k.length == 2 ? k : k + "_" }
    const tokens = (text) => [...text.matchAll(/\S+/g)].map((m) => ({ start: m.index, end: m.index + m[0].length }))
    const youTubeId = (url) => url?.match(/(?:watch\?(?:.*&)?v=|youtu\.be\/|\/embed\/)([\w-]{11})/)?.[1] ?? null

    /** When word `pos` starts: its own time, else the aligned word before it, else the line's start */
    const wordStart = (line, pos) => {
        for (let i = Math.min(pos, line[6].length - 1); i >= 0; i--) if (line[6][i] >= 0) return line[6][i] / 100
        return line[0]
    }

    /** SpeechService.ToHit: the link at `seconds` less a second, floored; the source itself if it cannot seek */
    const hit = (work, line, l, seconds, manxHighlights, englishHighlights) => {
        const time = Math.max(0, Math.floor(seconds - 1))
        const [start, end, manx, english, confidence, speaker] = line
        return {
            lineNumber: l + 2, manx, english: english || undefined, speaker: speaker || undefined, start, end,
            origin: confidence < 0 ? "human" : "asr", confidence: confidence < 0 ? undefined : confidence,
            manxHighlights, englishHighlights, time,
            link: work[DEEP] ? work[DEEP].replace("{t}", time) : work[STATUS] == "ok" ? work[SOURCE] : undefined,
        }
    }

    async function search(query, params) {
        const english = params.get("english") == "true", lang = english ? "en" : "gv"
        const origin = params.get("origin"), platform = params.get("platform")
        const minConfidence = Number(params.get("minConfidence")) || 0
        const terms = query.split(/\s+/).map(norm).filter(Boolean)
        const all = await works()
        const postings = await Promise.all(terms.map(async (t) => (await getJSON(`${lang}/${shard(t)}.json`))?.[t] ?? []))
        const later = postings.slice(1).map((p) => {
            const s = new Set()
            for (let i = 0; i < p.length; i += 4) s.add(`${p[i]},${p[i + 1]},${p[i + 2]}`)
            return s
        })
        const found = new Map()
        let matches = 0
        const first = postings[0] ?? []
        for (let i = 0; i < first.length; i += 4) {
            const [w, l, p, c] = [first[i], first[i + 1], first[i + 2], first[i + 3]]
            if (!later.every((s, k) => s.has(`${w},${l},${p + k + 1}`))) continue
            if ((origin && (c < 0 ? "human" : "asr") != origin) || (platform && all[w][PLATFORM] != platform)
                || (minConfidence && c >= 0 && c < minConfidence)) continue
            matches++
            if (!found.has(w)) found.set(w, new Map())
            const lines = found.get(w)
            if (!lines.has(l)) lines.set(l, [])
            lines.get(l).push(p)
        }
        const ranked = [...found].map(([w, lines]) => ({ w, lines, count: [...lines.values()].reduce((a, x) => a + x.length, 0) }))
            .sort((a, b) => b.count - a.count || all[a.w][NAME].localeCompare(all[b.w][NAME])).slice(0, MAX_RECORDINGS)
        const files = await Promise.all(ranked.map((r) => getJSON(`lines/${r.w}.json`)))
        const recordings = ranked.map((r, i) => {
            const work = all[r.w], lines = files[i].lines
            const shown = [...r.lines.keys()].sort((a, b) => a - b).slice(0, LINES_SHOWN)
            return {
                ident: work[IDENT], name: work[NAME], platform: work[PLATFORM], origin: work[ORIGIN],
                source: work[SOURCE] ?? undefined, date: work[DATE] ?? undefined, linkStatus: work[STATUS],
                seekable: work[DEEP] != null, count: r.count, matchedLines: r.lines.size,
                hits: shown.map((l) => {
                    const line = lines[l], firsts = r.lines.get(l)
                    const words = tokens(english ? line[3] : line[2])
                    const ranges = firsts.map((p) => ({ start: words[p].start, end: words[p + terms.length - 1].end }))
                    return english
                        ? hit(work, line, l, line[0], undefined, ranges)
                        : hit(work, line, l, wordStart(line, firsts[0]), ranges, undefined)
                }),
            }
        })
        return {
            query, numberOfMatches: matches, numberOfLines: [...found.values()].reduce((a, x) => a + x.size, 0),
            numberOfRecordings: found.size, recordings,
        }
    }

    async function work(ident) {
        const all = await works()
        const w = all.findIndex((x) => x[IDENT] == ident)
        if (w < 0) return null
        const x = all[w], { meta, lines } = await getJSON(`lines/${w}.json`)
        return {
            ident, name: x[NAME], platform: x[PLATFORM], origin: x[ORIGIN], source: x[SOURCE] ?? undefined,
            altUrls: x[ALT], linkStatus: x[STATUS], seekable: x[DEEP] != null, duration: x[DURATION] ?? undefined,
            createdCircaStart: x[DATE] ?? undefined, createdCircaEnd: meta.createdCircaEnd, notes: meta.notes,
            author: meta.author, translated: meta.translated, asrModel: meta.asr_model, corpusWork: meta.corpus_work,
            gitHubLink: `${REPO}/tree/main/OpenData/${meta.folder.split("/").map(encodeURIComponent).join("/")}`,
            lines: lines.map((line, l) => hit(x, line, l, line[0])),
        }
    }

    /** SpeechService.UrlKey: a YouTube video by its id, anything else without scheme, www. or trailing slash */
    const urlKey = (url) => {
        const v = youTubeId(url)
        if (v) return "youtube:" + v
        const m = url.trim().match(/^https?:\/\/(?:www\.)?(\S+)$/i)
        return m ? m[1].replace(/\/+$/, "").toLowerCase() : null
    }

    async function lookup(_, params) {
        const q = (params.get("q") ?? "").trim()
        if (!q) return []
        const key = urlKey(q)
        return (await works())
            .filter((x) => (key ? [x[SOURCE], ...x[ALT]].some((u) => u && urlKey(u) == key) : x[NAME].toLowerCase().includes(q.toLowerCase())))
            .sort((a, b) => a[NAME].localeCompare(b[NAME])).slice(0, 20)
            .map((x) => ({ ident: x[IDENT], name: x[NAME], platform: x[PLATFORM], source: x[SOURCE] ?? undefined, origin: x[ORIGIN] }))
    }

    async function statistics() {
        const all = await works()
        const human = all.filter((x) => x[ORIGIN] == "human").length
        const hours = all.reduce((a, x) => a + (x[DURATION] ?? 0), 0) / 3600
        return { recordings: all.length, human, asr: all.length - human, hours: Math.round(hours * 10) / 10 }
    }

    const handlers = { search, work, lookup, statistics }
    const realFetch = window.fetch.bind(window)
    window.fetch = async (input, init) => {
        const url = new URL(typeof input == "string" ? input : input.url, location.href)
        const m = url.pathname.match(/\/api\/Speech\/(Search|Work|Lookup|Statistics)(?:\/(.+))?$/i)
        if (!m) {
            // the text corpus's API needs the server: answer "not found" rather than ask Pages
            return /\/api\//i.test(url.pathname) && url.origin == location.origin
                ? new Response("null", { status: 404, headers: { "Content-Type": "application/json" } })
                : realFetch(input, init)
        }
        const body = await handlers[m[1].toLowerCase()](m[2] ? decodeURIComponent(m[2]) : "", url.searchParams)
        return new Response(JSON.stringify(body), {
            status: body == null ? 404 : 200, headers: { "Content-Type": "application/json" },
        })
    }
})()
