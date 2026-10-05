#!/bin/bash
# Monthly update (D36; monthly, Chris 2026-10-05), run by cron on titan on the 1st: new Abbyr Shen Reesht episodes go
# through the whole pipeline (fetch -> inventory -> TDNN -> Whisper -> n-best -> rescoring -> collect -> align -> export)
# and are pushed. Every stage only does what is new, so a quiet month costs minutes. GPU stages queue on gpusched.
# Opens a GitHub issue when it pushes new episodes (what was added) or fails (the log's tail); a quiet month says nothing.
#   crontab: 0 3 1 * * /exp/exp5/acp24csb/manx_speech_corpus/scripts/monthly.sh
set -euo pipefail
export PYTHONUNBUFFERED=1 HF_HOME=/store/store3/data/hf_cache/hub PATH="$HOME/.local/bin:$PATH"
REPO=$(cd "$(dirname "$0")/.." && pwd)
PY=/store/store3/software/bin/anaconda3/envs/speechbrain/bin/python
ASR=/store/store3/data/manx_speech_corpus/asr
GPUSCHED=~/gpu-scheduler/gpusched
FT=/exp/exp3/acp24csb/whisper-ft/ASR/transformer
LOG=/store/store3/data/manx_speech_corpus/work/logs/monthly_$(date -u +%F).log
NEW=$LOG.new  # the episodes downloaded this run
cd "$REPO"
exec > >(tee -a "$LOG") 2>&1
echo "=== monthly update $(date -u +%FT%TZ)"

issue() {  # issue TITLE BODY
    gh issue create -R Manx-forge/manx-speech-corpus --title "$1" --body "$2" --label monthly 2>/dev/null \
        || gh issue create -R Manx-forge/manx-speech-corpus --title "$1" --body "$2"
}
failed() {
    issue "Monthly update failed $(date -u +%F)" "Failed at line $1 of scripts/monthly.sh. Log on titan: $LOG

\`\`\`
$(tail -n 40 "$LOG")
\`\`\`"
}
trap 'failed $LINENO' ERR

gpu() {  # gpu NAME COMMAND: run on a free GPU through gpusched, wait, fail if the job failed
    local id
    id=$($GPUSCHED submit --name "$1" "$2" | sed -n 's/^submitted job \([0-9]*\).*/\1/p')
    echo "gpu: job $id ($1)"
    until [ -f ~/gpu-scheduler/state/done/"$id".json ]; do sleep 60; done
    grep -q '"exit_status": 0' ~/gpu-scheduler/state/done/"$id".json
}

git -c credential.helper='!gh auth git-credential' pull --ff-only  # the link checker's commits
$PY scripts/fetch_podcast.py | tee "$NEW"
$PY scripts/inventory.py
$PY scripts/asr.py tdnn
for csv in "$ASR"/segments_*.csv; do  # P3's Whisper pass (the w0 candidate) over each new batch
    [[ $csv == *.infer_partial.csv || -f ${csv%.csv}.infer_partial.csv ]] && continue
    b=$(basename "$csv" .csv)
    gpu "manx_monthly_$b" "export PYTHONUNBUFFERED=1 HF_HOME=$HF_HOME; cd $FT && mkdir -p $ASR/report_$b && \
        R=results/unfreeze_top12/save && $PY infer_cer.py --csv $csv --wav_root / --ckpt \$R/CKPT+2026-03-21+19-13-49+00 \
        --hub_dir \$R --out_dir $ASR/report_$b --batch 8"
done
$PY scripts/asr.py nbest
gpu manx_monthly_score "export PYTHONUNBUFFERED=1 HF_HOME=$HF_HOME; cd $REPO && $PY scripts/asr.py score segments 1"
$PY scripts/asr.py collect
$PY scripts/align.py asr
$PY scripts/export.py
$PY scripts/export.py check

git add OpenData registers
if git diff --cached --quiet; then
    echo "nothing new"
    exit 0
fi
git commit -qm "Monthly update $(date -u +%F)"
git -c credential.helper='!gh auth git-credential' push -q
echo "pushed $(git rev-parse --short HEAD)"
issue "Monthly update $(date -u +%F)" "New episodes, transcribed (AI), aligned and exported in $(git rev-parse --short HEAD):

$(sed -n 's/^downloaded /- /p' "$NEW")

$(git show --stat --format= HEAD -- OpenData | tail -n 1)"
