# Abbyr Shen Reesht – Automatic Transcriptions

This folder contains **automatically generated transcriptions** of episodes from the Manx-language radio programme _Abbyr Shen Reesht_ (“Say That Again”).

These transcriptions were generated using a **DNN-HMM hybrid ASR model** trained on the [Loayr dataset](https://manx-forge.github.io/speech-transcription-data/loayr/). The model was built with the Kaldi speech recognition toolkit and fine-tuned specifically for Manx.

---

## 📻 Source

The original audio was sourced from the publicly available _Abbyr Shen Reesht_ podcast archive hosted by **Manx Radio**:  
🔗 [https://www.manxradio.com/podcasts/abbyr-shen-reesht-say-that-again1/](https://www.manxradio.com/podcasts/abbyr-shen-reesht-say-that-again1/)

The programme features **high-quality, professionally recorded Manx speech**, typically in the form of:

- Single-speaker narrative or commentary
- Multi-speaker segments such as interviews and discussions
- Spontaneous or semi-scripted speech in a radio broadcast style

---

## 📁 Contents

Each episode includes:
- `.txt` — plain text transcription of the episode
- `.srt` — time-aligned transcription in subtitle format (for use in video or audio playback)

These files were generated automatically and **have not been manually corrected**. We hope that their current standard is good enough for practical use, though they are not perfect and will contain errors.

---

## ⚠️ Notes on Use

- Transcriptions may contain errors, especially in fast speech, overlapping turns, or domain-specific vocabulary.
- They are suitable for downstream tasks such as:
  - Automatic subtitling
  - Spoken corpus construction
  - Input for text-to-speech (TTS) systems
- However, they should **not be used as ground truth** examples without verification.

---

## 📜 Licensing

The original audio is the property of **Manx Radio**. Transcriptions are provided for research and educational purposes. Please attribute _Manx Radio_ if you want to use or redistribute this data.

---

🎯 This dataset is part of the broader [automatic_transcriptions](https://github.com/Manx-forge/automatic_transcriptions) project, which aims to connect and document automatically transcribed Manx-language resources.
