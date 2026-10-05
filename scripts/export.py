"""P5 export: one OpenData work per recording (D24) from the P4 alignments, human over ASR (D17).

  python scripts/export.py          writes OpenData/<source>/<collection>/<id>/{manifest.json.txt,document.csv,words.csv}
  python scripts/export.py check    data CI: schema, times monotonic and inside their line, manifest fields

document.csv: Speaker, Manx, [English], SubStart, SubEnd, Origin, Confidence (English only where a ground-truth source
has it, D7; Confidence on ASR lines only). words.csv: line, idx, word, start, end, status (times empty if unaligned).
Normalised human text and ASR text are lowercased (D6). Lines are the transcript's own lines, Loayr utterances where the
recording has Loayr English, the segments for ASR, and pause-split chunks of any human line longer than MAXW words.
"""
import csv
import collections
import difflib
import functools
import itertools
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "OpenData"
ASR = Path("/store/store3/data/manx_speech_corpus/asr/asr_segments.tsv")
ENGLISH = REPO / "loayr/full_eng_translations.tsv"
ASR_MODEL = "Whisper large-v3 fine-tuned (unfreeze_top12), n-best rescored with TDNN + KenLM (P3b)"
MAXW = 20
YT = "https://www.youtube.com/watch?v={video_id}&t={t}s"


def norm(w):
    return re.sub(r"[^\w]", "", w.upper())


def read_words(f):
    return [dict(word=r["text"], start=float(r["start_sec"]) if r["start_sec"] else None,
                 end=float(r["end_sec"]) if r["end_sec"] else None) for r in csv.DictReader(open(f, encoding="utf-8"))]


def english(ids):
    """Loayr ground-truth English per recording: [(Manx, English)] in utterance order. Loayr-v2 numbers the spoken
    dictionary 04…, the register 05…"""
    out = collections.defaultdict(list)
    for r in csv.DictReader(open(ENGLISH, encoding="utf-8-sig"), delimiter="\t"):
        rid = r["AudioID"] if r["AudioID"] in ids or not r["AudioID"].startswith("04") else "05" + r["AudioID"][2:]
        if r["English"].strip():
            out[rid].append((r["Manx"], r["English"].strip()))
    return out


def by_utterance(tokens, utts):
    """Assign each transcript token to a Loayr utterance by aligning the two token sequences."""
    flat = [(k, norm(w)) for k, (m, _) in enumerate(utts) for w in m.split()]
    sm = difflib.SequenceMatcher(None, [norm(t) for t in tokens], [w for _, w in flat], autojunk=False)
    owner = [None] * len(tokens)
    for a, b, n in sm.get_matching_blocks():
        for i in range(n):
            owner[a + i] = flat[b + i][0]
    first = next((o for o in owner if o is not None), 0)
    for i, o in enumerate(owner):  # unmatched tokens join the utterance before them
        owner[i] = o if o is not None else (owner[i - 1] if i else first)
    return owner


