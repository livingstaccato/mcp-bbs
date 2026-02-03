from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild raw ANSI stream from JSONL log.")
    parser.add_argument("log", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()

    out = bytearray()
    for line in args.log.read_text(encoding="utf-8").splitlines():
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

    args.out.write_bytes(out)


if __name__ == "__main__":
    main()
