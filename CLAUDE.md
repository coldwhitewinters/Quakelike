# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install all dependencies (including dev: pytest, pytest-cov)
uv sync --dev

# Run the game server
uv run python server.py
# Access at http://localhost:8080

# Run all tests
uv run pytest

# Run a single test module
uv run pytest tests/test_combat.py

# Run with coverage
uv run pytest --cov=quakelike --cov-report=html

# Docker (local)
docker-compose up --build
# Access at http://localhost:8080

# Deploy to Azure (first time)
./deploy.sh

# Redeploy after code changes
./deploy.sh --update
```

Environment variable `FLASK_DEBUG=true` enables Flask debug mode. `CORS_ORIGINS` overrides the allowed WebSocket origins (default: `http://localhost:8080`).

## Architecture

### Communication Flow
Browser ↔ Flask-SocketIO (WebSocket) ↔ `Game` object (per session)

`server.py` manages one `Game` instance per socket session (`request.sid`). On each `input` event, `game.handle_input(key)` processes the keystroke and returns the full render state dict, which is emitted back as `game_state`. The frontend (`static/game.js`) renders this dict directly — no partial updates.

### Backend Package (`quakelike/`)

| Module | Responsibility |
|--------|---------------|
| `game.py` | `Game` dataclass — state machine, input routing, turn loop, save/load |
| `gamemap.py` | `GameMap` dataclass, procedural map generation (room-corridor + Bresenham LOS); `GameMap.corpses` dict and `add_corpse()` method for enemy death markers |
| `entity.py` | `Entity` and `Position` base classes |
| `player.py` | `Player` (extends `Entity`) — stats, inventory, powerups, XP/leveling; `last_move_dir: tuple[int,int]` tracks the direction of the player's most recent move for dodge calculation |
| `enemies.py` | `EnemyDef` dataclass (incl. `ammo_drop` and `requires_water` fields), `Enemy` class (incl. `death_processed` flag), all 12 enemy definitions |
| `items.py` | `ItemDef` dataclass, `Item` class, all Quake items and weapons |
| `combat.py` | `player_melee_attack`, `player_fire_weapon`, `enemy_attack`, splash damage; `_calc_dodge_chance(move_dir, enemy_pos, player_pos)` helper drives movement-based dodge for RANGED attacks |
| `ai.py` | `update_enemy` — enemy alerting, pathfinding, attack logic; `requires_water` guard in `_wander()`, `_move_toward_player()`, and `_handle_adjacent_door()` prevents water-only enemies from entering dry tiles |
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
`_end_turn()` in `game.py` runs after every player action: enemy AI updates (`update_enemy` for each living enemy), player death check, powerup ticking, target list refresh. `_move_player()` sets `player.last_move_dir` before calling `_end_turn()` so that dodge rolls during the enemy loop have the current movement direction; `_end_turn()` resets `last_move_dir` to `(0, 0)` after the enemy loop so that non-move actions grant no dodge benefit.

### Frontend Animations
`get_render_state()` exposes two frame-list fields that the frontend animates before showing the final state (30 ms per tile):
- `travel_frames` — step positions for fast-travel autopath (rendered by `animateTravelFrames()`)
- `projectile_frames` — tile positions along the Bresenham line from player to target, rendered by `animateProjectileFrames()` using `projectile_char` (`*`) and `projectile_color` (yellow `#FFFF00`)

### Map Generation
`generate_map(level, rng)` in `gamemap.py`: random rooms → L-shaped corridors → doors → slipgates/entrance → environment features (water/lava) → item placement → enemy placement. Maps are generated lazily on first visit and cached in `Game.maps`. RNG is seeded per game for reproducibility.

### Save/Load
JSON-based, multi-save system. Each `Game` instance carries a UUID `game_id` (generated at `new_game` time). Saves are stored as `saves/game_<uuid>.json`.

