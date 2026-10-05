#!/bin/bash
# Weekly update (D36), run by cron on titan on Mondays: new Abbyr Shen Reesht episodes go through the whole pipeline
# (fetch -> inventory -> TDNN -> Whisper -> n-best -> rescoring -> collect -> align -> export) and are pushed.
# Every stage only does what is new, so a week without an episode costs minutes. GPU stages queue on gpusched.
#   crontab: 0 3 * * 1 /exp/exp5/acp24csb/manx_speech_corpus/scripts/weekly.sh >> /store/store3/data/manx_speech_corpus/work/logs/weekly.log 2>&1
set -euo pipefail
export PYTHONUNBUFFERED=1 HF_HOME=/store/store3/data/hf_cache/hub PATH="$HOME/.local/bin:$PATH"
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=/store/store3/software/bin/anaconda3/envs/speechbrain/bin/python
ASR=/store/store3/data/manx_speech_corpus/asr
GPUSCHED=~/gpu-scheduler/gpusched
FT=/exp/exp3/acp24csb/whisper-ft/ASR/transformer
cd "$REPO"
echo "=== weekly update $(date -u +%FT%TZ)"

gpu() {  # gpu NAME COMMAND: run on a free GPU through gpusched, wait, fail if the job failed
    local id
    id=$($GPUSCHED submit --name "$1" "$2" | sed -n 's/^submitted job \([0-9]*\).*/\1/p')
    echo "gpu: job $id ($1)"
    until [ -f ~/gpu-scheduler/state/done/"$id".json ]; do sleep 60; done
    grep -q '"exit_status": 0' ~/gpu-scheduler/state/done/"$id".json
}

git -c credential.helper='!gh auth git-credential' pull --ff-only  # the link checker's commits
$PY scripts/fetch_podcast.py
$PY scripts/inventory.py
$PY scripts/asr.py tdnn
for csv in "$ASR"/segments_*.csv; do  # P3's Whisper pass (the w0 candidate) over each new batch
    [[ $csv == *.infer_partial.csv || -f ${csv%.csv}.infer_partial.csv ]] && continue
    b=$(basename "$csv" .csv)
    gpu "manx_weekly_$b" "export PYTHONUNBUFFERED=1 HF_HOME=$HF_HOME; cd $FT && mkdir -p $ASR/report_$b && R=results/unfreeze_top12/save && $PY infer_cer.py \
        --csv $csv --wav_root / --ckpt \$R/CKPT+2026-03-21+19-13-49+00 --hub_dir \$R --out_dir $ASR/report_$b --batch 8"
done
$PY scripts/asr.py nbest
gpu manx_weekly_score "export PYTHONUNBUFFERED=1 HF_HOME=$HF_HOME; cd $REPO && $PY scripts/asr.py score segments 1"
$PY scripts/asr.py collect
$PY scripts/align.py asr
$PY scripts/export.py
$PY scripts/export.py check

git add OpenData registers
if git diff --cached --quiet; then
    echo "nothing new"
    exit 0
fi
git commit -qm "Weekly update $(date -u +%F)"
git -c credential.helper='!gh auth git-credential' push -q
echo "pushed $(git rev-parse --short HEAD)"
