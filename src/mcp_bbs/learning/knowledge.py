"""Knowledge base I/O operations."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def validate_knowledge_path(path: Path, root: Path) -> Path:
    """Ensure path is within knowledge root to prevent path injection.

    Args:
        path: Path to validate
        root: Knowledge root directory

    Returns:
        Resolved path if valid

    Raises:
        ValueError: If path is outside knowledge root
    """
    resolved = path.resolve()
    root_resolved = root.resolve()

    if not str(resolved).startswith(str(root_resolved)):
        raise ValueError(f"Path outside knowledge root: {path}")

    return resolved


_write_lock = asyncio.Lock()


async def append_md(path: Path, header: str, body: str, root: Path | None = None) -> str:
    """Append content to markdown file with path validation.

    Args:
        path: Path to markdown file
        header: Header for new file (used if file doesn't exist)
        body: Content to append
        root: Optional knowledge root for validation

    Returns:
        "ok" on success

    Raises:
        ValueError: If path is invalid
    """
    async with _write_lock:
        # Validate path if root provided
        if root:
            validate_knowledge_path(path, root)

        # Create directory and file if needed
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(f"# {header}\n\n", encoding="utf-8")

        # Append content
        with path.open("a", encoding="utf-8") as handle:
            handle.write(body)
            if not body.endswith("\n"):
                handle.write("\n")

    return "ok"
