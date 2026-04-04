/**
 * Quakelike - Browser Frontend
 * Handles rendering and input for the roguelike game.
 */

let socket = null;
let gameState = null;
let currentGameId = null;

// ============================================================
// SETTINGS STATE
// ============================================================

// Working copy of settings being edited in the overlay (never mutate directly)
let settingsWorkingCopy = null;  // { keybindings: {...}, game_options: {...} }

// Which keybinding action is currently awaiting a keypress (null if none)
let capturingAction = null;

// Human-readable labels for each action key
const ACTION_LABELS = {
    move_up:        'Move Up',
    move_down:      'Move Down',
    move_left:      'Move Left',
    move_right:     'Move Right',
    move_up_right:  'Move Up-Right',
    move_up_left:   'Move Up-Left',
    move_down_right:'Move Down-Right',
    move_down_left: 'Move Down-Left',
    inventory:      'Inventory',
    examine:        'Examine',
    fire:           'Fire',
    target_next:    'Target Next',
    target_prev:    'Target Prev',
    target_clear:   'Clear Target',
    swap_weapon:    'Swap Weapon',
    message_log:    'Message Log',
    help:           'Help',
    save:           'Save Game',
    quit:           'Quit',
    rest:           'Rest',
    pickup:         'Pick Up',
    slipgate_down:  'Slipgate Down',
    slipgate_up:    'Slipgate Up',
    fast_travel:    'Fast Travel',
};

// ============================================================
// CONNECTION
// ============================================================

function initSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log('Connected to server');
        socket.emit('list_saves');
    });

    socket.on('game_state', (state) => {
        gameState = state;
        if (state.game_id) {
            currentGameId = state.game_id;
        }
        if (state.goto_menu) {
            gotoMenu();
            return;
        }
        const projectileFrames = state.projectile_frames || [];
        const travelFrames = state.travel_frames || [];
        if (projectileFrames.length > 0) {
            animateProjectileFrames(state, projectileFrames, state.projectile_char, state.projectile_color);
        } else if (travelFrames.length > 1) {
            animateTravelFrames(state, travelFrames);
        } else {
            render(state);
        }
    });

    socket.on('saves_list', (data) => {
        const saves = data.saves || [];
        const continueBtn = document.getElementById('continue-btn');
        if (saves.length > 0) {
            continueBtn.disabled = false;
        } else {
            continueBtn.disabled = true;
        }
        populateSavesList(saves);
    });

    socket.on('goto_menu', () => {
        gotoMenu();
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

    socket.on('settings_data', (data) => {
        renderSettings(data);
    });

    socket.on('settings_saved', () => {
        showSettingsMessage('Settings saved.', 'success');
        setTimeout(() => {
            closeSettings();
        }, 800);
    });

    socket.on('settings_error', (data) => {
        const msg = (data && data.message) ? data.message : 'An error occurred saving settings.';
        showSettingsMessage(msg, 'error');
    });
}

// ============================================================
// GAME ACTIONS
// ============================================================

function newGame() {
    if (!socket || !socket.connected) {
        initSocket();
        // Use once() to avoid accumulating duplicate listeners across calls
        socket.once('connected', () => {
            socket.emit('new_game');
        });
    } else {
        socket.emit('new_game');
    }
    document.getElementById('title-screen').style.display = 'none';
    document.getElementById('game-screen').style.display = 'block';
}

function continueGame() {
    if (!socket || !socket.connected) {
        initSocket();
        // Use once() to avoid accumulating duplicate listeners across calls
        socket.once('connected', () => {
            socket.emit('list_saves');
        });
    } else {
        socket.emit('list_saves');
    }
    document.getElementById('game-select-overlay').style.display = 'block';
}

function loadSave(gameId) {
    document.getElementById('game-select-overlay').style.display = 'none';
    if (!socket || !socket.connected) {
        initSocket();
        // Use once() to avoid accumulating duplicate listeners across calls
        socket.once('connected', () => {
            socket.emit('load_game', { game_id: gameId });
        });
    } else {
        socket.emit('load_game', { game_id: gameId });
    }
    document.getElementById('title-screen').style.display = 'none';
    document.getElementById('game-screen').style.display = 'block';
}

function populateSavesList(saves) {
    const listEl = document.getElementById('saves-list');
    if (!listEl) return;
    if (saves.length === 0) {
        listEl.innerHTML = '<div style="color:#888; padding:8px;">No saved games found.</div>';
        return;
    }
    let html = '';
    for (const save of saves) {
        const date = save.timestamp
            ? new Date(save.timestamp * 1000).toLocaleString()
            : 'Unknown date';
        const displayName = save.display_name || save.id;
        html += `<div style="display:flex; align-items:center; justify-content:space-between; padding:6px 0; border-bottom:1px solid #333;">`;
        html += `<div style="color:#ccc; flex:1;">`;
        html += `<div>${escapeHtml(displayName)}</div>`;
        html += `<div style="color:#666; font-size:0.85em;">${escapeHtml(date)}</div>`;
        html += `</div>`;
        html += `<button onclick="loadSave('${escapeHtml(save.id)}')" style="margin-left:10px; color:#0f0;">Load</button>`;
        html += `</div>`;
    }
    listEl.innerHTML = html;
}

function gotoMenu() {
    gameState = null;
    currentGameId = null;
    document.getElementById('game-screen').style.display = 'none';
    document.getElementById('title-screen').style.display = 'block';
    // Hide any open overlays from the game screen
    document.getElementById('quit-confirm-overlay').style.display = 'none';
    if (socket && socket.connected) {
        socket.emit('list_saves');
    }
}

function sendInput(key) {
    if (socket && socket.connected) {
        socket.emit('input', { key: key });
    }
}

// ============================================================
// SETTINGS
// ============================================================

function openSettings() {
    // Ensure socket is initialised (may be called before a game starts)
    if (!socket || !socket.connected) {
        initSocket();
    }
    // Reset any previous capture state
    capturingAction = null;
    document.getElementById('settings-overlay').style.display = 'block';
    // Always start on the keybindings tab
    switchSettingsTab('keybindings');
    socket.emit('get_settings');
}

function closeSettings() {
    capturingAction = null;
    document.getElementById('settings-overlay').style.display = 'none';
    hideSettingsMessage();
    settingsWorkingCopy = null;
}

function switchSettingsTab(tab) {
    const kbSection = document.getElementById('settings-keybindings-section');
    const optSection = document.getElementById('settings-options-section');
    const kbTab = document.getElementById('settings-tab-keybindings');
    const optTab = document.getElementById('settings-tab-options');

    if (tab === 'keybindings') {
        kbSection.style.display = 'block';
        optSection.style.display = 'none';
        kbTab.classList.add('settings-tab-active');
        optTab.classList.remove('settings-tab-active');
    } else {
        kbSection.style.display = 'none';
        optSection.style.display = 'block';
        kbTab.classList.remove('settings-tab-active');
        optTab.classList.add('settings-tab-active');
    }
    // Cancel any key capture when switching tabs
    if (capturingAction) {
        capturingAction = null;
        renderKeybindingsTable(settingsWorkingCopy ? settingsWorkingCopy.keybindings : {});
    }
}

/**
 * Called when the server emits settings_data.
 * Takes a deep copy so that editing the table never modifies the server-sent data.
 */
function renderSettings(data) {
    settingsWorkingCopy = {
        keybindings: Object.assign({}, data.keybindings || {}),
        game_options: Object.assign({}, data.game_options || {}),
    };
    capturingAction = null;
    hideSettingsMessage();
    renderKeybindingsTable(settingsWorkingCopy.keybindings);
    renderGameOptions(settingsWorkingCopy.game_options);
}

function renderKeybindingsTable(keybindings) {
    const tbody = document.getElementById('settings-keybindings-body');
    if (!tbody) return;

    const actions = Object.keys(ACTION_LABELS);
    let html = '';
    for (const action of actions) {
        const label = ACTION_LABELS[action] || action;
        const key = keybindings[action] || '';
        const isCapturing = capturingAction === action;

        const rowClass = isCapturing ? ' class="capturing"' : '';
        const cellClass = isCapturing ? ' capturing' : '';
        const keyDisplay = isCapturing ? '[press any key]' : escapeHtml(key);

        html += `<tr${rowClass} data-action="${escapeHtml(action)}" onclick="startKeyCapture('${escapeHtml(action)}')">`;
        html += `<td>${escapeHtml(label)}</td>`;
        html += `<td class="key-cell${cellClass}">${keyDisplay}</td>`;
        html += '</tr>';
    }
    tbody.innerHTML = html;
}

function renderGameOptions(options) {
    const speedEl = document.getElementById('settings-animation-speed');
    const msgsEl = document.getElementById('settings-max-messages');
    if (speedEl && options.animation_speed_ms !== undefined) {
        speedEl.value = options.animation_speed_ms;
    }
    if (msgsEl && options.max_visible_messages !== undefined) {
        msgsEl.value = options.max_visible_messages;
    }
}

/**
 * Enter key-capture mode for the given action row.
 * Clicking a row that is already capturing cancels the capture.
 */
function startKeyCapture(action) {
    if (capturingAction === action) {
        // Cancel capture on second click
        capturingAction = null;
        renderKeybindingsTable(settingsWorkingCopy.keybindings);
        return;
    }
    capturingAction = action;
    renderKeybindingsTable(settingsWorkingCopy.keybindings);
}

/**
 * Normalise a KeyboardEvent into the string format used by the backend.
 * Returns null when the key should cancel capture (Escape).
 */
function normaliseKey(e) {
    if (e.key === 'Escape') return null;
    if (e.key === 'Enter') return 'Return';
    // Alt+key combos
    if (e.altKey && e.key.length === 1) return 'Alt-' + e.key;
    // Pass through everything else verbatim (handles ArrowUp, Tab, single chars, etc.)
    return e.key;
}

/**
 * Called from the document keydown handler when the settings overlay is open
 * and capturingAction is set.
 */
function handleSettingsKeyCapture(e) {
    e.preventDefault();
    e.stopPropagation();

    if (!settingsWorkingCopy || !capturingAction) return;

    const key = normaliseKey(e);

    if (key === null) {
        // Escape pressed — cancel capture without changing the binding
        capturingAction = null;
        renderKeybindingsTable(settingsWorkingCopy.keybindings);
        return;
    }

    const action = capturingAction;

    // Check for conflicts with other actions
    const conflictAction = findConflict(key, action, settingsWorkingCopy.keybindings);

    if (conflictAction) {
        const conflictLabel = ACTION_LABELS[conflictAction] || conflictAction;
        // Show conflict inline in the row rather than blocking the assignment
        showConflictInRow(action, key, conflictLabel);
        return;
    }

    // Apply binding
    settingsWorkingCopy.keybindings[action] = key;
    capturingAction = null;
    renderKeybindingsTable(settingsWorkingCopy.keybindings);
    hideSettingsMessage();
}

/**
 * Returns the name of the action already using `key`, excluding `excludeAction`.
 * Returns null if no conflict.
 */
function findConflict(key, excludeAction, keybindings) {
    for (const [action, boundKey] of Object.entries(keybindings)) {
        if (action !== excludeAction && boundKey === key) {
            return action;
        }
    }
    return null;
}

/**
 * Show an inline conflict warning in the capturing row.
 * The row remains in capture mode so the user can try a different key.
 */
function showConflictInRow(action, key, conflictLabel) {
    const tbody = document.getElementById('settings-keybindings-body');
    if (!tbody) return;

    const actions = Object.keys(ACTION_LABELS);
    let html = '';
    for (const a of actions) {
        const label = ACTION_LABELS[a] || a;
        const boundKey = settingsWorkingCopy.keybindings[a] || '';
        const isCapturing = a === action;

        if (isCapturing) {
            html += `<tr class="conflict" data-action="${escapeHtml(a)}" onclick="startKeyCapture('${escapeHtml(a)}')">`;
            html += `<td>${escapeHtml(label)}</td>`;
            html += `<td class="key-cell capturing">[press any key]</td>`;
            html += '</tr>';
            // Append a hint row
            html += `<tr class="conflict" style="cursor:default;" onclick="startKeyCapture('${escapeHtml(a)}')">`;
            html += `<td colspan="2" class="conflict-hint" style="padding:2px 8px 6px;">`;
            html += `"${escapeHtml(key)}" already bound to: ${escapeHtml(conflictLabel)}`;
            html += `</td></tr>`;
        } else {
            const rowClass = capturingAction === a ? ' class="capturing"' : '';
            const cellClass = capturingAction === a ? ' capturing' : '';
            html += `<tr${rowClass} data-action="${escapeHtml(a)}" onclick="startKeyCapture('${escapeHtml(a)}')">`;
            html += `<td>${escapeHtml(label)}</td>`;
            html += `<td class="key-cell${cellClass}">${escapeHtml(boundKey)}</td>`;
            html += '</tr>';
        }
    }
    tbody.innerHTML = html;
}

function collectCurrentSettings() {
    if (!settingsWorkingCopy) return null;

    const speedEl = document.getElementById('settings-animation-speed');
    const msgsEl = document.getElementById('settings-max-messages');

    const game_options = Object.assign({}, settingsWorkingCopy.game_options);
    if (speedEl) {
        game_options.animation_speed_ms = parseInt(speedEl.value, 10) || game_options.animation_speed_ms;
    }
    if (msgsEl) {
        game_options.max_visible_messages = parseInt(msgsEl.value, 10) || game_options.max_visible_messages;
    }

    return {
        keybindings: Object.assign({}, settingsWorkingCopy.keybindings),
        game_options,
    };
}

function showSettingsMessage(text, type) {
    const el = document.getElementById('settings-message');
    if (!el) return;
    el.textContent = text;
    el.style.display = 'block';
    if (type === 'error') {
        el.style.background = '#2a0000';
        el.style.color = '#f88';
        el.style.border = '1px solid #c00';
    } else {
        el.style.background = '#002a00';
        el.style.color = '#8f8';
        el.style.border = '1px solid #0a0';
    }
}

function hideSettingsMessage() {
    const el = document.getElementById('settings-message');
    if (el) el.style.display = 'none';
}

function isSettingsOpen() {
    const overlay = document.getElementById('settings-overlay');
    return overlay && overlay.style.display !== 'none';
}

// ============================================================
// INPUT HANDLING
// ============================================================

document.addEventListener('keydown', (e) => {
    // If settings overlay is open, route all input through settings handling
    if (isSettingsOpen()) {
        if (capturingAction) {
            handleSettingsKeyCapture(e);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            closeSettings();
        }
        return;
    }

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
        'i', 'x', 't', 'T', 'f', 'w', 'p', 'S', 'Q', 'O',
        '?', '>', '<', '.', ',', 'Enter', 'Escape', 'Tab',
        'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'
    ];

    let key = e.key;

    if (gameKeys.includes(key)) {
        e.preventDefault();
        // Intercept Q to show quit confirmation instead of sending to server
        if (key === 'Q') {
            document.getElementById('quit-confirm-overlay').style.display = 'block';
            return;
        }
        // Intercept O to open settings overlay without sending to server
        if (key === 'O') {
            openSettings();
            return;
        }
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

// Animates a projectile tile-by-tile along a pre-computed Bresenham path (30ms per tile),
// then renders the final post-shot game state once the animation completes.
function animateProjectileFrames(state, frames, char, color) {
    // Make a mutable deep copy of the map for animation
    const animMap = state.map.map(row => row.map(cell => Object.assign({}, cell)));

    let i = 0;

    function nextFrame() {
        // Restore previous frame position to its original tile from the final state
        if (i > 0) {
            const [py, px] = frames[i - 1];
            animMap[py][px] = Object.assign({}, state.map[py][px]);
        }
        if (i < frames.length) {
            const [fy, fx] = frames[i];
            animMap[fy][fx] = { char: char, color: color };
            renderMap(Object.assign({}, state, { map: animMap }));
            i++;
            setTimeout(nextFrame, 30);
        } else {
            render(state);
        }
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
            } else if (tile.targeted) {
                html += `<span class="tile" style="color:#000;background-color:#FF0000">${escapeHtml(tile.char)}</span>`;
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

    document.getElementById('close-game-select').onclick = function() {
        document.getElementById('game-select-overlay').style.display = 'none';
    };

    document.getElementById('confirm-quit-yes').onclick = function() {
        document.getElementById('quit-confirm-overlay').style.display = 'none';
        socket.emit('quit_without_save');
    };

    document.getElementById('confirm-quit-no').onclick = function() {
        document.getElementById('quit-confirm-overlay').style.display = 'none';
    };

    document.getElementById('settings-save-btn').onclick = function() {
        const settings = collectCurrentSettings();
        if (!settings) return;
        if (socket && socket.connected) {
            socket.emit('save_settings', settings);
        }
    };

    document.getElementById('settings-reset-btn').onclick = function() {
        if (socket && socket.connected) {
            socket.emit('reset_settings');
        }
    };

    document.getElementById('settings-cancel-btn').onclick = function() {
        closeSettings();
    };
});
