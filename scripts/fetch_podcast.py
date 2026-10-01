"""Sync Abbyr Shen Reesht (Manx Radio, weekly) from its RSS feed: register every episode, download the new ones.

registers/abbyr_shen_reesht.tsv holds one row per feed episode. Episodes already in the master keep their
09xxx id; new ones get the next free id. New audio is the publisher's mp3, byte for byte, named by feed guid, so timestamps match
what listeners hear. Safe to rerun: only episodes without a file on disk are downloaded.
"""
import csv
import email.utils
import html
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

FEED = "https://feeds.captivate.fm/abbyr-shen-reesht/"
PAGE = "https://www.manxradio.com/podcasts/abbyr-shen-reesht-say-that-again1/episode/abbyr-shen-reesht-say-that-again-{}/"
MASTER = Path("/store/store3/data/Manx_Resources/speech/recordings_metadata.tsv")
OLD_META = Path("/store/store3/data/Manx_Resources/speech/untranscribed/manx_radio/abbyr_shen_reesht/metadata.tsv")
OLD_AUDIO = Path("/store/store3/data/Manx_Resources/speech/untranscribed/manx_radio/abbyr_shen_reesht/episodes")
AUDIO = Path("/store/store3/data/manx_speech_corpus/audio/abbyr_shen_reesht")
REGISTER = Path(__file__).resolve().parents[1] / "registers/abbyr_shen_reesht.tsv"
COLS = ["id", "date", "title", "summary", "page_url", "media_url", "guid", "duration_s", "audio"]
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "manx-speech-corpus (github.com/Manx-forge)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def feed_episodes():
    for item in ET.fromstring(get(FEED)).iter("item"):
        dur = item.findtext(ITUNES + "duration") or "0"
        title = " ".join(item.findtext("title").split())
        yield dict(date=email.utils.parsedate_to_datetime(item.findtext("pubDate")).date(), title=title,
                   summary=" ".join(html.unescape(re.sub(r"<[^>]+>", " ", item.findtext("description") or "")).split()),
                   media_url=item.find("enclosure").get("url"), guid=item.findtext("guid"),
                   duration_s=sum(int(float(x)) * 60 ** k for k, x in enumerate(reversed(dur.split(":")))))


def page_url(ep):
    """Manx Radio's episode page: slug from the title, kept only if the page embeds this episode's audio."""
    slug = re.sub(r"[^a-z0-9]+", "-", ep["title"].lower().split("say that again", 1)[-1]).strip("-")
    try:
        return PAGE.format(slug) if ep["guid"].encode() in get(PAGE.format(slug)) else ""
    except OSError:
        return ""


def known_episodes():
    """The 305 episodes collected before this repo existed: id, page_url, audio, date, duration."""
    master = {r["url"]: r for r in csv.DictReader(open(MASTER, encoding="utf-8"), delimiter="\t")
              if r["source"] == "manx_radio"}
    return [dict(id=master[r["URL"]]["id"], page_url=r["URL"], audio=str(OLD_AUDIO / f"{master[r['URL']]['id']}.wav"),
                 date=datetime.strptime(r["Date"], "%d/%m/%Y").date(), dur=float(master[r["URL"]]["duration (s)"]))
            for r in csv.DictReader(open(OLD_META, encoding="utf-8"), delimiter="\t")]


def match_known(ep, known):
    """Feed dates and titles are unreliable (some are a year out), so match on duration; date breaks ties."""
    hits = [k for k in known if abs(k["dur"] - ep["duration_s"]) <= 2]
    best = min(hits, key=lambda k: abs((k["date"] - ep["date"]).days), default=None)
    if best:
        known.remove(best)
    return best


def main():
    rows = {r["guid"]: r for r in csv.DictReader(open(REGISTER, encoding="utf-8"), delimiter="\t")} if REGISTER.exists() else {}
    known = known_episodes() if not rows else []
    next_id = max(int(r["id"]) for r in rows.values()) + 1 if rows else 9305
    AUDIO.mkdir(parents=True, exist_ok=True)
    new = []
    for ep in sorted(feed_episodes(), key=lambda e: e["date"]):
        if ep["guid"] in rows:
            continue
        match = match_known(ep, known)
        if match:
            mp3 = AUDIO / f"{ep['guid']}.mp3"  # the publisher's file beats our old re-encode when we have it
            rid, url, audio = match["id"], match["page_url"], str(mp3) if mp3.exists() else match["audio"]
        else:
            rid, url, audio = f"0{next_id}", page_url(ep), str(AUDIO / f"{ep['guid']}.mp3")
            next_id += 1
        rows[ep["guid"]] = dict(ep, id=rid, date=ep["date"].isoformat(), page_url=url, audio=audio)
        if not Path(audio).exists():
            Path(audio).write_bytes(get(ep["media_url"]))
            new.append(rid)
            print(f"downloaded {rid} {ep['date']} {ep['title']}", flush=True)
    with open(REGISTER, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["date"]))
    print(f"{len(rows)} episodes registered, {len(new)} downloaded")
    return new


if __name__ == "__main__":
    sys.exit(0 if main() is not None else 1)
