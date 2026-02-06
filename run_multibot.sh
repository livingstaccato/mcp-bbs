#!/bin/bash
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
