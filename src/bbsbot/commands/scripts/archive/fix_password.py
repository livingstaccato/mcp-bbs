# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

import socket
import time


def test_password(keys_to_send: str) -> None:
    print(f"Testing keys: {repr(keys_to_send)}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", 2002))

    # Wait for initial menu
    time.sleep(1)
    s.recv(1024)

    # Send A
    s.sendall(b"A")
    time.sleep(1)
    resp = s.recv(1024).decode("ascii", errors="replace")
    print(f"Initial response: {repr(resp)}")

    # Send password
    s.sendall(keys_to_send.encode("ascii"))
    time.sleep(1)
    resp = s.recv(1024).decode("ascii", errors="replace")
    print(f"Final response: {repr(resp)}")
    s.close()


print("--- Test 1: game\\r ---")

test_password("game\\r")

print("\n--- Test 2: game\\n\\r ---")

test_password("game\\n\\r")

print("\n--- Test 3: game\\n ---")

test_password("game\\n")
