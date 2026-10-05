"""The static demo (GitHub Pages): demo/ plus a search index built from OpenData, so the speech search runs in the
browser with no server. Deployed by .github/workflows/demo.yml on every push to main.

  python scripts/demo.py OUT     writes OUT/ (demo/'s files, and OUT/data/)

OUT/data/works.json   [[name, platform, origin, source, deep_link, link_status, year, alt_urls, has_english], ...]
OUT/data/lines/<w>.json   [[start, end, manx, english, confidence, [word start centiseconds, -1 if unaligned]], ...]
OUT/data/<gv|en>/<k>.json   {term: [work, line, position, confidence, ...]}: the postings of every term whose first
                            two characters are k (confidence -1 for human lines), so a query fetches a few small files
Terms are normalised as demo/app.js normalises queries: lowercase, accents off, apostrophes kept inside a word.
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


def main(out):
    out = Path(out)
    shutil.copytree(REPO / "demo", out, dirs_exist_ok=True)
    (out / "data/lines").mkdir(parents=True, exist_ok=True)
    works, index = [], {"gv": collections.defaultdict(list), "en": collections.defaultdict(list)}
    for m in sorted((REPO / "OpenData").rglob("manifest.json.txt")):
        meta = json.loads(m.read_text(encoding="utf-8"))
        doc = list(csv.DictReader(open(m.parent / "document.csv", encoding="utf-8")))
        starts = collections.defaultdict(list)
        for x in csv.DictReader(open(m.parent / "words.csv", encoding="utf-8")):
            starts[int(x["line"])].append(round(float(x["start"]) * 100) if x["start"] else -1)
        w = len(works)
        date = meta.get("createdCircaStart") or ""
        works.append([meta["name"], meta["platform"], meta["origin"], meta.get("source"), meta.get("deep_link"),
                      meta["link_status"], int(date[:4]) if date[:4].isdigit() else None, meta.get("alt_urls", []),
                      int("English" in (doc[0] if doc else {}))])
        lines = []
        for li, row in enumerate(doc):
            conf = int(row["Confidence"]) if row["Confidence"] else -1
            lines.append([float(row["SubStart"]), float(row["SubEnd"]), row["Manx"], row.get("English") or "", conf,
                          starts[li]])
            for lang, text in (("gv", row["Manx"]), ("en", row.get("English") or "")):
                for pos, word in enumerate(text.split()):
                    if term := norm(word):
                        index[lang][term] += [w, li, pos, conf]
        (out / f"data/lines/{w}.json").write_text(json.dumps(lines, ensure_ascii=False, separators=(",", ":")),
                                                  encoding="utf-8")
    (out / "data/works.json").write_text(json.dumps(works, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    for lang, terms in index.items():
        shards = collections.defaultdict(dict)
        for term, postings in terms.items():
            shards[shard(term)][term] = postings
        (out / f"data/{lang}").mkdir(exist_ok=True)
        for key, part in shards.items():
            (out / f"data/{lang}/{key}.json").write_text(json.dumps(part, ensure_ascii=False, separators=(",", ":")),
                                                         encoding="utf-8")
    print(f"demo: {len(works)} works, {sum(len(t) for t in index.values())} terms -> {out}")


if __name__ == "__main__":
    main(*sys.argv[1:])
