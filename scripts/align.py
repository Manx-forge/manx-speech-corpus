"""P4 alignment: word timestamps for every transcript with timestamper (p2 chain TDNN-F, grapheme lexicon), read-only.

  human [P] [limit]  human transcripts (D21). Recordings of 30 s or more go through timestamp.sh (biased-LM
                     segmentation, forced alignment, gap fill), P at a time; shorter clips are force-aligned whole, all in
                     one Kaldi run. Resumes: a recording with outputs is not redone.
  asr [limit]        ASR text (asr/asr_segments.tsv), force-aligned per segment inside its own span (D19)
  qc                 aligned / unaligned word and aligned / interpolated phrase rates per source
Outputs: align/{human,asr}/<id>/<id>_{words,phrases}.csv in timestamper's format (index, start_sec, end_sec, text, status),
times absolute in the recording.
"""
import csv
import re
import collections
import subprocess
import sys
import wave
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TS = Path("/exp/exp5/acp24csb/timestamper")
sys.path.insert(0, str(TS / "local"))
from ctm_match import load_unspellable, match_ctm_to_tokens  # noqa: E402
from ctm_to_outputs import write_outputs  # noqa: E402
from normalise_text import normalise_token, split_phrases  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
ALIGN = Path("/store/store3/data/manx_speech_corpus/align")
MODEL = TS / "model"
LONG = 30.0  # seconds: from here on timestamp.sh finds the phrases itself


def recordings():
    return list(csv.DictReader(open(REPO / "registers/recordings.tsv", encoding="utf-8"), delimiter="\t"))


def transcript(r):
    """The human transcript as plain text, one phrase per line, control characters dropped (a NUL breaks the csv
    writer; form feeds become line breaks)."""
    t = r["transcript"]
    if t == "tsv:sentence":  # Common Voice: inventory.py keeps the sentence as the title
        text = r["title"]
    elif t.endswith("document.csv"):  # manx-search-data work: one subtitle per row
        text = "\n".join(row["Manx"] for row in csv.DictReader(open(t, encoding="utf-8-sig")))
    else:
        text = open(t, encoding="utf-8", errors="replace").read().replace("﻿", "")
    return re.sub(r"[\x00-\x08\x0b\x0e-\x1f\x7f]", "", text.replace("\x0c", "\n"))


def human_rows():
    """Recordings with a human transcript and audio, minus duplicates of another recording (and the second row of an id
    that is on disk twice)."""
    rows = {}
    for r in recordings():
        if r["transcript"] and r["audio"] and not (r["dup_of"] and not r["dup_of"].startswith("disk:")):
            rows.setdefault(r["id"], r)
    return list(rows.values())


def done(out, rid):
    return all((out / rid / f"{rid}_{k}.csv").exists() for k in ("words", "phrases"))


