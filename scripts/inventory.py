"""P1 inventory: one row per recording across every Manx speech source we hold.

Writes registers/recordings.tsv (the master inventory) and registers/link_register.tsv
(recordings whose link is missing or not a deep-linkable page). Read-only on all sources.

  python scripts/inventory.py          the registers
  python scripts/inventory.py titles   fetch the media's own titles into registers/titles.tsv (network; only new ones),
                                       where the master's are generic ("Conversational Interview"): YouTube videos by
                                       oEmbed, Clilstore units by their page. The registers prefer them.
"""
import csv
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import wave
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MR = Path("/store/store3/data/Manx_Resources")
MASTER = MR / "speech/recordings_metadata.tsv"
CV = MR / "datasets/common_voice/cv-corpus-24.0-2025-12-05/gv"
SPS = MR / "datasets/common_voice/sps-corpus-2.0-2025-12-05-gv/ss-corpus-gv.tsv"
FORVO = MR / "datasets/manx_source_comparison/gv.metadata.csv"
SEGMENTS = MR / "datasets/all_utts/16khz/wavs"  # held-out Loayr test recordings exist only as cuts here: excluded (Chris)
CACHE = Path("/store/store3/data/manx_speech_corpus/cache")
YT_AUDIO = CACHE / "audio"  # YouTube audio fetched with yt-dlp, for alignment only (never published)
REPO = Path(__file__).resolve().parents[1]
LOAYR = REPO / "loayr/recordings_metadata.csv"  # Manx-forge/loayr, imported (D35)
CORPUS = REPO / "external/manx-search-data/OpenData"
OUT = REPO / "registers"

COLS = ["id", "source", "collection", "title", "date", "domain", "style", "duration_s", "audio", "media_url", "transcript",
        "transcript_form", "url", "link_class", "video_id", "dup_of", "corpus_work", "in_master"]
YT_ID = re.compile(r"(?:watch\?v=|youtu\.be/|/embed/)([\w-]{11})")


def link_class(url):
    if not url or url in ("missing",):
        return "none"
    if url in ("app_files", "learn_manx_app_files"):
        return "app_only"
    if YT_ID.search(url):
        return "youtube_video"
    if "youtube.com/@" in url or "youtube.com/c/" in url or "youtube.com/channel" in url:
        return "channel"
    if re.fullmatch(r"https?://[^/]+/?", url):
        return "site_root"
    return "web_page"


def wav_seconds(p):
    try:
        with wave.open(str(p)) as w:
            return round(w.getnframes() / w.getframerate(), 2)
    except (wave.Error, EOFError):
        return ""


def speech_files():
    """id -> (wav, transcript) for the long-form audio under speech/. First path wins; others are dups."""
    found, dups = {}, defaultdict(list)
    for root, _, files in sorted(os.walk(MR / "speech")):
        for f in sorted(files):
            if not f.endswith(".wav"):
                continue
            rid, wav = f[:-4], Path(root) / f
            tr = next((t for t in (wav.with_suffix(".trans.txt"), wav.with_suffix(".txt")) if t.exists()), None)
            if rid in found:
                dups[rid].append(str(wav))
            else:
                found[rid] = (wav, tr)
    return found, dups


def transcript_form(p):
    if not p:
        return ""
    return "raw" if re.search(r"[a-z]", p.read_text(encoding="utf-8", errors="replace")) else "normalised"


def words(p):
    p = Path(p)
    rows = csv.DictReader(open(p, encoding="utf-8-sig")) if p.name == "document.csv" else [{"Manx": p.read_text(encoding="utf-8")}]
    return sum(len(r["Manx"].split()) for r in rows)


def corpus_works():
    """YouTube video id -> (ident, name, url, document.csv) for the audio works already in the text corpus."""
    out = {}
    for m in CORPUS.rglob("manifest.json.txt"):
        d = json.loads(m.read_text(encoding="utf-8-sig"))
        v = YT_ID.search(d.get("source", ""))
        if v:
            out[v.group(1)] = (d["ident"], d["name"], d["source"], m.parent / "document.csv")
    return out


