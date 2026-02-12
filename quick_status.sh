#!/bin/bash
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

# Quick status check for stress test

LOG_DIR=~/bbsbot_stress_logs

echo "╔════════════════════════════════════════════╗"
echo "║     BOT STRESS TEST STATUS CHECK           ║"
echo "╚════════════════════════════════════════════╝"
echo ""

TOTAL=$(ls $LOG_DIR/*.log 2>/dev/null | wc -l)
LOGGED_IN=$(grep -l "✓ Login complete" $LOG_DIR/*.log 2>/dev/null | wc -l)
COMPLETED=$(grep -l "SESSION COMPLETE" $LOG_DIR/*.log 2>/dev/null | wc -l)
ERRORS=$(grep -h "ERROR\|CRITICAL" $LOG_DIR/*.log 2>/dev/null | wc -l)

echo "Total Bot Instances: $TOTAL"
echo "Logins Successful:   $LOGGED_IN/$TOTAL"
echo "Sessions Completed:  $COMPLETED/$TOTAL"
echo "Errors Found:        $ERRORS"
echo ""

if [ $LOGGED_IN -eq $TOTAL ]; then
    echo "✓ All bots logged in successfully!"
fi

if [ $COMPLETED -eq $TOTAL ]; then
    echo "✓ All bots completed their sessions!"
    echo ""
    echo "READY FOR COMPLETION PROMISE"
fi
