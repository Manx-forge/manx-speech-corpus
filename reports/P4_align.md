# P4: alignment

`scripts/align.py`, using timestamper (read-only) with its model. Outputs: `align/{human,asr}/<id>/<id>_{words,phrases}.csv`
under `/store/store3/data/manx_speech_corpus/`. Signed off by Chris (2026-10-05) without a hand-check: alignment quality
is judged in the final result.

## `human`: whole transcripts, long-audio segmentation
10,375 of 10,378 recordings aligned. Short clips go through one Kaldi run; long ones through `timestamp.sh`, with `nj`
scaled to duration (Kaldi will not split fewer 30 s chunks than jobs). Logs: `work/logs/align_human*.log`.

| source | recordings | words | words aligned | phrases | phrases interpolated |
|---|---|---|---|---|---|
| clilstore | 57 | 42,133 | 100.0% | 57 | 0.0% |
| common_voice | 6,302 | 59,257 | 100.0% | 6,990 | 0.0% |
| learn_manx | 3,573 | 75,495 | 94.4% | 9,509 | 7.7% |
| youtube | 443 | 112,550 | 90.8% | 9,078 | 17.7% |

Not aligned (transcript problems, left for later): `msd-YouTube-Skeealyn-Vannin-Disk-1-Track-11` (empty transcript),
`04235` (6 words in 33 s) and `04230` (14 words in 32 s), too short for the long-audio segmenter.

The first run named the 11 YouTube corpus works by video ID. Those stale files remain inside `align/human/msd-*/`; `qc`
and the exports read only `<id>/<id>_words.csv`.

## `asr`: each segment aligned inside its own span (D19)
All 1,528 recordings (165,257 segments) in one Kaldi run, nj 32, about 1 h. Log: `work/logs/align_asr.log`.

| source | recordings | words | words aligned | phrases | phrases interpolated |
|---|---|---|---|---|---|
| common_voice | 129 | 4,088 | 100.0% | 472 | 0.0% |
| learn_manx | 760 | 380,061 | 99.9% | 44,466 | 0.0% |
| manx_radio | 368 | 1,219,817 | 100.0% | 105,155 | 0.0% |
| saysomething | 29 | 37,499 | 100.0% | 5,529 | 0.0% |
| youtube | 242 | 88,782 | 99.4% | 9,635 | 0.1% |
