/**
 * Quakelike - Browser Frontend
 * Handles rendering and input for the roguelike game.
 */

let socket = null;
let gameState = null;

// ============================================================
// CONNECTION
// ============================================================

function initSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log('Connected to server');
    });

    socket.on('game_state', (state) => {
        gameState = state;
        const frames = state.travel_frames;
        if (frames && frames.length > 1) {
            animateTravelFrames(state, frames);
        } else {
            render(state);
        }
    });

    socket.on('error', (data) => {
        console.error('Server error:', data.message);
    });

    socket.on('disconnect', () => {
        console.log('Disconnected from server');
        showConnectionStatus('Connection lost. Reconnecting...');
    });

    socket.on('reconnect', () => {
        console.log('Reconnected to server');
        hideConnectionStatus();
    });
}

// ============================================================
// GAME ACTIONS
// ============================================================

function newGame() {
    if (!socket || !socket.connected) {
        initSocket();
        // Wait for connection before sending
        socket.on('connected', () => {
            socket.emit('new_game');
        });
    } else {
        socket.emit('new_game');
    }
    document.getElementById('title-screen').style.display = 'none';
    document.getElementById('game-screen').style.display = 'block';
}

function loadGame() {
    if (!socket || !socket.connected) {
        initSocket();
        socket.on('connected', () => {
            socket.emit('load_game');
        });
    } else {
        socket.emit('load_game');
    }
    document.getElementById('title-screen').style.display = 'none';
    document.getElementById('game-screen').style.display = 'block';
}

function sendInput(key) {
    if (socket && socket.connected) {
        socket.emit('input', { key: key });
    }
}

// ============================================================
// INPUT HANDLING
// ============================================================

document.addEventListener('keydown', (e) => {
    if (!gameState) return;

    // Handle Alt+t first (clear target) before regular 't' handling
    if (e.altKey && e.key === 't') {
        e.preventDefault();
        sendInput('Alt-t');
        return;
    }

    // Prevent default for game keys
    const gameKeys = [
        'h', 'j', 'k', 'l', 'y', 'u', 'b', 'n', '_',
        'i', 'x', 't', 'T', 'f', 'w', 'p', 'S', 'Q',
        '?', '>', '<', '.', ',', 'Enter', 'Escape', 'Tab',
        'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'
    ];

    let key = e.key;

    if (gameKeys.includes(key)) {
        e.preventDefault();
        // Map Enter to Return for consistency
        if (key === 'Enter') key = 'Return';
        sendInput(key);
    }
});

// ============================================================
// RENDERING
// ============================================================

function animateTravelFrames(finalState, frames) {
    // Find the player tile from the final destination position
    const destY = finalState.player_pos[0];
    const destX = finalState.player_pos[1];
    const playerTile = finalState.map[destY][destX];  // the '@' tile

    // Make a mutable deep copy of the map for animation
    const animMap = finalState.map.map(row => row.map(cell => Object.assign({}, cell)));

    let frameIndex = 0;

    function nextFrame() {
        if (frameIndex >= frames.length - 1) {
            // Last frame: render the real final state
            render(finalState);
            return;
        }

        const [y, x] = frames[frameIndex];

        // Restore previous frame position to its underlying tile from the final state
        if (frameIndex > 0) {
            const [prevY, prevX] = frames[frameIndex - 1];
            animMap[prevY][prevX] = Object.assign({}, finalState.map[prevY][prevX]);
        }

        // Place player at current frame position
        animMap[y][x] = Object.assign({}, playerTile);

        renderMap(Object.assign({}, finalState, { map: animMap }));

        frameIndex++;
        setTimeout(nextFrame, 30);
    }

    nextFrame();
}

function render(state) {
    renderMap(state);
    renderStatusBar(state);
    renderMessages(state);
    renderInventory(state);
    renderLoot(state);
    renderMessageLog(state);
    renderExamine(state);
    renderHelp(state);
    renderOverlays(state);
}

