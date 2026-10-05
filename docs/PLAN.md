# Manx Speech Corpus: plan

## Current state (handover, 2026-10-05)
**Done:** P0–P4 (P3b + P4 signed off by Chris 2026-10-05; he judges quality in the final output). **P5 signed off** (Chris 2026-10-05; Common Voice
kept as one work per clip). Read the `reports/` files for details. Nothing is running.

**P5, export** (`scripts/export.py`, `reports/P5_export.md`):
- `OpenData/`: 11,902 works (10,374 human + 1,528 ASR), 195,187 lines, 2.02 M words. `export.py check` (data CI)
  passes on all of them.
- D35 done: `loayr/` and `automatic_transcriptions/` imported as subtrees with history. The old repos got a "moved" README
  and were archived on GitHub (Chris, 2026-10-05).
- `inventory.py` reads Loayr metadata from `loayr/`, and the 8 Skeealyn Vannin recordings we hold that are also corpus
  works now use the corpus `document.csv` (cased, speakers, English; D17). They were realigned; the old alignments are
  kept as `align/human/<id>.normalised/`. `0308` keeps ours (the corpus copy covers 60 %).
- Next: P6 (site).

**Fix later (Chris, 2026-10-05; not blocking):**
- URLs for the 11 bad YouTube links and the open rows in `registers/link_register.tsv`.
- A listen to the 12 batch-`20261001` recordings with no segments (list in `reports/P3_asr.md`).
- 3 human recordings not aligned (`reports/P4_align.md`): one empty transcript, `04235` and `04230` too short for the
  long-audio segmenter (could go through the short-clip path).
- The master repeats two ids for different recordings: `083612` (Foillan film vs a LearnManx lesson, crossed metadata)
  and `088445`. Export takes the first row, as alignment did; needs real ids from Chris.
- 11 stale `<videoID>_*.csv` files in `align/human/msd-*/` from the first run; `qc` and `export` read only `<id>/<id>_*`.
- `~/gpu-scheduler/config` is `ALLOWED_GPUS=0,1`; both GPUs idle.


## Goal

Extend corpus.gaelg.im with a **speech** counterpart to its text corpus. It will be a searchable record of transcriptions of
Manx audio. Each hit points the user to the **original audio at its source** (a link, plus a timestamp at the matched
phrase). The site hosts no audio, because of storage and licensing.

## What already exists (surveyed 2026-10-01)

### Site (`manx-corpus-search/`, C# backend + React client, MIT)
- `DocumentLine` already carries `Speaker`, `SubStart` and `SubEnd` per line. `YouTuber.tsx` embeds a YouTube player
  that seeks to a line's start. `AudioAttestationModal.tsx` plays dictionary attestations from recordings.
- Only YouTube is supported as a player and link target. Timing is per line, not per word.
- The data is read from `manx-search-data/OpenData`. It is not a submodule; it is copied or pulled at build/reindex
  time (`OPERATIONS.md`).

### Corpus data (`external/manx-search-data/`, shallow clone)
- 821 works, about 2.1 M Manx words. One folder per work holds `document.csv`, `manifest.json.txt` and `license.txt`.
- **23 works are already audio-linked** (`OpenData/Video/YouTube/...`: Skeealyn Vannin 1948, UOSH, Possan Ronsee Gaelgagh).
  Their schema is `Speaker, Manx, English, SubStart, SubEnd`, and they are timed by hand, only partly.

### Our audio (`/store/store3/data/Manx_Resources/`)
- `speech/recordings_metadata.tsv`: 5,493 recordings, **324 h** in total. Columns: id, domain, style, transcribed,
  description, duration, source, url, samplerate.

| source | transcribed h | untranscribed h | URL type |
|---|---|---|---|
| manx_radio | 0 | 154.3 | podcast episode pages (294), site root (11) |
| learn_manx | 11.0 | 93.3 | learnmanx.com (2,427), "other" (1,942, TBC) |
| youtube | 21.8 | 21.9 | video URLs (720), channel URLs (2) |
| saysomething | 0 | 15.8 | TBC |
| clilstore | 6.0 | 0 | clilstore page |
| **total** | **≈ 38.8 (12%)** | **≈ 285** | |

