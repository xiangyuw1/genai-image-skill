---
name: genai-image-generation
description: Generate and edit images through a GenAI2OpenAI-compatible proxy, including all supported OpenAI Images API parameters (model, n, size, quality, style, response_format, output_format, output_compression, background) and up to four reference images. Use when the user asks to create, draw, generate, or edit images / 生成图片 / 画图 / 文生图 / 图像编辑 / 改图, mentions gpt-image-2.5-sunburst or GPT-Image-2.5-Sunburst, or asks to call /v1/images/generations or /v1/images/edits.
---

# GenAI Image Generation

Use the bundled standard-library CLI. Do not hand-write HTTP requests unless the CLI
cannot express the request.

## Prerequisites

- A GenAI2OpenAI-compatible proxy is running. Default: `http://127.0.0.1:5000/v1`.
- If the proxy enforces a local key, export `GENAI_IMAGE_API_KEY` (or pass `--api-key`).
- Do not ask for or handle the proxy's upstream GenAI token; the proxy owns it.
- Python 3.9+ is enough; the script has no third-party dependencies.

## Quick start

Run from this skill directory:

```bash
# Text to image
python3 scripts/genai_image.py generate "a red cube on a wooden desk" \
  --size 1024x1024 --quality high --out-dir ./genai-images

# Reference-image edit, up to 4 images
python3 scripts/genai_image.py edit "turn the cube blue" \
  --image cube.png --image desk.png --out-dir ./genai-images
```

Defaults: model `gpt-image-2.5-sunburst`, `n=1`, `size=1024x1024`, `quality=auto`,
`style=vivid`, `response_format=url`, `output_format=png`, output directory `./genai-images`.

## Workflow

1. Decide the operation:
   - No reference image: `generate`.
   - One to four reference images: `edit`.
2. Build the prompt from the user's request. Keep it descriptive and self-contained.
3. Choose parameters. Always pass `--out-dir` when the user expects files in a specific place.
4. Run the CLI and report the saved paths and/or URLs.
5. If the user wants the raw API response, add `--json`.
6. If a new proxy parameter appears, forward it with `--extra-param KEY=VALUE`.

Do not invent parameters the proxy does not document. Do not call `/v1/chat/completions`
with an image model; the proxy rejects it.

## Parameter summary

| Parameter | CLI flag | Notes |
| --- | --- | --- |
| model | `--model` | `gpt-image-2.5-sunburst`; aliases `gpt-image-2`, `gpt-image-2.5` |
| count | `--n` | 1-10 |
| size | `--size` | `WIDTHxHEIGHT`; 655360-8294400 total pixels |
| quality | `--quality` | `low` / `medium` / `high` / `auto` |
| style | `--style` | `vivid` / `natural` |
| response | `--response-format` | `url` / `b64_json` |
| file format | `--output-format` | `png` / `jpeg` / `webp` |
| compression | `--output-compression` | 0-100, JPEG/WebP |
| background | `--background` | `auto` / `opaque` / `transparent`; upstream may return opaque |
| reference images | `--image PATH` | edit only, up to 4, 10MB each, 25MB total |
| mask | `--mask PATH` | accepted but ignored by the proxy |

For the complete parameter table, constraints, environment variables, and examples, read
[references/api-parameters.md](references/api-parameters.md).

## Output behavior

- `response_format=url`: downloads each image into `--out-dir`, prints `saved:` paths.
- `response_format=b64_json`: decodes and saves each image locally.
- `--no-save`: does not write files; prints URLs. Use when the caller only needs links.
- `--json`: prints `saved`, `urls`, `usage`, metadata, and any download failures.
- Image generation is synchronous and typically takes 15-40 seconds per image.

## Failure handling

- Proxy/API errors: report the printed upstream message and adjust the prompt or parameters.
- Validation errors (bad size, too many images, missing file): fix the invocation; do not retry blindly.
- Network errors: verify `--base-url` and that the proxy is running.
- Partial download failures: keep successful files and report the failures from the summary.