- `Game._serialize()` / `Game._deserialize()` — full state serialisation including RNG state and `game_id`.
- `Game._save_game()` — writes `saves/game_<game_id>.json`; also writes the legacy `saves/savegame.json` when using the default saves directory (backward compatibility only).
- `Game.load_game(game_id=None)` — loads by UUID when `game_id` is supplied; falls back to legacy `saves/savegame.json` when called without arguments. Rejects non-UUID values immediately to prevent path-traversal.
- `Game.quit_without_save()` — deletes the save file and returns a render-state dict with `goto_menu=True`; used by the `Q` confirmation flow.
- `list_saves(saves_dir)` — module-level function; scans `saves/` for `game_*.json` files and returns a list of metadata dicts (id, display_name, timestamp, level, map_idx) sorted newest-first. Skips corrupted or invalid files silently.
- Corpses (`GameMap.corpses`) are serialized per-map as part of the map state and restored on load.
- Permadeath deletes only the affected game's `game_<uuid>.json` save.
- All `game_id` values are validated against a strict UUID regex before any filesystem operation.

### Tile Characters
`#` wall · `.` floor · `+` door · `>` slipgate down · `<` slipgate up · `E` entrance · `~` water · `=` lava · `%` corpse

### Adding Content
- **New enemy**: Add `EnemyDef` to `quakelike/enemies.py` and append to `ALL_ENEMIES`; set `requires_water=True` for enemies that must spawn and remain on water tiles (e.g. Rotfish)
- **New item**: Add `ItemDef` to `quakelike/items.py` and append to the appropriate `ALL_*` list
- **New key binding**: Add constant to `constants.py`, handle in `game.py`

## Development Notes

- Controls are case-sensitive (`S` saves the game and returns to the main menu, `Q` quits without saving — the frontend shows a confirmation dialog before the save is deleted, lowercase letters move)
- The Rune appears on map index 39 (level 40); victory requires returning to map index 0 with the Rune in inventory
- `specs.md` contains the authoritative design requirements
- TDD is the intended workflow: write tests first, then implement

### Dodge Mechanic
When a player moves, `last_move_dir` is set to the unit step taken. During the subsequent enemy attack phase, `enemy_attack()` calls `_calc_dodge_chance(move_dir, enemy_pos, player_pos)` for every RANGED attack. MELEE, LEAP, and EXPLODE attack types auto-hit and are never dodgeable.

Dodge chance is determined by the cosine similarity between the player's movement direction and the attack vector (enemy → player), combined with distance:

| Movement angle relative to attack line | Dodge chance (at `DODGE_FULL_RANGE` ≥ 8 tiles) |
|----------------------------------------|------------------------------------------------|
| Perpendicular (strafing)               | `DODGE_CHANCE_PERPENDICULAR` = 50%             |
| Oblique (diagonal)                     | `DODGE_CHANCE_OBLIQUE` = 30%                   |
| Parallel (running toward/away)         | `DODGE_CHANCE_PARALLEL` = 10%                  |

Chance scales linearly with distance: it is halved at distance 0 and reaches full value at `DODGE_FULL_RANGE` (8) tiles or beyond. All four constants live in `constants.py`.

## Azure Deployment

The game is deployed to Azure Container Apps at:
`https://quakelike.nicegrass-99f8552c.westeurope.azurecontainerapps.io`

### Azure Resources

| Resource | Name | Purpose |
|---|---|---|
| Resource Group | `quakelike-rg` (West Europe) | Container for all resources |
| Container Registry | `quakelikeacr` | Stores Docker images |
| Storage Account | `quakelikestorage` | Azure Files share for `saves/` persistence |
| Container Apps Environment | `quakelike-env` | Shared runtime environment |
| Container App | `quakelike` | The running application |

### Configuration
- 0.5 vCPU / 1 GiB RAM, 1 replica (fixed — game sessions are in-memory; scaling would break session state)
- `saves/` mounted from Azure Files share `saves` via storage mount `saves-mount`
- `FLASK_DEBUG=false`, `CORS_ORIGINS` set to the app HTTPS URL

### Deployment Script
`deploy.sh` at the repo root handles both first-time setup and redeployments.

```bash
# First-time: provisions all Azure resources and deploys
./deploy.sh

# After code changes: rebuilds image and updates the running app
./deploy.sh --update

# Override defaults (e.g. different region or app name)
./deploy.sh -l eastus -a myquakelike
```

### Teardown
```bash
az group delete --name quakelike-rg --yes --no-wait
```
This deletes all Azure resources (ACR, storage, Container App, environment).

### Logs
```bash
az containerapp logs show --name quakelike --resource-group quakelike-rg --follow
```

## Safety Rules
- Never delete or create any GitHub repository under any circumstances
- Never run `gh repo delete` or `gh repo create` without explicit user confirmation in the current session
- Never merge a pull request without explicit user confirmation
