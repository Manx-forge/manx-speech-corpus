# P3 ASR and confidence (in progress)

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

## GPU run (Chris launches)
`whisper-ft/.../infer_cer.py` (the script that produced the original agreement CSV) runs unchanged with the
`unfreeze_top12` checkpoint: large-v3, fp16, beam 4, `<|english|>` token as in training. It decodes the calibration set
first (about 2 min), then all segments. It resumes if interrupted; resubmit the same command.

```bash
gpusched submit --name manx_asr "export PYTHONUNBUFFERED=1 HF_HOME=/store/store3/data/hf_cache/hub; \
cd /exp/exp3/acp24csb/whisper-ft/ASR/transformer && R=results/unfreeze_top12/save && \
for c in calib segments; do /store/store3/software/bin/anaconda3/envs/speechbrain/bin/python infer_cer.py \
  --csv /store/store3/data/manx_speech_corpus/asr/\$c.csv --wav_root / \
  --ckpt \$R/CKPT+2026-03-21+19-13-49+00 --hub_dir \$R \
  --out_dir /store/store3/data/manx_speech_corpus/asr/report_\$c --batch 16 || exit 1; done"
```
- **Duration:** about 4–8 h for 150k segments (308 h of audio) on one 3090.
- **Healthy log** (`gpusched logs <id>`): "Model ready on cuda:0 (fp16)", then batch progress lines. Progress can also be
  watched with `wc -l /store/store3/data/manx_speech_corpus/asr/segments.infer_partial.csv`.
- **If it fails:** an OOM means rerunning with `--batch 8`. A tokenizer path error means `HF_HOME` is wrong.

## After the run
Run `python scripts/asr.py collect` to print the calibration table, then
`python scripts/asr.py collect <green> <red>` with the proposed cut-offs. Chris signs off the bands.
