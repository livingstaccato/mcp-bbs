#!/usr/bin/env python3
"""Test pattern matching against actual TW2002 screen."""

import re

# Actual screen text from TW2002
screen = """Telnet connection detected.

Please enter your name (ENTER for none):                                        """

# Current pattern (doesn't match)
current_pattern = r"(?i)(enter|type)\s+(your\s+)?(user\s*name|handle|alias)\s*:?\s*$"

# Improved pattern (should match)
improved_pattern = r"(?i)(enter|type)\s+(your\s+)?(name|user\s*name|handle|alias)\s*.*:?\s*$"

print("Testing patterns against TW2002 screen")
print("=" * 80)
print("\nActual screen:")
print(repr(screen))
print()

print("Current pattern:")
print(f"  {current_pattern}")
match = re.search(current_pattern, screen, re.MULTILINE)
print(f"  Match: {match}")
print()

print("Improved pattern:")
print(f"  {improved_pattern}")
match = re.search(improved_pattern, screen, re.MULTILINE)
print(f"  Match: {match}")
if match:
    print(f"  Matched text: {repr(match.group(0))}")
print()

# Even simpler pattern
simple_pattern = r"(?i)enter\s+your\s+name"
print("Simple pattern:")
print(f"  {simple_pattern}")
match = re.search(simple_pattern, screen, re.MULTILINE)
print(f"  Match: {match}")
if match:
    print(f"  Matched text: {repr(match.group(0))}")
