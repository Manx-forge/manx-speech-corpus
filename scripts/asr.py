"""P3 ASR: Whisper (unfreeze_top12) over TDNN-segmented audio, with Whisper–TDNN agreement as confidence, and P3b
post-correction: each segment's candidates rescored with Whisper log-prob + KenLM (as Triskelion).

  prepare  write the decode CSVs: asr/segments.csv (every ASR-needed segment, transcript = TDNN LMWT 9 text)
           and asr/calib.csv (Loayr-v2 test segments, transcript = human reference)
  tdnn     for ASR-needed recordings with no TDNN pass yet (new podcast episodes etc.): decode with the p4 TDNN,
           segment the CTM exactly as the original segments were made, cut the wavs, write asr/segments_<batch>.csv
  (GPU)    run whisper-ft's infer_cer.py on calib.csv and each segments_*.csv (commands in reports/P3_asr.md);
           it writes <csv>.infer_partial.csv with hyp and cer
  nbest    per-segment TDNN 10-best (asr/tdnn_nbest.tsv; Loayr-v2 test: asr/calib_nbest.tsv), segments up to 30 s
  score    (GPU) fresh Whisper 1-best + teacher-forced log-prob of every candidate: asr/<calib|segments>.b<beam>*.score.jsonl
  tune     fit the rescoring weights on Loayr-v2 test (asr/weights.json), compare with each system and the oracle
  collect  asr/asr_segments.tsv (one row per segment: times, rescored text, its source, confidence, band, Whisper and
           TDNN 1-best) and the calibration table for the green/amber/red bands
"""
import collections
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


def lattice_nbest(lats, out):
    """Append (seg, rank, text) rows for the LMWT 9 10-best of every lattice in `lats` (glob, Kaldi cwd) to `out`."""
    words = CALIB_TDNN / "graph_tdnn/words.txt"
    raw = out.with_suffix(".raw")
    kaldi(f"gunzip -c {lats} | lattice-scale --inv-acoustic-scale=9 ark:- ark:- | lattice-to-nbest --n=10 ark:- ark:- "
          f"2>/dev/null | nbest-to-linear ark:- ark:/dev/null ark,t:- 2>/dev/null | utils/int2sym.pl -f 2- {words} > {raw}")
    new = not out.exists()
    with open(out, "a", encoding="utf-8") as f:
        if new:
            f.write("seg\trank\ttext\n")
        for l in open(raw, encoding="utf-8"):
            key, _, text = l.partition(" ")
            seg, rank = re.sub(r"^lbi-", "", key).rsplit("-", 1)
            f.write(f"{seg}\t{rank}\t{lower(text)}\n")
    raw.unlink()


def nbest(limit=None):
    """Per-segment TDNN 10-best (the long-form lattices cannot give one): decode every Whisper-decoded segment wav not
    yet in asr/tdnn_nbest.tsv. The Loayr-v2 test lattices already exist, so calib_nbest.tsv comes straight from them."""
    if not (WORK / "calib_nbest.tsv").exists():
        lattice_nbest(" ".join(f"{d}/lat.*.gz" for d in sorted(CALIB_TDNN.glob("decode_test_split*"))), WORK / "calib_nbest.tsv")
    out = WORK / "tdnn_nbest.tsv"
    done = {l.split("\t", 1)[0] for l in open(out, encoding="utf-8")} if out.exists() else set()
    segs = {Path(r["path"]).stem: r["path"] for sh in sorted(WORK.glob("segments_*.infer_partial.csv"))
            for r in csv.DictReader(open(sh, encoding="utf-8"))}
    span = {l.split()[0]: l.split()[2:4] for seg, _ in segment_sources() for l in open(seg)}
    # over 30 s Whisper saw only the first 30 s (they keep the TDNN text), and the lattice decode of 100-250 s
    # segments takes far longer than everything else
    todo = sorted(s for s in set(segs) - done if float(span[s][1]) - float(span[s][0]) <= 30)[:int(limit) if limit else None]
    if not todo:
        print("nbest: nothing to decode")
        return
    batch = f"nbest_{datetime.now():%Y%m%d%H%M}"
    data, dec = KWORK / f"data/{batch}", KWORK / f"exp/tdnn/decode_{batch}"
    data.mkdir(parents=True)
    (data / "wav.scp").write_text("".join(f"{s} {segs[s]}\n" for s in todo))
    (data / "utt2spk").write_text("".join(f"{s} {s}\n" for s in todo))
    nj = min(32, len(todo))
    print(f"nbest: decoding {len(todo)} segments as {batch} (nj={nj})", flush=True)
    kaldi(f"utils/utt2spk_to_spk2utt.pl data/{batch}/utt2spk > data/{batch}/spk2utt; "
          f"steps/make_mfcc.sh --mfcc-config conf/mfcc_hires.conf --nj {nj} --cmd \"$train_cmd\" data/{batch}; "
          f"steps/compute_cmvn_stats.sh data/{batch}; "
          f"steps/online/nnet2/extract_ivectors_online.sh --cmd \"$train_cmd\" --nj {nj} data/{batch} "
          f"{K}/exp/nnet3_nn2/extractor exp/ivectors_{batch}; "
          f"steps/nnet3/decode.sh --acwt 1.0 --post-decode-acwt 10.0 --skip-scoring true --nj {nj} --cmd \"$decode_cmd\" "
          f"--online-ivector-dir exp/ivectors_{batch} {CALIB_TDNN}/graph_tdnn data/{batch} {dec}")
    lattice_nbest(f"{dec}/lat.*.gz", out)
    got = {l.split("\t", 1)[0] for l in open(out, encoding="utf-8")}
    print(f"nbest: {len(got & set(todo))} of {len(todo)} segments have an n-best in {out}")


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