- Alignments, in `datasets/all_long/`:
  - `segments_supervised` + `text_supervised` give utterance segments for the transcribed audio.
  - `unsupervised_ctms/score_{5..20}_*.ctm` give word-level Kaldi CTMs for the pseudo-labelled audio. There are 16 LM
    weights, and which one is final is TBC.
  - `datasets/pseudo-labelled/` (with `srt/`, `transcriptions/`) and `speech/automatic_transcriptions/abbyr-v1` are
    also there. How these relate to each other is TBC.
- Pseudo-label text is uppercase, normalised and unpunctuated (`OOILLEY NY SHIRVEISHYN`). The corpus text is cased and
  punctuated.

### Alignment and transcript assets found (2026-10-01)
- **Pseudo-labels (TDNN):** `kaldi/egs/manx-p4-refine_asr/s5/exp/chain_nn2/tdnn_1d_sp/decode_unsupervised/`
  - `score_{5..20}/unsupervised_hires.ctm` are word-level CTMs with absolute times, made 2025-08-30.
  - `datasets/pseudo-labelled/<id>/<id>-NNN.{txt,wav}` hold the same TDNN text, segmented. There are 1,345 recordings.
  - `ctm_conf.all` has word confidences, but only for 8 recordings (a partial run).
- **Human transcripts aligned:** `kaldi/egs/manx/s5`, with per-document biased-LM decodes (`exp/tri3/doc_decodes/split_doc`,
  581 docs) and `align_best_ctm_per_doc.sh`. Also `datasets/all_long/{segments,text}_supervised`.
- **`/exp/exp5/acp24csb/timestamper/`:** the packaged Manx forced aligner (Kaldi, biased-LM segmentation, grapheme lexicon).
  It turns audio + raw transcript into word and phrase CSVs with an `aligned / interpolated / unaligned` status.
  `datasets/HOYFM/` is where it was used on the UOSH HOYFM works already in the corpus.
- **TDNN–Whisper agreement:** `datasets/all_utts/16khz/train.infer_partial.csv` (`path, transcript, hyp, cer`;
  176,156 utterances). `transcript` is the TDNN label, `hyp` an earlier Whisper output, and `cer` their disagreement.
- **Improved Whisper, trained on the agreement-filtered labels:**
  `/exp/exp3/acp24csb/whisper-ft/ASR/transformer/results/unfreeze_top12/`.
  - whisper-large-v3 (SpeechBrain), top 12 layers unfrozen, 5 epochs, trained on `train_cer0.5_verified.csv`.
  - It beats every `cer_cutoff/*` model. Test CER: lr1 8.4, lr2 15.2, lr3 25.5, lr4 20.1.
  - It is a SpeechBrain checkpoint (`save/CKPT+2026-03-21+19-13-49+00/whisper.ckpt`), not HF format.
- **Speech metadata files:** `speech/recordings_metadata.tsv` (master), `endangered_langs/Manx/metadata.csv`,
  `datasets/Loayr-v2/train.tsv`, `datasets/common_voice/cv-corpus-24.0-2025-12-05/gv/*.tsv`, `datasets/TTS/*/metadata.csv`,
  and `text/parallel/{skeealyn_vannin,learnmanx,...}/pairs.csv` (ground-truth English).

## Decisions (Chris, 2026-10-01)

