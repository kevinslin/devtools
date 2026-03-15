#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WHISPER_GIT = "git+https://github.com/openai/whisper.git"
SAFE_EXTENSIONS = {"wav", "mp3", "m4a", "mp4", "mpeg", "mpga", "webm", "ogg", "flac"}
FORCE_CONVERT_EXTENSIONS = {"amr", "awb", "3ga", "gsm"}
FORCE_CONVERT_CODECS = {"amr_nb", "amr_wb", "amr", "gsm", "gsm_ms"}
WORD_RE = re.compile(r"[A-Za-z0-9']+")
FIRST_PERSON_RE = re.compile(r"\b(i|me|my|mine|i'm|i've|i'd|i'll)\b", re.IGNORECASE)
SECOND_PERSON_RE = re.compile(r"\b(you|your|yours|you're|you've|you'll)\b", re.IGNORECASE)
QUESTION_WORD_RE = re.compile(r"\b(who|what|when|where|why|how|did|do|does|are|can|could|will|would)\b", re.IGNORECASE)
CONVERSATION_CUES = (
    "i said",
    "what did you",
    "how are you",
    "thank you",
    "sorry",
    "yes",
    "no",
    "okay",
    "are you",
    "can you",
    "why are you",
)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tool.whisper",
        description="Transcribe audio/video to markdown using OpenAI Whisper.",
    )
    p.add_argument("inputfile", help="Path to input audio/video file.")
    p.add_argument(
        "outputfile",
        nargs="?",
        help="Optional markdown output path. Defaults to /tmp/whisper-YYYY-MM-DD-file-title.md",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Whisper model name (default: WHISPER_MODEL env var or 'base').",
    )
    p.add_argument(
        "--language",
        default=None,
        help="Optional language hint (e.g. en, es).",
    )
    p.add_argument(
        "--force-convert",
        action="store_true",
        help="Force ffmpeg conversion to 16k mono wav before transcription.",
    )
    p.add_argument(
        "--no-auto-clean",
        action="store_true",
        help="Disable transcript cleaning and inferred speaker turns.",
    )
    return p


def require_binary(name: str) -> None:
    if shutil.which(name):
        return
    raise RuntimeError(f"Required binary '{name}' is not installed or not on PATH")


def run(cmd: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def probe_audio(path: Path) -> dict:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-print_format",
        "json",
        str(path),
    ]
    result = run(cmd, capture=True)
    payload = json.loads(result.stdout or "{}")
    audio = next((s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), None)
    if not audio:
        raise RuntimeError("No audio stream found in input file")
    return {
        "codec_name": (audio.get("codec_name") or "").lower(),
        "sample_rate": audio.get("sample_rate"),
        "duration": payload.get("format", {}).get("duration"),
    }


def should_convert(path: Path, info: dict, force_convert: bool) -> bool:
    if force_convert:
        return True

    ext = path.suffix.lower().lstrip(".")
    codec = (info.get("codec_name") or "").lower()

    if ext in FORCE_CONVERT_EXTENSIONS:
        return True
    if codec in FORCE_CONVERT_CODECS or codec.startswith("amr"):
        return True
    if ext in SAFE_EXTENSIONS:
        return False
    return True


def convert_to_wav(src: Path) -> Path:
    fd, tmp_name = tempfile.mkstemp(prefix="whisper-converted-", suffix=".wav")
    Path(tmp_name).unlink(missing_ok=True)
    wav_path = Path(tmp_name)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(wav_path),
    ]
    run(cmd)
    return wav_path


def ensure_whisper_module():
    try:
        return importlib.import_module("whisper")
    except ModuleNotFoundError:
        print("Installing OpenAI Whisper from GitHub...", file=sys.stderr)
        run([sys.executable, "-m", "pip", "install", "--upgrade", WHISPER_GIT])
        importlib.invalidate_caches()
        return importlib.import_module("whisper")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-").lower()
    return slug or "audio"


def default_output_path(input_path: Path) -> Path:
    date = dt.datetime.now().strftime("%Y-%m-%d")
    stem = slugify(input_path.stem)
    return Path(f"/tmp/whisper-{date}-{stem}.md")


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\s+([,.;:?!])", r"\1", text)
    text = re.sub(r"\.{4,}", "...", text)
    return text


def clean_sentence(text: str) -> str:
    text = normalize_text(text)
    if not text:
        return ""
    if text[0].isalpha():
        text = text[0].upper() + text[1:]
    if text[-1] not in ".?!":
        text += "."
    return text


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


def extract_utterances(full_text: str) -> list[str]:
    text = normalize_text(full_text)
    if not text:
        return []

    pieces = re.split(r"(?<=[.?!])\s+", text)
    utterances: list[str] = []
    for piece in pieces:
        cleaned = clean_sentence(piece)
        if not cleaned:
            continue
        words = count_words(cleaned)
        if utterances and words <= 2:
            previous = utterances[-1].rstrip(".?!")
            utterances[-1] = clean_sentence(f"{previous} {cleaned}")
            continue
        utterances.append(cleaned)
    return utterances


