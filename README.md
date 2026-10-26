# genai-image-skill

A portable Agent Skill plus a dependency-free CLI for generating and editing images through a
[GenAI2OpenAI](https://github.com/xiangyuw1/GenAI2OpenAI)-compatible proxy.

The skill exposes the proxy's OpenAI Images API:

- `POST /v1/images/generations` — text to image
- `POST /v1/images/edits` — one to four reference images
- Model: `gpt-image-2.5-sunburst` (aliases: `gpt-image-2`, `gpt-image-2.5`)

All proxy-supported image parameters are wired through the CLI: `model`, `prompt`, `n`, `size`,
`quality`, `style`, `response_format`, `output_format`, `output_compression`, `background`,
and up to four reference images. Unknown future parameters can be forwarded with `--extra-param`.

## Structure

```text
genai-image-skill/
├── install.sh
├── README.md
└── skills/
    └── genai-image-generation/
        ├── SKILL.md
        ├── agents/openai.yaml
        ├── references/api-parameters.md
        └── scripts/genai_image.py
```

The skill folder follows the standard Agent Skills layout (`SKILL.md` + optional `scripts/` and
`references/`), so it can be copied into Claude Code, OpenCode, Codex, or any agent that supports
the `SKILL.md` convention.

## Install

Auto-detect installed agents and symlink the skill (recommended):

```bash
./install.sh
```

Choose targets explicitly:

```bash
./install.sh --target opencode --target codex --target agents
./install.sh --target claude --copy
./install.sh --target ~/my-agent/skills
```

Other commands:

```bash
./install.sh --list        # show resolved destinations
./install.sh --uninstall   # remove installed copies/symlinks
./install.sh --help
```

Manual install is also fine — copy `skills/genai-image-generation/` into one of:

| Agent | Skills directory |
| --- | --- |
| Claude Code | `~/.claude/skills/` or `.claude/skills/` in a project |
| OpenCode | `${XDG_CONFIG_HOME:-~/.config}/opencode/skills/` or `.opencode/skills/` |
| Codex | `${CODEX_HOME:-~/.codex}/skills/` |
| Generic Agent Skills | `~/.agents/skills/` |

For a project-local install, place the folder under `.claude/skills/`, `.opencode/skills/`, or
the equivalent directory for your agent.

## Use

The target proxy must be running. Default endpoint is `http://127.0.0.1:5000/v1`.

```bash
# Text to image
python3 skills/genai-image-generation/scripts/genai_image.py generate \
  "a red cube on a wooden desk" \
  --size 1024x1024 --quality high --out-dir ./genai-images

# Multiple images, JPEG output
python3 skills/genai-image-generation/scripts/genai_image.py generate \
  "cyberpunk cat portrait" \
  --n 2 --size 1536x1024 --output-format jpeg --output-compression 90

# Reference-image edit (up to 4)
python3 skills/genai-image-generation/scripts/genai_image.py edit \
  "turn the cube blue" \
  --image cube.png --image desk.png --quality medium
```

If the proxy enforces a local API key:

```bash
export GENAI_IMAGE_API_KEY="your-local-proxy-key"
```

Configuration environment variables:

| Variable | Purpose |
| --- | --- |
| `GENAI_IMAGE_BASE_URL` | Proxy base URL, default `http://127.0.0.1:5000/v1` |
| `GENAI_IMAGE_API_KEY` | Local proxy API key |
| `OPENAI_API_KEY` | Fallback API key if the GenAI-specific variable is unset |
| `GENAI_IMAGE_MODEL` | Default image model |
| `GENAI_IMAGE_OUT_DIR` | Default output directory |

Run `python3 skills/genai-image-generation/scripts/genai_image.py --help` or read
[references/api-parameters.md](skills/genai-image-generation/references/api-parameters.md)
for every parameter, constraint, and example.

## Notes

- The CLI uses only the Python standard library (Python 3.9+).
- Image requests are synchronous and usually take 15-40 seconds each.
- `--no-save` prints result URLs without downloading; `--json` prints a machine-readable summary.
- `--dry-run` shows the exact request without sending it.
- The proxy currently returns opaque backgrounds even when `transparent` is requested, and
  ignores `mask` because the upstream has no mask semantics.
- The skill never stores or asks for the upstream GenAI token; only the proxy's local API key is used.

## Status

This repository is initialized locally. Add a remote when you want to publish it:

```bash
git remote add origin <your-repo-url>
git push -u origin main
```