| # | Topic | Decision |
|---|---|---|
| D1 | Deliverable | A working implementation of our design proposal, handed to David. Chris may own the site later. |
| D2 | Repo | Speech gets its own git repo, maintained separately from text. No Linear or Symphony. |
| D3 | Write-up | No paper. It will become an impact case study later. |
| D4 | Pseudo-labels shown | ASR transcripts are included by default. Every hit is flagged **human** or **AI-generated**, with a toggle to filter. ASR text is excluded from word statistics and dictionary attestations. |
| D5 | Confidence | Use TDNN vs Whisper-FT agreement as the confidence signal. WER is about 15–20% on revived Manx. |
| D6 | ASR text display | Show it as it is, lowercased. Punctuation restoration may come later. |
| D7 | English | Include English only from a ground-truth source. No machine translation. No English column when there is none. |
| D8 | Timing | Word-level timestamps from CTMs. |
| D9 | Offsets | Long-form files are untrimmed, so timestamps should match the source. Spot-check before relying on this. Short utterances (e.g. the spoken dictionary) were trimmed. |
| D10 | Deep links | YouTube is confirmed. Other sources get a check procedure, run by Chris. |
| D11 | Broken links | Keep a register of broken or missing links and metadata. LearnManx app dumps (the spoken dictionary) have no public URL. Others will be remediated later. Add an **automated periodic link checker**. |
| D12 | Link rot | Check periodically and keep archive.org fallbacks. |
| D13 | Rights | The corpus is a Culture Vannin resource, so there is no rights concern for transcripts. |
| D14 | Speakers | Anything already shown publicly online may be shown. There are no speaker labels and no diarisation. |
| D15 | Metadata | The csv/tsv files in Manx_Resources are everything we have. |
| D16 | Scope | **Everything.** Aim for all Manx speech on the web. Anything missing from the master TSV gets added to it. |
| D17 | Existing 23 works | Integrate them into our data, UI and metadata. Human alignments take priority over ASR. |
| D18 | ASR model | Regenerate pseudo-labels with the improved Whisper `unfreeze_top12` (confirmed). Confidence is its agreement with TDNN. |
| D19 | Displayed ASR text | Whisper text, force-aligned with `timestamper` to get word times. |
| D20 | TDNN LMWT | Choose the LM weight by best dev result: **LMWT 9** (dev WER 17.81%). |
| D21 | Human transcripts | Re-align everything with `timestamper` so the whole corpus has one format and status flags. |
| D22 | No-URL sources | Keep them. Show the source name with no link, plus the human/AI flag. |
| D23 | v1 scope | v1 is the audio we have now. Automated discovery comes later. **Contribute** flow: a member checks whether we have a source; if not, they submit it with timestamps, and we point them to the timestamper on gaelgai.im. |
| D24 | Units | One work per recording. Lines are the human transcript lines; for ASR, the existing `all_utts` segments, which are also the Whisper decode units. |
| D25 | Link target | First matched word minus about 1 s, floored to whole seconds. |
| D26 | Site | A branch of `manx-corpus-search`. Two main nav links, **Text** and **Speech**, plus a **Contribute** page. Delivered as a working version David can open in his browser. |
| D27 | Repo | Public, in the **Manx-forge** GitHub org (Chris and David are both members). |
| D28 | Duplicates | YouTube is the canonical link. Other platforms are kept as alternates. |
| D29 | Link checker | A scheduled GitHub Action. |
| D30 | Confidence display | Show every line. AI lines get a confidence % coloured green, amber or red. |
| D31 | Demo hosting | Any option, as long as it is easy and free for both Chris and David. |
| D32 | Contributions | Through a GitHub issue form on the speech repo. Timestamper: https://gaelgai.im/#timestamp |
| D33 | Search UI | Speech has its own search page, separate from text search. |
| D34 | Naming | Data repo `Manx-forge/manx-speech-corpus`. The site fork also lives in Manx-forge. |
| D35 | Existing repos | Absorb everything: `Manx-forge/automatic_transcriptions` and `Manx-forge/loayr` move into the new repo. |
| D36 | Abbyr Shen Reesht | Backfilled from the RSS feed (`scripts/fetch_podcast.py`, `registers/abbyr_shen_reesht.tsv`). A **weekly job** fetches each new Sunday episode, then runs ASR, alignment and export, and pushes. It is installed once P3–P5 exist. |
| D37 | Confidence bands | green ≥ 90% agreement, amber 60–90%, red < 60%. Calibrated on Loayr-v2 test (P3). Kept for the P3b rescored text (Chris, 2026-10-04); agreement is now fresh Whisper vs TDNN 1-best. Rescored WER: green 7.3, amber 18.9, red 33.9. |
| D38 | Red segments | ~~Show the TDNN text instead of Whisper's.~~ Superseded 2026-10-04 (Chris): rescoring (P3b) picks every segment's text. |
| D39 | Embargoed audio | `Manx_Resources/embargoed/` (e.g. the Triskelion documentary tracks) is **never** included, whatever D16 says, until Chris lifts the embargo. |

## Design

