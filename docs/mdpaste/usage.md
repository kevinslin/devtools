# mdpaste

`mdpaste` reads Markdown from the macOS clipboard, converts it into rich text, and writes plain text, HTML, and RTF back to the clipboard so pasting into Gmail or Google Docs preserves formatting.

## Quickstart

```sh
mdpaste
```

## Command

```sh
mdpaste
```

## Behavior

- `mdpaste` reads the current clipboard as plain text and treats it as Markdown.
- It renders that Markdown to HTML with `markdown-it-py`.
- It converts the HTML to RTF with macOS `textutil`.
- It writes plain text, HTML, and RTF flavors back to the clipboard using macOS `osascript`/JXA.
- Plain-text paste targets still receive the original Markdown.

## Requirements

- macOS
- `python3`
- `markdown-it-py`
- `osascript`
- `textutil`

## Example

```sh
# copy markdown first, then upgrade the clipboard to rich text
pbcopy <<'EOF'
# Weekly Update

- shipped `mdpaste`
- fixed the Gmail paste flow
EOF

mdpaste
```

After running `mdpaste`, paste into Gmail or Google Docs to preserve headings, lists, emphasis, and links.

## Exit codes

- `0`: clipboard conversion completed successfully.
- `1`: the clipboard could not be read, conversion failed, or the runtime requirements were not available.
