#!/usr/bin/env python3
"""
PlantUML to SVG Converter
=========================
Converts PlantUML diagrams (.puml files or Markdown code blocks) into high-quality
SVG vector images suitable for GitHub Markdown documentation.

Features:
- Zero external dependencies (uses standard Python library: urllib, zlib, re, argparse).
- Supports PlantUML text encoding algorithm for instant cloud rendering with sprite icon support.
- Extracts ```plantuml ... ``` blocks from Markdown files and syncs them to SVG.
- Automatically saves source .puml files alongside generated .svg files for easy editing.

Usage examples:
  python scripts/render_plantuml.py --file docs/diagrams/mode1_incoming.puml
  python scripts/render_plantuml.py --dir docs/diagrams/
  python scripts/render_plantuml.py --sync-readme
  python scripts/render_plantuml.py --markdown README.md --output-dir docs/diagrams --replace-in-markdown
"""

import os
import sys
import re
import zlib
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Tuple, Optional

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
DEFAULT_SERVER = "https://www.plantuml.com/plantuml"


def encode_plantuml(text: str) -> str:
    """
    Encodes PlantUML text using zlib deflate and PlantUML custom 6-bit encoding.
    Algorithm:
    1. UTF-8 encode text
    2. Deflate compress (zlib.compress)
    3. Strip zlib 2-byte header and 4-byte checksum
    4. Map 3 bytes into 4 characters using 6-bit alphabet
    """
    zlib_compressed = zlib.compress(text.encode("utf-8"))
    deflated = zlib_compressed[2:-4]

    def encode_3bytes(b1: int, b2: int, b3: int) -> str:
        c1 = b1 >> 2
        c2 = ((b1 & 0x3) << 4) | (b2 >> 4)
        c3 = ((b2 & 0xF) << 2) | (b3 >> 6)
        c4 = b3 & 0x3F
        return (
            PLANTUML_ALPHABET[c1 & 0x3F]
            + PLANTUML_ALPHABET[c2 & 0x3F]
            + PLANTUML_ALPHABET[c3 & 0x3F]
            + PLANTUML_ALPHABET[c4 & 0x3F]
        )

    res = []
    i = 0
    length = len(deflated)
    while i < length:
        b1 = deflated[i]
        b2 = deflated[i + 1] if i + 1 < length else 0
        b3 = deflated[i + 2] if i + 2 < length else 0

        if i + 2 < length:
            res.append(encode_3bytes(b1, b2, b3))
        elif i + 1 < length:
            c1 = b1 >> 2
            c2 = ((b1 & 0x3) << 4) | (b2 >> 4)
            c3 = ((b2 & 0xF) << 2)
            res.append(PLANTUML_ALPHABET[c1 & 0x3F] + PLANTUML_ALPHABET[c2 & 0x3F] + PLANTUML_ALPHABET[c3 & 0x3F])
        else:
            c1 = b1 >> 2
            c2 = ((b1 & 0x3) << 4)
            res.append(PLANTUML_ALPHABET[c1 & 0x3F] + PLANTUML_ALPHABET[c2 & 0x3F])
        i += 3

    return "".join(res)


def render_puml_to_svg(puml_content: str, server_url: str = DEFAULT_SERVER) -> str:
    """
    Sends encoded PlantUML content to the server and returns the SVG string.
    """
    puml_trimmed = puml_content.strip()
    if not puml_trimmed.startswith("@startuml"):
        puml_trimmed = f"@startuml\n{puml_trimmed}"
    if not puml_trimmed.endswith("@enduml"):
        puml_trimmed = f"{puml_trimmed}\n@enduml"

    encoded = encode_plantuml(puml_trimmed)
    url = f"{server_url.rstrip('/')}/svg/{encoded}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) LiveSpeech-PlantUML-Converter/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise RuntimeError(f"Server returned HTTP status {resp.status}")
        svg_content = resp.read().decode("utf-8")
        return svg_content


def convert_file(puml_path: Path, output_svg_path: Optional[Path] = None, server_url: str = DEFAULT_SERVER) -> Path:
    """
    Converts a single .puml file into a .svg file.
    """
    if output_svg_path is None:
        output_svg_path = puml_path.with_suffix(".svg")

    print(f"🔄 Converting: {puml_path} -> {output_svg_path} ...")
    content = puml_path.read_text(encoding="utf-8")
    svg = render_puml_to_svg(content, server_url)

    output_svg_path.parent.mkdir(parents=True, exist_ok=True)
    output_svg_path.write_text(svg, encoding="utf-8")
    print(f"✅ Generated: {output_svg_path} ({len(svg):,} bytes)")
    return output_svg_path


def convert_directory(dir_path: Path, server_url: str = DEFAULT_SERVER) -> List[Path]:
    """
    Converts all .puml files in a directory to .svg.
    """
    puml_files = sorted(dir_path.glob("*.puml"))
    if not puml_files:
        print(f"ℹ️ No .puml files found in {dir_path}")
        return []

    results = []
    for puml_file in puml_files:
        svg_path = convert_file(puml_file, server_url=server_url)
        results.append(svg_path)
    return results


