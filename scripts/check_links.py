"""Link checker (D11, D12, D29): is every exported work's source still there? Run weekly by a GitHub Action.

  python scripts/check_links.py [limit]

Checks each work's source URL and, where it differs, the media file its deep link seeks in. YouTube videos are checked
through oEmbed (a deleted, private or unembeddable video fails); anything else by HEAD, falling back to a one-byte GET.
A newly broken link gets a registers/link_register.tsv row (status open) with the Wayback Machine's closest snapshot;
a checker row whose link works again becomes status fixed. The changes are printed as Markdown, for the Action's issue.
Stdlib only, so it runs anywhere.
"""
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REGISTER = REPO / "registers/link_register.tsv"
COLS = ["id", "source", "url", "issue", "status", "archive_url"]
TAG = "[link check]"
UA = {"User-Agent": "manx-speech-corpus link checker (github.com/Manx-forge/manx-speech-corpus)"}
YT_ID = re.compile(r"(?:watch\?(?:.*&)?v=|youtu\.be/|/embed/)([\w-]{11})")


def fetch(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, r.read(2048) if method == "GET" else b""


def problem(url):
    """None if the link works, else what is wrong with it."""
    try:
        video = YT_ID.search(url)
        if video:
            fetch("https://www.youtube.com/oembed?format=json&url="
                  + urllib.parse.quote(f"https://www.youtube.com/watch?v={video.group(1)}"))
            return None
        try:
            fetch(url, "HEAD")
        except urllib.error.HTTPError as e:
            if e.code not in (403, 405, 501):  # servers refusing HEAD get a GET
                raise
            fetch(url, headers={"Range": "bytes=0-0"})
        return None
    except urllib.error.HTTPError as e:
        if YT_ID.search(url):
            return {401: "video private or not embeddable", 403: "video private or not embeddable"}.get(
                e.code, f"video unavailable (oEmbed HTTP {e.code})")
        if e.code in (401, 403, 429):  # refuses robots (Twitter from GitHub's runners), not gone
            return None
        return f"unreachable (HTTP {e.code})"
    except Exception as e:  # DNS, TLS, timeout
        return f"unreachable ({type(e).__name__})"


def snapshot(url):
    try:
        _, body = fetch("https://archive.org/wayback/available?url=" + urllib.parse.quote(url))
        found = json.loads(body).get("archived_snapshots", {}).get("closest", {})
        return found.get("url", "") if found.get("available") else ""
    except Exception:
        return ""


def targets():
    """(work resource id, platform, url) for every exported work's links"""
    for m in sorted((REPO / "OpenData").rglob("manifest.json.txt")):
        w = json.loads(m.read_text(encoding="utf-8"))
        urls = {w["source"]} if w.get("source") else set()
        if w.get("deep_link"):
            urls.add(re.sub(r"[#&?]t=\{t\}s?$", "", w["deep_link"]))
        for url in sorted(urls):
            yield w["resource_id"], w["platform"], url


def main(limit=None):
    rows = [dict(zip(COLS, r + [""] * (len(COLS) - len(r)))) for r in
            list(csv.reader(open(REGISTER, encoding="utf-8"), delimiter="\t"))[1:]]
    known = {(r["id"], r["url"]) for r in rows if r["status"] != "fixed"}
    # and this checker's open rows: a flagged work's export drops its deep link, so only the register remembers it
    todo = list(dict.fromkeys(list(targets()) + [(r["id"], r["source"], r["url"]) for r in rows
                                                 if TAG in r["issue"] and r["status"] == "open"]))
    todo = todo[:int(limit) if limit else None]
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda t: problem(t[2]), todo))
    today = date.today().isoformat()
    broken, fixed = [], []
    for (rid, platform, url), issue in zip(todo, results):
        if issue and (rid, url) not in known:
            row = dict(id=rid, source=platform, url=url, issue=f"{issue} {TAG} {today}", status="open",
                       archive_url=snapshot(url))
            rows.append(row)
            broken.append(row)
    working = {(rid, url) for (rid, _, url), issue in zip(todo, results) if issue is None}
    for r in rows:
        if TAG in r["issue"] and r["status"] == "open" and (r["id"], r["url"]) in working:
            r["status"] = "fixed"
            fixed.append(r)
    with open(REGISTER, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"Checked {len(todo)} links on {today}: {len(broken)} newly broken, {len(fixed)} fixed.\n")
    for title, rs in (("Newly broken", broken), ("Working again", fixed)):
        if rs:
            print(f"### {title}\n\n| id | source | url | issue | archived copy |\n|---|---|---|---|---|")
            print("\n".join(f"| {r['id']} | {r['source']} | {r['url']} | {r['issue']} | {r['archive_url']} |" for r in rs))
            print()


if __name__ == "__main__":
    main(*sys.argv[1:])