FT = Path("/exp/exp3/acp24csb/whisper-ft/ASR/transformer/results/unfreeze_top12/save")  # read-only
LM = "/exp/exp5/acp24csb/language_modelling/exp/best_lms/final/best_4g.arpa.gz"
WTRAIN = Path("/exp/exp3/acp24csb/whisper-ft/ASR/transformer/results/cer_cutoff/data/train_cer0.5_verified.csv")


def candidates(name):
    """seg -> (wav, {text: [sources]}): the P3 Whisper hypothesis (w0) and the TDNN 10-best (tdnn = rank 1, tdnnK)."""
    shards = [WORK / "calib.infer_partial.csv"] if name == "calib" else sorted(WORK.glob("segments_*.infer_partial.csv"))
    kbest = collections.defaultdict(list)
    for r in csv.DictReader(open(WORK / ("calib_nbest.tsv" if name == "calib" else "tdnn_nbest.tsv"), encoding="utf-8"),
                            delimiter="\t"):
        kbest[r["seg"]].append((int(r["rank"]), r["text"]))
    out = {}
    for sh in shards:
        for r in csv.DictReader(open(sh, encoding="utf-8")):
            seg = Path(r["path"]).stem
            if seg not in kbest:  # over 30 s, or not decoded yet
                continue
            c = collections.defaultdict(list)
            c[lower(r["hyp"])].append("w0")
            for k, t in sorted(kbest[seg]):
                c[t].append("tdnn" if k == 1 else f"tdnn{k}")
            out[seg] = (r["path"], dict(c))
    return out


