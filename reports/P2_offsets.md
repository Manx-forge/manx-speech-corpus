# P2 offset and link check report (2026-10-01)

**Verdict: our audio is timestamp-identical to what is online.** Times measured on our files can be used directly in links.

## Method
For each pair, we fetched the online audio and cross-correlated it against our file:
- 10 ms energy envelopes give a coarse lag, refined at sample level;
- the measurement is taken at the start, and at the end for files over 4.5 min, to catch drift;
- durations are compared.

The pass criterion is |lag| < 0.1 s and |duration difference| < 0.5 s. This was an ad-hoc check, so the scripts were not
committed (CLAUDE.md).

## Results
| source | sample | pass | worst lag | worst duration difference |
|---|---|---|---|---|
| YouTube (21 collections, stratified) | 21 | 20 | 0.08 s | 0.12 s |
| Manx Radio (old wav vs publisher mp3) | 4 | 4 | 0.000 s | 0.00 s |
| LearnManx direct mp3 | 6 | 6 | 0.000 s | 0.00 s |
| Clilstore (page's mp3) | 4 | 4 | 0.000 s | 0.00 s |

- **The one YouTube failure was a wrong URL, not an offset.** `086350` ("A Walk Around Cregneash", part two) links to
  "Paul Kalkbrenner - Part Two".
- **No drift was seen** in any file long enough to measure it. The YouTube lags of 0–80 ms come from codec padding and
  are below the 1 s pre-roll (D25).

## Link findings
An oEmbed check of all 692 YouTube IDs found:
- **7 wrong videos**: "A Walk Around Cregneash" parts 2–6, 8 and 10 link to Paul Kalkbrenner tracks, evidently picked
  by searching for "part N".
- **1 wrong video**: `083612` (LearnManx lesson) links to a Brazilian band video.
- **3 unavailable videos**: `082460` and `088140` (Cregneash parts 7 and 9) and `08646`.

All 11 are in `registers/link_register.tsv` as `open`. Until they are fixed, these recordings are shown with their source
name and no link.

## How each source can deep-link
| source | link we show | how to seek |
|---|---|---|
| YouTube | video | `&t=<s>s` (whole seconds), or embedded player `seekTo` |
| Manx Radio | episode page, plus the publisher mp3 (`media_url`) | `<mp3>#t=<s>` (W3C media fragment); the page player has no seek parameter |
| LearnManx | mostly a direct mp3 (2,191 recordings); 233 are pages (220 of them the 1000 Words page) | `<mp3>#t=<s>` |
| Clilstore | page, which embeds `clilstore.eu/cs/<id>/<file>.mp3` | none: the server cannot seek (see below). Show the start time as text |

## Deep-link check (Chris, 2026-10-02)
Links 1–3 start at about 1:00. Link 4 (Clilstore) starts at 0:00. The reason: clilstore.eu ignores HTTP Range requests.
It returns `200` with the whole file, with no `Accept-Ranges` or `Content-Length` and no CORS headers, so neither
the browser nor our own page can seek in it. Clilstore is 2.1 h of audio. Its hits keep the link and show the start
time as text.

Links tested:
1. https://www.youtube.com/watch?v=jQi2ICXyxYw&t=60s
2. https://episodes.captivate.fm/episode/a2d439a5-4fdf-40b1-aa8b-e394cf96f555.mp3#t=60
3. https://www.learnmanx.com/media/bunneydys/bunneydys%2036.mp3#t=60
4. https://clilstore.eu/cs/9362/Saggyrt_as_ny_shellanyn.mp3#t=60
