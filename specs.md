# Quakelike

## The game

Quakelike is a roguelike based on the original quake. The idea is to have something like a hybrid between nethack and quake 1. The mechanics will be relatively simple, resembling those of quake, but the interface and gameplay will be that of nethack.

## Programming language

Python for all the game logic and you can choose between Python or Javascript for the frontend. 

## Development

Split the main problem into smaller subproblems. From these subproblems define features that need to be developed. 

Make an implementation plan that organizes the development of all the needed features and execute it.
Use a TDD methodology for development. Write tests for all the required features, implement the features and then make sure that all the tests are passing and that the game behaves as it should.

The tests should reflect the required functionality as given by the specs defined in this document, together with any extra functionality and code required to satisfy these requirements.

Tests should not be written just so that they pass, but they should be written to really cover the functionality that should be implemented.

When a feature is done, make a pull request and review it. If there are any deficiencies in the code, then it should be improved until no further improvements are required. At that stage the feature branch can be merged into main.

## Controls

The controls are case sensitive

k: go up
j: go down
l: go right
h: go left
u: go diagonally up-right
y: go diagonally up-left
n: go diagonally down-right
b: go diagonally down-left
>: go down staircase
<: go up staircase
i: open inventory
x: pick/drop items
return: use/activate item
t: target enemies
f: fire weapon
w: equip previously equipped weapon
p: open message log
_: enter fast travel cursor mode (move cursor with movement keys, _ to confirm teleport, Escape to cancel)
S: save game
Q: quit game without saving

## Map

The maps should be procedurally generated.

The game consists of multiple maps. There should be 40 maps.

The maps are connected by slipgates, like in quake.

You can go back and forth between maps using the slipgate.

The first map contains the entrance, which is a special gate that the player should return to once he has fulfilled the victory condition.

The last map contains a rune, which is required to win the game.

The maps should be indoor areas that resemble the architecture and design of quake levels. 

The terrain, walls and objects should reflect the environment elements present in quake.

ASCII should be used to render the map. No tiles.

## UI

The game should have a text interface.

The game should be playable in a browser. 

There should be a main window that displays the whole game environment like in any roguelike.

There should be a status bar, with info about the health, armor and ammo count for the different weapons, together with the experience level and other such status information about the character

There should be a small area to display incoming messages. Only the last three messages should be displayed.

A window with the inventory should be displayed when pressing the "inventory key". It should be positioned on the right side.

If there is something that can be looted where the player is standing, then another window should be opened on the left to display the contents that can be looted. In this case one would have the loot and the inventory side by side, and it should be possible to move things from the loot to the inventory and vice-versa.

Navigation through the inventory should be possible with the up and down keys.

Left and right keys cycles between the loot and inventory windows.

The "pick/drop key" moves things from the inventory to the loot/floor or from the loot/floor to the inventory.

The "pick/drop key" can be used without opening the inventory. When standing on something that can be picked, that key should open the loot panel and the inventory panel and set the cursor on the first item of the loot panel.

The "use key" should activate the selected item if it is possible to use it.

Targeted enemies are highlighted.

Appropiate characters and colors are chosen for each enemy, item and terrain feature.

Messages should be displayed giving additional information about things that can't be shown directly on the rendered environment, like incoming damage and damage dealt during combat, who attacked whom, the nature of the attack, the results of interacting with the environment, activation of items, etc.

## Inventory

The inventory should have a maximum capacity of ten items.

## Enemies

The enemies should be the same as the ones present in quake. All of them should be included, no more, no less. Their attacks, stats and behaviors should reflect the ones in the original game as much as possible.

## Items

Items should include all weapons, ammo, armor, medpacks, and powerups that are available in quake and nothing else. 

Their stats and behaviors should be as close to the original game as possible.

Weapons should be equipped to be fired. They can be equipped by activating them in the inventory menu. Only a single weapon can be equipped at a given time.

There is a key to equip the previously equipped weapon. This can be used to quickly swap weapons without going to the inventory.

The ammo should be stored in the inventory to be available. If there is no ammo for a particular weapon in the inventory then it can't  be fired.

Ammo can't be activated, only stored. 

The armor should be activated to fill the armor counter.

The medpacks should be activated to refill the health counter.

Items that can be activated are consumed after activation.

## Combat

With the target key one can cycle through the enemies on the player's line of sight

With the fire key one can fire the currently equipped weapon to the targeted enemy, or straight ahead if nothing is targetted.

One can always perform melee attacks on enemies that are standing next to the player by walking towards them. The damage should be the same as the one dealt when using the axe in the original game.

The enemies should only attack the player.

Friendly fire is enabled. Enemies can deal damage to each other by accident.

Enemies should avoid hitting their comrades during combat.

## Death

Death is permanent and ends the game. An end game screen should be displayed when over.

## Victory 

The objective is to reach the last map (map 40) retrieve the rune, and bring it back to the entrance at the beginning. A victory screen should be displayed in this case.