def pause_split(idx, words):
    """Split a long run of word indices at its widest pause until no chunk exceeds MAXW words."""
    if len(idx) <= MAXW:
        return [idx]
    gaps = [(words[b]["start"] - words[a]["end"], i) for i, (a, b) in enumerate(zip(idx, idx[1:]), 1)
            if MAXW // 4 <= i <= len(idx) - MAXW // 4 and words[a]["end"] is not None and words[b]["start"] is not None]
    cut = max(gaps)[1] if gaps else len(idx) // 2
    return pause_split(idx[:cut], words) + pause_split(idx[cut:], words)


def human_lines(r, text, words, eng):
    """[(speaker, english, [word indices])] for a human transcript; words match its text.split() one to one."""
    t = r["transcript"]
    if t.endswith("document.csv"):
        src = [(x.get("Speaker") or "", (x.get("English") or "").strip(), x["Manx"] or "") for x in csv.DictReader(open(t, encoding="utf-8-sig"))]
    else:
        src = [("", "", line) for line in text.split("\n")]
    lines, i = [], 0
    for spk, en, manx in src:
        n = len(manx.split())
        if n:
            lines.append((spk, en, list(range(i, i + n))))
        i += n
    assert i == len(words), f"{r['id']}: {i} transcript tokens, {len(words)} aligned words"
    if eng and not any(en for _, en, _ in lines):
        owner = by_utterance([w["word"] for w in words], eng)
        lines = [("", eng[k][1], [i for _, i in g]) for k, g in
                 ((k, list(g)) for k, g in itertools.groupby(zip(owner, range(len(words))), key=lambda x: x[0]))]
    return [(spk, en, chunk) for spk, en, idx in lines for chunk in (pause_split(idx, words) if not en else [idx])]


def span(idx, words):
    ts = [(words[i]["start"], words[i]["end"]) for i in idx if words[i]["start"] is not None]
    return (min(s for s, _ in ts), max(e for _, e in ts)) if ts else (None, None)


def fill(spans, lo, hi):
    """Spread lines with no aligned word evenly between their neighbours."""
    spans = [list(s) for s in spans]
    i = 0
    while i < len(spans):
        if spans[i][0] is not None:
            i += 1
            continue
        j = i
        while j < len(spans) and spans[j][0] is None:
            j += 1
        a = spans[i - 1][1] if i else lo
        b = max(a, spans[j][0] if j < len(spans) else hi)
        for k in range(i, j):
            spans[k] = [a + (k - i) * (b - a) / (j - i), a + (k - i + 1) * (b - a) / (j - i)]
        i = j
    return spans


def deep_link(r):
    if r["video_id"]:
        return YT.replace("{video_id}", r["video_id"])
    media = r["media_url"] or (r["url"] if re.search(r"\.(mp3|m4a)$", r["url"], re.I) else "")
    return f"{media}#t={{t}}" if media and r["source"] != "clilstore" else None  # clilstore cannot seek (P2)


def collection(r):
    parts = [p for p in r["collection"].split("/") if p not in ("transcribed", "untranscribed", r["source"])]
    return "/".join(parts) or "misc"


@functools.cache
def corpus_manifests():
    return {d["ident"]: d for d in (json.loads(m.read_text(encoding="utf-8-sig"))
                                    for m in (REPO / "external/manx-search-data/OpenData").rglob("manifest.json.txt"))}


def export():
    sys.path.insert(0, str(REPO / "scripts"))
    from align import ALIGN, recordings, transcript  # timestamper's modules: titan only, unlike check()
    recs = {}
    for r in recordings():
        recs.setdefault(r["id"], r)  # the master repeats two ids; alignment used the first row too
    alt = collections.defaultdict(list)
    for r in recs.values():
        if r["dup_of"] and not r["dup_of"].startswith("disk:") and r["url"]:
            alt[r["dup_of"]].append(r["url"])
    register = [r for r in csv.DictReader(open(REPO / "registers/link_register.tsv", encoding="utf-8"), delimiter="\t")
                if r["status"] != "fixed"]
    issues = {r["id"]: r["issue"] for r in register}
    archived = {r["id"]: r["archive_url"] for r in register if r["archive_url"]}  # D12: check_links.py
    segs = collections.defaultdict(list)
    for s in csv.DictReader(open(ASR, encoding="utf-8"), delimiter="\t"):
        segs[s["recording"]].append(s)
    eng = english({r["id"] for r in recs.values()})
    n = collections.Counter()
    for rid, r in recs.items():
        if (ALIGN / "human" / rid / f"{rid}_words.csv").exists():
            origin, words = "human", read_words(ALIGN / "human" / rid / f"{rid}_words.csv")
            lines = [(spk, en, idx, "human", "") for spk, en, idx in human_lines(r, transcript(r), words, eng.get(rid))]
            lo, hi = 0.0, float(r["duration_s"] or 0) or max((w["end"] or 0) for w in words)
            spans = fill([span(idx, words) for *_, idx, _, _ in lines], lo, hi)
        elif rid in segs:
            origin, words = "asr", read_words(ALIGN / "asr" / rid / f"{rid}_words.csv")
            lines, spans, i = [], [], 0
            for s in sorted(segs[rid], key=lambda s: float(s["start"])):
                k = len(s["text"].split())
                idx = list(range(i, i + k))
                i += k
                if re.search(r"\w", s["text"]):
                    a, b = span(idx, words)
                    lines.append(("", "", idx, "asr", str(round(float(s["confidence"])))))
                    spans.append((a, b) if a is not None else (float(s["start"]), float(s["end"])))
            assert i == len(words), f"{rid}: {i} segment tokens, {len(words)} aligned words"
        else:
            continue
        if not lines:  # an empty transcript
            continue
        lower = origin == "asr" or r["transcript_form"] == "normalised"
        has_en = any(en for _, en, *_ in lines)
        d = OUT / r["source"] / collection(r) / rid
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "document.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["Speaker", "Manx"] + ["English"] * has_en + ["SubStart", "SubEnd", "Origin", "Confidence"])
            for (spk, en, idx, org, conf), (a, b) in zip(lines, spans):
                manx = " ".join(words[i]["word"] for i in idx)
                w.writerow([spk, manx.lower() if lower else manx] + [" ".join(en.lower().split() if en.isupper() else en.split())] * has_en
                           + [f"{a:.2f}", f"{b:.2f}", org, conf])
        with open(d / "words.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow(["line", "idx", "word", "start", "end", "status"])
            for li, (*_, idx, _, _) in enumerate(lines):
                for k, i in enumerate(idx):
                    x = words[i]
                    al = x["start"] is not None
                    w.writerow([li, k, x["word"].lower() if lower else x["word"], f"{x['start']:.2f}" if al else "",
                                f"{x['end']:.2f}" if al else "", "aligned" if al else "unaligned"])
        cw = corpus_manifests().get(r["corpus_work"], {})
        m = {"ident": f"speech-{rid}", "name": cw.get("name") or unquote(r["title"]).strip() or f"{r['source']} {rid}",
             **{k: cw[k] for k in ("createdCircaStart", "createdCircaEnd", "author", "notes", "translated") if k in cw},
             **({"createdCircaStart": r["date"], "createdCircaEnd": r["date"]} if r["date"] else {}),
             "source": r["url"] if r["link_class"] in ("youtube_video", "web_page") else None,
             "platform": r["source"], "resource_id": rid, "origin": origin,
             **({"asr_model": ASR_MODEL} if origin == "asr" else {"transcript_form": r["transcript_form"]}),
             "aligner": "timestamper", "duration": float(r["duration_s"] or 0) or None,
             "deep_link": deep_link(r) if rid not in issues else None, "alt_urls": alt.get(rid, []),
             "link_status": issues.get(rid, "ok"), **({"archive_url": archived[rid]} if rid in archived else {}),
             **({"corpus_work": r["corpus_work"]} if r["corpus_work"] else {})}
        (d / "manifest.json.txt").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        n[origin] += 1
        n["lines"] += len(lines)
        n["words"] += len(words)
    print(f"export: {n['human']} human + {n['asr']} asr works, {n['lines']} lines, {n['words']} words -> {OUT}")


def check():
    """Data CI over OpenData: fails (exit 1) on the first 20 problems."""
    errs = []
    need = {"ident", "name", "source", "platform", "resource_id", "origin", "aligner", "deep_link", "alt_urls", "link_status"}
    idents = set()
    works = sorted(OUT.rglob("manifest.json.txt"))
    for mf in works:
        d = mf.parent
        m = json.loads(mf.read_text(encoding="utf-8"))
        bad = lambda msg: errs.append(f"{d.relative_to(REPO)}: {msg}")  # noqa: E731
        if need - m.keys():
            bad(f"manifest lacks {sorted(need - m.keys())}")
        if m.get("ident") in idents:
            bad("duplicate ident")
        idents.add(m.get("ident"))
        doc = list(csv.DictReader(open(d / "document.csv", encoding="utf-8")))
        cols = list(doc[0].keys()) if doc else []
        if cols not in (["Speaker", "Manx", "SubStart", "SubEnd", "Origin", "Confidence"],
                        ["Speaker", "Manx", "English", "SubStart", "SubEnd", "Origin", "Confidence"]):
            bad(f"document.csv columns {cols}")
            continue
        for i, l in enumerate(doc):
            a, b = float(l["SubStart"]), float(l["SubEnd"])
            if not 0 <= a <= b or not l["Manx"] or l["Origin"] not in ("human", "asr") \
                    or (l["Confidence"] != "" if l["Origin"] == "human" else not 0 <= int(l["Confidence"]) <= 100):
                bad(f"line {i}: {l}")
        prev = -1.0
        for x in csv.DictReader(open(d / "words.csv", encoding="utf-8")):
            li = int(x["line"])
            if not 0 <= li < len(doc) or (x["status"] == "aligned") != (x["start"] != ""):
                bad(f"word {x}")
            elif x["start"]:
                s, e = float(x["start"]), float(x["end"])
                if not (s <= e and float(doc[li]["SubStart"]) - 0.01 <= s and e <= float(doc[li]["SubEnd"]) + 0.01):
                    bad(f"word outside its line or reversed: {x}")
                if m["origin"] == "human" and s < prev - 0.01:
                    bad(f"word times go backwards: {x}")
                prev = s
        if len(errs) >= 20:
            break
    print("\n".join(errs) or f"check: {len(works)} works OK")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    check() if sys.argv[1:] == ["check"] else export()