### Repositories
| Repo | Role |
|---|---|
| `Manx-forge/manx-speech-corpus` (new, public) | The speech data, the build pipeline, the link checker and the contribution issue forms. Absorbs `automatic_transcriptions` and `loayr`, whose history is imported as a subtree. |
| `Manx-forge/manx-corpus-search` (fork of `david-allison/…`) | Branch `speech`: the site changes. Handed to David as a PR to upstream. |
| `david-allison/manx-search-data` | Unchanged, except that the 23 existing audio works point to their speech-repo counterpart (D17). Proposed to David, not done unilaterally. |

The local working copy is `/exp/exp5/acp24csb/manx_speech_corpus/`. Large intermediates (decodes, alignments, wav caches) go
in `/store/store3/data/manx_speech_corpus/`, never in the git repo or `$HOME`.

### Data layout (speech repo). It mirrors `manx-search-data` so the existing loader can be extended rather than replaced.
```
OpenData/<source>/<collection>/<work>/
  manifest.json.txt   # ident, name, date/circa, source platform, url (nullable), alt_urls[], deep_link
                      #   template, origin: human|asr, asr_model, aligner + version, duration, licence,
                      #   link_status, last_checked, archive_url, resource_id (master TSV id)
  document.csv        # Speaker, Manx, [English], SubStart, SubEnd, Origin, Confidence
                      #   (no English column when there is none, D7)
  words.csv           # line, idx, word, start, end, status (aligned|interpolated|unaligned)
registers/
  recordings.tsv      # master inventory = speech/recordings_metadata.tsv, reconciled and extended (D16)
  link_register.tsv   # broken, missing or redirected links, with reason and remediation status (D11)
```
- **Origin** is per line, so a work can mix human and ASR lines, with human taking priority (D17).
- **Confidence** applies to ASR lines only. It is `100 × (1 − CER(Whisper, TDNN))` on that segment. The green, amber and red
  thresholds are calibrated in Phase 3, not guessed (see below).
- Text normalisation for search reuses the site's `NormalizeManx`. ASR text is stored lowercased (D6).

### Site changes (`speech` branch)
1. Top nav: **Text** (the current site), **Speech** and **Contribute** (D26).
2. A Speech search page (D33). It uses its own index over `document.csv` and `words.csv`. Filters: origin (human/AI), source,
   date and confidence band. Every hit shows its source, the human/AI badge, the confidence pill (D30) and a deep link to
   the first matched word minus 1 s (D25). An embedded YouTube player is used where the source is YouTube. Elsewhere the
   hit shows "source link + timestamp mm:ss", or the source name only when there is no URL (D22).
3. ASR lines are kept out of word statistics, frequency lists and dictionary attestations (D4).
4. The Contribute page:
   - a "do we have this?" lookup by URL or title against `recordings.tsv`;
   - a link to https://gaelgai.im/#timestamp;
   - a button to a prefilled GitHub issue form on the speech repo (D32).
5. Work page: the transcript, with click-to-seek for YouTube and timestamps for everything else, plus the metadata panel.

### Ops
- **Link checker** (D29): a weekly GitHub Action that HEAD/GETs every URL. YouTube availability is checked through oEmbed.
  It writes `link_register.tsv`, opens an issue with the changes, and records a Wayback Machine snapshot URL where one
  exists (D12).
- **Data CI**: a GitHub Action validating schema, monotonic times, words inside line spans, and the manifest fields.
- **Demo** (D31): the site fork deployed from GitHub as a Docker web service on a free tier (Render free, Koyeb as fallback).
  Neither Chris nor David needs a card or a server. **Risk:** free tiers give about 512 MB of RAM, and the site holds its
  index in RAM. Phase 6 measures memory; if it doesn't fit, the demo loads the speech index plus a text subset, and this is
  stated on the demo.

## Phases
Each phase ends with a short report in `reports/` and a stop for Chris's sign-off. Under the working rules, GPU and long
CPU jobs are given to Chris as commands to run, not launched by Claude, unless Chris says otherwise.

**P0. Repos and scaffolding.** DONE 2026-10-01: both repos created, `speech` branch made, workspace and CLAUDE.md in place.
- Create `Manx-forge/manx-speech-corpus` and fork the site into Manx-forge. Both are outward-facing, so each gets a
  confirmation first.
- Add the local `CLAUDE.md`, the layout and the `/store` workspace.

