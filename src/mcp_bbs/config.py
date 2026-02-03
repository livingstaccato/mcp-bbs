"""Configuration module for mcp-bbs.

Handles XDG-compliant directory resolution and knowledge base setup.
"""

import os
import warnings
from pathlib import Path

try:
    from platformdirs import user_data_dir

    PLATFORMDIRS_AVAILABLE = True
except ImportError:
    PLATFORMDIRS_AVAILABLE = False


def get_default_knowledge_root() -> Path:
    """Get the default knowledge root directory.

    Priority order:
    1. BBS_KNOWLEDGE_ROOT environment variable
    2. XDG/platform-specific directory via platformdirs
    3. Fallback to .bbs-knowledge in current directory (if platformdirs unavailable)

    Returns:
        Path to the knowledge root directory
    """
    # Priority 1: Environment variable override
    env_root = os.getenv("BBS_KNOWLEDGE_ROOT")
    if env_root:
        return Path(env_root)

    # Priority 2: XDG/platform-specific directory
    if PLATFORMDIRS_AVAILABLE:
        xdg_path = user_data_dir("mcp-bbs", "mcp-bbs")
        return Path(xdg_path)

    # Priority 3: Fallback (if platformdirs not available)
    warnings.warn(
        "platformdirs not available, using .bbs-knowledge in current directory. "
        "Install platformdirs for XDG-compliant paths.",
        stacklevel=2,
    )
    return Path.cwd() / ".bbs-knowledge"


def validate_knowledge_root(knowledge_root: Path) -> Path:
    """Validate and create knowledge root directory structure.

    Creates the directory and required subdirectories if they don't exist:
    - knowledge_root/
    - knowledge_root/shared/
    - knowledge_root/shared/bbs/

    Args:
        knowledge_root: Path to the knowledge root directory

    Returns:
        The validated knowledge root path

    Raises:
        OSError: If directory creation fails
    """
    # Create main directory
    knowledge_root.mkdir(parents=True, exist_ok=True)

    # Create standard subdirectories
    shared_dir = knowledge_root / "shared"
    shared_dir.mkdir(exist_ok=True)

    bbs_dir = shared_dir / "bbs"
    bbs_dir.mkdir(exist_ok=True)

    return knowledge_root
