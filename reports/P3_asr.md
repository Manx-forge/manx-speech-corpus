# P3 ASR and confidence (DONE 2026-10-04; P3b post-correction in progress)

## Setup (done 2026-10-01)
- **TDNN LMWT = 9** (D20). It has the best dev WER, 17.81% (p4 `decode_dev`); LMWT 8 gives 18.11% and 10 gives 18.34%. It is
  also the weight the existing pseudo-labels and segments were made with, so nothing needs regenerating.
- **Segments** (D24) come from `all_long/segments_unsupervised`: the TDNN CTM split at 0.5 s pauses into 2–10 s segments.
  - 149,790 segments cover 1,333 recordings.
  - 953 segments, from 10 recordings never cut into `all_utts`, were cut from the long-form audio into
    `/store/.../asr/wavs`.
- **Not yet covered:** 207 recordings (26.8 h) with no TDNN pass yet. These are the 63 new Abbyr Shen Reesht episodes,
  130 Common Voice SPS clips and 14 others. Their TDNN decode and segmentation come next (CPU) and use the same code the
  weekly job will use.
- **Calibration set:** the Loayr-v2 test split, 1,139 human-transcribed segments from 57 held-out recordings. The TDNN
  LMWT 9 hypotheses already exist for these segments, and only 1 of the 57 recordings is in Whisper's training data.

## GPU run (launched by Claude on Chris's instruction, 2026-10-01)
`whisper-ft/.../infer_cer.py` (the script that produced the original agreement CSV) runs unchanged with the
`unfreeze_top12` checkpoint: large-v3, fp16, beam 4, `<|english|>` token as in training. It resumes if interrupted.

- **Calibration** (`calib.csv`, 1,139 segments): **done**.
  - Batch 16 ran out of memory, so it reran at batch 8.
  - `infer_cer.py` does not create its `--out_dir`, so the command makes it first.
- **Segments**: **done** as gpusched jobs **145** (`segments_0.csv`), **146** (`segments_1.csv`) and **148**
  (`segments_20261001.csv`), all finished 2026-10-02 by 08:46 UTC. `segments.csv` was split in half so both GPUs could
  work at once; 145 was requeued onto GPU 1 midway and resumed from its partial file.
- **To resume after a failure:** resubmit the same job.

```bash
for s in 0 1; do gpusched submit --name manx_asr_$s "export PYTHONUNBUFFERED=1 HF_HOME=/store/store3/data/hf_cache/hub; \
cd /exp/exp3/acp24csb/whisper-ft/ASR/transformer && R=results/unfreeze_top12/save && \
mkdir -p /store/store3/data/manx_speech_corpus/asr/report_segments_$s && \
/store/store3/software/bin/anaconda3/envs/speechbrain/bin/python infer_cer.py \
  --csv /store/store3/data/manx_speech_corpus/asr/segments_$s.csv --wav_root / \
  --ckpt \$R/CKPT+2026-03-21+19-13-49+00 --hub_dir \$R \
  --out_dir /store/store3/data/manx_speech_corpus/asr/report_segments_$s --batch 8"; done
```

## Calibration result (Loayr-v2 test, 1,139 segments, human references)
Overall WER on this set: Whisper 34.3%, TDNN 28.0%. Agreement predicts Whisper's true error monotonically:

| Whisper–TDNN agreement | segments | share | Whisper WER |
|---|---|---|---|
| ≥ 95% | 246 | 21.6% | 12.3 |
| 90–95% | 141 | 12.4% | 19.7 |
| 85–90% | 132 | 11.6% | 22.9 |
| 80–85% | 81 | 7.1% | 26.5 |
| 70–80% | 126 | 11.1% | 31.2 |
| 60–70% | 81 | 7.1% | 36.1 |
| 50–60% | 59 | 5.2% | 36.9 |
| < 50% | 273 | 24.0% | 103.2 |

- **The < 50% band is hallucination.** These are mostly very short clips (median 1.6 s) where Whisper loops on a phrase,
  e.g. "ellan ellan ellan …". The main segments are at least 2 s, so this band should be smaller there, and either way the
  agreement score marks it red.
- **Bands, signed off by Chris (D37):**

  | band | segments | Whisper WER | TDNN WER |
  |---|---|---|---|
  | green ≥ 90% | 387 | 15.3 | 15.1 |
  | amber 60–90% | 420 | 27.9 | 26.4 |
  | red < 60% | 332 | 88.6 | 59.0 |
- **Red segments show the TDNN text** (D38, Chris). TDNN is far better there (59.0 vs 88.6 WER); the line is still
  flagged AI. `asr_segments.tsv` records which system each line came from (`text_source`).

- **Segments over 30 s:** 199 of the 149,790 segments are longer than Whisper's 30 s window; the segmenter only splits at
  word boundaries. This is 2.55 h of 220 h. Whisper transcribes only the first 30 s of each, so these segments score low
  agreement and mostly fall back to TDNN text (D38).

## TDNN step for new recordings (`asr.py tdnn <batch>`)
This step is for recordings with no TDNN pass yet. It is the same step the weekly podcast job uses.
1. Convert the audio to 16 kHz files in `asr/wav16k/`.
2. Decode with the p4 TDNN: same model, graph, i-vector extractor and decode options as `run_tdnn_inference.sh`, using
   the recipe read-only from our own work dir `asr/kaldi/`.
3. Take the CTM at LMWT 9 and segment it with the original `make_segments_unsup.py` at its defaults.
4. Cut the segment wavs and write `asr/segments_<batch>.csv` for Whisper.

