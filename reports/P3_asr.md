# P3 ASR and confidence (in progress: GPU decode running)

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
- **Segments**: running as gpusched jobs **145** (GPU 0, `segments_0.csv`) and **146** (GPU 1, `segments_1.csv`).
  `segments.csv` was split in half so both GPUs work at once. Together they decode about 2.6 segments/s, so they should
  finish around **2026-10-02 04:30 UTC**.
- **Progress:** `cat /store/store3/data/manx_speech_corpus/asr/segments_*.infer_partial.csv | wc -l` (target 149,790).
  Logs: `gpusched logs 145` and `gpusched logs 146`.
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
  14 others). Running in the background; log at `/store/store3/data/manx_speech_corpus/work/logs/tdnn_20261001.log`.

## Still to do in P3
1. A Whisper run on `segments_20261001.csv` once the TDNN batch is done (same command, one job).
2. `python scripts/asr.py collect` once all decodes finish, which writes `asr/asr_segments.tsv`.
