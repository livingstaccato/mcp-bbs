#!/bin/bash
# Monitor stress test progress

LOG_DIR=~/bbsbot_stress_logs

while true; do
    clear
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║          BOT STRESS TEST PROGRESS MONITOR                     ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""

    # Count active logs
    TOTAL=$(ls $LOG_DIR/*.log 2>/dev/null | wc -l)

    if [ $TOTAL -eq 0 ]; then
        echo "No logs found yet..."
        sleep 5
        continue
    fi

    echo "Total Logs: $TOTAL"
    echo ""

    # Check login status
    LOGGED_IN=$(grep -l "✓ Login complete" $LOG_DIR/*.log 2>/dev/null | wc -l)
    echo "✓ Logins Successful: $LOGGED_IN/$TOTAL"

    # Check for errors
    ERRORS=$(grep -h "ERROR\|CRITICAL" $LOG_DIR/*.log 2>/dev/null | wc -l)
    echo "⚠️ Errors: $ERRORS"

    # Check for sessions completed
    COMPLETED=$(grep -l "SESSION COMPLETE" $LOG_DIR/*.log 2>/dev/null | wc -l)
    echo "✓ Sessions Completed: $COMPLETED"

    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "Last 5 Log Entries:"
    echo ""

    # Show a few recent log updates
    for log in $(ls -t $LOG_DIR/*.log 2>/dev/null | head -3); do
        basename=$(basename "$log")
        TURNS=$(grep -o "\[Turn [0-9]*\]" "$log" | tail -1 | tr -d '[]')
        LOGIN=$(grep "✓ Login complete" "$log" | tail -1 | sed 's/.*Sector /Sector /')

        if [ -n "$LOGIN" ]; then
            printf "%-35s %s\n" "$basename" "$TURNS"
        fi
    done

    echo ""
    echo "Refresh: Ctrl+C to stop, updates every 10 seconds"
    sleep 10
done
