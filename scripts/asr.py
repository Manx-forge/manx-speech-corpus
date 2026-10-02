"""P3 ASR: Whisper (unfreeze_top12) over TDNN-segmented audio, with Whisper–TDNN agreement as confidence.

  prepare  write the decode CSVs: asr/segments.csv (every ASR-needed segment, transcript = TDNN LMWT 9 text)
           and asr/calib.csv (Loayr-v2 test segments, transcript = human reference)
  tdnn     for ASR-needed recordings with no TDNN pass yet (new podcast episodes etc.): decode with the p4 TDNN,
           segment the CTM exactly as the original segments were made, cut the wavs, write asr/segments_<batch>.csv
  (GPU)    run whisper-ft's infer_cer.py on calib.csv and each segments_*.csv (commands in reports/P3_asr.md);
           it writes <csv>.infer_partial.csv with hyp and cer
  collect  asr/asr_segments.tsv (one row per segment: times, displayed text, confidence, band, both hypotheses)
           and the calibration table for the green/amber/red bands
"""
import csv
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import jiwer

MR = Path("/store/store3/data/Manx_Resources/datasets")
SEGMENTS = MR / "all_long/segments_unsupervised"   # TDNN LMWT 9 CTM, split at 0.5 s pauses, 2-10 s
TDNN_TEXT = MR / "all_long/text_unsupervised"
SEG_WAVS = MR / "all_utts/16khz/wavs"
CALIB_WAVS = MR / "Loayr-v2/test"
CALIB_REF = MR / "Loayr-v2/test.tsv"
K = Path("/exp/exp5/acp24csb/kaldi/egs/manx-p4-refine_asr/s5")  # read-only: model, graph, extractor, recipe scripts
CALIB_TDNN = K / "exp/chain_nn2/tdnn_1d_sp"
MAKE_SEGMENTS = MR / "all_long/make_segments_unsup.py"  # defaults (0.5 s pause, 2-10 s, 0.2 s pad) made SEGMENTS
WORK = Path("/store/store3/data/manx_speech_corpus/asr")
KWORK = WORK / "kaldi"  # our Kaldi work dir: links to the recipe and model, our own data/ and decode dirs
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


def segment_sources():
    """(segments, text) file pairs: the original TDNN pass plus every batch decoded by tdnn()."""
    return [(SEGMENTS, TDNN_TEXT)] + [(p, p.with_name("text")) for p in sorted(KWORK.glob("data/*/segments_lmwt9"))]


def kaldi(cmd):
    subprocess.run(["bash", "-c", f"export PYTHONPATH=${{PYTHONPATH:-}}; . ./cmd.sh; . ./path.sh; set -euo pipefail; {cmd}"], cwd=KWORK, check=True)


