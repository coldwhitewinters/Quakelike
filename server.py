"""Flask web server for Quakelike."""

from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO, emit

from quakelike.game import Game

app = Flask(__name__, static_folder='static', template_folder='static')
socketio = SocketIO(app, cors_allowed_origins='*')

# Global game instance per session (single player for now)
games: dict[str, Game] = {}


def get_game(sid: str) -> Game:
    """Get or create a game for a session."""
    if sid not in games:
        games[sid] = Game()
    return games[sid]


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
    from flask import request
    sid = request.sid
    if sid in games:
        del games[sid]


@socketio.on('new_game')
def on_new_game(data=None):
    from flask import request
    sid = request.sid
    game = get_game(sid)
    seed = data.get('seed') if data else None
    game.new_game(seed=seed)
    state = game._get_render_state()
    emit('game_state', state)


@socketio.on('load_game')
def on_load_game():
    from flask import request
    sid = request.sid
    game = get_game(sid)
    if game.load_game():
        state = game._get_render_state()
        emit('game_state', state)
    else:
        emit('error', {'message': 'No save game found.'})


@socketio.on('input')
def on_input(data):
    from flask import request
    sid = request.sid
    game = get_game(sid)
    if game.player is None:
        emit('error', {'message': 'No game in progress. Start a new game.'})
        return

    key = data.get('key', '')
    state = game.handle_input(key)
    emit('game_state', state)


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
