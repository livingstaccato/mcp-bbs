#!/bin/bash
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

# Bot Testing Matrix - Tests different configurations
# Usage: ./test_bot_matrix.sh

set -e

PYTHONPATH=src
export PYTHONPATH

LOG_DIR="test_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$LOG_DIR"

echo "================================"
echo "BOT TESTING MATRIX"
echo "================================"
echo "Log directory: $LOG_DIR"
echo ""

# Test counter
test_num=0

# Function to run a test
run_test() {
    test_num=$((test_num + 1))
    local config=$1
    local description=$2
    local max_turns=${3:-20}
    local timeout=${4:-60}

    echo "[$test_num] Testing: $description"
    echo "    Config: $config"
    echo "    Max turns: $max_turns"

    local log_file="$LOG_DIR/test_${test_num}_$(basename $config .yaml).log"

    # Run bot with timeout
    if timeout ${timeout}s python -m bbsbot tw2002 bot --config "$config" > "$log_file" 2>&1; then
        # Check if bot completed successfully
        if grep -q "SESSION COMPLETE" "$log_file"; then
            echo "    ✓ PASSED - Session completed"
            grep "Total profit:" "$log_file" || true
        else
            echo "    ~ PARTIAL - Bot ran but didn't complete"
            tail -5 "$log_file"
        fi
    else
        exit_code=$?
        if [ $exit_code -eq 124 ]; then
            echo "    ⏱  TIMEOUT - Bot still running after ${timeout}s"
        else
            echo "    ✗ FAILED - Exit code: $exit_code"
            tail -10 "$log_file"
        fi
    fi
    echo ""
}

# Test 1: Opportunistic strategy (baseline - should get stuck)
run_test "config/test_opportunistic_stuck.yaml" "Opportunistic Baseline" 50 60

# Test 2: AI strategy with auto-intervention
run_test "config/test_ai_intervention.yaml" "AI Auto-Intervention" 100 120

# Test 3: AI strategy with manual intervention
run_test "config/test_ai_manual_intervention.yaml" "AI Manual Intervention" 100 120

echo "================================"
echo "TESTING COMPLETE"
echo "================================"
echo "Results saved to: $LOG_DIR"
echo "Total tests run: $test_num"
echo ""
echo "Summary:"
grep -r "✓ PASSED\|✗ FAILED\|⏱  TIMEOUT\|~ PARTIAL" "$LOG_DIR" | wc -l