def score(name, beam=4, shard="0/1", batch=16, limit=None):
    """GPU, as Triskelion's decode.py (unfreeze_top12, 0.25 s lead of silence, <|en|> prompt): a fresh Whisper 1-best (w,
    beam search; none if beam is 0) and the teacher-forced log-prob of every candidate, plus pre (the TDNN's leading words
    + the Whisper hypothesis, when Whisper drops the first word: pseudo-label edge words). P3's infer_cer.py decode
    (w0) used a nonexistent prompt token and no lead, and is far worse. shard k/n takes every n-th segment, one job per GPU.
    Writes asr/<name>.b<beam>[.<k>of<n>].score.jsonl, resumable."""
    import json
    import torch
    import torchaudio
    from transformers import GenerationMixin, WhisperFeatureExtractor, WhisperForConditionalGeneration, WhisperTokenizer
    base = next((FT / "whisper_checkpoint/models--openai--whisper-large-v3/snapshots").iterdir())
    tokdir = next(Path("/store/store3/data/hf_cache/hub/models--openai--whisper-large-v3/snapshots").iterdir())
    beam = int(beam)
    k, n = map(int, shard.split("/"))
    out = WORK / f"{name}.b{beam}{f'.{k}of{n}' if n > 1 else ''}.score.jsonl"
    # done by any shard: a later run (the monthly job, one shard) must not redo the corpus run's two
    done = {json.loads(l)["seg"] for f in WORK.glob(f"{name}.b{beam}*.score.jsonl") for l in open(f, encoding="utf-8")}
    cands = candidates(name)
    rows = [s for i, s in enumerate(sorted(cands)) if i % n == k and s not in done][:int(limit) if limit else None]
    if not rows:
        print(f"score {name}: nothing to do")
        return
    dur = {s: torchaudio.info(cands[s][0]).num_frames / 16000 for s in rows}
    rows.sort(key=dur.get)  # batches of similar length
    print(f"score {name}: {len(done)} done, {len(rows)} to do", flush=True)
    model = WhisperForConditionalGeneration.from_pretrained(base)
    state = torch.load(FT / "CKPT+2026-03-21+19-13-49+00/whisper.ckpt", map_location="cpu")
    state = {k: v for k, v in state.items() if k != "_mel_filters"}
    state.setdefault("proj_out.weight", state["model.decoder.embed_tokens.weight"])
    model.load_state_dict(state, strict=True)
    model = model.eval().to("cuda", torch.float16)
    fe, tok = WhisperFeatureExtractor.from_pretrained(base), WhisperTokenizer.from_pretrained(tokdir)
    t = tok.convert_tokens_to_ids
    eot = t("<|endoftext|>")
    prompt = [t("<|startoftranscript|>"), t("<|en|>"), t("<|transcribe|>"), t("<|notimestamps|>")]
    pad = torch.zeros(4000)

    def gen(feats, max_new):
        dec = torch.tensor([prompt] * len(feats), device="cuda")
        seqs = GenerationMixin.generate(model, input_features=feats, decoder_input_ids=dec, num_beams=beam,
                                        max_new_tokens=max_new).tolist()
        return [lower(tok.decode(q[4:q.index(eot, 4)] if eot in q[4:] else q[4:], skip_special_tokens=True)) for q in seqs]

    with open(out, "a", encoding="utf-8") as fh, torch.no_grad():
        for b in range(0, len(rows), int(batch)):
            segs = rows[b:b + int(batch)]
            wavs = [torch.cat([pad, torchaudio.load(cands[s][0])[0][0]]).numpy() for s in segs]
            feats = fe(wavs, sampling_rate=16000, return_tensors="pt").input_features.to("cuda", torch.float16)
            enc = model.model.encoder(feats).last_hidden_state
            hyp = gen(feats, min(220, int(16 + 10 * max(dur[s] for s in segs)))) if beam else [None] * len(segs)
            for i, s in enumerate(segs):
                c = collections.defaultdict(list, {x: list(v) for x, v in cands[s][1].items()})
                if hyp[i] is not None:
                    c[hyp[i]].append("w")
                hw = (hyp[i] if hyp[i] is not None else next(x for x, v in c.items() if "w0" in v)).split()
                tw = next(x for x, v in c.items() if "tdnn" in v).split()
                if tw and hw and hw[0] != tw[0]:
                    j = tw[:3].index(hw[0]) if hw[0] in tw[:3] else 1
                    c[" ".join(tw[:j] + hw)].append("pre")
                texts = list(c)
                seqs = [prompt + tok.encode(" " + x, add_special_tokens=False)[:440] + [eot] for x in texts]
                res = []
                for o in range(0, len(seqs), 16):
                    chunk = seqs[o:o + 16]
                    n = max(len(q) for q in chunk)
                    ids = torch.full((len(chunk), n), eot, device="cuda")
                    for k, q in enumerate(chunk):
                        ids[k, :len(q)] = torch.tensor(q)
                    lp = model(encoder_outputs=(enc[i:i + 1].expand(len(chunk), -1, -1),),
                               decoder_input_ids=ids[:, :-1]).logits.float().log_softmax(-1)
                    tl = lp.gather(-1, ids[:, 1:, None])[..., 0]
                    res += [(tl[k, 3:len(q) - 1].sum().item(), len(q) - 4) for k, q in enumerate(chunk)]
                fh.write(json.dumps({"seg": s, "dur": round(dur[s], 3), "nbest": [
                    {"text": x, "logp": round(lp_, 3), "ntok": n_, "src": c[x]} for x, (lp_, n_) in zip(texts, res)]},
                    ensure_ascii=False) + "\n")
            if b // int(batch) % 100 == 0:
                print(f"  {b + len(segs)}/{len(rows)}", flush=True)


FEATS = ["lm", "words", "tdnn", "tdnnk", "w", "w0", "fw"]  # weights; the Whisper logp has weight 1
GRID = {"lm": [0, 0.02, 0.05, 0.075, 0.1, 0.125, 0.15, 0.2, 0.3, 0.5, 1.0], "words": [-2, -1, -0.5, 0, 0.25, 0.5, 0.75, 1, 1.5, 2, 4],
        "tdnn": [-4, -1, 0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 6, 8], "tdnnk": [-8, -2, -1, 0, 0.5, 1, 1.5, 2, 3, 4],
        "w": [-12, -8, -6, -4, -3, -2, -1, 0, 2, 4], "w0": [-12, -8, -6, -4, -3, -2, -1, 0, 2, 4], "fw": [-4, -2, -1, 0, 1, 2, 4, 8]}


