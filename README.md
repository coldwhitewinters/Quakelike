# Quakelike

A roguelike dungeon crawler inspired by the classic FPS game Quake. Explore 40 procedurally-generated maps, battle iconic Quake enemies, collect powerful weapons, and find the legendary Rune to win!

## Features

### Core Gameplay
- **40 Procedurally-Generated Levels**: Each playthrough offers unique dungeon layouts with rooms, corridors, and hazards
- **Turn-Based Combat**: Strategic combat system with melee and ranged weapons
- **Classic Quake Enemies**: Face off against 12 enemy types including Rottweilers, Grunts, Knights, Ogres, Fiends, Shamblers, and more
- **Arsenal of Weapons**: Collect iconic Quake weapons including:
  - Axe (melee)
  - Shotgun and Double-Barrelled Shotgun
  - Nailgun and Super Nailgun
  - Grenade Launcher and Rocket Launcher
  - Thunderbolt (lightning gun)
- **Powerups**: Gain temporary advantages with Quad Damage, Invulnerability, Invisibility, and Biosuit
- **Armor System**: Protect yourself with Green Armor, Yellow Armor, and Red Armor
- **Experience & Leveling**: Gain XP from defeating enemies and level up your character
- **Save/Load System**: Save your progress and continue your adventure later

### Game Mechanics
- **Line of Sight**: Fog of war reveals the dungeon as you explore
- **Intelligent Enemy AI**: Enemies detect, pursue, and attack with various strategies
- **Inventory Management**: Collect and manage items with a 10-item capacity
- **Hazard Tiles**: Navigate around water and lava
- **Slipgates**: Portal between dungeon levels
- **The Rune**: Find the legendary Rune on map 20 and return to the entrance on map 1 to win!

## Installation & Setup

### Option 1: Play Online

The game is deployed on Azure and available at:

**https://quakelike.nicegrass-99f8552c.westeurope.azurecontainerapps.io**

### Option 2: Docker (Local)

```bash
# Build and run with docker-compose
docker-compose up --build

# Access the game at http://localhost:8080
```

### Option 3: Local Development

Requirements:
- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/)

```bash
# Install dependencies
uv sync

# Run the server
uv run python server.py

# Access the game at http://localhost:8080
```

## How to Play

### Starting the Game
1. Open your web browser and navigate to the online URL above, or `http://localhost:8080` if running locally
2. Click "New Game" to start a fresh adventure
3. Click "Load Game" to continue a saved game

### Controls

#### Movement
- `h` - Move left
- `j` - Move down
- `k` - Move up
- `l` - Move right
- `y` - Move diagonally up-left
- `u` - Move diagonally up-right
- `b` - Move diagonally down-left
- `n` - Move diagonally down-right

#### Actions
- `i` - Open/close inventory
- `x` - Pick up or drop items
- `Return` (Enter) - Use selected item
- `w` - Swap to previous weapon
- `t` - Enter targeting mode
- `f` - Fire equipped weapon
- `>` - Use slipgate down (descend to next level)
- `<` - Use slipgate up (ascend to previous level)

#### UI Navigation
- `Arrow Keys` - Navigate menus and lists
- `p` - View full message log
- `S` - Save game
- `Q` - Quit game
- `Escape` - Close menus/cancel targeting

### Objective

Your goal is to:
1. Explore the 40 dungeon levels
2. Find the **Rune** (located on map 20)
3. Return to the **Entrance** (E) on map 1
4. Survive the journey!

## Game Mechanics

### Combat
- **Melee Combat**: Walk into an enemy to attack with your axe (10-20 damage)
- **Ranged Combat**:
  - Press `t` to enter targeting mode
  - Use arrow keys to select an enemy
  - Press `f` to fire your equipped weapon
  - Different weapons have different ranges and ammo types

### Weapons & Ammo
- **Shells**: Ammunition for Shotgun and Double-Barrelled Shotgun
- **Nails**: Ammunition for Nailgun and Super Nailgun
- **Rockets**: Ammunition for Grenade Launcher and Rocket Launcher
- **Cells**: Ammunition for Thunderbolt

### Armor
- **Green Armor**: 100 armor points, 30% damage absorption
- **Yellow Armor**: 150 armor points, 60% damage absorption
- **Red Armor**: 200 armor points, 80% damage absorption

### Powerups
All powerups last for 30 turns:
- **Quad Damage**: Deal 4x damage with all weapons
- **Invulnerability**: Become immune to all damage
- **Invisibility**: Enemies have difficulty detecting you
- **Biosuit**: Protection from environmental hazards

### Enemy Types
| Enemy | Health | Special Abilities |
|-------|--------|-------------------|
| Rottweiler | 25 | Fast melee attacker |
| Grunt | 30 | Shotgun-wielding soldier |
| Rotfish | 25 | Swims in water |
| Knight | 75 | Armored melee fighter |
| Zombie | 60 | Throws projectiles |
| Scrag | 80 | Flying wizard with acid attack |
| Death Knight | 250 | Fire magic and melee |
| Ogre | 200 | Grenade launcher and chainsaw |
| Spawn | 80 | Explodes on contact |
| Fiend | 300 | Leaping demon |
| Vore | 400 | Fires homing projectiles |
| Shambler | 600 | Lightning attacks and devastating melee |

## Project Structure

