from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WatchSettings:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    protocol: str = "raw"  # "raw" or "json"
    metadata: bool = False
    send_clear: bool = False
    include_snapshot_text: bool = False


watch_settings = WatchSettings()
