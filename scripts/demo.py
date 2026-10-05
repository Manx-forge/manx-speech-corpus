"""The demo on GitHub Pages: the site's own client (manx-corpus-search, branch speech, built with the Pages base path)
with demo/speech-api.js answering its api/Speech calls from a static index of OpenData, so it needs no server.
Deployed by .github/workflows/demo.yml.

  python scripts/demo.py OUT CLIENT_BUILD BASE     e.g. _site site/CorpusSearch/ClientApp/build /manx-speech-corpus/

OUT/data/works.json        [[ident, name, platform, origin, source, deep_link, link_status, date, alt_urls, duration]]
OUT/data/lines/<w>.json    {meta: {...}, lines: [[start, end, manx, english, confidence, speaker, [word start cs]]]}
OUT/data/<gv|en>/<k>.json  {term: [work, line, position, confidence, ...]}: the postings of every term whose first two
                           characters are k (confidence -1 for human lines), so a query fetches a few small files
Terms are normalised as speech-api.js normalises queries: lowercase, accents off, apostrophes kept inside a word.
"""
import collections
import csv
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def norm(word):
    w = unicodedata.normalize("NFD", word.lower().replace("’", "'").replace("‘", "'"))
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"^[^\w]+|[^\w]+$", "", w)


def shard(term):
    key = re.sub(r"[^a-z0-9]", "_", term[:2])
    return key if len(key) == 2 else key + "_"


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main(out, client, base):
    out = Path(out)
    shutil.copytree(client, out, dirs_exist_ok=True)
    shutil.copy(REPO / "demo/speech-api.js", out)
    # the API script runs first (module scripts are deferred); deep links and the two pages load the same shell
    page = (out / "index.html").read_text(encoding="utf-8")
    page = page.replace("<script type=\"module\"", f"<script src=\"{base}speech-api.js\"></script>\n    <script type=\"module\"", 1)
    for path in ["index.html", "404.html", "speech/index.html", "contribute/index.html"]:
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        (out / path).write_text(page, encoding="utf-8")

    (out / "data/lines").mkdir(parents=True, exist_ok=True)
    works, index = [], {"gv": collections.defaultdict(list), "en": collections.defaultdict(list)}
    for m in sorted((REPO / "OpenData").rglob("manifest.json.txt")):
        meta = json.loads(m.read_text(encoding="utf-8"))
        doc = list(csv.DictReader(open(m.parent / "document.csv", encoding="utf-8")))
        starts = collections.defaultdict(list)
        for x in csv.DictReader(open(m.parent / "words.csv", encoding="utf-8")):
            starts[int(x["line"])].append(round(float(x["start"]) * 100) if x["start"] else -1)
        w = len(works)
        works.append([meta["ident"], meta["name"], meta["platform"], meta["origin"], meta.get("source"),
                      meta.get("deep_link"), meta["link_status"], meta.get("createdCircaStart"), meta.get("alt_urls", []),
                      meta.get("duration")])
        lines = []
        for li, row in enumerate(doc):
            conf = int(row["Confidence"]) if row["Confidence"] else -1
            lines.append([float(row["SubStart"]), float(row["SubEnd"]), row["Manx"], row.get("English") or "", conf,
                          row["Speaker"], starts[li]])
            for lang, text in (("gv", row["Manx"]), ("en", row.get("English") or "")):
                for pos, word in enumerate(text.split()):
                    if term := norm(word):
                        index[lang][term] += [w, li, pos, conf]
        keep = ["createdCircaEnd", "notes", "author", "translated", "asr_model", "corpus_work"]
        dump(out / f"data/lines/{w}.json", {"meta": {**{k: meta[k] for k in keep if k in meta},
                                                     "folder": m.parent.relative_to(REPO / "OpenData").as_posix()},
                                            "lines": lines})
    dump(out / "data/works.json", works)
    for lang, terms in index.items():
        shards = collections.defaultdict(dict)
        for term, postings in terms.items():
            shards[shard(term)][term] = postings
        (out / f"data/{lang}").mkdir(exist_ok=True)
        for key, part in shards.items():
            dump(out / f"data/{lang}/{key}.json", part)
    print(f"demo: {len(works)} works, {sum(len(t) for t in index.values())} terms -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