```
Quakelike/
├── quakelike/              # Main game package
│   ├── game.py             # Game state and main loop
│   ├── gamemap.py          # Map generation and management
│   ├── player.py           # Player character class
│   ├── enemies.py          # Enemy definitions
│   ├── items.py            # Item and weapon definitions
│   ├── combat.py           # Combat system
│   ├── ai.py               # Enemy AI behavior
│   ├── inventory.py        # Inventory management
│   ├── entity.py           # Base entity classes
│   ├── message.py          # Message log system
│   └── constants.py        # Game constants and configuration
├── static/                 # Frontend assets
│   ├── index.html          # HTML interface
│   ├── game.js             # JavaScript game client
│   └── style.css           # Styling
├── tests/                  # Test suite
│   ├── test_game.py
│   ├── test_combat.py
│   ├── test_ai.py
│   └── ...                 # Additional test modules
├── server.py               # Flask web server
├── pyproject.toml          # Python project configuration
├── Dockerfile              # Docker container definition
├── docker-compose.yml      # Docker compose configuration
├── deploy.sh               # Azure deployment script
└── README.md               # This file
```

## Architecture

### Backend (Python)
- **Flask**: Web framework for serving the game
- **Flask-SocketIO**: Real-time WebSocket communication between client and server
- **Game Engine**: Pure Python game logic with no external game framework dependencies
- **State Management**: Complete game state serialization for save/load functionality

### Frontend (JavaScript)
- **Socket.IO Client**: Real-time communication with backend
- **Vanilla JavaScript**: No framework dependencies
- **Canvas-less Rendering**: Uses HTML/CSS for flexible, accessible display

### Communication Flow
1. Browser client connects via WebSocket
2. User inputs are sent to server
3. Server processes game logic
4. Complete game state is sent back to client
5. Client renders the updated state

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=quakelike --cov-report=html

# Run specific test module
uv run pytest tests/test_game.py
```

### Code Structure

- **Entity System**: Base `Entity` class for all game objects (player, enemies)
- **Component Pattern**: Separate systems for combat, AI, inventory, etc.
- **Procedural Generation**: Dungeon generation with room-corridor algorithm
- **Pathfinding**: Line-of-sight and movement AI using distance calculations
- **Save System**: JSON-based serialization of complete game state

### Adding New Content

#### Adding a New Enemy
Edit `quakelike/enemies.py`:

```python
NEW_ENEMY = EnemyDef(
    name='Enemy Name',
    char='X',
    color='#RRGGBB',
    health=100,
    speed=1,
    attacks=[...],
    xp_value=50,
    min_map_level=10,
    description='Description',
)
```

#### Adding a New Item
Edit `quakelike/items.py`:

```python
NEW_ITEM = ItemDef(
    name='Item Name',
    item_type=ItemType.WEAPON,
    char='?',
    color='#RRGGBB',
    # ... other properties
    description='Description',
)
```

## Technologies Used

### Backend
- **Python 3.10+**: Core game logic
- **Flask 3.0+**: Web server framework
- **Flask-SocketIO 5.3+**: WebSocket support
- **gevent 24.2+**: Async worker for WebSocket connections

### Frontend
- **HTML5**: Structure
- **CSS3**: Styling and layout
- **JavaScript (ES6+)**: Client-side game logic
- **Socket.IO Client**: Real-time communication

### Development & Testing
- **uv**: Package and project manager
- **pytest 8.0+**: Testing framework
- **pytest-cov 4.0+**: Code coverage
- **Docker**: Containerization
- **Docker Compose**: Local development environment

### Cloud Infrastructure
- **Azure Container Apps**: Serverless container hosting
- **Azure Container Registry**: Private Docker image registry
- **Azure Files**: Persistent storage for game saves

## Game Design Notes

### Differences from Original Quake
- **Turn-Based**: Unlike the fast-paced FPS, this is turn-based strategy
- **Top-Down View**: Classic roguelike ASCII display instead of 3D
- **Procedural Dungeons**: Each playthrough generates new map layouts
- **Roguelike Mechanics**: Permadeath, resource management, exploration

### Inspiration
This game combines elements from:
- **Quake (1996)**: Enemy types, weapons, items, and atmosphere
- **NetHack**: Classic roguelike mechanics and ASCII display
- **Dungeon Crawl Stone Soup**: Modern roguelike UI and balance

## License

This is a fan project inspired by Quake. Quake is a registered trademark of id Software LLC.

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

### Development Setup
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests to ensure everything works
5. Submit a pull request

## Tips for Playing

1. **Save Often**: Press `S` to save your progress regularly
2. **Manage Resources**: Ammo and health are limited, use them wisely
3. **Explore Thoroughly**: Each map may contain valuable items
4. **Learn Enemy Patterns**: Different enemies require different strategies
5. **Use Powerups Strategically**: Save powerful powerups for tough fights
6. **Level Up**: Gain XP by defeating enemies to increase your stats
7. **Armor Saves Lives**: Always wear the best armor you can find
8. **Know When to Retreat**: Use slipgates to escape dangerous situations

## Troubleshooting

### Game won't start
- Ensure Docker is running (if using Docker)
- Check that port 8080 is not in use by another application
- Verify Python 3.10+ is installed (if running locally)

### Can't connect to server
- Check that the server is running
- Verify you're accessing `http://localhost:8080`
- Check browser console for WebSocket connection errors

### Save game not loading
- Ensure you have a saved game (press `S` during gameplay)
- Check that `savegame.json` exists in the project directory

## Deployment

The game is hosted on Azure Container Apps. Deployment is managed via `deploy.sh`.

### Redeploy after code changes

```bash
./deploy.sh --update
```

This rebuilds the Docker image in Azure Container Registry and updates the running container app.

### First-time setup on a new Azure subscription

```bash
# Requires Azure CLI installed and logged in (az login)
./deploy.sh
```

### Teardown

```bash
az group delete --name quakelike-rg --yes --no-wait
```

### View live logs

```bash
az containerapp logs show --name quakelike --resource-group quakelike-rg --follow
```

## Acknowledgments

- id Software for creating Quake
- The roguelike development community for inspiration
- All playtesters and contributors

---

**Enjoy your descent into the dungeons! May you find the Rune and return victorious!**
