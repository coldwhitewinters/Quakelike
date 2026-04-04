"""Flask web server for Quakelike."""

import os
import threading
import time
import webbrowser

from flask import Flask, render_template, send_from_directory, request
from flask_socketio import SocketIO, emit

from quakelike.game import Game, _validate_game_id
from quakelike.settings import GameSettings

# Path to the global settings file.  Tests patch quakelike.settings.SETTINGS_PATH
# directly; server handlers load settings via GameSettings.load() which reads
# from that module-level variable, so patching quakelike.settings.SETTINGS_PATH
# is sufficient to redirect reads/writes in both module and server handlers.
SETTINGS_PATH = 'settings.json'

app = Flask(__name__, static_folder='static', template_folder='static')
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:8080')
socketio = SocketIO(app, cors_allowed_origins=cors_origins)

# Session timeout in seconds (1 hour)
SESSION_TIMEOUT = 3600

# Game sessions with last-activity timestamps
games: dict[str, Game] = {}
last_activity: dict[str, float] = {}


def get_game(sid: str) -> Game:
    """Get or create a game for a session."""
    if sid not in games:
        _cleanup_stale_sessions()
        games[sid] = Game()
    last_activity[sid] = time.time()
    return games[sid]


def _cleanup_stale_sessions() -> None:
    """Remove sessions that have been inactive longer than SESSION_TIMEOUT."""
    now = time.time()
    stale = [sid for sid, ts in last_activity.items()
             if now - ts > SESSION_TIMEOUT]
    for sid in stale:
        games.pop(sid, None)
        last_activity.pop(sid, None)


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@socketio.on('connect')
def on_connect():
    emit('connected', {'status': 'ok'})


@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    games.pop(sid, None)
    last_activity.pop(sid, None)


@socketio.on('new_game')
def on_new_game(data=None):
    sid = request.sid
    game = get_game(sid)
    seed = data.get('seed') if data else None
    # Load current settings so remapped keys take effect in this session
    game.settings = GameSettings.load()
    game.new_game(seed=seed)
    state = game.get_render_state()
    emit('game_state', state)


@socketio.on('load_game')
def on_load_game(data=None):
    sid = request.sid
    game = get_game(sid)
    game_id = data.get('game_id') if isinstance(data, dict) else None
    # Reject non-UUID game_id values before passing to load_game() to prevent
    # path-traversal attacks from a malicious client.
    if game_id is not None and not _validate_game_id(game_id):
        emit('error', {'message': 'Invalid game ID.'})
        return
    if game.load_game(game_id=game_id):
        state = game.get_render_state()
        emit('game_state', state)
    else:
        emit('error', {'message': 'No save game found.'})


@socketio.on('list_saves')
def on_list_saves():
    from quakelike.game import list_saves
    saves = list_saves()
    emit('saves_list', {'saves': saves})


@socketio.on('quit_without_save')
def on_quit_without_save():
    sid = request.sid
    game = games.get(sid)
    if game:
        game.quit_without_save()
        games.pop(sid, None)
        last_activity.pop(sid, None)
    emit('goto_menu', {})


@socketio.on('input')
def on_input(data):
    if not isinstance(data, dict):
        emit('error', {'message': 'Invalid input format.'})
        return
    key = data.get('key', '')
    if not isinstance(key, str) or len(key) > 20:
        emit('error', {'message': 'Invalid key.'})
        return

    sid = request.sid
    game = get_game(sid)
    if game.player is None:
        emit('error', {'message': 'No game in progress. Start a new game.'})
        return

    state = game.handle_input(key)
    if state.get('goto_menu'):
        games.pop(sid, None)
        last_activity.pop(sid, None)
        emit('goto_menu', {})
    else:
        emit('game_state', state)


@socketio.on('get_settings')
def on_get_settings():
    """Emit current settings (loaded from disk or defaults if file is absent/corrupt)."""
    settings = GameSettings.load()
    emit('settings_data', settings.to_dict())


@socketio.on('save_settings')
def on_save_settings(data):
    """Validate and persist incoming settings; update active game session if any."""
    from quakelike.settings import DEFAULT_KEYBINDINGS as _DEFAULT_KB

    if not isinstance(data, dict):
        emit('settings_error', {'message': 'Invalid settings payload.'})
        return

    # Reject payloads that are missing any required action — from_dict() would
    # silently fill in defaults, masking the omission from validate().
    submitted_bindings = data.get("keybindings", {})
    if not isinstance(submitted_bindings, dict):
        emit('settings_error', {'message': 'keybindings must be a dict.'})
        return
    missing = [a for a in _DEFAULT_KB if a not in submitted_bindings]
    if missing:
        emit('settings_error', {
            'message': f"Missing required action(s): {', '.join(missing)}"
        })
        return

    try:
        settings = GameSettings.from_dict(data)
        settings.validate()
    except (ValueError, TypeError) as exc:
        emit('settings_error', {'message': str(exc)})
        return

    settings.save()

    # Update the active game session so remapped keys take effect immediately
    sid = request.sid
    game = games.get(sid)
    if game is not None:
        game.settings = settings

    emit('settings_saved', settings.to_dict())


@socketio.on('reset_settings')
def on_reset_settings():
    """Reset settings to defaults, persist them, and emit the default settings_data."""
    settings = GameSettings.reset()
    sid = request.sid
    game = games.get(sid)
    if game is not None:
        game.settings = settings
    emit('settings_data', settings.to_dict())


if __name__ == '__main__':
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    threading.Timer(1.0, lambda: webbrowser.open('http://localhost:8080')).start()
    socketio.run(app, host='0.0.0.0', port=8080, debug=debug)
