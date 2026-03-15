# `autocrop-video`

<div align="center"><img src="../../assets/autocrop-video-logo.png" alt="Autocrop video mascot" width="120" /></div>

Detect the actual video frame inside a larger screen recording, then optionally crop the source file down to that rectangle.

The detector is tuned for recordings where the real video is embedded inside a browser or app window and the surrounding UI is mostly static.

Requirements:

- `ffmpeg`
- `ffprobe`
- Python 3

## Usage

Print the detected bounding box as JSON:

```bash
bin/autocrop-video detect input.mp4
```

Print only the `ffmpeg` crop filter string:

```bash
bin/autocrop-video detect input.mp4 --format crop
```

Crop the file and print the detected box:

```bash
bin/autocrop-video crop input.mp4 output.mp4 --overwrite
```

Tune detection resolution or sample count for harder cases:

```bash
bin/autocrop-video detect input.mp4 --detection-width 480 --sample-count 32
```

Tune output encoding when cropping:

```bash
bin/autocrop-video crop input.mp4 output.mp4 --overwrite --crf 20 --preset slow
```

## How Detection Works

1. Sample low-resolution grayscale frames across the recording with `ffmpeg`.
2. Build temporal activity profiles to find the moving region that is clearly inside the real video.
3. Use edge-strength profiles to expand from that moving core to the actual rectangular video border.
4. Convert the detected box back to source-video coordinates and keep the crop dimensions even for H.264 output.

## Output Shape

`detect --format json` returns:

```json
{
  "bbox": {
    "x": 444,
    "y": 216,
    "width": 2484,
    "height": 1368,
    "crop_filter": "crop=2484:1368:444:216"
  },
  "source": "/absolute/path/to/input.mp4",
  "detection_width": 320,
  "sampled_frames": 24,
  "scaled_width": 320,
  "scaled_height": 175,
  "crop_filter": "crop=2484:1368:444:216"
}
```
