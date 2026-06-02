#!/usr/bin/env bash
# transcribe.sh — extract audio (if needed) and transcribe a practice talk to
# plain text + timestamped subtitles, for the practice-talk-review skill.
#
# Backends, tried in priority order (best for Apple Silicon first):
#   1. mlx_whisper    (pip install mlx-whisper)      — fast, local, Metal-accelerated
#   2. whisper        (pip install -U openai-whisper) — cross-platform, slower
#   3. whisper-cli    (brew install whisper-cpp)      — C++ engine; needs a ggml model
#
# Usage:
#   transcribe.sh <input-audio-or-video> [--out DIR] [--model NAME]
#                 [--prompt "domain terms"] [--language en]
#
# Output: prints the path of the plain-text transcript as the final stdout line.
# All progress/log chatter goes to stderr, so callers can capture stdout cleanly.
set -euo pipefail

err()  { printf '%s\n' "$*" >&2; }
die()  { err "ERROR: $*"; exit 1; }

INPUT=""
OUT=""
MODEL="${WHISPER_MODEL:-}"
# A domain prompt biases Whisper toward the right spelling of jargon/acronyms.
PROMPT="${WHISPER_PROMPT:-An academic research seminar with technical terminology, acronyms, and equations.}"
LANG="${WHISPER_LANG:-en}"

while [ $# -gt 0 ]; do
  case "$1" in
    --out)      OUT="${2:?}"; shift 2 ;;
    --model)    MODEL="${2:?}"; shift 2 ;;
    --prompt)   PROMPT="${2:?}"; shift 2 ;;
    --language) LANG="${2:?}"; shift 2 ;;
    -h|--help)  err "Usage: transcribe.sh <input> [--out DIR] [--model NAME] [--prompt TEXT] [--language LANG]"; exit 0 ;;
    -*)         die "unknown option: $1" ;;
    *)          if [ -z "$INPUT" ]; then INPUT="$1"; else die "unexpected extra argument: $1"; fi; shift ;;
  esac
done

[ -n "$INPUT" ] || die "no input file. Usage: transcribe.sh <audio-or-video> [options]"
[ -f "$INPUT" ] || die "input file not found: $INPUT"
command -v ffmpeg  >/dev/null 2>&1 || die "ffmpeg not found. Install with: brew install ffmpeg"
command -v ffprobe >/dev/null 2>&1 || die "ffprobe not found. Install with: brew install ffmpeg"

base="$(basename "$INPUT")"; stem="${base%.*}"
if [ -z "$OUT" ]; then OUT="$(cd "$(dirname "$INPUT")" && pwd)/${stem}-review"; fi
mkdir -p "$OUT"

# 1) Confirm the file actually contains an audio stream.
if ! ffprobe -v error -select_streams a -show_entries stream=index -of csv=p=0 "$INPUT" | grep -q .; then
  die "no audio stream found in: $INPUT"
fi

# 2) Extract / normalize to 16 kHz mono WAV (what Whisper expects).
WAV="$OUT/${stem}.16k.wav"
err ">> extracting audio → $WAV"
ffmpeg -nostdin -y -i "$INPUT" -vn -ac 1 -ar 16000 "$WAV" >/dev/null 2>&1 \
  || die "ffmpeg failed to extract audio from: $INPUT"

# 3) Select a transcription backend.
backend=""
if   command -v mlx_whisper >/dev/null 2>&1; then backend="mlx"
elif command -v whisper     >/dev/null 2>&1; then backend="openai"
elif command -v whisper-cli >/dev/null 2>&1; then backend="cpp"
fi

if [ -z "$backend" ]; then
  err ""
  err "No speech-to-text backend is installed. Install ONE of these, then re-run:"
  err "  pip install mlx-whisper          # recommended on Apple Silicon (fast, local)"
  err "  pip install -U openai-whisper    # cross-platform (slower, pure PyTorch)"
  err "  brew install whisper-cpp         # C++ engine (also set WHISPER_CPP_MODEL=<ggml.bin>)"
  err ""
  err "The normalized audio is already prepared here: $WAV"
  exit 3
fi
err ">> transcribing with backend: $backend (this can take a few minutes; the model downloads once)"

# 4) Run the backend. Retry without the domain prompt if the flag is unsupported.
case "$backend" in
  mlx)
    M="${MODEL:-mlx-community/whisper-large-v3-turbo}"
    mlx_whisper "$WAV" --model "$M" --output-dir "$OUT" --output-format all --language "$LANG" --initial-prompt "$PROMPT" >&2 \
      || mlx_whisper "$WAV" --model "$M" --output-dir "$OUT" --output-format all --language "$LANG" >&2 \
      || die "mlx_whisper transcription failed"
    ;;
  openai)
    M="${MODEL:-turbo}"
    whisper "$WAV" --model "$M" --output_dir "$OUT" --output_format all --language "$LANG" --initial_prompt "$PROMPT" >&2 \
      || whisper "$WAV" --model "$M" --output_dir "$OUT" --output_format all --language "$LANG" >&2 \
      || die "whisper transcription failed"
    ;;
  cpp)
    [ -n "${WHISPER_CPP_MODEL:-}" ] \
      || die "whisper.cpp found but WHISPER_CPP_MODEL is unset (path to a ggml model, e.g. ggml-large-v3-turbo.bin)"
    whisper-cli -m "$WHISPER_CPP_MODEL" -f "$WAV" -l "$LANG" --prompt "$PROMPT" -otxt -osrt -of "$OUT/${stem}" >&2 \
      || die "whisper-cli transcription failed"
    ;;
esac

# 5) Locate the plain-text transcript and report its path on stdout.
TXT="$OUT/${stem}.16k.txt"
[ -f "$TXT" ] || TXT="$(ls -1t "$OUT"/*.txt 2>/dev/null | head -1 || true)"
{ [ -n "${TXT:-}" ] && [ -f "$TXT" ]; } || die "transcription finished but no .txt output was found in $OUT"

err ">> done. transcript: $TXT"
err ">> timestamped subtitles + json also in: $OUT"
printf '%s\n' "$TXT"
