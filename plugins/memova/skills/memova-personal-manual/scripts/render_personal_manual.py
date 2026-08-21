#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "memova_personal_manual_document_v1"
MARKDOWN_NAME = "personal-manual.md"
HTML_NAME = "personal-manual.html"
MAX_SOURCE_BYTES = 500_000


def main() -> int:
    parser = argparse.ArgumentParser(description="Render matching Personal Manual Markdown/HTML.")
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    source_path = Path(args.input_json).expanduser().resolve()
    raw = source_path.read_bytes()
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError(f"structured source exceeds {MAX_SOURCE_BYTES} UTF-8 bytes")
    document = json.loads(raw.decode("utf-8"))
    normalized = validate_document(document)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        output_dir.chmod(0o700)
    except OSError:
        pass
    markdown_path = output_dir / MARKDOWN_NAME
    html_path = output_dir / HTML_NAME
    markdown = render_markdown(normalized)
    html_content = render_html(normalized)
    markdown_path.write_text(markdown, encoding="utf-8", newline="\n")
    html_path.write_text(html_content, encoding="utf-8", newline="\n")
    for path in (markdown_path, html_path):
        try:
            path.chmod(0o600)
        except OSError:
            pass
    result = {
        "markdown_path": str(markdown_path),
        "html_path": str(html_path),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(html_content.encode("utf-8")).hexdigest(),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def validate_document(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {
        "schema_version",
        "language",
        "title",
        "subtitle",
        "overview",
        "sections",
    }:
        raise ValueError("structured source has unsupported fields")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version must be {SCHEMA_VERSION}")
    language = _text(value.get("language"), "language", maximum=35)
    if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", language):
        raise ValueError("language must be a BCP 47-style language tag")
    title = _text(value.get("title"), "title", maximum=255)
    subtitle = _optional_text(value.get("subtitle"), "subtitle", maximum=500)
    overview = _text_list(value.get("overview"), "overview", maximum_items=20)
    raw_sections = value.get("sections")
    if not isinstance(raw_sections, list) or not 1 <= len(raw_sections) <= 30:
        raise ValueError("sections must contain 1..30 items")
    sections: list[dict[str, Any]] = []
    for index, section in enumerate(raw_sections):
        if not isinstance(section, dict) or set(section) - {"heading", "paragraphs", "bullets"}:
            raise ValueError(f"sections[{index}] has unsupported fields")
        paragraphs = _text_list(
            section.get("paragraphs", []), f"sections[{index}].paragraphs", maximum_items=30
        )
        bullets = _text_list(
            section.get("bullets", []), f"sections[{index}].bullets", maximum_items=50
        )
        if not paragraphs and not bullets:
            raise ValueError(f"sections[{index}] must contain paragraphs or bullets")
        sections.append(
            {
                "heading": _text(section.get("heading"), f"sections[{index}].heading", 255),
                "paragraphs": paragraphs,
                "bullets": bullets,
            }
        )
    return {
        "language": language,
        "title": title,
        "subtitle": subtitle,
        "overview": overview,
        "sections": sections,
    }


def render_markdown(document: dict[str, Any]) -> str:
    parts = [f"# {document['title']}"]
    if document["subtitle"]:
        parts.extend(["", document["subtitle"]])
    for paragraph in document["overview"]:
        parts.extend(["", paragraph])
    for section in document["sections"]:
        parts.extend(["", f"## {section['heading']}"])
        for paragraph in section["paragraphs"]:
            parts.extend(["", paragraph])
        if section["bullets"]:
            parts.append("")
            parts.extend(f"- {item}" for item in section["bullets"])
    return "\n".join(parts).rstrip() + "\n"


def render_html(document: dict[str, Any]) -> str:
    language = html.escape(document["language"], quote=True)
    body: list[str] = [
        f'<!doctype html><html lang="{language}"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        f"<title>{html.escape(document['title'])}</title>",
        "<style>"
        "body{margin:0;background:#f5f7fb;color:#172033;"
        "font:16px/1.65 system-ui,-apple-system,sans-serif}"
        "main{max-width:860px;margin:0 auto;padding:56px 24px 80px}"
        "header,section{background:#fff;border:1px solid #e7eaf0;border-radius:18px;"
        "padding:28px;margin-bottom:18px;box-shadow:0 8px 30px #1720330d}"
        "h1,h2{line-height:1.2}h1{font-size:2.4rem;margin:0}"
        "h2{font-size:1.35rem;margin:0 0 14px}"
        ".subtitle{color:#657087;font-size:1.1rem}"
        "p:last-child,ul:last-child{margin-bottom:0}li+li{margin-top:8px}"
        "@media(max-width:600px){main{padding:24px 14px 48px}"
        "header,section{padding:20px}h1{font-size:2rem}}"
        "</style>",
        '</head><body data-memova-personal-manual="v1"><main><header>',
        f"<h1>{html.escape(document['title'])}</h1>",
    ]
    if document["subtitle"]:
        body.append(f'<p class="subtitle">{html.escape(document["subtitle"])}</p>')
    body.extend(f"<p>{html.escape(paragraph)}</p>" for paragraph in document["overview"])
    body.append("</header>")
    for section in document["sections"]:
        body.extend(["<section>", f"<h2>{html.escape(section['heading'])}</h2>"])
        body.extend(f"<p>{html.escape(paragraph)}</p>" for paragraph in section["paragraphs"])
        if section["bullets"]:
            body.append("<ul>")
            body.extend(f"<li>{html.escape(item)}</li>" for item in section["bullets"])
            body.append("</ul>")
        body.append("</section>")
    body.append("</main></body></html>\n")
    return "".join(body)


def _text(value: Any, field: str, maximum: int = 10_000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{field} must be non-empty text up to {maximum} characters")
    return value.strip()


def _optional_text(value: Any, field: str, maximum: int) -> str | None:
    if value is None or value == "":
        return None
    return _text(value, field, maximum)


def _text_list(value: Any, field: str, maximum_items: int) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum_items:
        raise ValueError(f"{field} must be a list with at most {maximum_items} items")
    return [_text(item, f"{field}[]") for item in value]


if __name__ == "__main__":
    raise SystemExit(main())
