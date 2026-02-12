#!/bin/bash
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

# Quick launcher for multi-bot TW2002 gameplay

set -e

cd "$(dirname "$0")"

# Default to 5 bots, or accept count as argument
NUM_BOTS="${1:-5}"

echo "====================================================================="
echo "Starting TW2002 Multi-Bot System with $NUM_BOTS bots"
echo "====================================================================="
echo ""
echo "Press Ctrl+C to stop all bots gracefully"
echo ""

python3 -m bbsbot.commands.scripts.play_tw2002_multibot "$NUM_BOTS"