`collect` picks up every batch automatically.
- **Batch `20261001`:** 207 recordings, 26.8 h (63 new Abbyr Shen Reesht episodes, 130 Common Voice SPS clips,
  14 others). Done: 15,468 segments from 195 recordings. The other 12 have no usable segments: 7 clips under 2 s
  (`0518xx113`), `sps-42321` with no words, and 4 with only 1–2 recognised words (`010755058`, `082226`, `084515`,
  `084588`), probably music or non-Manx. Worth a listen.

## Result: `asr/asr_segments.tsv` (`asr.py collect`, 2026-10-04)
165,258 segments, 242.9 h, 1,528 recordings (1,333 + the 195 from batch `20261001`). No empty texts, no bad times.
Log: `/store/store3/data/manx_speech_corpus/work/logs/asr_collect.log`.

| band | segments | share | hours | displayed text |
|---|---|---|---|---|
| green ≥ 90% | 107,450 | 65.0% | 157.5 | Whisper |
| amber 60–90% | 35,550 | 21.5% | 48.2 | Whisper |
| red < 60% | 22,258 | 13.5% | 37.1 | TDNN (D38) |

Green is far bigger here than on the calibration set (34%), as expected: these segments are at least 2 s long, so there
are fewer hallucination loops. Columns: `recording, segment, start, end, text, text_source, confidence, band, whisper, tdnn`.

## P3b: post-correction by rescoring (Chris, 2026-10-04)
Each segment of up to 30 s gets about 12 candidates:
- `w`: a fresh Whisper 1-best;
- `w0`: the P3 hypothesis;
- the TDNN 10-best, decoded per segment by `asr.py nbest`;
- `pre`: the TDNN's leading words + Whisper, for dropped first words.

Each candidate is scored with teacher-forced Whisper log-prob + KenLM (`best_4g`) + word count + source indicators, as in
Triskelion's `rescore.py`. The weights were fitted on half of the uncontaminated Loayr-v2 test set and checked on the
other half (`asr.py tune`; logs `work/logs/asr_tune_b{1,4}.log`).

**The P3 decode was the weak link.** `infer_cer.py` forces a nonexistent `<|english|>` token and adds no lead-in silence.
`score` decodes as Triskelion's `decode.py` does (`<|en|>` prompt, 0.25 s of lead silence).

| WER, Loayr-v2 test (uncontaminated, 560 + 560) | tune | eval |
|---|---|---|
| Whisper, P3 decode | 28.8 | 41.7 |
| TDNN 1-best | 25.8 | 30.9 |
| P3 band rule (red → TDNN, D38) | 26.9 | 31.5 |
| Whisper, fresh decode, beam 1 | 16.9 | 19.7 |
| Whisper, fresh decode, beam 4 | 16.2 | 19.4 |
| **rescored, beam 1** (chosen) | **15.7** | **19.0** |
| rescored, beam 4 | 15.5 | 19.9 |
| oracle (beam 1 candidates) | 10.6 | 13.5 |

- **Beam 1 was chosen.** Rescored, it is as good as beam 4 (17.2 vs 17.5 pooled) and its calibration decode took 628 s
  against 867 s.
- **Confidence:** Whisper–TDNN agreement (fresh Whisper vs TDNN 1-best) predicts the rescored text's WER far better
  than the rescoring posterior. At ≥ 0.95 agreement the WER is 5.8, against 15.0 at a posterior ≥ 0.95.
- **Bands with the D37 thresholds unchanged.** Chris kept them and dropped D38 (2026-10-04). They replace the P3 table:

  | band | share | rescored WER (was: P3 displayed text) |
  |---|---|---|
  | green ≥ 0.9 | 34% | 7.3 (15.3) |
  | amber 0.6–0.9 | 37% | 18.9 (27.9) |
  | red < 0.6 | 28% | 33.9 (59.0) |
- **Segments over 30 s** (Whisper saw only their first 30 s) are not rescored. They keep the long-form TDNN text, with
  `text_source` `tdnn_longform`.
- **Corpus run.** `asr.py nbest` started 2026-10-04 11:06 (about 8 h, CPU). A watcher (`work/logs/score_watcher.sh`)
  then sets `ALLOWED_GPUS=0,1` and submits `asr.py score segments 1 k/2` for k = 0, 1 (Chris: both GPUs). The estimate is
  about 12 h. Then run `asr.py collect`; the P3 table is kept as `asr/asr_segments.p3.tsv`.

## P3b result: `asr/asr_segments.tsv` (`asr.py collect`, 2026-10-05)
Scored by gpusched jobs 154/155 (165,057 segments). The same 165,258 segments and 242.9 h, now with the rescored text.
Log: `/store/store3/data/manx_speech_corpus/work/logs/asr_collect_p3b.log`. Signed off by Chris (2026-10-05).

| band | segments | share | hours | rescored WER on Loayr test |
|---|---|---|---|---|
| green ≥ 0.9 | 75,100 | 45.4% | 109.1 | 7.3 |
| amber 0.6–0.9 | 60,142 | 36.4% | 83.7 | 18.9 |
| red < 0.6 | 30,016 | 18.2% | 50.1 | 33.9 |

`text_source`: `whisper` 112,278, `tdnn` 39,384, `whisper_p3` 13,278 (the rescoring picked the P3 hypothesis),
`tdnn_longform` 201, `tdnn+whisper` 117.