def features(path, lm):
    """seg -> [(text, Whisper logp, {feature: value})]; the first candidate is the fresh Whisper 1-best (P3's if none)."""
    import json
    import math
    out = {}
    for l in open(path, encoding="utf-8"):
        r = json.loads(l)
        cands = []
        for c in sorted(r["nbest"], key=lambda c: ("w" not in c["src"], "w0" not in c["src"])):
            src = set(c["src"])
            cands.append((c["text"], c["logp"], {
                "lm": lm.score(c["text"].upper()) * math.log(10), "words": len(c["text"].split()), "tdnn": "tdnn" in src,
                "tdnnk": "tdnn" not in src and any(k.startswith("tdnn") for k in src), "w": "w" in src, "w0": "w0" in src,
                "fw": src == {"pre"}}))
        out[r["seg"]] = cands
    return out


def pick(cands, w):
    return max(cands, key=lambda x: x[1] + sum(w.get(k, 0) * x[2][k] for k in FEATS))[0]


def posterior(cands, w):
    """Softmax share of the picked candidate over all candidates' combined scores."""
    import math
    sc = [x[1] + sum(w.get(k, 0) * x[2][k] for k in FEATS) for x in cands]
    return 1 / sum(math.exp(v - max(sc)) for v in sc)


def calib_split():
    """Human references and the Loayr-v2 test segments in neither the Whisper nor the TDNN training data."""
    seen = {l.split(",", 1)[0].split("__")[-1] for l in open(WTRAIN, encoding="utf-8")}
    seen |= {l.split(" ", 1)[0].removeprefix("lbi-") for l in open(K / "data/Loayr-v2/train/text", encoding="utf-8")}
    ref = {Path(r["path"]).stem: lower(r["sentence"]) for r in csv.DictReader(open(CALIB_REF, encoding="utf-8"), delimiter="\t")}
    return ref, sorted(s for s in calib_tdnn() if s in ref and s not in seen)


def tune(beam=1):
    """Fit the rescoring weights on half of Loayr-v2 test (split by recording, minus segments in the Whisper or TDNN
    training data, as in Triskelion) and report on the other half. Writes asr/weights.json."""
    import json
    import kenlm
    ref, segs = calib_split()
    lm = kenlm.Model(LM)
    feats = features(WORK / f"calib.b{beam}.score.jsonl", lm)
    segs = [s for s in segs if s in feats]
    size = collections.Counter(s.rsplit("-", 1)[0] for s in segs)
    half, n = {}, {"tune": 0, "eval": 0}
    for rec in sorted(size, key=lambda k: (-size[k], k)):  # greedy balance by segment count
        half[rec] = min(n, key=lambda k: (n[k], k))
        n[half[rec]] += size[rec]
    split = {h: [s for s in segs if half[s.rsplit("-", 1)[0]] == h] for h in n}
    tdnn = {s: next(c[0] for c in feats[s] if c[2]["tdnn"]) for s in segs}

    def wer(h, choose):
        return 100 * jiwer.wer([ref[s] or "<empty>" for s in split[h]], [choose(s) or "<empty>" for s in split[h]])

    def row(label, choose):
        print(f"  {label:34s} tune {wer('tune', choose):6.2f}   eval {wer('eval', choose):6.2f}")

    print(f"Loayr-v2 test, uncontaminated: tune {n['tune']} / eval {n['eval']} segments")
    row("whisper", lambda s: feats[s][0][0])
    row("whisper (P3 decode)", lambda s: next(c[0] for c in feats[s] if c[2]["w0"]))
    row("tdnn 1-best", lambda s: tdnn[s])
    agree = {s: 1 - min(1.0, jiwer.cer(tdnn[s] or "-", next(c[0] for c in feats[s] if c[2]["w0"]) or "-")) for s in segs}
    row("P3 band rule (red -> tdnn, D38)", lambda s: tdnn[s] if agree[s] < RED else next(c[0] for c in feats[s] if c[2]["w0"]))
    row("oracle", lambda s: min(feats[s], key=lambda x: jiwer.wer(ref[s] or "<empty>", x[0] or "<empty>"))[0])
    w = {k: 0 for k in FEATS}
    best = wer("tune", lambda s: pick(feats[s], w))
    for _ in range(4):  # coordinate descent over the grid
        moved = False
        for k in FEATS:
            for v in GRID[k]:
                trial = {**w, k: v}
                e = wer("tune", lambda s: pick(feats[s], trial))
                if e < best - 1e-9:
                    best, w, moved = e, trial, True
        if not moved:
            break
    row("rescored", lambda s: pick(feats[s], w))
    print(f"  weights {w}")
    both = split["tune"] + split["eval"]
    picked = {s: pick(feats[s], w) for s in both}
    for name, conf in [("rescoring posterior", lambda s: posterior(feats[s], w)),
                       ("whisper-tdnn agreement", lambda s: agreement(feats[s]))]:
        c = {s: conf(s) for s in both}
        print(f"rescored WER by {name} (tune + eval, {len(both)} segments): >= | segments | WER")
        for lo in (0.95, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.0):
            sel = [s for s in both if c[s] >= lo]
            print(f"  {lo:.2f} | {len(sel):4d} | {100 * jiwer.wer([ref[s] or '<empty>' for s in sel], [picked[s] or '<empty>' for s in sel]):5.1f}")
    (WORK / "weights.json").write_text(json.dumps({"beam": int(beam), **w}))


