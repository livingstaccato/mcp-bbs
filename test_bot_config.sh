#!/bin/bash
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

# Test a single bot configuration and verify behavior

CONFIG_FILE="$1"
TEST_NUM="$2"

if [ -z "$CONFIG_FILE" ] || [ -z "$TEST_NUM" ]; then
    echo "Usage: $0 <config_file> <test_number>"
    exit 1
fi

CONFIG_NAME=$(basename "$CONFIG_FILE" .yaml)
LOG_FILE="/tmp/bot_test_${TEST_NUM}.log"

echo "Testing #$TEST_NUM: $CONFIG_NAME"

# Run bot with 60s timeout (login takes ~30s, allows ~30s for trading)
PYTHONPATH=src timeout 60s python -m bbsbot tw2002 bot --config "$CONFIG_FILE" > "$LOG_FILE" 2>&1

EXIT_CODE=$?

# Check results
if grep -q "✓ Login complete" "$LOG_FILE"; then
    LOGIN_STATUS="✓ PASS"

    # Check for trading activity
    TRADE_COUNT=$(grep -c "Trade complete" "$LOG_FILE" || echo "0")

    # Check for errors
    ERROR_COUNT=$(grep -c "WARNING\|ERROR" "$LOG_FILE" || echo "0")

    # Extract sector and credits
    SECTOR=$(grep "✓ Login complete" "$LOG_FILE" | sed -E 's/.*Sector ([0-9]+).*/\1/' | head -1)
    CREDITS=$(grep "✓ Login complete" "$LOG_FILE" | sed -E 's/.*Credits: ([0-9]+).*/\1/' | head -1)

    OVERALL="✓ PASS"
    NOTES="Login OK, ${TRADE_COUNT} trades, ${ERROR_COUNT} errors"
else
    LOGIN_STATUS="✗ FAIL"
    OVERALL="✗ FAIL"
    TRADE_COUNT="0"
    SECTOR="N/A"
    CREDITS="N/A"

    # Check what failed
    if grep -q "patterns from" "$LOG_FILE"; then
        NOTES="Pattern loading failed"
    elif grep -q "Timeout" "$LOG_FILE"; then
        NOTES="Timeout during login"
    else
        NOTES="Login sequence failed"
    fi
fi

# Output result
echo "| $TEST_NUM | $CONFIG_NAME | $OVERALL | $LOGIN_STATUS | $TRADE_COUNT | $CREDITS | $NOTES |"