**P1. Inventory (CPU).** DONE 2026-10-01: see `reports/P1_inventory.md`.
- Reconcile every audio file on disk against `recordings_metadata.tsv`. Add the missing sources: Common Voice, the Loayr
  versions, Skeealyn Vannin, HOYFM, chyndaa, TTS, `endangered_langs`, and the contents of `automatic_transcriptions` and
  `loayr`.
- Classify each URL as YouTube video, other platform, channel or root, or none. Build the first `link_register.tsv`.
- Map ground-truth English (`text/parallel/*/pairs.csv`, the 23 existing works).
- Find duplicates across platforms (D28).
- Report: hours by source × origin × link class.

**P2. Offset spot-check (D9, D10).** DONE 2026-10-01: all sources timestamp-identical, 11 bad YouTube links registered; see `reports/P2_offsets.md`.
- YouTube: for a stratified sample of about 20 recordings, fetch the online audio and cross-correlate it with the on-disk
  file. Pass if the offset is under 0.1 s and the duration difference is under 0.5 s.
- Manx Radio, LearnManx, Clilstore and saysomething: Chris follows a written manual procedure (open the link, seek to 3
  listed timestamps, confirm the listed words are heard). This also records whether each platform supports deep links.
- Any source that fails gets a per-work offset, or is flagged.

**P3. ASR and confidence (GPU).** DONE 2026-10-04: LMWT 9, bands signed off (D37/D38), Whisper + TDNN on 165,258 segments from 1,528 recordings, `asr/asr_segments.tsv` written. See `reports/P3_asr.md`.
- Pick the TDNN LMWT by best dev-lr WER (D20). Get or regenerate TDNN text per `all_utts` segment.
- Decode every non-human segment with Whisper `unfreeze_top12` (D18). A rough guess is 4–8 h on one 3090.
- Compute per-segment agreement.
- **Calibrate the colours:** on the human-transcribed test sets (lr1–4, bc), decode with both systems and relate agreement
  to true CER. Set green/amber/red so that, for example, green means true WER ≲ 15% and red means ≳ 40%. Chris signs off
  the thresholds.

**P3b. ASR post-correction (Chris, 2026-10-04).** DONE 2026-10-05: rescored text collected, signed off. See `reports/P3_asr.md`.

**P4. Alignment (CPU, long).** DONE 2026-10-05: 10,375 human + 1,528 ASR recordings aligned, signed off. See `reports/P4_align.md`.
- Run `timestamper` over every recording: human transcripts (D21), and Whisper text for ASR works (D19). For ASR, align
  per segment within its known span, which is more robust than whole-recording biased-LM search.
- QC: aligned/interpolated/unaligned rates per source. Hand-check about 10 random words per source against the audio.

**P5. Export.** DONE 2026-10-05, signed off: see `reports/P5_export.md`.
- Build `OpenData/` works and the registers. Merge human over ASR (D17). Absorb the two Manx-forge repos (D35).
- Data CI passes.

**P6. Site.**
- Implement the site changes on the `speech` branch, with tests in the repo's existing NUnit/vitest style.
- Measure memory and run locally.

**P7. Ops and demo.** Includes the weekly Abbyr Shen Reesht job (D36): a cron job on titan every Monday that runs fetch → ASR (GPU, a few minutes) → align → export → push.
- Add the link-checker and data-CI Actions, the issue form, and the free-tier deploy.
- Write `HANDOVER.md` for David: what changed, how to run it, the PR scope, and what is proposed for `manx-search-data`.

## Risks and checks
- **Whisper hallucination on silence or music** (podcast jingles). Mitigation: segment-level decoding, plus a
  repeated-n-gram and length-ratio filter. A flagged segment gets 0% confidence rather than being removed.
- **TDNN segment boundaries cutting words.** Timestamper re-aligns within padded spans.
- **Podcast dynamic ad insertion** shifting timestamps. P2 catches this.
- **YouTube `t=` takes whole seconds.** The floor and 1 s pre-roll make this safe.
- **Upstream drift.** The site is pushed often (last push 2026-09-28), so rebase the `speech` branch before handover.

## Open items
- **Punctuation restoration** for ASR text (Chris, 2026-10-04): later, as a trained model. Not Claude in-session at
  corpus scale (1.68M words).
