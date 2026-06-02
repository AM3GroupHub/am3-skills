#!/usr/bin/env python3
"""Prepare timing, filler, and sentence-candidate evidence for talk review."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


TIME_RE = re.compile(
    r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})"
)
INLINE_STAMP_RE = re.compile(r"^(?P<stamp>\d{2}:\d{2}:\d{2})\s+Speaker\s+\d+\s*$")
WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'/_+-]*")
FILLER_PATTERNS = [
    r"\bum+\b",
    r"\buh+\b",
    r"\ber+\b",
    r"\bah+\b",
    r"\blike\b",
    r"\byou know\b",
    r"\bkind of\b",
    r"\bsort of\b",
    r"\bso yeah\b",
    r"\bbasically\b",
    r"\bactually\b",
]
VAGUE_PATTERNS = [
    r"\bstuff\b",
    r"\bthings?\b",
    r"\bsomething\b",
    r"\bmaybe\b",
    r"\bprobably\b",
    r"\bI think\b",
    r"\byou can see\b",
    r"\bnot really\b",
]
REPAIR_PATTERNS = [
    r"\bsorry\b",
    r"\bI mean\b",
    r"\blet me\b",
    r"\bor,? actually\b",
]


@dataclass
class Cue:
    start: float
    end: float
    text: str


def parse_time(value: str) -> float:
    match = TIME_RE.search(value)
    if not match:
        raise ValueError(f"bad SRT timestamp: {value}")
    parts = {key: int(val) for key, val in match.groupdict().items()}
    return (
        parts["h"] * 3600
        + parts["m"] * 60
        + parts["s"]
        + parts["ms"] / 1000
    )


def parse_clock(value: str) -> float:
    hours, minutes, seconds = [int(part) for part in value.split(":")]
    return hours * 3600 + minutes * 60 + seconds


def fmt_time(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    seconds = max(0, int(round(seconds)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_srt(path: Path) -> list[Cue]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    blocks = re.split(r"\n\s*\n", raw.strip())
    cues: list[Cue] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_line_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if time_line_index is None:
            continue
        start_raw, end_raw = lines[time_line_index].split("-->", 1)
        text = clean_text(" ".join(lines[time_line_index + 1 :]))
        if text:
            cues.append(Cue(parse_time(start_raw), parse_time(end_raw), text))
    return cues


def parse_inline_timestamp_transcript(text: str) -> list[Cue]:
    cues: list[Cue] = []
    current_start: float | None = None
    current_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        match = INLINE_STAMP_RE.match(line)
        if match:
            if current_start is not None and current_lines:
                cues.append(Cue(current_start, current_start, clean_text(" ".join(current_lines))))
            current_start = parse_clock(match.group("stamp"))
            current_lines = []
            continue
        if line:
            current_lines.append(line)
    if current_start is not None and current_lines:
        cues.append(Cue(current_start, current_start, clean_text(" ".join(current_lines))))
    for index, cue in enumerate(cues[:-1]):
        cue.end = cues[index + 1].start
    if cues:
        cues[-1].end = cues[-1].start
    return cues


def sentence_split(text: str) -> list[str]:
    text = clean_text(text)
    pieces = re.split(r"(?<=[.!?])\s+", text)
    sentences = [piece.strip() for piece in pieces if piece.strip()]
    if len(sentences) <= 1 and len(text.split()) > 45:
        chunks = re.split(r"\s+(?=(?:and|but|so|because|then|which|where)\b)", text)
        sentences = []
        current: list[str] = []
        for chunk in chunks:
            current.append(chunk)
            if len(" ".join(current).split()) >= 30:
                sentences.append(" ".join(current).strip())
                current = []
        if current:
            sentences.append(" ".join(current).strip())
    return sentences


def sentences_from_cues(cues: list[Cue]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    current: list[str] = []
    start: float | None = None
    end: float | None = None
    for cue in cues:
        if start is None:
            start = cue.start
        current.append(cue.text)
        end = cue.end
        joined = clean_text(" ".join(current))
        if re.search(r"[.!?][\"')\]]?$", joined) or len(joined.split()) >= 45:
            rows.extend(sentence_rows(joined, start, end))
            current = []
            start = None
            end = None
    if current:
        rows.extend(sentence_rows(clean_text(" ".join(current)), start, end))
    return rows


def sentence_rows(text: str, start: float | None, end: float | None) -> list[dict[str, object]]:
    sentences = sentence_split(text)
    if not sentences:
        return []
    rows = []
    for sentence in sentences:
        rows.append({"start": start, "end": end, "text": sentence})
    return rows


def count_pattern(patterns: Iterable[str], text: str) -> int:
    return sum(len(re.findall(pattern, text, flags=re.IGNORECASE)) for pattern in patterns)


def flag_sentence(sentence: str) -> tuple[int, list[str]]:
    words = WORD_RE.findall(sentence)
    flags: list[str] = []
    score = 0
    if len(words) >= 50:
        flags.append("very long/mouthful")
        score += 5
    elif len(words) >= 35:
        flags.append("long/mouthful")
        score += 3
    fillers = count_pattern(FILLER_PATTERNS, sentence)
    if fillers:
        flags.append(f"filler x{fillers}")
        score += min(4, fillers)
    vague = count_pattern(VAGUE_PATTERNS, sentence)
    if vague:
        flags.append("vague or informal wording")
        score += 2
    repairs = count_pattern(REPAIR_PATTERNS, sentence)
    if repairs:
        flags.append("self-repair/apology")
        score += 3
    if len(words) < 7 and not re.search(r"[.!?]$", sentence):
        flags.append("fragment")
        score += 2
    if re.search(r"\b(this|that|it|they)\b", sentence, re.I) and not re.search(
        r"\b(because|therefore|so|which means|as a result)\b", sentence, re.I
    ):
        if len(words) >= 20:
            flags.append("possible missing referent or local logic")
            score += 1
    return score, flags


def ffprobe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return None


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def write_markdown(
    out: Path,
    transcript: Path,
    summary: dict[str, object],
    sentence_candidates: list[dict[str, object]],
) -> None:
    lines = [
        "# Transcript Review Prep",
        "",
        f"- Transcript: `{transcript}`",
        f"- Duration: {summary['duration']}",
        f"- Word count: {summary['word_count']}",
        f"- Speaking rate: {summary['words_per_minute']} words/min",
        f"- Target slot: {summary['target_minutes']}",
        f"- Filler count: {summary['filler_count']}",
        "",
        "## Sentence Candidates",
        "",
        "Use these as candidates for sentence-level review; verify them against the transcript/audio before making final claims.",
        "",
        "| Time | Words | Flags | Sentence |",
        "|---|---:|---|---|",
    ]
    for row in sentence_candidates[:40]:
        flags = ", ".join(row["flags"]) if row["flags"] else "review for logic"
        lines.append(
            "| {time} | {words} | {flags} | {sentence} |".format(
                time=row["time"],
                words=row["word_count"],
                flags=markdown_escape(flags),
                sentence=markdown_escape(str(row["text"])[:280]),
            )
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare timing, filler, and sentence-candidate evidence from a talk transcript."
    )
    parser.add_argument("transcript", type=Path)
    parser.add_argument("--srt", type=Path)
    parser.add_argument("--media", type=Path)
    parser.add_argument("--target-minutes", type=float)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    text = args.transcript.read_text(encoding="utf-8", errors="replace")
    cues = parse_srt(args.srt) if args.srt and args.srt.exists() else []
    if not cues:
        cues = parse_inline_timestamp_transcript(text)
    duration_seconds = cues[-1].end if cues else None
    if duration_seconds is None and args.media:
        duration_seconds = ffprobe_duration(args.media)

    if cues:
        rows = sentences_from_cues(cues)
    else:
        rows = sentence_rows(text, None, None)

    candidates: list[dict[str, object]] = []
    for row in rows:
        sentence = str(row["text"])
        words = WORD_RE.findall(sentence)
        score, flags = flag_sentence(sentence)
        if score or len(words) >= 30:
            candidates.append(
                {
                    "time": fmt_time(row.get("start")),
                    "word_count": len(words),
                    "score": score,
                    "flags": flags,
                    "text": sentence,
                }
            )
    candidates.sort(key=lambda item: (-int(item["score"]), -int(item["word_count"])))

    word_count = len(WORD_RE.findall(text))
    minutes = duration_seconds / 60 if duration_seconds else None
    words_per_minute = round(word_count / minutes, 1) if minutes else "n/a"
    summary = {
        "transcript": str(args.transcript),
        "duration": fmt_time(duration_seconds),
        "duration_seconds": round(duration_seconds, 2) if duration_seconds else None,
        "word_count": word_count,
        "words_per_minute": words_per_minute,
        "target_minutes": args.target_minutes if args.target_minutes else "n/a",
        "filler_count": count_pattern(FILLER_PATTERNS, text),
        "sentence_candidate_count": len(candidates),
    }

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(args.out, args.transcript, summary, candidates)
        summary["markdown"] = str(args.out)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
