"""Test to reproduce screen buffer capture issue."""

from __future__ import annotations

import pyte


# Simulate the menu display scenario
def test_menu_capture():
    """Test that menu options are captured in screen buffer."""

    # Create a screen
    screen = pyte.Screen(80, 25)
    stream = pyte.Stream(screen)

    # Simulate menu being displayed
    menu_text = """
<A> Attack this Port
<T> Trade at this Port
<Q> Quit, nevermind
Enter your choice [T] :"""

    # Feed text to screen
    stream.feed(menu_text)

    # Get display
    display = "\n".join(screen.display)

    print("=== Screen Display ===")
    print(display)
    print("\n=== End Display ===")

    # Check if menu options are captured
    assert "<A> Attack this Port" in display, "Menu option A missing"
    assert "<T> Trade at this Port" in display, "Menu option T missing"
    assert "<Q> Quit, nevermind" in display, "Menu option Q missing"
    assert "Enter your choice" in display, "Prompt missing"


def test_menu_with_cursor_positioning():
    """Test menu with ANSI cursor positioning sequences."""

    screen = pyte.Screen(80, 25)
    stream = pyte.Stream(screen)

    # Simulate menu with cursor positioning (common in BBS)
    # This moves cursor to specific positions, potentially clearing
    stream.feed("<A> Attack this Port\r\n")
    stream.feed("<T> Trade at this Port\r\n")
    stream.feed("<Q> Quit, nevermind\r\n")
    stream.feed("Enter your choice [T] :")

    display = "\n".join(screen.display)

    print("\n=== Screen Display (with \\r\\n) ===")
    print(display)
    print("\n=== End Display ===")

    assert "<A> Attack this Port" in display, "Menu option A missing"
    assert "<T> Trade at this Port" in display, "Menu option T missing"
    assert "<Q> Quit, nevermind" in display, "Menu option Q missing"


def test_menu_with_clear_and_reposition():
    """Test menu where cursor is repositioned after clearing."""

    screen = pyte.Screen(80, 25)
    stream = pyte.Stream(screen)

    # Display menu
    stream.feed("<A> Attack this Port\r\n")
    stream.feed("<T> Trade at this Port\r\n")
    stream.feed("<Q> Quit, nevermind\r\n")
    stream.feed("Enter your choice [T] :")

    # Now simulate cursor moving back to prompt line (common pattern)
    # ESC[A moves cursor up one line
    stream.feed("\x1b[3A")  # Move up 3 lines (back to first menu option)
    stream.feed("\x1b[K")  # Clear from cursor to end of line

    display = "\n".join(screen.display)

    print("\n=== Screen Display (after clear) ===")
    print(display)
    print("\n=== End Display ===")


def test_menu_with_home_and_clear():
    """Test menu where screen is cleared and only prompt remains."""

    screen = pyte.Screen(80, 25)
    stream = pyte.Stream(screen)

    # Display menu
    stream.feed("<A> Attack this Port\r\n")
    stream.feed("<T> Trade at this Port\r\n")
    stream.feed("<Q> Quit, nevermind\r\n")
    stream.feed("Enter your choice [T] :")

    print("\n=== Before Clear ===")
    print("\n".join(screen.display))

    # Clear screen (ESC[2J) and move cursor home (ESC[H)
    stream.feed("\x1b[2J\x1b[H")
    stream.feed("Enter your choice [T] :")

    display = "\n".join(screen.display)

    print("\n=== After Clear (only prompt) ===")
    print(display)
    print("\n=== End Display ===")

    # This would fail - menu is gone!
    # assert "<A> Attack this Port" in display, "Menu option A missing"


if __name__ == "__main__":
    print("Test 1: Simple menu capture")
    try:
        test_menu_capture()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")

    print("\n" + "=" * 60)
    print("Test 2: Menu with \\r\\n")
    try:
        test_menu_with_cursor_positioning()
        print("✓ PASSED")
    except AssertionError as e:
        print(f"✗ FAILED: {e}")

    print("\n" + "=" * 60)
    print("Test 3: Menu with cursor repositioning")
    test_menu_with_clear_and_reposition()

    print("\n" + "=" * 60)
    print("Test 4: Menu with clear screen")
    test_menu_with_home_and_clear()