def tdnn(batch=None):
    rec = {r["id"]: r for r in csv.DictReader(open(REPO / "registers/recordings.tsv", encoding="utf-8"), delimiter="\t")
           if not r["transcript"] and r["audio"]}
    done = {l.split()[1] for seg, _ in segment_sources() for l in open(seg)}
    todo = sorted(set(rec) - done)
    if not todo:
        print("tdnn: nothing to decode")
        return
    batch = batch or datetime.now().strftime("%Y%m%d")
    model = KWORK / "exp/tdnn"
    if not model.exists():
        model.mkdir(parents=True)
        for f in ["final.mdl", "frame_subsampling_factor", "tree", "cmvn_opts", "phones.txt"]:
            (model / f).symlink_to(CALIB_TDNN / f)
        for f in ["steps", "utils", "conf", "path.sh", "cmd.sh"]:
            (KWORK / f).symlink_to(K / f)
    data = KWORK / f"data/{batch}"
    data.mkdir(parents=True, exist_ok=True)
    wav16 = WORK / "wav16k"  # Kaldi reads real 16 kHz files: piped ffmpeg output breaks wav-to-duration
    wav16.mkdir(exist_ok=True)
    for r in todo:
        if not (wav16 / f"{r}.wav").exists():
            subprocess.run(["ffmpeg", "-v", "error", "-i", rec[r]["audio"], "-ac", "1", "-ar", "16000",
                            str(wav16 / f"{r}.wav")], check=True)
    with open(data / "wav.scp", "w") as f:
        f.writelines(f"{r} {wav16 / r}.wav\n" for r in todo)
    with open(data / "utt2spk", "w") as f:
        f.writelines(f"{r} {r}\n" for r in todo)
    nj = min(16, len(todo))
    dec = model / f"decode_{batch}"
    ctm = dec / f"score_9/{batch}.ctm"
    print(f"tdnn: decoding {len(todo)} recordings as batch {batch} (nj={nj})", flush=True)
    if not ctm.exists():  # resume: a finished decode is not repeated
        kaldi(f"utils/utt2spk_to_spk2utt.pl data/{batch}/utt2spk > data/{batch}/spk2utt; "
              f"utils/data/get_reco2dur.sh data/{batch}; "
              f"steps/make_mfcc.sh --mfcc-config conf/mfcc_hires.conf --nj {nj} --cmd \"$train_cmd\" data/{batch}; "
              f"steps/compute_cmvn_stats.sh data/{batch}; "
              f"steps/online/nnet2/extract_ivectors_online.sh --cmd \"$train_cmd\" --nj {nj} data/{batch} "
              f"{K}/exp/nnet3_nn2/extractor exp/ivectors_{batch}; "
              f"steps/nnet3/decode.sh --acwt 1.0 --post-decode-acwt 10.0 --skip-scoring true --nj {nj} --cmd \"$decode_cmd\" "
              f"--online-ivector-dir exp/ivectors_{batch} {CALIB_TDNN}/graph_tdnn data/{batch} {dec}; "
              f"steps/get_ctm.sh --cmd \"$decode_cmd\" --frame-shift 0.03 --min-lmwt 9 --max-lmwt 9 "
              f"data/{batch} {CALIB_TDNN}/graph_tdnn {dec}")
    subprocess.run([sys.executable, str(MAKE_SEGMENTS), str(ctm), str(data / "segments_lmwt9"),
                    str(data / "text"), "--reco2dur", str(data / "reco2dur")], check=True)
    text = dict(l.rstrip("\n").split(" ", 1) for l in open(data / "text", encoding="utf-8") if " " in l)
    rows = []
    for line in open(data / "segments_lmwt9"):
        seg, r, start, end = line.split()
        wav = WORK / "wavs" / r / f"{seg}.wav"
        if not wav.exists():
            wav.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["ffmpeg", "-v", "error", "-ss", start, "-to", end, "-i", rec[r]["audio"],
                            "-ac", "1", "-ar", "16000", str(wav)], check=True)
        rows.append((str(wav), lower(text.get(seg, ""))))
    write_csv(WORK / f"segments_{batch}.csv", rows)
    print(f"segments_{batch}.csv: {len(rows)} segments from {len({Path(p).parent.name for p, _ in rows})} of {len(todo)} recordings")


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


GREEN, RED = 0.9, 0.6  # agreement bands, signed off by Chris 2026-10-01 (D37)


def collect(green=GREEN, red=RED):
    tdnn = calib_tdnn()
    cal = [r for r in csv.DictReader(open(WORK / "calib.infer_partial.csv", encoding="utf-8"))]
    pts = []
    for r in cal:
        u = Path(r["path"]).stem
        if u in tdnn and r["transcript"]:
            conf = 1 - min(1.0, jiwer.cer(tdnn[u] or "-", r["hyp"] or "-"))
            pts.append((conf, r["transcript"], r["hyp"], tdnn[u] or "-"))
    print(f"calibration on {len(pts)} Loayr-v2 test segments: Whisper WER by Whisper–TDNN agreement")
    print("agreement >= | segments | Whisper WER (pooled)")
    for lo in (0.95, 0.9, 0.85, 0.8, 0.7, 0.6, 0.5, 0.0):
        sel = [p for p in pts if p[0] >= lo]
        print(f"  {lo:.2f}  | {len(sel):5d} | {100 * jiwer.wer([p[1] for p in sel], [p[2] for p in sel]):5.1f}")
    for b in ("green", "amber", "red"):
        sel = [p for p in pts if band(p[0], green, red) == b]
        shown = [p[3] if b == "red" else p[2] for p in sel]
        print(f"  {b:5s}: {len(sel):5d} segments, displayed-text WER {100 * jiwer.wer([p[1] for p in sel], shown):.1f}")

    times = {l.split()[0]: l.split()[1:] for seg, _ in segment_sources() for l in open(seg)}
    with open(WORK / "asr_segments.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["recording", "segment", "start", "end", "text", "text_source", "confidence", "band", "whisper", "tdnn"])
        n = 0
        shards = sorted(WORK.glob("segments_*.infer_partial.csv"))  # segments.csv was split in two, one per GPU
        for r in (r for sh in shards for r in csv.DictReader(open(sh, encoding="utf-8"))):
            seg = Path(r["path"]).stem
            rec, start, end = times[seg]
            conf = 1 - min(1.0, float(r["cer"]))
            b = band(conf, green, red)  # red: Whisper is mostly hallucinating, TDNN is far better (D38)
            text, src = (r["transcript"], "tdnn") if b == "red" else (r["hyp"], "whisper")
            w.writerow([rec, seg, start, end, text, src, round(100 * conf), b, r["hyp"], r["transcript"]])
            n += 1
    print(f"asr_segments.tsv: {n} segments")


if __name__ == "__main__":
    {"prepare": prepare, "tdnn": tdnn, "collect": collect}[sys.argv[1]](*sys.argv[2:])