def should_treat_as_dialogue(utterances: list[str], full_text: str) -> bool:
    if len(utterances) < 8:
        return False

    lowered = full_text.lower()
    words = [count_words(u) for u in utterances]
    average_words = (sum(words) / len(words)) if words else 0.0
    short_utterances = sum(1 for count in words if count <= 7)
    question_marks = full_text.count("?")
    question_starts = len(QUESTION_WORD_RE.findall(lowered))
    first_person = len(FIRST_PERSON_RE.findall(lowered))
    second_person = len(SECOND_PERSON_RE.findall(lowered))
    cue_hits = sum(lowered.count(cue) for cue in CONVERSATION_CUES)

    score = 0
    if len(utterances) >= 12:
        score += 2
    if short_utterances >= max(4, len(utterances) // 3):
        score += 1
    if average_words <= 16:
        score += 1
    if question_marks >= 2 or question_starts >= 5:
        score += 2
    if first_person >= 5 and second_person >= 5:
        score += 2
    if cue_hits >= 6:
        score += 1
    return score >= 5


def infer_dialogue_lines(utterances: list[str]) -> list[str]:
    if not utterances:
        return []

    lines: list[str] = []
    speaker_index = 0
    bucket: list[str] = []
    bucket_words = 0

    for utterance in utterances:
        bucket.append(utterance)
        bucket_words += count_words(utterance)
        flush = utterance.endswith("?") or bucket_words >= 18
        if not flush:
            continue

        combined = normalize_text(" ".join(bucket))
        speaker = f"Speaker {(speaker_index % 2) + 1}"
        lines.append(f"**{speaker}:** {combined}")
        speaker_index += 1
        bucket = []
        bucket_words = 0

    if bucket:
        combined = normalize_text(" ".join(bucket))
        speaker = f"Speaker {(speaker_index % 2) + 1}"
        lines.append(f"**{speaker}:** {combined}")

    return lines


def clean_transcript_text(full_text: str) -> str:
    utterances = extract_utterances(full_text)
    if not utterances:
        return "(no transcription text returned)"
    return "\n\n".join(utterances)


def render_markdown(
    *,
    input_path: Path,
    transcribed_path: Path,
    output_path: Path,
    converted: bool,
    model: str,
    language: str,
    duration: str | None,
    text: str,
    utterances: list[str],
    auto_cleaned: bool,
) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    duration_line = duration if duration else "unknown"
    raw_transcript = text.strip() or "(no transcription text returned)"
    dialogue_detected = should_treat_as_dialogue(utterances, raw_transcript) if auto_cleaned else False

    if auto_cleaned and dialogue_detected:
        inferred_lines = infer_dialogue_lines(utterances)
        cleaned_body = "\n\n".join(inferred_lines) if inferred_lines else clean_transcript_text(raw_transcript)
        body_heading = "## Transcript (Cleaned + Inferred Speaker Turns)"
        speaker_mode = "`yes`"
    elif auto_cleaned:
        cleaned_body = clean_transcript_text(raw_transcript)
        body_heading = "## Transcript (Cleaned)"
        speaker_mode = "`no`"
    else:
        cleaned_body = raw_transcript
        body_heading = "## Transcript"
        speaker_mode = "`no`"

    markdown = (
        "# Whisper Transcript\n\n"
        f"- Generated: {now}\n"
        f"- Input: `{input_path}`\n"
        f"- Audio used: `{transcribed_path}`\n"
        f"- Converted with ffmpeg: `{'yes' if converted else 'no'}`\n"
        f"- Model: `{model}`\n"
        f"- Language: `{language}`\n"
        f"- Duration (seconds): `{duration_line}`\n"
        f"- Auto cleaned: `{'yes' if auto_cleaned else 'no'}`\n"
        f"- Dialogue detected: `{'yes' if dialogue_detected else 'no'}`\n"
        f"- Inferred speaker turns: {speaker_mode}\n"
        f"- Output file: `{output_path}`\n\n"
        f"{body_heading}\n\n"
        f"{cleaned_body}\n"
    )
    if auto_cleaned:
        markdown += f"\n## Transcript (Raw Whisper)\n\n{raw_transcript}\n"
    return markdown


def main() -> int:
    args = parser().parse_args()

    input_path = Path(args.inputfile).expanduser().resolve()
    if not input_path.exists():
        raise RuntimeError(f"Input file does not exist: {input_path}")

    output_path = Path(args.outputfile).expanduser().resolve() if args.outputfile else default_output_path(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    require_binary("ffmpeg")
    require_binary("ffprobe")

    info = probe_audio(input_path)
    converted = should_convert(input_path, info, args.force_convert)

    transcription_input = input_path
    converted_path: Path | None = None

    try:
        if converted:
            print("Converting audio with ffmpeg...", file=sys.stderr)
            converted_path = convert_to_wav(input_path)
            transcription_input = converted_path

        whisper = ensure_whisper_module()
        model_name = args.model or os.getenv("WHISPER_MODEL", "base")
        language_hint = args.language or "auto"

        print(f"Loading Whisper model '{model_name}'...", file=sys.stderr)
        model = whisper.load_model(model_name)

        transcribe_kwargs = {"fp16": False}
        if args.language:
            transcribe_kwargs["language"] = args.language

        print("Running transcription...", file=sys.stderr)
        result = model.transcribe(str(transcription_input), **transcribe_kwargs)
        raw_text = result.get("text", "")
        utterances = extract_utterances(raw_text)

        markdown = render_markdown(
            input_path=input_path,
            transcribed_path=transcription_input,
            output_path=output_path,
            converted=converted,
            model=model_name,
            language=language_hint,
            duration=info.get("duration"),
            text=raw_text,
            utterances=utterances,
            auto_cleaned=not args.no_auto_clean,
        )

        output_path.write_text(markdown, encoding="utf-8")
        sys.stdout.write(markdown)
        print(f"Wrote markdown transcript to {output_path}", file=sys.stderr)
        return 0
    finally:
        if converted_path and converted_path.exists():
            converted_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
