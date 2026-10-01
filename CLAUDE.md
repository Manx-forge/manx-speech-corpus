# Claude working agreement: manx_speech_corpus

The plan and decisions (D1…) are in `docs/PLAN.md`. Update it as phases close.

## Hard rules
- **GPU jobs and long CPU jobs are user-launched.** Present them as commands (what the command does, duration, log path,
  what healthy output looks like). Use `nohup` and `export PYTHONUNBUFFERED=1`.
- **Source data is read-only:** `/store/store3/data/Manx_Resources/`, `/exp/exp5/acp24csb/kaldi/egs/manx*`,
  `/exp/exp5/acp24csb/timestamper/`, `/exp/exp3/acp24csb/whisper-ft/`. Copy before patching. Never delete anything.
- **Intermediates go in `/store/store3/data/manx_speech_corpus/`** (`asr/`, `align/`, `cache/`, `work/`). Never put them
  in this git repo or under `$HOME`.
- **Pushes to the two Manx-forge repos are standing-approved.** Anything else outward-facing (GitHub issues/PRs, deploys, anything sent to David or upstream) needs confirmation first.
- **Keep the repos clean, tidy and MINIMAL. This is the top priority.** Prefer one script per pipeline stage, extended rather than duplicated. No one-off helpers, no throwaway files committed. Ad-hoc checks run inline or in scratch and are never committed.
- **No `Co-Authored-By: Claude` anywhere**: not in commits, PRs or docs.
- Smoke-test logs go to `/tmp`; real-run logs go to `/store/store3/data/manx_speech_corpus/work/logs/`.

## Repos in this workspace
| Path | Remote | Notes |
|---|---|---|
| `.` | `Manx-forge/manx-speech-corpus` | data, pipeline, registers |
| `manx-corpus-search/` | `origin` = `Manx-forge/manx-corpus-search` (fork), `upstream` = `david-allison/…` | site work on branch `speech` |
| `external/manx-search-data/` | `david-allison/manx-search-data` | read-only reference (shallow) |

GitHub uses HTTPS with gh as the credential helper (no SSH key on titan):
`git -c credential.helper='!gh auth git-credential' push ...`

## Style
Short answers that lead with the conclusion. Stop at each phase boundary for Chris's sign-off.

## Tools
- yt-dlp (current version, our own copy; the shared `yt-dlp` env's copy is too old and YouTube returns 403):
  `PYTHONPATH=/store/store3/data/manx_speech_corpus/cache/tools/yt_dlp_pkg /store/store3/software/bin/anaconda3/envs/yt-dlp/bin/python -m yt_dlp --js-runtimes node:/store/store3/software/bin/anaconda3/envs/yt-dlp/bin/node ...`
