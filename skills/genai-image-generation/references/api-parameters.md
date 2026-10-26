# GenAI Image API and CLI Reference

## Contents

- [Connection](#connection)
- [Endpoints](#endpoints)
- [Image parameters](#image-parameters)
- [Edit-only parameters](#edit-only-parameters)
- [CLI-only options](#cli-only-options)
- [Environment variables](#environment-variables)
- [Constraints and upstream quirks](#constraints-and-upstream-quirks)
- [Examples](#examples)
- [Errors](#errors)

## Connection

The CLI talks to a GenAI2OpenAI-compatible proxy, not directly to the GenAI upstream.

- Default base URL: `http://127.0.0.1:5000/v1`
- Authentication: local proxy API key, sent as `Authorization: Bearer <key>`.
- The proxy's own GenAI upstream token is configured on the proxy and must not be put in the skill.

## Endpoints

| Operation | Endpoint | Content type |
| --- | --- | --- |
| Text-to-image | `POST {base_url}/images/generations` | `application/json` |
| Reference-image edit | `POST {base_url}/images/edits` | `multipart/form-data` |

Both return an OpenAI Images API shape (`created`, `data`, `usage`, plus `size`/`quality`/
`output_format`/`background` when provided by the proxy).

## Image parameters

| Parameter | Values | Default | Applies to | Notes |
| --- | --- | --- | --- | --- |
| `prompt` | string | required | both | Text description or edit instruction. |
| `model` | model id | `gpt-image-2.5-sunburst` | both | `gpt-image-2`, `gpt-image-2.5` are aliases. |
| `n` | integer 1-10 | `1` | both | Number of images requested. |
| `size` | `WIDTHxHEIGHT` | `1024x1024` | both | Total pixels must be 655360-8294400. |
| `quality` | `low`, `medium`, `high`, `auto` | `auto` | both | `standard`/`hd` are not accepted by the proxy CLI. |
| `style` | `vivid`, `natural` | `vivid` | both | OpenAI-compatible style hint. |
| `response_format` | `url`, `b64_json` | `url` | both | `b64_json` is decoded and saved locally. |
| `output_format` | `png`, `jpeg`, `webp` | `png` | both | File extension is derived from this value. |
| `output_compression` | integer 0-100 | proxy uses 80 | both | Only meaningful for JPEG/WebP. |
| `background` | `auto`, `opaque`, `transparent` | unset | both | Forwarded, but upstream currently returns opaque. |
| `extra-param` | `KEY=VALUE` | none | both | Repeatable escape hatch for new proxy parameters. |

`size` presets commonly used by the upstream image workbench include `1024x1024`,
`1536x1024`, `1024x1536`, `2048x1152`, `1152x2048`, `2048x1536`, and `1536x2048`.

## Edit-only parameters

| Parameter | Values | Default | Notes |
| --- | --- | --- | --- |
| `image` | file path | required | Repeat up to 4 times. Each file <= 10MB, total <= 25MB. |
| `mask` | file path | unset | Accepted for OpenAI compatibility but ignored by the proxy. |

Reference images are sent as raw base64 in the proxy's multipart fields `imageBase64` /
`imageBase64List`. The CLI handles that conversion.

## CLI-only options

| Option | Default | Purpose |
| --- | --- | --- |
| `--base-url` | `http://127.0.0.1:5000/v1` | Proxy base URL. |
| `--api-key` | env | Local proxy API key. |
| `--out-dir` | `./genai-images` | Directory for downloaded/decoded images. |
| `--prefix` | `image` | Saved filename prefix; unsafe characters are replaced with `-`. |
| `--timeout` | `600` | Request/download timeout in seconds. |
| `--no-save` | off | Do not write files; print result URLs instead. |
| `--json` | off | Print a machine-readable summary instead of human text. |
| `--dry-run` | off | Print the JSON/multipart request without sending it. |

## Environment variables

| Variable | Purpose |
| --- | --- |
| `GENAI_IMAGE_BASE_URL` | Overrides the proxy base URL. |
| `GENAI_IMAGE_API_KEY` | Local proxy API key. |
| `OPENAI_API_KEY` | Fallback proxy API key if the GenAI-specific variable is unset. |
| `GENAI_IMAGE_MODEL` | Default model id. |
| `GENAI_IMAGE_OUT_DIR` | Default output directory. |

## Constraints and upstream quirks

- The proxy is synchronous; one image usually takes about 15-40 seconds, and `n > 1` can take longer.
- Result URLs are relative upstream paths; the proxy expands them to
  `https://genaipic.shanghaitech.edu.cn/sys/common/static/...`.
- Transparent backgrounds are not currently honored by the upstream image model.
- The upstream has no mask semantics; `mask` is ignored.
- Image-generation models cannot be used with `/v1/chat/completions` or `/v1/responses`.
- The local result files are written by the CLI; `--no-save` skips downloads entirely.

## Examples

```bash
# One 1024x1024 PNG
python3 scripts/genai_image.py generate "a red cube on a wooden desk" \
  --quality high --out-dir ./out

# Multiple images with JPEG output and no local download
python3 scripts/genai_image.py generate "cyberpunk cat portrait" \
  --n 2 --size 1536x1024 --output-format jpeg --output-compression 90 --no-save

# Reference-image edit with up to 4 images
python3 scripts/genai_image.py edit "turn the cube blue" \
  --image cube.png --image desk.png --quality medium

# Machine-readable output and extra future parameter
python3 scripts/genai_image.py generate "minimal logo" --json \
  --extra-param moderation=auto
```

## Errors

| Situation | Result |
| --- | --- |
| Missing prompt | exit 2 with a usage message |
| Invalid `n`, size, quality, or `output_compression` | exit 1, validation error |
| Reference image missing or too large | exit 1, validation error |
| Proxy unreachable | exit 1, connection error |
| Proxy returns HTTP/API error | exit 1, upstream message is printed |
| Some images fail to download | other images are kept; failures are listed in the summary |
