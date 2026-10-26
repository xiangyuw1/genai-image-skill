#!/usr/bin/env python3
"""Generate and edit images through a GenAI2OpenAI-compatible proxy.

Uses only the Python standard library so it works in any agent environment.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:5000/v1"
DEFAULT_MODEL = "gpt-image-2.5-sunburst"
DEFAULT_OUT_DIR = "./genai-images"
MAX_REFERENCE_IMAGES = 4
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024

EXIT_API = 1
EXIT_USAGE = 2


class CliError(Exception):
    """An expected API/network error that should be printed without a traceback."""


class UsageError(CliError):
    """An invalid invocation or parameter."""


def env(name: str, fallback: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else fallback


def build_common_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--base-url",
        default=env("GENAI_IMAGE_BASE_URL", DEFAULT_BASE_URL),
        help=f"Proxy base URL (default: {DEFAULT_BASE_URL}; env: GENAI_IMAGE_BASE_URL)",
    )
    parser.add_argument(
        "--api-key",
        default=env("GENAI_IMAGE_API_KEY") or env("OPENAI_API_KEY"),
        help="Local proxy API key (env: GENAI_IMAGE_API_KEY or OPENAI_API_KEY)",
    )
    parser.add_argument(
        "--model",
        default=env("GENAI_IMAGE_MODEL", DEFAULT_MODEL),
        help=f"Image model id (default: {DEFAULT_MODEL}; env: GENAI_IMAGE_MODEL)",
    )
    parser.add_argument("--n", type=int, default=1, help="Number of images, 1-10 (default: 1)")
    parser.add_argument("--size", default="1024x1024", help="Image size, WIDTHxHEIGHT (default: 1024x1024)")
    parser.add_argument(
        "--quality",
        default="auto",
        choices=["low", "medium", "high", "auto"],
        help="Quality (default: auto)",
    )
    parser.add_argument(
        "--style",
        default="vivid",
        choices=["vivid", "natural"],
        help="Style (default: vivid)",
    )
    parser.add_argument(
        "--response-format",
        default="url",
        choices=["url", "b64_json"],
        help="Response format (default: url)",
    )
    parser.add_argument(
        "--output-format",
        default="png",
        choices=["png", "jpeg", "webp"],
        help="Output file format (default: png)",
    )
    parser.add_argument(
        "--output-compression",
        type=int,
        default=None,
        help="JPEG/WebP compression 0-100 (default: proxy uses 80)",
    )
    parser.add_argument(
        "--background",
        default=None,
        choices=["auto", "opaque", "transparent"],
        help="Background (upstream currently returns opaque)",
    )
    parser.add_argument(
        "--out-dir",
        default=env("GENAI_IMAGE_OUT_DIR", DEFAULT_OUT_DIR),
        help=f"Directory for saved images (default: {DEFAULT_OUT_DIR}; env: GENAI_IMAGE_OUT_DIR)",
    )
    parser.add_argument("--prefix", default="image", help="Saved filename prefix (default: image)")
    parser.add_argument("--timeout", type=float, default=600.0, help="Request timeout seconds (default: 600)")
    parser.add_argument("--no-save", action="store_true", help="Do not download/save results; print URLs only")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON summary")
    parser.add_argument("--dry-run", action="store_true", help="Print the request without sending it")
    parser.add_argument(
        "--extra-param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Extra form/JSON parameter (repeatable); forwarded to the proxy",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    common = build_common_parser()
    parser = argparse.ArgumentParser(
        description="Generate or edit images through a GenAI2OpenAI-compatible proxy.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate",
        parents=[common],
        help="Text-to-image generation",
        description="Generate images from a text prompt.",
    )
    generate.add_argument("prompt_pos", nargs="?", metavar="PROMPT", help="Image prompt")
    generate.add_argument("--prompt", dest="prompt_opt", help="Image prompt (alternative to positional)")

    edit = subparsers.add_parser(
        "edit",
        parents=[common],
        help="Reference-image generation/editing",
        description="Generate or edit images from one to four reference images.",
    )
    edit.add_argument("prompt_pos", nargs="?", metavar="PROMPT", help="Edit prompt")
    edit.add_argument("--prompt", dest="prompt_opt", help="Edit prompt (alternative to positional)")
    edit.add_argument(
        "--image",
        action="append",
        default=[],
        metavar="PATH",
        help="Reference image path; repeat up to 4 times",
    )
    edit.add_argument(
        "--mask",
        default=None,
        metavar="PATH",
        help="Optional mask file; accepted for OpenAI compatibility but ignored by the proxy",
    )
    return parser


def parse_extra_params(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in values:
        if "=" not in raw:
            raise UsageError(f"--extra-param must be KEY=VALUE, got: {raw}")
        key, value = raw.split("=", 1)
        key = key.strip()
        if not key:
            raise UsageError(f"--extra-param has an empty key: {raw}")
        result[key] = value
    return result


def build_headers(api_key: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "genai-image-skill/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def endpoint_url(base_url: str, command: str) -> str:
    suffix = "/images/edits" if command == "edit" else "/images/generations"
    return base_url.rstrip("/") + suffix


def summarize_http_error(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text[:500] or "(empty response body)"
    if isinstance(payload, dict):
        for key in ("error", "message", "errMsg"):
            value = payload.get(key)
            if isinstance(value, dict):
                message = value.get("message") or value.get("error")
                if message:
                    return str(message)
            if value:
                return str(value)
    return text[:500]


def http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = dict(headers)
    request_headers["Content-Type"] = "application/json"
    return http_post(url, body, request_headers, timeout)


def http_post_multipart(
    url: str,
    fields: dict[str, Any],
    files: list[tuple[str, Path]],
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    boundary = "----genai-image-" + uuid.uuid4().hex
    body = bytearray()

    for key, value in fields.items():
        body.extend(f'--{boundary}\r\n'.encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")

    for field_name, path in files:
        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body.extend(f'--{boundary}\r\n'.encode("utf-8"))
        body.extend(
            f'Content-Disposition: form-data; name="{field_name}"; filename="{path.name}"\r\n'.encode("utf-8")
        )
        body.extend(f'Content-Type: {content_type}\r\n\r\n'.encode("utf-8"))
        body.extend(content)
        body.extend(b"\r\n")

    body.extend(f'--{boundary}--\r\n'.encode("utf-8"))
    request_headers = dict(headers)
    request_headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    return http_post(url, bytes(body), request_headers, timeout)


def http_post(url: str, body: bytes, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise CliError(f"HTTP {exc.code}: {summarize_http_error(exc.read())}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"Cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise CliError(f"Request timed out after {timeout:g}s") from exc

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliError(f"Proxy returned non-JSON response: {raw[:300]!r}") from exc

    if isinstance(payload, dict) and payload.get("error"):
        raise CliError(str(payload["error"]))
    if not isinstance(payload, dict):
        raise CliError(f"Unexpected response type: {type(payload).__name__}")
    return payload


def safe_prefix(prefix: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", prefix).strip("-._")
    return cleaned or "image"


def extension_for(output_format: str) -> str:
    return "jpg" if output_format == "jpeg" else output_format


def download_image(url: str, destination: Path, timeout: float) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "genai-image-skill/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            destination.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise CliError(f"Failed to download {url}: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise CliError(f"Failed to download {url}: {exc.reason}") from exc


def save_results(payload: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, list) or not data:
        raise CliError("Proxy response contained no image data")

    out_dir = Path(args.out_dir).expanduser()
    if not args.no_save:
        out_dir.mkdir(parents=True, exist_ok=True)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    prefix = safe_prefix(args.prefix)
    extension = extension_for(args.output_format)
    saved: list[str] = []
    urls: list[str] = []
    failures: list[str] = []

    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if isinstance(url, str) and url:
            urls.append(url)

        if args.no_save:
            continue

        destination = out_dir / f"{prefix}_{stamp}_{index}.{extension}"
        if isinstance(item.get("b64_json"), str):
            try:
                destination.write_bytes(base64.b64decode(item["b64_json"]))
                saved.append(str(destination))
            except (ValueError, OSError) as exc:
                failures.append(f"item {index}: failed to decode b64_json: {exc}")
            continue

        if isinstance(url, str) and url:
            url_extension = Path(url.split("?", 1)[0]).suffix.lstrip(".")
            if url_extension and len(url_extension) <= 5:
                destination = out_dir / f"{prefix}_{stamp}_{index}.{url_extension}"
            try:
                download_image(url, destination, args.timeout)
                saved.append(str(destination))
            except (CliError, OSError) as exc:
                failures.append(f"item {index}: {exc}")
            continue

        failures.append(f"item {index}: response item has neither url nor b64_json")

    if not args.no_save and not saved:
        detail = "; ".join(failures) if failures else "no usable image items"
        raise CliError(f"No images were saved: {detail}")

    summary: dict[str, Any] = {
        "command": args.command,
        "model": args.model,
        "saved": saved,
        "urls": urls,
        "failures": failures,
        "created": payload.get("created"),
        "size": payload.get("size"),
        "quality": payload.get("quality"),
        "output_format": payload.get("output_format"),
        "background": payload.get("background"),
        "usage": payload.get("usage"),
    }
    return summary


def validate_size(size: str) -> str:
    normalized = str(size).strip().lower().replace("×", "x").replace("*", "x")
    if normalized == "auto":
        return "auto"
    parts = normalized.split("x")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise UsageError("--size must be WIDTHxHEIGHT or auto, e.g. 1024x1024")
    width, height = int(parts[0]), int(parts[1])
    pixels = width * height
    if pixels < 655360 or pixels > 8294400:
        raise UsageError(
            f"--size {width}x{height} is out of range; total pixels must be 655360-8294400"
        )
    return f"{width}x{height}"


def validate_common(args: argparse.Namespace) -> None:
    if not args.model or not isinstance(args.model, str):
        raise UsageError("--model must be a non-empty string")
    if args.n < 1 or args.n > 10:
        raise UsageError("--n must be between 1 and 10")
    if args.output_compression is not None and not 0 <= args.output_compression <= 100:
        raise UsageError("--output-compression must be between 0 and 100")
    args.size = validate_size(args.size)


def validate_images(paths: list[str], mask: str | None) -> list[Path]:
    if not paths:
        raise UsageError("edit requires at least one --image PATH")
    if len(paths) > MAX_REFERENCE_IMAGES:
        raise UsageError(f"edit supports at most {MAX_REFERENCE_IMAGES} reference images")
    resolved: list[Path] = []
    total = 0
    for raw in paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise UsageError(f"Reference image not found: {path}")
        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise UsageError(f"Reference image exceeds 10MB: {path}")
        total += size
        resolved.append(path)
    if total > MAX_TOTAL_BYTES:
        raise UsageError("Total reference image size exceeds 25MB")
    if mask:
        mask_path = Path(mask).expanduser()
        if not mask_path.is_file():
            raise UsageError(f"Mask file not found: {mask_path}")
        print("warning: --mask is accepted for compatibility but ignored by the proxy", file=sys.stderr)
    return resolved


def build_generation_payload(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "style": args.style,
        "response_format": args.response_format,
        "output_format": args.output_format,
    }
    if args.output_compression is not None:
        payload["output_compression"] = args.output_compression
    if args.background:
        payload["background"] = args.background
    payload.update(parse_extra_params(args.extra_param))
    return payload


def build_edit_fields(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "model": args.model,
        "prompt": prompt,
        "n": args.n,
        "size": args.size,
        "quality": args.quality,
        "style": args.style,
        "response_format": args.response_format,
        "output_format": args.output_format,
    }
    if args.output_compression is not None:
        fields["output_compression"] = args.output_compression
    if args.background:
        fields["background"] = args.background
    fields.update(parse_extra_params(args.extra_param))
    return fields


def print_human_summary(summary: dict[str, Any], no_save: bool) -> None:
    for path in summary["saved"]:
        print(f"saved: {path}")
    if no_save:
        for url in summary["urls"]:
            print(f"url: {url}")
    else:
        for url in summary["urls"]:
            print(f"source: {url}")
    for failure in summary["failures"]:
        print(f"warning: {failure}", file=sys.stderr)
    usage = summary.get("usage")
    if isinstance(usage, dict) and usage.get("total_tokens") is not None:
        print(f"usage: {usage.get('total_tokens')} tokens")
    metadata = ", ".join(
        f"{key}={summary[key]}"
        for key in ("model", "size", "quality", "output_format", "background")
        if summary.get(key) is not None
    )
    if metadata:
        print(f"meta: {metadata}")


def run(args: argparse.Namespace) -> int:
    validate_common(args)

    prompt = args.prompt_opt or args.prompt_pos
    if not prompt or not str(prompt).strip():
        raise UsageError("a non-empty prompt is required")
    prompt = str(prompt)

    url = endpoint_url(args.base_url, args.command)
    headers = build_headers(args.api_key)

    if args.command == "edit":
        images = validate_images(args.image, args.mask)
        fields = build_edit_fields(args, prompt)
        extra_files = [("image", path) for path in images]
        if args.mask:
            extra_files.append(("mask", Path(args.mask).expanduser()))

        if args.dry_run:
            dry_run = {
                "url": url,
                "fields": fields,
                "files": [{"field": field, "path": str(path)} for field, path in extra_files],
            }
            print(json.dumps(dry_run, ensure_ascii=False, indent=2))
            return 0

        payload = http_post_multipart(url, fields, extra_files, headers, args.timeout)
        summary = save_results(payload, args)
    else:
        payload = build_generation_payload(args, prompt)
        if args.dry_run:
            dry_run = {"url": url, "payload": payload}
            print(json.dumps(dry_run, ensure_ascii=False, indent=2))
            return 0

        response = http_post_json(url, payload, headers, args.timeout)
        summary = save_results(response, args)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_human_summary(summary, args.no_save)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return run(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_API
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
