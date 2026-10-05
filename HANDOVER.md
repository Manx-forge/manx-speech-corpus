# Handover: the speech corpus for corpus.gaelg.im

For David. This repo (`Manx-forge/manx-speech-corpus`) and a branch of the site (`Manx-forge/manx-corpus-search`,
branch `speech`) add a **Speech** counterpart to the text corpus. It searches transcripts of Manx recordings, and every hit links to the
recording at its source, at the moment the phrase is spoken. No audio is hosted.

## What a reader gets
- **Speech search** (`/speech`): Manx or English, with the site's query language. Hits are lines, grouped by
  recording. Each line is marked **Human** or **AI n%**, coloured green, amber or red, and its time links to the source:
  YouTube `&t=`, an mp3's `#t=`, or the time as text where the source cannot seek. Filters: transcribed by, AI
  confidence floor, source.
- **Recording page** (`/speech/<ident>`): the transcript with times, the YouTube player for YouTube sources, and the metadata.
- **Contribute** (`/contribute`): "do we have this recording?", then the timestamper and a GitHub issue form.
- The nav becomes Text, Speech, Dictionary, Browse All, Contribute, Translations.

**Demo: <https://manx-forge.github.io/manx-speech-corpus/>.** It opens instantly, with no server. It is the site's own client
from the `speech` branch, unchanged. `demo/speech-api.js` answers its speech API from a static index built by
`scripts/demo.py`, and Browse All's speech side is saved from the real server, which the workflow starts for the
purpose. `.github/workflows/demo.yml` redeploys it whenever the data changes. Its search is simpler than
the server's (words and phrases, no advanced syntax), and Text, Dictionary and Browse open on the live corpus. To run the real site with both corpora, open the `speech` branch
[in a Codespace](https://codespaces.new/Manx-forge/manx-corpus-search/tree/speech): it builds and starts itself in a
few minutes; the Ports tab, port 5000, opens it.

## The site PR (`Manx-forge/manx-corpus-search:speech` → `david-allison/manx-corpus-search:master`)
Two commits on top of upstream master: the speech corpus, and the Codespaces demo config (optional). The text corpus behaves exactly as before.

| | |
|---|---|
| New | `Service/SpeechService.cs` (its own `LuceneIndex` + `Searcher`), `Controllers/SpeechController.cs` (`api/Speech/{Search,Work,Lookup,Statistics}`), `Model/SpeechDocument.cs`; client `routes/{Speech,SpeechWork,Contribute}.tsx`, `components/SpeechLine.tsx`, `api/SpeechApi.ts`, `routes/Speech.css` |
| Changed | `LuceneIndex`: three optional line fields (`origin`, `confidence`, `word_starts`) and `ScanLines`, a per-line `Scan`. `Searcher.ScanLines`. `DocumentLine`: `Origin`, `Confidence`, `WordStarts`. `DocumentLineMap`: English optional. `SpaRouteGuard`: the three pages. `Startup`: load the speech corpus. `NavMenu`, `App.tsx`. `LineText`: `markChunks` exported. Mobile nav wraps |
| Deploy | `tools/init.sh` shallow-clones this repo into a new volume `/var/corpus-search/speech-data` and sets `Speech__OpenDataPath`. Nothing is copied into the image |
| Tests | NUnit `SpeechServiceTest` (16, against a 3-recording fixture); vitest `SpeechLine.test.tsx` (11). All existing tests pass |

- **Why a separate index:** AI transcripts must never feed the word statistics, frequency lists or dictionary
  attestations. A second index guarantees that with no filtering anywhere else.
- **Memory**, measured on 2 cores: today's site settles at 437 MB; with speech, 775 MB (910 MB peak while loading).
  The speech corpus takes about 70 s to load. This fits the 2 GB droplet.
- **Run it locally:** `Loading__OpenDataPath=<manx-search-data>/OpenData Speech__OpenDataPath=<this repo>/OpenData`.

## This repo
| Path | |
|---|---|
| `OpenData/<source>/<collection>/<id>/` | one work per recording: `manifest.json.txt`, `document.csv`, `words.csv` (layout as `manx-search-data`) |
| `registers/recordings.tsv` | the master inventory (12,682 recordings) |
| `registers/link_register.tsv` | broken, missing or wrong links: from the inventory, the offset checks and the monthly link checker |
| `scripts/` | the pipeline: `inventory`, `fetch_podcast`, `asr`, `align`, `export`, `check_links`, `monthly.sh` |
| `reports/` | what each build phase found and decided |
| `loayr/`, `automatic_transcriptions/` | the two earlier Manx-forge repos, imported with their history (the originals are archived) |

- **Files:**
  - `document.csv`: `Speaker, Manx, [English], SubStart, SubEnd, Origin, Confidence`. English appears only from a
    ground-truth translation. Confidence (0–100) is on AI lines only.
  - `words.csv`: `line, idx, word, start, end, status`.
  - The manifest adds `platform`, `origin`, `deep_link` (a template with `{t}`), `alt_urls`, `link_status`,
    `archive_url` and `corpus_work` to the usual fields.
- **Contents:** 11,902 works, 352 h.
  - 10,374 human-transcribed: mostly short Common Voice and spoken-dictionary clips; about 500 are long recordings.
  - 1,528 AI-transcribed: Manx Radio, Learn Manx lessons, YouTube.
- **AI transcripts:**
  - Made by fine-tuned Whisper large-v3, with each segment's candidates rescored against the TDNN's n-best and a
    4-gram LM.
  - Confidence is Whisper–TDNN agreement. The bands were calibrated on Loayr test data: green has ≈ 7% word error,
    amber ≈ 19%, red ≈ 34%.
  - Word times come from forced alignment with the Manx timestamper.
- **Automation:**
  - **Data CI** (`.github/workflows/data-ci.yml`) runs `scripts/export.py check` on every change to `OpenData/`.
  - **Link checker** (`link-check.yml`) runs monthly, on the 1st. It commits register changes and opens an issue listing them.
  - **Monthly episode job** (`scripts/monthly.sh`) is a cron job on titan, on the 1st. It runs the new Abbyr Shen Reesht
    episodes through the pipeline, pushes, and opens an issue saying what it added (or why it failed). It needs titan's models and GPUs, so it cannot run in Actions.
  - **Contributions** arrive through the issue form (`.github/ISSUE_TEMPLATE/recording.yml`).

## Proposed for `manx-search-data` (not done)
23 of its works are recordings (`OpenData/Video/...`). The speech corpus holds 22 of them: Skeealyn Vannin Disk 1
Track 11 has an empty transcript. Their transcripts were re-aligned word by word, so they now have full timings. The
proposal is to add `"speechWork": "speech-<id>"` to those 22 manifests, so the text corpus's video pages can link to the speech page with its timings. The `corpus_work` field
of each speech manifest already gives the reverse link.

## Known gaps
- Two ids in the master inventory name two different recordings each (`083612`, `088445`). The first row is used.
- 3 human transcripts could not be aligned (one is empty, two are too short for long-audio alignment).
- 11 YouTube links in the register still need correct URLs.
- AI text is lowercase with no punctuation. Punctuation restoration is planned as a trained model.
