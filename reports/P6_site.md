# P6: site

The `speech` branch of `manx-corpus-search` (commit `f244763`, on top of upstream `c984c32`). Not yet pushed; see "Push".

## What it adds
- **Nav (D26):** Text (the current home page), Speech, Dictionary, Browse All, Contribute, Translations. On a phone the
  links wrap to two rows.
- **Speech search, `/speech` (D33):** Manx or English, with the site's own query language and normalisation.
  - Results are matched lines, grouped by recording, most matches first: up to 100 recordings, 3 lines each, with a link to the rest.
  - Every line shows a **Human** or **AI n%** badge, coloured green, amber or red by the D37 bands (D4, D30).
  - Every line has a time that links to the recording at its source, at the **matched word less 1 s**, floored (D25):
    YouTube `&t=`, mp3 `#t=`. Where the source cannot seek (Clilstore), the time is shown beside a plain link. Where
    there is no public link, the source name is shown (D22).
  - Filters: transcribed by (anyone, people, AI), AI lines (all, amber and green, green only), source platform.
- **Recording page, `/speech/<ident>`:**
  - The metadata panel: source and alternate links, date, length, speakers, transcript origin and model, notes,
    a GitHub link to the data, and a link to the text corpus's copy of the 23 shared works.
  - YouTube recordings embed the site's existing sticky player; click a time to seek.
  - Every line has its time, speaker, Manx, English (where there is ground truth) and badge.
- **Contribute, `/contribute` (D23, D32):** a "do we have this?" lookup. A URL matches a work's source or alternate
  links (a YouTube URL in any form, by its video ID); anything else matches titles. Then links to the
  [timestamper](https://gaelgai.im/#timestamp) and a prefilled GitHub issue on the speech repo. The issue form
  (`recording.yml`) is a P7 item.

## How
- **Its own index (D4).** `SpeechService` holds a second `LuceneIndex` and `Searcher`, so ASR text never reaches the
  text corpus's statistics, frequency lists or dictionary attestations. The query language, normalisation and
  highlighting are the same code.
- `LuceneIndex` gains three line fields: `origin` and `confidence` (filters), and `word_starts`, the start time of
  each word, read from `words.csv` at load. It also gains `ScanLines`, a per-line variant of `Scan`. With `word_starts`, a hit
  links to its matched word without reading files at query time. An unaligned word falls back to the aligned word
  before it, and an English match to its line.
- API: `api/Speech/Search/{query}`, `Work/{ident}`, `Lookup?q=`, `Statistics`.
- Data: `Speech:OpenDataPath`, by default `SpeechData` beside the server. In production `tools/init.sh` clones
  `Manx-forge/manx-speech-corpus` (shallow) to a new volume and reads it in place.
- Text corpus changes: the English column becomes optional, `markChunks` is exported for reuse, and
  `SpaRouteGuard` knows the new pages. Nothing else in the text corpus's behaviour changes.

## Tests
- NUnit: 886 pass (870 before, plus 16 new in `SpeechServiceTest`). The new ones load a 3-recording fixture and cover
  links at the word, the unaligned fallback, the 0 s floor, unseekable sources, English hits, every filter, the
  recording page, lookup by URL and title, and the route guard.
- vitest: 433 pass (42 files before, plus `SpeechLine.test.tsx`): bands, badges, links and seeking, time
  formatting, YouTube IDs. `tsc`, eslint and prettier are clean.
- Checked by hand in headless Chromium at desktop and phone widths: search, both kinds of recording page, Contribute.

## Memory and load time
Measured locally with the full text corpus (821 works) and the speech corpus (11,902 works). The 2-core runs are
pinned with `taskset` to stand in for the production droplet (2 GB RAM).

| configuration | settled RSS | peak while loading | speech load |
|---|---|---|---|
| text only, 2 cores | 437 MB | 554 MB | – |
| text + speech, 2 cores | 775 MB | 910 MB | 72 s |
| speech only, 2 cores | 751 MB | 761 MB | – |
| text + speech, 40 cores, server GC | 964 MB | – | 40 s |

- **The production droplet (2 GB) fits text + speech** with room to spare.
- **A 512 MB free tier fits neither corpus**, not even today's site (437 MB settled, 554 MB peak). The speech index is
  most of the speech cost, because it carries every field the text index has (cased and lemma variants with term vectors).
  For the P7 demo the options are a host with about 1 GB, or a slimmer speech index (no lemma or cased fields).
  Measure before choosing.

## Push
GitHub refused the push to `Manx-forge/manx-corpus-search`. The branch sits on upstream's latest master, which
changes `.github/workflows/deploy-image.yml`, and the active gh account (`chris-sj-bartley`) has no `workflow`
scope. The other logged-in account (`c-bartley`) has it. Either:
- `gh auth refresh -h github.com -s workflow` (adds the scope to the active account), or
- push as `c-bartley`.
