"""P3 ASR: Whisper (unfreeze_top12) over TDNN-segmented audio, with Whisper–TDNN agreement as confidence.

  prepare  write the decode CSVs: asr/segments.csv (every ASR-needed segment, transcript = TDNN LMWT 9 text)
           and asr/calib.csv (Loayr-v2 test segments, transcript = human reference)
  (GPU)    run whisper-ft's infer_cer.py on calib.csv and on segments_{0,1}.csv (segments.csv halved, one per GPU) (commands in reports/P3_asr.md); it writes
           <csv>.infer_partial.csv with hyp and cer
  collect  asr/asr_segments.tsv (one row per segment with times, both texts and confidence)
           and the calibration table for the green/amber/red bands
"""
import csv
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import jiwer

MR = Path("/store/store3/data/Manx_Resources/datasets")
SEGMENTS = MR / "all_long/segments_unsupervised"   # TDNN LMWT 9 CTM, split at 0.5 s pauses, 2-10 s
TDNN_TEXT = MR / "all_long/text_unsupervised"
SEG_WAVS = MR / "all_utts/16khz/wavs"
CALIB_WAVS = MR / "Loayr-v2/test"
CALIB_REF = MR / "Loayr-v2/test.tsv"
CALIB_TDNN = Path("/exp/exp5/acp24csb/kaldi/egs/manx-p4-refine_asr/s5/exp/chain_nn2/tdnn_1d_sp")
WORK = Path("/store/store3/data/manx_speech_corpus/asr")
REPO = Path(__file__).resolve().parents[1]


def lower(t):
    return " ".join(t.lower().split())


def prepare():
    need = {r["id"]: r["audio"] for r in csv.DictReader(open(REPO / "registers/recordings.tsv", encoding="utf-8"), delimiter="\t")
            if not r["transcript"] and r["audio"]}
    text = dict(l.rstrip("\n").split(" ", 1) for l in open(TDNN_TEXT, encoding="utf-8") if " " in l)
    WORK.mkdir(parents=True, exist_ok=True)
    rows, cut = [], 0
    for line in open(SEGMENTS):
        seg, rec, start, end = line.split()
        if rec not in need or seg not in text:
            continue
        wav = SEG_WAVS / rec / f"{seg}.wav"
        if not wav.exists():  # a few recordings were never cut into all_utts; cut them from the long-form file
            wav = WORK / "wavs" / rec / f"{seg}.wav"
            if not wav.exists():
                wav.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["ffmpeg", "-v", "error", "-ss", start, "-to", end, "-i", need[rec],
                                "-ac", "1", "-ar", "16000", str(wav)], check=True)
                cut += 1
        rows.append((str(wav), lower(text[seg])))
    write_csv(WORK / "segments.csv", rows)
    print(f"segments.csv: {len(rows)} segments from {len({Path(p).parent.name for p, _ in rows})} recordings ({cut} cut)")

    ref = {Path(r["path"]).stem: lower(r["sentence"]) for r in csv.DictReader(open(CALIB_REF, encoding="utf-8"), delimiter="\t")}
    calib = [(str(CALIB_WAVS / u.rsplit("-", 1)[0] / u.rsplit("-", 1)[0] / f"{u}.wav"), t) for u, t in sorted(ref.items())]
    write_csv(WORK / "calib.csv", calib)
    print(f"calib.csv: {len(calib)} segments")


def write_csv(path, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "transcript"])
        w.writerows(rows)


def calib_tdnn():
    """Loayr-v2 test TDNN hypotheses at LMWT 9 (best dev WER), keyed like the wav stems."""
    words = dict(l.split()[::-1] for l in open(CALIB_TDNN / "graph_tdnn/words.txt", encoding="utf-8"))
    out = {}
    for tra in sorted(CALIB_TDNN.glob("decode_test_split*/scoring/9.0.0.tra")):
        for l in open(tra):
            utt, *ids = l.split()
            out[re.sub(r"^lbi-", "", utt)] = lower(" ".join(words[i] for i in ids))
    return out


def band(conf, green, red):
    return "green" if conf >= green else "red" if conf < red else "amber"


def collect(green=None, red=None):
    tdnn = calib_tdnn()
    cal = [r for r in csv.DictReader(open(WORK / "calib.infer_partial.csv", encoding="utf-8"))]
    pts = []
    for r in cal:
        u = Path(r["path"]).stem
        if u in tdnn and r["transcript"]:
            conf = 1 - min(1.0, jiwer.cer(tdnn[u] or "-", r["hyp"] or "-"))
            pts.append((conf, r["transcript"], r["hyp"]))
    print(f"calibration on {len(pts)} Loayr-v2 test segments: Whisper WER by Whisper–TDNN agreement")
    print("agreement >= | segments | Whisper WER (pooled)")
    for lo in (0.95, 0.9, 0.85, 0.8, 0.7, 0.6, 0.5, 0.0):
        sel = [p for p in pts if p[0] >= lo]
        print(f"  {lo:.2f}  | {len(sel):5d} | {100 * jiwer.wer([p[1] for p in sel], [p[2] for p in sel]):5.1f}")
    if green is not None:
        for b in ("green", "amber", "red"):
            sel = [p for p in pts if band(p[0], green, red) == b]
            if sel:
                print(f"  {b:5s}: {len(sel):5d} segments, WER {100 * jiwer.wer([p[1] for p in sel], [p[2] for p in sel]):.1f}")

    times = {l.split()[0]: l.split()[1:] for l in open(SEGMENTS)}
    with open(WORK / "asr_segments.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["recording", "segment", "start", "end", "whisper", "tdnn", "confidence"])
        n = 0
        shards = sorted(WORK.glob("segments_*.infer_partial.csv"))  # segments.csv was split in two, one per GPU
        for r in (r for sh in shards for r in csv.DictReader(open(sh, encoding="utf-8"))):
            seg = Path(r["path"]).stem
            rec, start, end = times[seg]
            w.writerow([rec, seg, start, end, r["hyp"], r["transcript"], round(100 * (1 - min(1.0, float(r["cer"]))))])
            n += 1
    print(f"asr_segments.tsv: {n} segments")


if __name__ == "__main__":
    {"prepare": prepare, "collect": lambda: collect(*map(float, sys.argv[2:4])) if len(sys.argv) > 3 else collect()}[sys.argv[1]]()
