#!/bin/bash
# Live Intervention System Testing Script
# Runs intervention tests against localhost:2002

set -e

HOST=${1:-localhost}
PORT=${2:-2002}

echo "=================================================="
echo "Intervention System Live Testing"
echo "Target: $HOST:$PORT"
echo "=================================================="
echo ""

# Check if OLLAMA is running
echo "1. Verifying OLLAMA is running..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "   ✓ OLLAMA is running"
    if curl -s http://localhost:11434/api/tags | grep -q "gemma3"; then
        echo "   ✓ gemma3 model available"
    else
        echo "   ✗ gemma3 model NOT found"
        echo "   Run: ollama pull gemma3"
        exit 1
    fi
else
    echo "   ✗ OLLAMA not running"
    echo "   Start OLLAMA: ollama serve"
    exit 1
fi
echo ""

# Check if TW2002 server is available
echo "2. Verifying TW2002 server..."
if nc -z $HOST $PORT 2>/dev/null; then
    echo "   ✓ Server reachable at $HOST:$PORT"
else
    echo "   ✗ Server not reachable at $HOST:$PORT"
    echo "   Start server or check connection"
    exit 1
fi
echo ""

# Test 1: Opportunistic baseline
echo "=================================================="
echo "Test 1: Opportunistic Strategy (Baseline)"
echo "Expected: Bot gets stuck in loops"
echo "Config: config/test_opportunistic_stuck.yaml"
echo "=================================================="
echo ""
echo "Run the following command:"
echo "python -m bbsbot.main --config config/test_opportunistic_stuck.yaml --host $HOST --port $PORT"
echo ""
read -p "Press Enter when ready to continue to Test 2..."
echo ""

# Test 2: AI intervention with auto-apply
echo "=================================================="
echo "Test 2: AI Strategy with Auto-Apply Intervention"
echo "Expected: Bot gets stuck → intervention → recovery"
echo "Config: config/test_ai_intervention.yaml"
echo "=================================================="
echo ""
echo "Run the following command:"
echo "python -m bbsbot.main --config config/test_ai_intervention.yaml --host $HOST --port $PORT"
echo ""
echo "Monitor for:"
echo "  - Intervention trigger in logs"
echo "  - LLM analysis response"
echo "  - Goal change after intervention"
echo "  - Bot recovery (new sectors, trades)"
echo ""
read -p "Press Enter when ready to continue to Test 3..."
echo ""

# Test 3: Manual intervention
echo "=================================================="
echo "Test 3: AI Strategy with Manual Intervention"
echo "Expected: Bot gets stuck → intervention logged → manual recovery"
echo "Config: config/test_ai_manual_intervention.yaml"
echo "=================================================="
echo ""
echo "Run the following command:"
echo "python -m bbsbot.main --config config/test_ai_manual_intervention.yaml --host $HOST --port $PORT"
echo ""
echo "When bot gets stuck, use MCP tools:"
echo "  1. tw2002_get_intervention_status()"
echo "  2. tw2002_set_goal(goal='exploration')"
echo "  3. tw2002_get_bot_status() to verify recovery"
echo ""
read -p "Press Enter when complete..."
echo ""

# Monitor session logs
echo "=================================================="
echo "Viewing Recent Intervention Events"
echo "=================================================="
echo ""
SESSION_DIR="$HOME/.bbsbot/sessions"
if [ -d "$SESSION_DIR" ]; then
    echo "Recent intervention events:"
    grep '"event": "llm.intervention"' "$SESSION_DIR"/*.jsonl 2>/dev/null | tail -10 || echo "No interventions logged yet"
else
    echo "No session directory found at $SESSION_DIR"
fi
echo ""

echo "=================================================="
echo "Testing Complete"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Review session logs in $HOME/.bbsbot/sessions/"
echo "  2. Check for intervention events"
echo "  3. Verify bot recovery after interventions"
echo "  4. Tune thresholds in config if needed"
