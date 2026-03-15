---
name: whisper
description: Transcribe local audio or video into Markdown using OpenAI Whisper with automatic GitHub installation, ffmpeg conversion for AMR/unsupported inputs, and automatic cleanup with inferred speaker turns for dialogue-like conversations. Use when a user asks to decode Voice Memo or telephony audio, produce local speech-to-text output, or save a readable transcript as markdown.
dependencies: []
---

# whisper

Run local Whisper transcription and emit markdown to stdout and file.

## Command

Use:
`$tool.whisper [inputfile] [outputfile]`

Map `$tool.whisper` to:
`./skills/whisper/scripts/tool.whisper`

Arguments:
- `inputfile` (required): source audio/video path.
- `outputfile` (optional): markdown output path. Default: `/tmp/whisper-YYYY-MM-DD-file-title.md`.

## Workflow

1. Verify `ffmpeg` and `ffprobe` are available on `PATH`.
2. Ensure Whisper is installed from OpenAI GitHub (`git+https://github.com/openai/whisper.git`).
3. Detect whether conversion is needed.
4. Convert AMR/telephony or unknown containers to `wav` (`16k`, mono) with `ffmpeg` when needed.
5. Transcribe with Whisper (`base` model by default).
6. Auto-clean transcript text for readability.
7. Infer speaker turns (`Speaker 1`, `Speaker 2`) when the transcript appears to be a multi-person conversation.
8. Print markdown transcript to stdout and write identical markdown to output file.

## Notes

- Keep stdout clean markdown so output can be piped directly.
- Set `WHISPER_MODEL` to override the default model.
- Use `--no-auto-clean` to disable cleaning and speaker-turn inference.
- The script writes progress and non-markdown logs to stderr.
