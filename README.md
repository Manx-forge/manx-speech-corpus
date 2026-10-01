# Manx Speech Corpus

Searchable transcriptions of Manx Gaelic speech. Every result links to the **original audio at its source**, at the
timestamp where the searched phrase is spoken. This is the speech counterpart to the text corpus at
[corpus.gaelg.im](https://corpus.gaelg.im/).

No audio is hosted here. The repository holds transcripts, word-level timings, metadata and links.

- Transcripts are either **human** (professional or community) or **AI-generated** (a fine-tuned Whisper model,
  force-aligned). Every line says which, and AI lines carry a confidence score.
- Links are checked automatically. Broken or missing links are tracked in `registers/link_register.tsv`.
- Missing a recording? Check whether we have it, timestamp it with the [Manx timestamper](https://gaelgai.im/#timestamp),
  and open an issue.

Status: under construction. See [docs/PLAN.md](docs/PLAN.md).

## Layout
| Path | Contents |
|---|---|
| `OpenData/<source>/<collection>/<work>/` | `manifest.json.txt`, `document.csv`, `words.csv` per recording |
| `registers/` | master recording inventory, link register |
| `scripts/` | build pipeline (inventory, ASR, alignment, export, link checks) |
| `reports/` | per-phase build reports |