def timestamp(r, out):
    """One long recording through timestamp.sh. Its output stem is the audio's basename after resolving links, so it
    gets a 16 kHz copy named <id>.wav."""
    d = out / r["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "transcript.txt").write_text(transcript(r), encoding="utf-8")
    audio = ALIGN / "wav16k" / f"{r['id']}.wav"
    nj = min(4, max(1, int(wav16(r["audio"], audio) // 40)))  # Kaldi will not split fewer 30 s chunks than jobs
    with open(d / "timestamp.log", "w") as log:
        rc = subprocess.run(["bash", str(TS / "timestamp.sh"), "--formats", "csv", "--nj", str(nj), str(audio),
                             str(d / "transcript.txt"), str(d)], stdout=log, stderr=subprocess.STDOUT).returncode
    print(f"  {r['id']}: {'ok' if rc == 0 else f'FAILED ({rc}), see {d}/timestamp.log'}", flush=True)


def wav16(src, dst):
    """Kaldi reads real 16 kHz mono files (piped ffmpeg output breaks the duration scripts)."""
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", src, "-ac", "1", "-ar", "16000", str(dst)], check=True)
    with wave.open(str(dst)) as w:
        return w.getnframes() / w.getframerate()


def kaldi(cmd, cwd):
    subprocess.run(["bash", "-c", f". ./path.sh; set -euo pipefail; {cmd}"], cwd=cwd, check=True)


def spans(units, name, out, nj=32):
    """Force-align each unit's text inside its own audio, all units in one Kaldi run.

    units: (recording, unit id, 16 kHz wav, offset of the wav in the recording, duration, text). Writes one words/phrases
    pair per recording; unaligned words keep no time, phrases with no aligned word are interpolated inside their unit."""
    work = ALIGN / "work" / f"{name}_{datetime.now():%Y%m%d%H%M%S}"  # a fresh Kaldi dir per run: no stale splits
    data = work / "data"
    data.mkdir(parents=True, exist_ok=True)
    for f in ["steps", "utils", "path.sh"]:
        if not (work / f).exists():
            (work / f).symlink_to(TS / f)
    toks = {}
    for rec, uid, wav, off, dur, text in units:
        toks[uid] = [(pid, normalise_token(o), o) for pid, p in enumerate(split_phrases(text)) for o in p.split()]
    keep = sorted(u for u in toks if any(n for _, n, _ in toks[u]))
    wavs = {u[1]: u[2] for u in units}
    (work / "text").write_text("".join(f"{u} {' '.join(n for _, n, _ in toks[u] if n)}\n" for u in keep), encoding="utf-8")
    (data / "text").write_text((work / "text").read_text(encoding="utf-8"), encoding="utf-8")
    (data / "wav.scp").write_text("".join(f"{u} {wavs[u]}\n" for u in keep))
    (data / "utt2spk").write_text("".join(f"{u} {u}\n" for u in keep))
    nj = min(nj, len(keep))
    print(f"{name}: aligning {len(keep)} units (nj={nj})", flush=True)
    kaldi(f"python3 {TS}/local/make_run_dict.py {MODEL}/dict text dict; "
          f"utils/prepare_lang.sh --share-silence-phones true --phone-symbol-table {MODEL}/phones.txt dict '<UNK>' lang_tmp lang; "
          f"cp {MODEL}/topo lang/topo; "
          f"utils/utt2spk_to_spk2utt.pl data/utt2spk > data/spk2utt; utils/fix_data_dir.sh data; "
          f"steps/make_mfcc.sh --mfcc-config {MODEL}/conf/mfcc_hires.conf --nj {nj} --cmd run.pl data; "
          f"steps/compute_cmvn_stats.sh data; utils/fix_data_dir.sh data; "
          f"steps/online/nnet2/extract_ivectors_online.sh --cmd run.pl --nj {nj} data {MODEL}/extractor ivectors; "
          f"steps/nnet3/align.sh --cmd run.pl --nj {nj} --use-gpu false "
          f"--scale-opts '--transition-scale=1.0 --acoustic-scale=1.0 --self-loop-scale=1.0' --beam 10 --retry-beam 60 "
          f"--frames-per-chunk 150 --online-ivector-dir ivectors data lang {MODEL}/am ali; "
          f"steps/get_train_ctm.sh --cmd run.pl --frame-shift 0.03 data lang ali ali", work)
    ctm = collections.defaultdict(list)
    for l in open(work / "ali/ctm", encoding="utf-8"):
        u, _, beg, d, w = l.split()[:5]
        ctm[u].append((float(beg), float(beg) + float(d), w))
    unspellable = load_unspellable(work / "dict/oov_unspellable.txt")
    by_rec = collections.defaultdict(list)
    for u in units:
        by_rec[u[0]].append(u)
    for rec, us in by_rec.items():
        words, phrases = [], []
        for _, uid, _, off, dur, text in sorted(us, key=lambda u: u[3]):
            tokens = [dict(pid=p, norm=n, orig=o, start=None, end=None) for p, n, o in toks[uid]]
            match_ctm_to_tokens(sorted(ctm.get(uid, [])), tokens, unspellable)
            for t in tokens:
                words.append((t["start"] + off if t["start"] is not None else None,
                              t["end"] + off if t["end"] is not None else None, t["orig"],
                              "aligned" if t["start"] is not None else "unaligned"))
            ps = split_phrases(text)
            rows = []
            for pid, p in enumerate(ps):
                mem = [t for t in tokens if t["pid"] == pid and t["start"] is not None]
                rows.append([min(t["start"] for t in mem) + off, max(t["end"] for t in mem) + off, p, "aligned"] if mem
                            else [None, None, p, "interpolated"])
            i = 0
            while i < len(rows):  # spread phrases with no aligned word between their neighbours, inside the unit
                if rows[i][0] is not None:
                    i += 1
                    continue
                j = i
                while j < len(rows) and rows[j][0] is None:
                    j += 1
                lo = rows[i - 1][1] if i else off
                hi = max(lo, rows[j][0] if j < len(rows) else off + dur)
                for k in range(i, j):
                    rows[k][0], rows[k][1] = lo + (k - i) * (hi - lo) / (j - i), lo + (k - i + 1) * (hi - lo) / (j - i)
                i = j
            phrases += [tuple(r) for r in rows]
        d = out / rec
        d.mkdir(parents=True, exist_ok=True)
        write_outputs(phrases, f"{rec}_phrases", ["csv"], d)
        write_outputs(words, f"{rec}_words", ["csv"], d)  # written last: its presence marks the recording done
    print(f"{name}: wrote {len(by_rec)} recordings to {out}", flush=True)


def human(parallel=8, limit=None):
    out = ALIGN / "human"
    rows = [r for r in human_rows() if not done(out, r["id"])][:int(limit) if limit else None]
    short = [r for r in rows if float(r["duration_s"] or 0) < LONG]
    long_ = sorted((r for r in rows if float(r["duration_s"] or 0) >= LONG), key=lambda r: -float(r["duration_s"]))
    print(f"human: {len(short)} short clips, {len(long_)} long recordings to align", flush=True)
    if short:
        with ThreadPoolExecutor(16) as ex:
            durs = list(ex.map(lambda r: wav16(r["audio"], ALIGN / "wav16k" / f"{r['id']}.wav"), short))
        units = [(r["id"], r["id"], ALIGN / "wav16k" / f"{r['id']}.wav", 0.0, d, transcript(r)) for r, d in zip(short, durs)]
        spans(units, "human_short", out)
    with ThreadPoolExecutor(int(parallel)) as ex:  # longest first, so the pool finishes evenly
        list(ex.map(lambda r: timestamp(r, out), long_))
    print(f"human: {sum(done(out, r['id']) for r in human_rows())} of {len(human_rows())} recordings aligned")


def asr(limit=None):
    work = Path("/store/store3/data/manx_speech_corpus/asr")
    wav = {Path(r["path"]).stem: r["path"] for sh in sorted(work.glob("segments_*.infer_partial.csv"))
           for r in csv.DictReader(open(sh, encoding="utf-8"))}
    out = ALIGN / "asr"
    segs = [r for r in csv.DictReader(open(work / "asr_segments.tsv", encoding="utf-8"), delimiter="\t")
            if not done(out, r["recording"])]
    recs = sorted({r["recording"] for r in segs})[:int(limit) if limit else None]
    keep = set(recs)
    units = [(r["recording"], r["segment"], wav[r["segment"]], float(r["start"]), float(r["end"]) - float(r["start"]), r["text"])
             for r in segs if r["recording"] in keep]
    print(f"asr: {len(units)} segments from {len(recs)} recordings to align", flush=True)
    if units:
        spans(units, "asr", out)


def qc():
    src = {r["id"]: r["source"] for r in recordings()}
    for kind in ["human", "asr"]:
        root = ALIGN / kind
        if not root.exists():
            continue
        words, phrases, recs = (collections.defaultdict(collections.Counter) for _ in range(3))
        for f in root.glob("*/*_words.csv"):
            rec = f.name.removesuffix("_words.csv")
            s = src.get(rec, "?")
            recs[s]["n"] += 1
            words[s].update(r["status"] for r in csv.DictReader(open(f, encoding="utf-8")))
            p = f.with_name(f"{rec}_phrases.csv")
            if p.exists():
                phrases[s].update(r["status"] for r in csv.DictReader(open(p, encoding="utf-8")))
        print(f"\n{kind}: source | recordings | words | aligned % | phrases | interpolated %")
        for s in sorted(recs):
            w, p = words[s], phrases[s]
            print(f"  {s:13s} | {recs[s]['n']:6d} | {sum(w.values()):8d} | {100 * w['aligned'] / max(1, sum(w.values())):5.1f} "
                  f"| {sum(p.values()):7d} | {100 * p['interpolated'] / max(1, sum(p.values())):5.1f}")


if __name__ == "__main__":
    {"human": human, "asr": asr, "qc": qc}[sys.argv[1]](*sys.argv[2:])
