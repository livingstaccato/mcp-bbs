#!/bin/bash
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

# Quick readiness check for intervention system testing

echo "=============================================="
echo "Intervention System Test Readiness Check"
echo "=============================================="
echo ""

# Check 1: Tests passing
echo "1. Running unit tests..."
if python -m pytest tests/ -q --tb=no 2>&1 | tail -1 | grep -q "passed"; then
    echo "   ✅ All tests passing"
else
    echo "   ❌ Tests failing - fix before proceeding"
    exit 1
fi
echo ""

# Check 2: OLLAMA running
echo "2. Checking OLLAMA..."
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "   ✅ OLLAMA running"
    if curl -s http://localhost:11434/api/tags | grep -q "gemma3"; then
        echo "   ✅ gemma3 model available"
    else
        echo "   ⚠️  gemma3 not found - run: ollama pull gemma3"
        exit 1
    fi
else
    echo "   ❌ OLLAMA not running - start with: ollama serve"
    exit 1
fi
echo ""

# Check 3: Test configs exist
echo "3. Checking test configurations..."
if [ -f "examples/configs/test_opportunistic_stuck.yaml" ] && \
   [ -f "examples/configs/test_ai_intervention.yaml" ] && \
   [ -f "examples/configs/test_ai_manual_intervention.yaml" ]; then
    echo "   ✅ All 3 test configs present"
else
    echo "   ❌ Missing test configs"
    exit 1
fi
echo ""

# Check 4: Documentation
echo "4. Checking documentation..."
if [ -f "docs/guides/QUICK_START.md" ] && \
   [ -f "docs/guides/INTELLIGENT_BOT.md" ]; then
    echo "   ✅ Testing documentation present"
else
    echo "   ⚠️  Missing documentation files"
fi
echo ""

# Check 5: TW2002 server (optional)
echo "5. Checking TW2002 server..."
HOST=${1:-localhost}
PORT=${2:-2002}
if nc -z $HOST $PORT 2>/dev/null; then
    echo "   ✅ Server reachable at $HOST:$PORT"
    echo ""
    echo "=============================================="
    echo "✅ ALL CHECKS PASSED - READY FOR TESTING"
    echo "=============================================="
    echo ""
    echo "Next steps:"
    echo "  1. Run: uv run bbsbot tw2002 bot -c examples/configs/test_opportunistic_stuck.yaml --host $HOST --port $PORT"
    echo "  2. Monitor: tail -f ~/.bbsbot/sessions/*.jsonl | grep '\"event\": \"llm.intervention\"'"
else
    echo "   ⚠️  Server not reachable at $HOST:$PORT"
    echo ""
    echo "=============================================="
    echo "⚠️  MOSTLY READY - Server check failed"
    echo "=============================================="
    echo ""
    echo "Start TW2002 server on $HOST:$PORT or specify different host/port:"
    echo "  ./scripts/check_test_readiness.sh <host> <port>"
fi
echo ""