def process_markdown_file(
    md_path: Path,
    output_dir: Path,
    replace_in_md: bool = True,
    server_url: str = DEFAULT_SERVER,
    naming_prefix: Optional[List[str]] = None,
) -> List[Tuple[Path, Path]]:
    """
    Extracts all ```plantuml code blocks from a Markdown file,
    saves them as .puml and renders them as .svg files in output_dir,
    and optionally replaces the raw code block with Markdown image tags.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    md_text = md_path.read_text(encoding="utf-8")

    pattern = re.compile(r"```plantuml\s*\n(.*?)```", re.DOTALL)
    matches = list(pattern.finditer(md_text))

    if not matches:
        print(f"ℹ️ No ```plantuml code blocks found in {md_path}")
        return []

    print(f"🔍 Found {len(matches)} PlantUML diagram(s) in {md_path}")
    results = []

    # Map standard diagram names if provided, otherwise deduce from nearby headers
    default_names = naming_prefix or []

    for idx, match in enumerate(matches, 1):
        puml_code = match.group(1).strip()
        
        # Determine diagram name
        if idx - 1 < len(default_names):
            name = default_names[idx - 1]
        else:
            # Look at previous 300 chars for header
            before_text = md_text[: match.start()]
            headers = re.findall(r"#{2,5}\s*(.+)", before_text)
            if headers:
                header = headers[-1].strip()
                # sanitize to filename
                clean_name = re.sub(r"[^a-zA-Z0-9_\-]+", "_", header).strip("_").lower()
                name = clean_name or f"diagram_{idx}"
            else:
                name = f"diagram_{idx}"

        puml_file = output_dir / f"{name}.puml"
        svg_file = output_dir / f"{name}.svg"

        print(f"📝 Saving source: {puml_file}")
        puml_file.write_text(puml_code + "\n", encoding="utf-8")

        print(f"🎨 Rendering SVG: {svg_file}")
        svg_content = render_puml_to_svg(puml_code, server_url)
        svg_file.write_text(svg_content, encoding="utf-8")
        print(f"✅ Generated {svg_file.name} ({len(svg_content):,} bytes)")

        results.append((puml_file, svg_file))

    if replace_in_md:
        # Re-build markdown with relative image paths
        def replacer(match_obj):
            replacer.count += 1
            idx = replacer.count
            if idx - 1 < len(results):
                _, svg_p = results[idx - 1]
                # Relative path from markdown file to SVG file
                try:
                    rel_path = os.path.relpath(svg_p, md_path.parent).replace("\\", "/")
                except ValueError:
                    rel_path = str(svg_p).replace("\\", "/")
                return f'<p align="center">\n  <img src="{rel_path}" alt="{svg_p.stem}" width="100%">\n</p>'
            return match_obj.group(0)

        replacer.count = 0
        new_md_text = pattern.sub(replacer, md_text)
        md_path.write_text(new_md_text, encoding="utf-8")
        print(f"📄 Updated {md_path} with rendered SVG image references.")

    return results


def sync_readme(repo_root: Path, server_url: str = DEFAULT_SERVER) -> None:
    """
    Standard project sync:
    1. Extracts/renders all diagrams in README.md into docs/diagrams/
    2. Names them mode1_incoming, mode2_outgoing, mode3_bidirectional
    3. Replaces raw plantuml blocks in README.md with centered SVG image embeddings.
    """
    readme_path = repo_root / "README.md"
    diagrams_dir = repo_root / "docs" / "diagrams"

    if not readme_path.exists():
        print(f"❌ Error: README.md not found at {readme_path}")
        sys.exit(1)

    preset_names = ["mode1_incoming", "mode2_outgoing", "mode3_bidirectional"]
    print(f"🚀 Syncing PlantUML diagrams from {readme_path} to {diagrams_dir}...")
    results = process_markdown_file(
        md_path=readme_path,
        output_dir=diagrams_dir,
        replace_in_md=True,
        server_url=server_url,
        naming_prefix=preset_names,
    )
    print(f"✨ Successfully synced {len(results)} diagrams!")


def main():
    parser = argparse.ArgumentParser(
        description="Convert PlantUML diagrams to SVG vector images (Zero dependencies)."
    )
    parser.add_argument("--file", "-f", type=Path, help="Path to a single .puml file to convert to .svg")
    parser.add_argument("--out", "-o", type=Path, help="Optional output SVG file path (when using --file)")
    parser.add_argument("--dir", "-d", type=Path, help="Path to a directory containing .puml files to convert")
    parser.add_argument("--markdown", "-m", type=Path, help="Path to a Markdown file with ```plantuml code blocks")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/diagrams"),
        help="Directory to save generated .puml and .svg files (default: docs/diagrams)",
    )
    parser.add_argument(
        "--replace-in-markdown",
        action="store_true",
        help="Replace ```plantuml blocks in markdown file with SVG image links",
    )
    parser.add_argument(
        "--sync-readme",
        action="store_true",
        help="Extract diagrams from README.md, render SVGs into docs/diagrams/, and update README.md",
    )
    parser.add_argument(
        "--server",
        type=str,
        default=DEFAULT_SERVER,
        help=f"PlantUML server URL (default: {DEFAULT_SERVER})",
    )

    args = parser.parse_args()

    repo_root = Path.cwd()

    try:
        if args.sync_readme:
            sync_readme(repo_root, server_url=args.server)
        elif args.file:
            convert_file(args.file, args.out, server_url=args.server)
        elif args.dir:
            convert_directory(args.dir, server_url=args.server)
        elif args.markdown:
            process_markdown_file(
                md_path=args.markdown,
                output_dir=args.output_dir,
                replace_in_md=args.replace_in_markdown,
                server_url=args.server,
            )
        else:
            # Default behavior when invoked without arguments:
            # Check docs/diagrams and render all .puml files found
            default_dir = repo_root / "docs" / "diagrams"
            if default_dir.exists() and list(default_dir.glob("*.puml")):
                print(f"📁 Auto-detecting diagrams in {default_dir}...")
                convert_directory(default_dir, server_url=args.server)
            else:
                parser.print_help()
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
