# Trade Wars 2002 Documentation

Game-specific documentation for Trade Wars 2002 (TW2002) implementation.

## Overview

This directory contains technical reference material specific to the TW2002 game:

- **Login flows** - BBS and TWGS login sequences
- **Game mechanics** - Port editor, trading formulas
- **AI guidance** - LLM prompt hints for better AI decisions
- **Troubleshooting** - Common issues and solutions

## Documentation Files

### [LLM_HINTS.md](LLM_HINTS.md)
**AI prompt guidance for LLM-driven strategies**

Contains:
- Game context and objectives
- Trading strategy hints
- Navigation guidance
- Combat advice
- Risk management
- Resource optimization tips

Use this when implementing or debugging AI strategies.

### [TEDIT_REFERENCE.md](TEDIT_REFERENCE.md)
**Port editor technical reference**

Contains:
- Port types and characteristics
- Commodity pricing formulas
- Trading calculations
- Port generation parameters
- Economic model details

Use this for understanding trading mechanics.

### [TWGS_LOGIN_FLOW.md](TWGS_LOGIN_FLOW.md)
**TWGS (Trade Wars Game Server) login sequence**

Contains:
- Login screen detection
- Authentication flow
- Prompt patterns
- Session initialization
- Error handling

Use this for debugging login issues with TWGS servers.

### [bbs-login-solution.md](bbs-login-solution.md)
**BBS login troubleshooting guide**

Contains:
- Common login problems
- Screen detection issues
- Prompt pattern debugging
- Test credentials
- Connection troubleshooting

Use this when bots can't connect to BBS systems.

### [credentials.md](credentials.md)
**Test credentials and connection details**

Contains:
- Test server addresses
- Demo accounts
- Port numbers
- Connection examples

Use this for testing and development.

## Related Documentation

### Core System Documentation
- **[System Architecture](../../../docs/SYSTEM_ARCHITECTURE.md)** - Complete system overview
- **[Documentation Index](../../../docs/README.md)** - All documentation

### Code References
- **Rules**: `rules.json` - Prompt detection patterns (195 rules)
- **Prompts**: `prompts.json` - Prompt definitions
- **Game Logic**: `src/bbsbot/games/tw2002/` - Implementation

## Quick Reference

### Prompt Detection
```python
# Rules are loaded from rules.json
from bbsbot.learning.detector import PromptDetector
from bbsbot.learning.rules import RuleSet

rules = RuleSet.from_json_file("games/tw2002/rules.json")
detector = PromptDetector(rules.to_prompt_patterns())
```

### Adding New Prompts
1. Edit `rules.json`
2. Add pattern with `match` and optional `negative_match`
3. Put specific patterns BEFORE generic ones (order matters)
4. Test with real game screens
5. Update tests

### Debugging Login Issues
1. Check `bbs-login-solution.md` for common problems
2. Enable debug logging: `BBSBOT_LOG_LEVEL=DEBUG`
3. Review screen captures in session logs
4. Verify prompt patterns in `rules.json`
5. Test with `credentials.md` accounts

## File Organization

```
games/tw2002/
├── docs/                              # This directory
│   ├── README.md                      # This file
│   ├── LLM_HINTS.md                   # AI guidance
│   ├── TEDIT_REFERENCE.md             # Port mechanics
│   ├── TWGS_LOGIN_FLOW.md             # TWGS login
│   ├── bbs-login-solution.md          # BBS troubleshooting
│   └── credentials.md                 # Test accounts
│
├── rules.json                         # Prompt patterns (195 rules)
├── prompts.json                       # Prompt definitions
└── session.jsonl                      # Debug log (gitignored)
```

## Contributing

When adding game-specific documentation:

1. **Login flows** → Add to `TWGS_LOGIN_FLOW.md` or create new flow doc
2. **Game mechanics** → Add to `TEDIT_REFERENCE.md` or create new reference
3. **AI hints** → Add to `LLM_HINTS.md`
4. **Troubleshooting** → Add to `bbs-login-solution.md`
5. **Test data** → Add to `credentials.md`

Keep documentation focused on TW2002-specific details. General system docs go in `docs/`.

---

**Last Updated**: 2026-02-06
