#!/usr/bin/env python3
"""Generate diagrams from Mermaid files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import structlog

log = structlog.get_logger()


def generate_diagrams(format: str = "svg") -> int:
    """Generate diagrams in specified format.

    Args:
        format: Output format ("svg" or "png")

    Returns:
        Exit code (0 for success, 1 for error)
    """
    try:
        import mermaid
    except ImportError:
        log.error(
            "mermaid_not_installed",
            hint="Install with: uv pip install -e '.[dev]'",
        )
        return 1

    diagrams_dir = Path(__file__).parent / "diagrams"
    mmd_files = sorted(diagrams_dir.glob("*.mmd"))

    if not mmd_files:
        log.warning("no_mermaid_files", path=str(diagrams_dir))
        return 0

    success_count = 0
    for mmd_file in mmd_files:
        try:
            output_file = mmd_file.with_suffix(f".{format}")

            # Skip if output is newer than source
            if output_file.exists():
                mmd_mtime = mmd_file.stat().st_mtime
                out_mtime = output_file.stat().st_mtime
                if out_mtime > mmd_mtime:
                    log.info(
                        "skipped",
                        file=output_file.name,
                        reason="up_to_date",
                    )
                    success_count += 1
                    continue

            log.info(
                "generating",
                source=mmd_file.name,
                target=output_file.name,
                format=format,
            )

            # Read mermaid content
            code = mmd_file.read_text()

            # Generate diagram based on format
            if format == "svg":
                mermaid.Mermaid(code).to_svg(output_file)
            elif format == "png":
                mermaid.Mermaid(code).to_png(output_file)
            else:
                log.error("unsupported_format", format=format)
                return 1

            log.info("generated", file=output_file.name, size=output_file.stat().st_size)
            success_count += 1

        except Exception as e:
            log.error(
                "generation_failed",
                file=mmd_file.name,
                error=str(e),
                error_type=type(e).__name__,
            )
            return 1

    log.info(
        "diagram_generation_complete",
        count=success_count,
        format=format,
    )
    return 0


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    parser = argparse.ArgumentParser(
        description="Generate diagrams from Mermaid source files"
    )
    parser.add_argument(
        "--format",
        choices=["svg", "png", "both"],
        default="svg",
        help="Output format (default: svg)",
    )
    args = parser.parse_args()

    if args.format == "both":
        # Generate SVG first, then PNG
        exit_code = generate_diagrams("svg")
        if exit_code == 0:
            exit_code = generate_diagrams("png")
        return exit_code
    else:
        return generate_diagrams(args.format)


if __name__ == "__main__":
    sys.exit(main())
