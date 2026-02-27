"""Regression test: fast-travel step delay in static/game.js must be <= 30 ms.

The frontend auto-advances the player one step per server round-trip by sending
'_' again whenever `state.traveling` is truthy.  The setTimeout that drives this
loop must be short enough not to feel laggy.  This test extracts the numeric
delay value from the source file and asserts it is at most 30 ms.
"""

import pathlib
import re


GAME_JS = pathlib.Path(__file__).parent.parent / "static" / "game.js"

# Matches:  setTimeout(() => sendInput('_'), <number>)
# Captures the numeric argument (the delay in milliseconds).
_PATTERN = re.compile(
    r"setTimeout\(\s*\(\s*\)\s*=>\s*sendInput\('_'\)\s*,\s*(\d+)\s*\)"
)

MAX_DELAY_MS = 30


def test_fast_travel_step_delay_is_at_most_30_ms():
    """The setTimeout delay for auto-travel continuation must not exceed 30 ms."""
    source = GAME_JS.read_text(encoding="utf-8")

    matches = _PATTERN.findall(source)
    assert matches, (
        f"Could not find the expected setTimeout(() => sendInput('_'), <N>) "
        f"call in {GAME_JS}. The pattern may need updating if the code changed."
    )

    # There should be exactly one such call; assert on all matches to be safe.
    for raw_value in matches:
        delay_ms = int(raw_value)
        assert delay_ms <= MAX_DELAY_MS, (
            f"Fast-travel step delay is {delay_ms} ms "
            f"(found in {GAME_JS}), but must be <= {MAX_DELAY_MS} ms. "
            f"Reduce the setTimeout argument on the 'state.traveling' branch."
        )
