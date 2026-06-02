---
name: practice-talk-review
description: Analyze academic practice talks from audio, video, or transcript files. Use when Codex needs to transcribe a rehearsal recording (MP3, MP4, M4A, WAV, MOV, or other media), turn it into a spoken script, and produce candid presentation coaching on logic gaps, flow, formal-talk quality, sentence-level broken wording, pronunciation clarity, pacing, and how results are explained.
---

# Practice-Talk Review

Turn a rehearsal recording into concrete, rubric-grounded coaching for an academic talk. Accept either an audio/video file or an existing transcript. For media input, extract audio, transcribe it into a spoken script with timestamps, then analyze the script for:

- logic gaps and structural problems
- smoothness, flow, timing, and transitions
- result-framing quality
- sentence-level broken wording, pronunciation/clarity risks, informal or ill-conditioned sentences, and broken local logic

Bundled files, relative to this skill directory:

- `scripts/transcribe.sh` - ffmpeg plus local Whisper transcription with backend auto-detection.
- `scripts/transcript_stats.py` - transcript/SRT helper for timing, filler counts, and sentence candidates.
- `reference/rubric.md` - the analysis criteria. Read this before analyzing.
- `reference/report-template.md` - the report format. Use this when writing the final markdown report.

## Workflow

1. **Get the input.** Use the path the user gave. If no path is available, ask for one concise follow-up. Verify it exists. Accept common audio/video containers such as MP3, MP4, M4A, WAV, MOV, AAC, FLAC, and WebM.

2. **Gather light context when useful.** Ask for only missing high-value context: talk title, target time slot in minutes, audience/venue, and 3-8 key terms or acronyms. Skip this if the user wants to proceed immediately.

3. **Transcribe media input.** If the input is audio/video, run:
```bash
bash "<skill-dir>/scripts/transcribe.sh" "<INPUT>" --prompt "<title>. Terms: <comma-separated terms>."
```

The script extracts/normalizes audio, chooses a local backend in this order: `mlx_whisper`, `whisper`, `whisper-cli`, and writes transcript/subtitle artifacts into a `<stem>-review/` folder beside the input. It prints the plain-text transcript path as the last stdout line.

If the script exits with code 3, no speech-to-text backend is installed. Relay the printed install options to the user and stop unless they ask you to install one. The normalized audio remains in the review folder, so re-running after installation is fast.

4. **Prepare evidence from the transcript.** Locate the `.txt` transcript and the matching `.srt` when available. Run:
```bash
python3 "<skill-dir>/scripts/transcript_stats.py" "<TRANSCRIPT.txt>" --srt "<TRANSCRIPT.srt>" --media "<INPUT>" --target-minutes "<minutes>" --out "<review-dir>/sentence-candidates.md"
```
Omit flags whose inputs are unavailable. Use the generated `sentence-candidates.md` as evidence, not as the final critique.

5. **Analyze against the rubric.** Read `reference/rubric.md` and apply it. Work strictly from what was said. Attach a short quote plus an approximate timestamp to each major finding. Normalize obvious ASR errors in technical terms for readability, but do not invent slide content or problems not supported by the audio.

6. **Include sentence-level analysis for audio/video reviews.** Identify the most consequential broken or weak sentences, especially sentences that are:
- grammatically broken, unfinished, or full of false starts
- too long or mouthful for a formal talk
- informal, vague, apologetic, or under-confident
- locally illogical because the subject, claim, evidence, or consequence is missing
- likely pronunciation/clarity risks because ASR repeatedly fragments or mis-hears core technical terms

For pronunciation, never criticize accent. Frame feedback as intelligibility and term-drilling: "This term needs slower, cleaner articulation" or "ASR instability suggests this phrase may need rehearsal." Provide a better formal sentence and, where helpful, a short practice note.

7. **Write the report.** Follow `reference/report-template.md`. Save it next to the input as `<stem>-review/<stem>-feedback.md`, or next to the transcript as `<stem>-feedback.md` for transcript-only input. Use the `Heard -> Problem -> Fix -> Principle` shape with rubric tags. Lead with logic, then flow, then results, then sentence-level repairs. End with the top 3 priorities and one honest overall verdict.

8. **Report back.** Give the user the report path and the top 3 priorities. If transcription failed because dependencies are missing, give the exact next command from the script output.

## Scope & honesty

- Review the spoken talk: logic, structure, transitions, pacing, wording, pronunciation clarity, and how results are explained out loud.
- Do not judge slide design unless the user supplies slides or the narration makes the issue audible, such as "as you can see here" without defining axes.
- Be candid and concrete. Name real weaknesses plainly, including under-rehearsal, no research question, undefined data, bad formal tone, or sentence-level breakdowns. Pair every serious criticism with an actionable fix.
- Treat ASR as noisy. Use transcript evidence, but sanity-check jargon and do not over-read single-word transcription mistakes.
- Keep audio processing local through the bundled script unless the user explicitly asks for a cloud transcription route.

## Tips to tell the user (for a better recording)

- Record in a quiet room with a headset or lapel mic.
- Speak as in the real talk; do not read a hidden script.
- Say slide numbers or section transitions aloud so the review can map feedback to the deck.
- Provide the title and key terms so the transcript spells jargon correctly.
