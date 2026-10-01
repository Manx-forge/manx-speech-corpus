# P1 inventory report (2026-10-01)

`scripts/inventory.py` produces `registers/recordings.tsv` (12,619 recordings, 323 h; 40 h human) and
`registers/link_register.tsv` (1,975 rows). The table below is from the first run, before the 81 test recordings were
excluded. It is read-only on every source.

## What we hold
| source | human: recordings | human: h | no transcript: recordings | no transcript: h |
|---|---|---|---|---|
| manx_radio | 0 | 0.0 | 305 | 154.3 |
| learn_manx | 3,573 | 10.9 | 802 | 93.4 |
| youtube | 446 | 14.4 | 289 | 29.7 |
| saysomething | 0 | 0.0 | 29 | 15.8 |
| common_voice | 6,302 | 10.1 | 130 | 0.8 |
| clilstore | 57 | 4.8 | 5 | 1.1 |
| loayr (not in master) | 0 | 0.0 | 5 | 0.0 |
| forvo | 756 | (single words) | 0 | 0.0 |
| **total** | 11,134 | 40.2 | 1,565 | 295.2 |

- **New relative to the master TSV:**
  - Common Voice 24.0 validated: 6,302 clips.
  - Common Voice spontaneous (SPS): 130 clips.
  - Forvo: 756 word pages.
  - 5 Loayr IDs.
  - 13 corpus audio works we had no recording of (`msd-*`): UOSH HOYFM ×8, Possan Ronsee ×2, ChellveeishSeyr, and 2 Skeealyn Vannin tracks.
- **Overlap with the text corpus:** 10 of its 23 audio works are recordings we already hold (Skeealyn Vannin, matched by
  YouTube ID). The `corpus_work` column records the match.
- **Duplicates:**
  - 33 IDs exist twice on disk, e.g. `083612` is in both `foillan_film_archive` and `adult_manx`.
  - 4 recordings share a YouTube video with another recording.
  - All are recorded in `dup_of`.

## Problems found
1. **81 recordings (12.0 h) exist only as segments in `all_utts`.** These are the held-out Loayr test recordings
   (lr1–4: `0101`, `0106`, `0202`, `0315`, ...). There is no long-form file, so timestamps relative to the source need segment
   offsets. `endangered_langs/Manx/metadata.csv` has start and end times for many of them, but long-form audio is cleaner.
   These recordings *are* human-transcribed (test CSVs), even though the table above counts them as having no transcript.
2. **774 recordings have no audio on disk:**
   - 756 Forvo words (public mp3 URLs);
   - 12 corpus works whose audio is only on YouTube;
   - 5 Loayr IDs;
   - 1 master row.

   Aligning the 12 YouTube works needs their audio.
3. **Most human transcripts are normalised.** 3,774 recordings (20.0 h) are uppercase with apostrophes and punctuation
   stripped (`TAD` for `t'ad`). Only 289 recordings plus Common Voice keep the original spelling. Matching against all the
   parallel text we hold (`text/parallel`, corpus Video works) recovers the original for only about 65 recordings
   (≥ 80% 5-gram coverage).
4. **Ground-truth English** is available from:
   - Loayr `full_eng_translations.tsv`: 1,653 recordings. Spoken-dictionary IDs map from Loayr-v2's `04…113` scheme to the
     master's `05…113`, and all 1,345 of them remap cleanly.
   - The 23 corpus works.
   - `text/parallel/skeealyn_vannin`.

   The Loayr English is uppercase.
5. **Links** (`link_register.tsv`):
   - 1,944 LearnManx app dumps have no public URL (permanent).
   - 29 saysomething recordings and 1 YouTube recording have no URL.
   - 2 have channel URLs.
   - Manx Radio (305) and LearnManx pages are classed `web_page`. Whether they deep-link is checked in P2.

## Decisions (Chris, 2026-10-01)
- **Test recordings are excluded.** Chris says longer files already in the collection cover them. All 81 segment-only
  recordings are dropped. Only 26 of them share a URL with a long-form file we hold. The other 55 point elsewhere and are
  listed here in case they are worth revisiting: 0106 0140 0157 0158 0201 0202 0218 0229 0306 0315 0328 0360 0401–0410
  0429 0458 0463 0481 0483 04120–04129 04140 04228 04255 04285 04294 04313 04323 04326 04334 04340 04372 04382 04390
  04393 04394 04399 04426 04456.
- **Normalised human text** is shown lowercased and keeps its human origin.
- **`registers/recordings.tsv` is the master inventory.** `Manx_Resources/speech/recordings_metadata.tsv` stays as the
  historical source.
- **saysomething** (29 recordings) was taken down by the publisher. The rows stay as "permanent" in the link register,
  and the recordings are cited by source name only (D22).
- **Open:** audio for the 12 corpus works we hold no recording of (see the conversation of 2026-10-01).
