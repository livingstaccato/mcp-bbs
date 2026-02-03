#!/usr/bin/env python3
"""Generate SVG diagrams from Mermaid files."""

from __future__ import annotations

from pathlib import Path

import mermaid

DIAGRAMS_DIR = Path(__file__).parent / "diagrams"


def generate_diagram(mmd_file: Path) -> None:
    """Generate SVG from Mermaid file."""
    svg_file = mmd_file.with_suffix(".svg")
    print(f"Generating {svg_file.name} from {mmd_file.name}...")

    # Read mermaid content
    mermaid_code = mmd_file.read_text()

    # Generate SVG using mermaid-py
    mermaid.Mermaid(mermaid_code).to_svg(svg_file)

    print(f"✓ Generated {svg_file}")


def main() -> None:
    """Generate all diagrams."""
    for mmd_file in DIAGRAMS_DIR.glob("*.mmd"):
        generate_diagram(mmd_file)


if __name__ == "__main__":
    main()
