# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install all dependencies (including dev: pytest, pytest-cov)
uv sync --dev

# Run the game server
uv run python server.py
# Access at http://localhost:5000

# Run all tests
uv run pytest

# Run a single test module
uv run pytest tests/test_combat.py

# Run with coverage
uv run pytest --cov=quakelike --cov-report=html

# Docker
docker-compose up --build
```

Environment variable `FLASK_DEBUG=true` enables Flask debug mode. `CORS_ORIGINS` overrides the allowed WebSocket origins (default: `http://localhost:5000`).

## Architecture

### Communication Flow
Browser ↔ Flask-SocketIO (WebSocket) ↔ `Game` object (per session)

`server.py` manages one `Game` instance per socket session (`request.sid`). On each `input` event, `game.handle_input(key)` processes the keystroke and returns the full render state dict, which is emitted back as `game_state`. The frontend (`static/game.js`) renders this dict directly — no partial updates.

### Backend Package (`quakelike/`)

| Module | Responsibility |
|--------|---------------|
| `game.py` | `Game` dataclass — state machine, input routing, turn loop, save/load |
| `gamemap.py` | `GameMap` dataclass, procedural map generation (room-corridor + Bresenham LOS) |
| `entity.py` | `Entity` and `Position` base classes |
| `player.py` | `Player` (extends `Entity`) — stats, inventory, powerups, XP/leveling |
| `enemies.py` | `EnemyDef` dataclass, `Enemy` class, all 12 enemy definitions |
| `items.py` | `ItemDef` dataclass, `Item` class, all Quake items and weapons |
| `combat.py` | `player_melee_attack`, `player_fire_weapon`, `enemy_attack`, splash damage |
| `ai.py` | `update_enemy` — enemy alerting, pathfinding, attack logic |
| `inventory.py` | `Inventory` — 10-item max, ammo tracking, equip logic |
| `message.py` | `MessageLog` — rolling message history |
| `constants.py` | All magic numbers, tile chars, key bindings, colors |

### Game State Machine
`GameState` enum in `game.py` controls input routing:
- `PLAYING` → normal movement/combat
- `INVENTORY` / `LOOT` → item management panels
- `TARGETING` → ranged target selection
- `FAST_TRAVEL` → cursor-based destination selection for step-by-step autopath travel
- `MESSAGE_LOG` → scrollable log view
- `GAME_OVER` / `VICTORY` → terminal states

### Turn Loop
`_end_turn()` in `game.py` runs after every player action: enemy AI updates (`update_enemy` for each living enemy), player death check, powerup ticking, target list refresh.

### Map Generation
`generate_map(level, rng)` in `gamemap.py`: random rooms → L-shaped corridors → doors → slipgates/entrance → environment features (water/lava) → item placement → enemy placement. Maps are generated lazily on first visit and cached in `Game.maps`. RNG is seeded per game for reproducibility.

### Save/Load
JSON-based, saved to `saves/savegame.json`. `Game._serialize()` / `Game._deserialize()` handles full state including RNG state. Permadeath deletes the save on player death.

### Tile Characters
`#` wall · `.` floor · `+` door · `>` slipgate down · `<` slipgate up · `E` entrance · `~` water · `=` lava

### Adding Content
- **New enemy**: Add `EnemyDef` to `quakelike/enemies.py` and append to `ALL_ENEMIES`
- **New item**: Add `ItemDef` to `quakelike/items.py` and append to the appropriate `ALL_*` list
- **New key binding**: Add constant to `constants.py`, handle in `game.py`

## Development Notes

- Controls are case-sensitive (`S` saves, `Q` quits, lowercase letters move)
- The Rune appears on map index 39 (level 40); victory requires returning to map index 0 with the Rune in inventory
- `specs.md` contains the authoritative design requirements
- TDD is the intended workflow: write tests first, then implement

## Safety Rules
- Never delete or create any GitHub repository under any circumstances
- Never run `gh repo delete` or `gh repo create` without explicit user confirmation in the current session