def fetch_titles():
    path = OUT / "titles.tsv"
    have = {r["id"]: r for r in csv.DictReader(open(path, encoding="utf-8"), delimiter="\t")} if path.exists() else {}
    wrong = {r["id"] for r in csv.DictReader(open(OUT / "link_register.tsv", encoding="utf-8"), delimiter="\t")
             if r["status"] == "open"}  # a wrong or dead link would name the wrong thing
    rows = [r for r in csv.DictReader(open(OUT / "recordings.tsv", encoding="utf-8"), delimiter="\t")
            if r["id"] not in have and r["id"] not in wrong and (r["video_id"] or r["source"] == "clilstore")]

    def title(r):
        try:
            if r["video_id"]:
                url = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(
                    f"https://www.youtube.com/watch?v={r['video_id']}")
                with urllib.request.urlopen(url, timeout=30) as f:
                    return json.load(f)["title"]
            unit = re.search(r"page\.php\?id=(\d+)", r["url"])
            with urllib.request.urlopen(f"https://clilstore.eu/clilstore/page.php?id={unit.group(1)}", timeout=30) as f:
                return re.search(r"<title>CLILstore unit \d+: ([^<]+)", f.read().decode("utf-8", "replace")).group(1).strip()
        except Exception:
            return None

    with ThreadPoolExecutor(8) as ex:
        found = dict(zip((r["id"] for r in rows), ex.map(title, rows)))
    have.update({rid: dict(id=rid, title=t) for rid, t in found.items() if t})
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["id", "title"], delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(have.values(), key=lambda r: r["id"]))
    print(f"titles: {sum(1 for t in found.values() if t)} of {len(rows)} fetched, {len(have)} in {path}")


