from __future__ import annotations

import base64
import json
from pathlib import Path


def rebuild_raw_stream(log_path: str | Path, out_path: str | Path) -> None:
    log_path = Path(log_path)
    out_path = Path(out_path)

    out = bytearray()
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("event") != "read":
            continue
        data = record.get("data", {})
        raw_b64 = data.get("raw_bytes_b64", "")
        if not raw_b64:
            continue
        out.extend(base64.b64decode(raw_b64))

    out_path.write_bytes(out)