def band(conf, green, red):
    return "green" if conf >= green else "red" if conf < red else "amber"


GREEN, RED = 0.9, 0.6  # agreement bands, signed off by Chris 2026-10-01 (D37)


def agreement(cands):
    """Whisper–TDNN agreement (1 - CER between the fresh Whisper 1-best and the TDNN 1-best): the confidence (D37)."""
    tdnn = next((c[0] for c in cands if c[2]["tdnn"]), "")
    return 1 - min(1.0, jiwer.cer(tdnn or "-", cands[0][0] or "-"))


def collect(green=GREEN, red=RED):
    """asr/asr_segments.tsv: the rescored pick per segment (P3b). Segments not rescored (over 30 s: Whisper saw only their
    first 30 s) keep the long-form TDNN text (text_source tdnn_longform)."""
    import json
    import kenlm
    w = json.loads((WORK / "weights.json").read_text())
    lm = kenlm.Model(LM)
    ref, segs = calib_split()
    cal = features(WORK / f"calib.b{w['beam']}.score.jsonl", lm)
    print(f"calibration on {len(segs)} uncontaminated Loayr-v2 test segments: rescored WER by band")
    for b in ("green", "amber", "red"):
        sel = [s for s in segs if band(agreement(cal[s]), green, red) == b]
        print(f"  {b:5s}: {len(sel):5d} segments, WER {100 * jiwer.wer([ref[s] or '<empty>' for s in sel], [pick(cal[s], w) or '<empty>' for s in sel]):.1f}")

    scored = {}
    for sh in sorted(WORK.glob(f"segments.b{w['beam']}*.score.jsonl")):
        scored.update(features(sh, lm))
    times = {l.split()[0]: l.split()[1:] for seg, _ in segment_sources() for l in open(seg)}
    n = collections.Counter()
    with open(WORK / "asr_segments.tsv", "w", encoding="utf-8", newline="") as f:
        out = csv.writer(f, delimiter="\t", lineterminator="\n")
        out.writerow(["recording", "segment", "start", "end", "text", "text_source", "confidence", "band", "whisper", "tdnn"])
        for r in (r for sh in sorted(WORK.glob("segments_*.infer_partial.csv")) for r in csv.DictReader(open(sh, encoding="utf-8"))):
            seg = Path(r["path"]).stem
            rec, start, end = times[seg]
            if seg in scored:
                cs = scored[seg]
                text = pick(cs, w)
                src = next(c for c in cs if c[0] == text)[2]
                kind = "whisper" if src["w"] else "tdnn" if src["tdnn"] or src["tdnnk"] else "whisper_p3" if src["w0"] else "tdnn+whisper"
                conf, hyp, tdnn = agreement(cs), cs[0][0], next((c[0] for c in cs if c[2]["tdnn"]), "")
            else:
                text, kind, conf, hyp, tdnn = r["transcript"], "tdnn_longform", 1 - min(1.0, float(r["cer"])), r["hyp"], r["transcript"]
            out.writerow([rec, seg, start, end, text, kind, round(100 * conf), band(conf, green, red), hyp, tdnn])
            n[kind] += 1
    print(f"asr_segments.tsv: {sum(n.values())} segments, text from {dict(n)}")


if __name__ == "__main__":
    {"prepare": prepare, "tdnn": tdnn, "nbest": nbest, "score": score, "tune": tune, "collect": collect}[sys.argv[1]](*sys.argv[2:])