def main():
    files, disk_dups = speech_files()
    works = corpus_works()
    loayr_url = {r["recording_id"]: r["url/source"] for r in csv.DictReader(open(LOAYR, encoding="utf-8-sig"))}
    rows = []

    for r in csv.DictReader(open(MASTER, encoding="utf-8"), delimiter="\t"):
        rid = r["id"]
        wav, tr = files.get(rid, (None, None))
        if not wav and (SEGMENTS / rid).is_dir():
            continue
        audio = str(wav or "")
        coll = str(wav.parent.relative_to(MR / "speech")).split(f"/{rid}")[0] if wav else ""
        rows.append(dict(id=rid, source=r["source"], collection=coll, title=r["description"], domain=r["domain"],
                         style=r["style"], duration_s=r["duration (s)"], audio=audio,
                         transcript=str(tr) if tr else "", transcript_form=transcript_form(tr),
                         url=r["url"].strip(), in_master="y"))
    master_ids = {r["id"] for r in csv.DictReader(open(MASTER, encoding="utf-8"), delimiter="\t")}

    by_id = {r["id"]: r for r in rows}
    for ep in csv.DictReader(open(OUT / "abbyr_shen_reesht.tsv", encoding="utf-8"), delimiter="\t"):  # fetch_podcast.py
        r = by_id.get(ep["id"])
        if r is None:
            r = dict(id=ep["id"], source="manx_radio", collection="untranscribed/manx_radio/abbyr_shen_reesht",
                     domain="podcast", url=ep["page_url"], in_master="n")
            rows.append(r)
        r.update(title=ep["title"], date=ep["date"], audio=ep["audio"], media_url=ep["media_url"],
                 duration_s=r.get("duration_s") or ep["duration_s"])

    for rid, url in loayr_url.items():  # loayr recordings never added to the master
        if rid not in master_ids and not (SEGMENTS / rid).is_dir():
            wav, tr = files.get(rid, (None, None))
            rows.append(dict(id=rid, source="loayr", url=url, audio=str(wav or ""), transcript=str(tr or ""),
                             transcript_form=transcript_form(tr), duration_s=wav_seconds(wav) if wav else "",
                             in_master="n"))

    dur = {r["clip"]: int(r["duration[ms]"]) / 1000 for r in csv.DictReader(open(CV / "clip_durations.tsv"), delimiter="\t")}
    for r in csv.DictReader(open(CV / "validated.tsv", encoding="utf-8"), delimiter="\t", quoting=csv.QUOTE_NONE):
        rows.append(dict(id="cv-" + r["path"].removesuffix(".mp3"), source="common_voice", collection="cv-24.0/validated",
                         title=r["sentence"], style="read-speech", duration_s=dur.get(r["path"], ""),
                         audio=str(CV / "clips" / r["path"]), transcript="tsv:sentence", transcript_form="raw",
                         in_master="n"))
    for r in csv.DictReader(open(SPS, encoding="utf-8"), delimiter="\t"):
        rows.append(dict(id=f"sps-{r['audio_id']}", source="common_voice", collection="sps-2.0", title=r["prompt"],
                         style="spontaneous", duration_s=int(r["duration_ms"]) / 1000,
                         audio=str(SPS.parent / "audios" / r["audio_file"]),
                         transcript="tsv:transcription" if r["transcription"] else "",
                         transcript_form="raw" if r["transcription"] else "", in_master="n"))
    for r in csv.DictReader(open(FORVO, encoding="utf-8")):
        rows.append(dict(id=f"forvo-{r['assigned_id']}", source="forvo", collection="words", title=r["transcript_word"],
                         style="spoken_dictionary", url=r["word_url"], transcript="csv:transcript_word",
                         transcript_form="raw", in_master="n"))
    held = {YT_ID.search(r["url"]).group(1) for r in rows if YT_ID.search(r.get("url", ""))}
    for vid, (ident, name, url, doc) in works.items():  # corpus audio works we hold no recording of (D17)
        if vid not in held:
            audio = YT_AUDIO / f"{vid}.wav"
            audio = audio if audio.exists() else None
            rows.append(dict(id=f"msd-{ident}", source="youtube", collection="manx-search-data", title=name,
                             url=url, audio=str(audio or ""), duration_s=wav_seconds(audio) if audio else "",
                             transcript=str(doc), transcript_form="raw", in_master="n"))

    # link class, YouTube id, duplicates (same video, or same id on disk twice), overlap with the text corpus
    first_by_video = {}
    for r in rows:
        r["url"] = r.get("url") or loayr_url.get(r["id"], "")
        r["link_class"] = link_class(r["url"])
        v = YT_ID.search(r["url"])
        r["video_id"] = v.group(1) if v else ""
        r["corpus_work"] = works[r["video_id"]][0] if r["video_id"] in works else ""
        if r["corpus_work"] and r.get("transcript_form") == "normalised" and words(works[r["video_id"]][3]) >= 0.9 * words(r["transcript"]):
            r["transcript"], r["transcript_form"] = str(works[r["video_id"]][3]), "raw"  # cased, with English (D17)
        if r["video_id"]:
            r["dup_of"] = first_by_video.setdefault(r["video_id"], r["id"])
            if r["dup_of"] == r["id"]:
                r["dup_of"] = ""
    for r in rows:
        if r["id"] in disk_dups and not r.get("dup_of"):
            r["dup_of"] = "disk:" + ";".join(disk_dups[r["id"]])

    titles = OUT / "titles.tsv"  # the media's own titles (fetch_titles) over the master's descriptions
    own = {t["id"]: t["title"] for t in csv.DictReader(open(titles, encoding="utf-8"), delimiter="\t")} if titles.exists() else {}
    for r in rows:
        r["title"] = own.get(r["id"]) or r.get("title", "")
        sv = re.search(r"Skeealyn Vannin,? Disk (\d+) Track (\w+)", r["title"])
        if sv:  # as the text corpus names and dates them (the Irish Folklore Commission recorded them in 1948)
            r["title"], r["date"] = f"🎥 Skeealyn Vannin, Disk {sv.group(1)} Track {sv.group(2)}", r.get("date") or "1948"
    OUT.mkdir(exist_ok=True)
    with open(OUT / "recordings.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", restval="", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    issues = {"none": "no URL recorded", "channel": "channel URL, not the video", "site_root": "site root, not the page",
              "app_only": "LearnManx app dump; no public URL"}
    reg = OUT / "link_register.tsv"
    derived = set(issues.values()) | {"removed by publisher"}
    found = [r for r in csv.reader(open(reg, encoding="utf-8"), delimiter="\t")][1:] if reg.exists() else []
    found = [r for r in found if r[3] not in derived]  # rows from checks (P2, link checker) are kept, not regenerated
    with open(reg, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["id", "source", "url", "issue", "status", "archive_url"])  # archive_url: check_links.py
        w.writerows([r["id"], r["source"], r["url"], "removed by publisher" if r["source"] == "saysomething" else issues[r["link_class"]],
                     "permanent" if r["link_class"] == "app_only" or r["source"] == "saysomething" else "open", ""]
                    for r in rows if r["link_class"] in issues and r["source"] != "common_voice")
        w.writerows(r + [""] * (6 - len(r)) for r in found)
    print(f"{len(rows)} recordings -> {OUT / 'recordings.tsv'}")


if __name__ == "__main__":
    fetch_titles() if sys.argv[1:] == ["titles"] else main()