function renderMap(state) {
    const mapDisplay = document.getElementById('map-display');
    const map = state.map;

    let html = '';
    for (let y = 0; y < state.map_height; y++) {
        html += '<div class="map-row">';
        for (let x = 0; x < state.map_width; x++) {
            const tile = map[y][x];
            if (tile.cursor) {
                // Examine cursor: invert colors with a highlight style
                html += `<span class="tile examine-cursor" style="color:#000;background-color:#FFD700">${escapeHtml(tile.char)}</span>`;
            } else {
                html += `<span class="tile" style="color:${tile.color}">${escapeHtml(tile.char)}</span>`;
            }
        }
        html += '</div>';
    }
    mapDisplay.innerHTML = html;
}

function renderStatusBar(state) {
    const bar = document.getElementById('status-bar');
    const s = state.status;

    // Health color
    let healthClass = 'health-high';
    if (s.health <= 25) healthClass = 'health-low';
    else if (s.health <= 50) healthClass = 'health-mid';

    let html = '';
    html += `<span class="stat"><span class="stat-label">HP:</span> <span class="stat-value ${healthClass}">${s.health}/${s.max_health}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Armor:</span> <span class="stat-value armor-value">${s.armor}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Wpn:</span> <span class="stat-value weapon-name">${escapeHtml(s.weapon)}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Shl:</span> <span class="stat-value ammo-shells">${s.ammo.shells}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Nls:</span> <span class="stat-value ammo-nails">${s.ammo.nails}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Rkt:</span> <span class="stat-value ammo-rockets">${s.ammo.rockets}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Cls:</span> <span class="stat-value ammo-cells">${s.ammo.cells}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Lvl:</span> <span class="stat-value">${s.level}</span></span>`;
    html += `<span class="stat"><span class="stat-label">XP:</span> <span class="stat-value">${s.xp}</span></span>`;
    html += `<span class="stat"><span class="stat-label">Map:</span> <span class="stat-value">${s.map_level}/${40}</span></span>`;

    if (s.powerups && s.powerups.length > 0) {
        html += `<span class="stat powerup-active">${s.powerups.join(' ')}</span>`;
    }

    bar.innerHTML = html;
}

function renderMessages(state) {
    const area = document.getElementById('message-area');
    const msgs = state.messages || [];

    let html = '';
    for (const msg of msgs) {
        html += `<div class="message">${escapeHtml(msg)}</div>`;
    }
    area.innerHTML = html;
}

function renderInventory(state) {
    const panel = document.getElementById('inventory-panel');

    if (!state.show_inventory) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';
    panel.className = 'side-panel' + (state.active_panel === 'inventory' ? ' active-panel' : '');

    const list = document.getElementById('inventory-list');
    const items = state.inventory || [];

    if (items.length === 0) {
        list.innerHTML = '<div class="item-entry" style="color:#666">(empty)</div>';
        return;
    }

    let html = '';
    for (const item of items) {
        const selectedClass = item.selected ? ' selected' : '';
        const equippedMarker = item.equipped ? '<span class="equipped-marker">[E]</span>' : '';
        const qtyText = item.quantity > 1 ? `x${item.quantity}` : '';

        html += `<div class="item-entry${selectedClass}">`;
        html += `<span class="item-char" style="color:${item.color}">${escapeHtml(item.char)}</span>`;
        html += `<span class="item-name">${escapeHtml(item.name)}</span>`;
        html += equippedMarker;
        if (qtyText) html += `<span class="item-qty">${qtyText}</span>`;
        html += '</div>';
    }
    list.innerHTML = html;
}

function renderLoot(state) {
    const panel = document.getElementById('loot-panel');

    // Show loot panel whenever in INVENTORY or LOOT state
    if (!state.show_loot) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = 'block';
    panel.className = 'side-panel' + (state.active_panel === 'loot' ? ' active-panel' : '');

    const list = document.getElementById('loot-list');
    const items = state.loot || [];

    if (items.length === 0) {
        list.innerHTML = '<div class="item-entry" style="color:#666">(nothing here)</div>';
        return;
    }

    let html = '';
    for (const item of items) {
        const selectedClass = item.selected ? ' selected' : '';
        const qtyText = item.quantity > 1 ? `x${item.quantity}` : '';

        html += `<div class="item-entry${selectedClass}">`;
        html += `<span class="item-char" style="color:${item.color}">${escapeHtml(item.char)}</span>`;
        html += `<span class="item-name">${escapeHtml(item.name)}</span>`;
        if (qtyText) html += `<span class="item-qty">${qtyText}</span>`;
        html += '</div>';
    }
    list.innerHTML = html;
}

