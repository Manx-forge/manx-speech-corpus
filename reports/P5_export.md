# P5: export

`scripts/export.py` writes one work per recording (D24) to `OpenData/<source>/<collection>/<id>/` from the P4 alignments
and `asr/asr_segments.tsv`. `export.py check` is the data CI (schema, times inside their line, human word times
monotonic, manifest fields, unique idents). Log: `/store/store3/data/manx_speech_corpus/work/logs/export.log`.

**11,902 works: 10,374 human + 1,528 ASR, 195,187 lines, 2.02 M words, 352 h.** About 86 MB of csv/json, no file over 5 MB.

| source | origin | works | hours | lines | with English | with deep link |
|---|---|---|---|---|---|---|
| clilstore | human | 57 | 4.8 | 3,233 | 4 | 0 (cannot seek, P2) |
| common_voice | human | 6,302 | 10.1 | 6,302 | 0 | 0 (no URL) |
| common_voice | asr | 129 | 0.8 | 472 | 0 | 0 (no URL) |
| learn_manx | human | 3,572 | 10.9 | 9,402 | 1,446 | 1,470 |
| learn_manx | asr | 760 | 92.7 | 44,466 | 0 | 720 |
| manx_radio | asr | 368 | 180.3 | 105,155 | 0 | 367 |
| saysomething | asr | 29 | 15.8 | 5,529 | 0 | 0 (taken down) |
| youtube | human | 443 | 18.6 | 10,993 | 183 | 442 |
| youtube | asr | 242 | 18.8 | 9,635 | 0 | 230 |

## Files
- `manifest.json.txt`: `ident` (`speech-<id>`), `name`, `source` (the page URL, or null), `platform`, `resource_id`,
  `origin`, `asr_model` or `transcript_form`, `aligner`, `duration`, `deep_link` (a template with `{t}` in whole
  seconds, or null), `alt_urls` (D28), `link_status` (`ok` or the link-register issue), and for the 23 corpus works
  `corpus_work` plus the corpus manifest's dates, author, notes and translator.
- `document.csv`: `Speaker, Manx, [English], SubStart, SubEnd, Origin, Confidence`. English appears only where a
  ground-truth source has it (D7). Confidence (0–100) is on ASR lines only.
- `words.csv`: `line, idx, word, start, end, status`. Unaligned words have no times.

## How lines are made
- **ASR:** one line per segment (D24). Line times come from the aligned words, falling back to the segment span.
- **Human:** the transcript's own lines (corpus `document.csv` rows keep their speaker and English). Where Loayr has
  ground-truth English (1,633 works), the transcript is cut at the Loayr utterances by aligning the two token sequences,
  and each line carries its English. Any remaining line over 20 words is split at its widest pauses, so the one-line
  normalised transcripts read as phrases.
- Normalised human text, ASR text and the uppercase Loayr English are lowercased (D6, P1).
- Lines with no aligned word are spread evenly between their neighbours.

## Changes upstream of the export
- **D35:** `Manx-forge/loayr` and `Manx-forge/automatic_transcriptions` are imported with their history
  (`git subtree`) as `loayr/` and `automatic_transcriptions/`. The old repos are untouched.
- **D17:** 8 Skeealyn Vannin recordings we hold are also corpus works. `inventory.py` now gives them the corpus
  `document.csv` (cased, speakers, English) in place of our normalised transcript, and they were realigned.
  The old alignments are kept as `align/human/<id>.normalised/`. `0308` keeps ours, because the corpus copy covers only
  60 % of it.

## Not exported
- Recordings with no aligned transcript: Forvo (756 single-word pages, no audio), 5 Loayr IDs with no audio, the 3
  human recordings P4 could not align, and `057871` (an empty transcript).
- Duplicates of another recording (`dup_of`); their URLs become the canonical work's `alt_urls`.