function renderMessageLog(state) {
    const overlay = document.getElementById('message-log-overlay');

    if (!state.show_message_log) {
        overlay.style.display = 'none';
        return;
    }

    overlay.style.display = 'block';

    const logDiv = document.getElementById('full-message-log');
    const msgs = state.all_messages || [];

    let html = '';
    for (let i = 0; i < msgs.length; i++) {
        html += `<div class="log-entry">${escapeHtml(msgs[i])}</div>`;
    }
    logDiv.innerHTML = html;

    // Auto-scroll to bottom
    logDiv.scrollTop = logDiv.scrollHeight;
}

function renderExamine(state) {
    let overlay = document.getElementById('examine-overlay');

    if (!state.show_examine) {
        if (overlay) overlay.style.display = 'none';
        return;
    }

    // Create overlay if it doesn't exist
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'examine-overlay';
        overlay.style.cssText = [
            'position:absolute',
            'bottom:0',
            'left:0',
            'right:0',
            'background:#1a1a1a',
            'border-top:1px solid #555',
            'padding:4px 8px',
            'font-family:monospace',
            'font-size:13px',
            'color:#FFD700',
            'z-index:100',
        ].join(';');
        const mainArea = document.getElementById('main-area');
        if (mainArea) {
            mainArea.style.position = 'relative';
            mainArea.appendChild(overlay);
        } else {
            document.getElementById('game-screen').appendChild(overlay);
        }
    }

    const info = state.examine_info || '';
    const cursor = state.examine_cursor || [0, 0];
    overlay.textContent = `[EXAMINE] (${cursor[0]},${cursor[1]}) ${info}  -- Esc or x to exit`;
    overlay.style.display = 'block';
}

function renderHelp(state) {
    let overlay = document.getElementById('help-overlay');

    if (!state.show_help) {
        if (overlay) overlay.style.display = 'none';
        return;
    }

    // Create overlay if it doesn't exist
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'help-overlay';
        overlay.style.cssText = [
            'position:fixed',
            'top:50%',
            'left:50%',
            'transform:translate(-50%,-50%)',
            'background:#111',
            'border:2px solid #FFD700',
            'padding:16px 24px',
            'font-family:monospace',
            'font-size:14px',
            'color:#ccc',
            'z-index:500',
            'max-height:80vh',
            'overflow-y:auto',
            'min-width:400px',
            'white-space:pre',
        ].join(';');
        document.body.appendChild(overlay);
    }

    const lines = state.help_content || [];
    overlay.textContent = lines.join('\n');
    overlay.style.display = 'block';
}

function renderOverlays(state) {
    const gameOver = document.getElementById('game-over-overlay');
    const victory = document.getElementById('victory-overlay');

    if (state.state === 'GAME_OVER') {
        gameOver.style.display = 'flex';
        victory.style.display = 'none';

        const stats = document.getElementById('death-stats');
        const s = state.status;
        stats.innerHTML = `
            <div>Level ${s.level} | XP: ${s.xp} | Map: ${s.map_level}/40 | Turn: ${s.turn}</div>
            <div>You were slain in the depths.</div>
        `;
    } else if (state.state === 'VICTORY') {
        victory.style.display = 'flex';
        gameOver.style.display = 'none';

        const stats = document.getElementById('victory-stats');
        const s = state.status;
        stats.innerHTML = `
            <div>Level ${s.level} | XP: ${s.xp} | Turn: ${s.turn}</div>
            <div>You retrieved the Rune and escaped!</div>
            <div>The nightmare is over... for now.</div>
        `;
    } else {
        gameOver.style.display = 'none';
        victory.style.display = 'none';
    }
}

// ============================================================
// UTILITIES
// ============================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showConnectionStatus(message) {
    let el = document.getElementById('connection-status');
    if (!el) {
        el = document.createElement('div');
        el.id = 'connection-status';
        el.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#c00;color:#fff;text-align:center;padding:4px;z-index:9999;font-family:monospace;';
        document.body.prepend(el);
    }
    el.textContent = message;
    el.style.display = 'block';
}

function hideConnectionStatus() {
    const el = document.getElementById('connection-status');
    if (el) el.style.display = 'none';
}

// ============================================================
// INITIALIZATION
// ============================================================

window.addEventListener('load', () => {
    initSocket();
});
