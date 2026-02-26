/**
 * QUAEST.TECH — World Scene
 * Main game scene: tile rendering via RenderTexture, player movement,
 * district detection, NPC interaction, and UI overlays.
 */

import Phaser from 'phaser';
import {
  TILE_SIZE, MAP_COLS, MAP_ROWS, WORLD_W, WORLD_H,
  TILE, SOLID_TILES, DISTRICTS, SPAWN, PLAYER_SPEED,
} from '../config.js';
import { generateMap, getDistrictAt } from '../utils/mapGenerator.js';

export class WorldScene extends Phaser.Scene {
  constructor() {
    super({ key: 'WorldScene' });
  }

  create() {
    // Get callbacks from React via game registry
    this._callbacksRef = this.game.registry.get('callbacks');

    // ── Generate map data ──
    this.mapData = generateMap();

    // ── Render map using RenderTexture (one draw call) ──
    this._renderMap();

    // ── Player ──
    this._createPlayer();

    // ── NPCs ──
    this.npcs = [];
    this._placeNPCs();

    // ── Camera ──
    this.cameras.main.setBounds(0, 0, WORLD_W, WORLD_H);
    this.cameras.main.startFollow(this.player, true, 0.08, 0.08);
    this.cameras.main.setZoom(2);

    // ── Input ──
    this.cursors = this.input.keyboard.createCursorKeys();
    this.wasd = this.input.keyboard.addKeys({
      up: Phaser.Input.Keyboard.KeyCodes.W,
      down: Phaser.Input.Keyboard.KeyCodes.S,
      left: Phaser.Input.Keyboard.KeyCodes.A,
      right: Phaser.Input.Keyboard.KeyCodes.D,
    });
    this.interactKey = this.input.keyboard.addKey(Phaser.Input.Keyboard.KeyCodes.E);

    // ── UI Overlays ──
    this.currentDistrict = null;
    this.labelTween = null;
    this.interactTarget = null;
    this._clickMoveTimer = null;
    this._dialogBubble = null;

    this._createDistrictLabel();
    this._createInteractPrompt();
    this._createMinimap();
    this._createCoordDisplay();

    // ── Click-to-move ──
    this.input.on('pointerdown', (pointer) => {
      const worldPoint = this.cameras.main.getWorldPoint(pointer.x, pointer.y);
      this._movePlayerTo(worldPoint.x, worldPoint.y);
    });

    // ── Interact key ──
    this.interactKey.on('down', () => {
      if (this.interactTarget) {
        this._handleInteraction(this.interactTarget);
      }
    });

    // Check initial district
    this._checkDistrict();
  }

  update(time) {
    if (!this.player) return;

    const speed = PLAYER_SPEED;
    let vx = 0, vy = 0;

    if (this.cursors.left.isDown || this.wasd.left.isDown) vx = -speed;
    else if (this.cursors.right.isDown || this.wasd.right.isDown) vx = speed;

    if (this.cursors.up.isDown || this.wasd.up.isDown) vy = -speed;
    else if (this.cursors.down.isDown || this.wasd.down.isDown) vy = speed;

    // Normalize diagonal
    if (vx !== 0 && vy !== 0) {
      vx /= 1.414;
      vy /= 1.414;
    }

    // Cancel click-to-move on keyboard input
    if (vx !== 0 || vy !== 0) {
      if (this._clickMoveTimer) {
        this._clickMoveTimer.remove();
        this._clickMoveTimer = null;
      }
    }

    // Apply velocity
    this.player.body.setVelocity(vx, vy);

    // Direction + walk animation
    const moving = vx !== 0 || vy !== 0;
    if (moving) {
      const walkFrame = Math.floor(time / 200) % 2;
      let dir = 'down';
      if (vy < 0) dir = 'up';
      else if (vy > 0) dir = 'down';
      else if (vx < 0) dir = 'left';
      else if (vx > 0) dir = 'right';
      this.player.setTexture(`player_${dir}_${walkFrame}`);
    }

    // Tile collision
    this._handleCollision();

    // District check
    this._checkDistrict();

    // Interaction proximity
    this._checkInteractionProximity();

    // Update minimap + coords
    this._updateMinimap();
    this._updateCoords();
  }

  // ─── Notify React via callbacks ref ───
  _notify(type, data) {
    const cbs = this._callbacksRef?.current;
    if (!cbs) return;
    if (type === 'district' && cbs.onDistrictChange) cbs.onDistrictChange(data);
    if (type === 'interact' && cbs.onInteract) cbs.onInteract(data);
  }

  // ─────────────────────────────────────────────
  // MAP RENDERING (RenderTexture)
  // ─────────────────────────────────────────────

  _renderMap() {
    const rt = this.add.renderTexture(0, 0, WORLD_W, WORLD_H).setOrigin(0, 0).setDepth(0);

    for (let r = 0; r < MAP_ROWS; r++) {
      for (let c = 0; c < MAP_COLS; c++) {
        const tileId = this.mapData[r][c];
        const key = `tile_${tileId}`;
        rt.drawFrame(key, undefined, c * TILE_SIZE, r * TILE_SIZE);
      }
    }
  }

  // ─────────────────────────────────────────────
  // PLAYER
  // ─────────────────────────────────────────────

  _createPlayer() {
    // Player starts facing down, frame 0
    this.player = this.physics.add.sprite(SPAWN.x, SPAWN.y, 'player_down_0');
    this.player.setOrigin(0.5, 0.5);
    this.player.setDepth(10);
    this.player.body.setSize(10, 10);
    this.player.body.setOffset(3, 5);
    this.player.body.setCollideWorldBounds(true);

    this.physics.world.setBounds(0, 0, WORLD_W, WORLD_H);
  }

  // ─────────────────────────────────────────────
  // COLLISION
  // ─────────────────────────────────────────────

  _handleCollision() {
    const px = this.player.x;
    const py = this.player.y;
    const vx = this.player.body.velocity.x;
    const vy = this.player.body.velocity.y;

    // Check X direction
    if (vx !== 0) {
      const testX = px + (vx > 0 ? 6 : -6);
      const testCol = Math.floor(testX / TILE_SIZE);
      const testRow = Math.floor(py / TILE_SIZE);
      if (this._isSolid(testCol, testRow)) {
        this.player.body.velocity.x = 0;
      }
    }

    // Check Y direction
    if (vy !== 0) {
      const testY = py + (vy > 0 ? 7 : -3);
      const testCol = Math.floor(px / TILE_SIZE);
      const testRow = Math.floor(testY / TILE_SIZE);
      if (this._isSolid(testCol, testRow)) {
        this.player.body.velocity.y = 0;
      }
    }
  }

  _isSolid(col, row) {
    if (row < 0 || row >= MAP_ROWS || col < 0 || col >= MAP_COLS) return true;
    return SOLID_TILES.has(this.mapData[row][col]);
  }

  // ─────────────────────────────────────────────
  // CLICK-TO-MOVE
  // ─────────────────────────────────────────────

  _movePlayerTo(worldX, worldY) {
    const dx = worldX - this.player.x;
    const dy = worldY - this.player.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < 8) return;

    const angle = Math.atan2(dy, dx);
    this.player.body.velocity.x = Math.cos(angle) * PLAYER_SPEED;
    this.player.body.velocity.y = Math.sin(angle) * PLAYER_SPEED;

    if (this._clickMoveTimer) this._clickMoveTimer.remove();
    this._clickMoveTimer = this.time.delayedCall((dist / PLAYER_SPEED) * 1000, () => {
      if (this.player?.body) {
        this.player.body.velocity.x = 0;
        this.player.body.velocity.y = 0;
      }
    });
  }

  // ─────────────────────────────────────────────
  // DISTRICTS
  // ─────────────────────────────────────────────

  _createDistrictLabel() {
    const cx = this.cameras.main.width / 2;

    this.districtLabelBg = this.add.rectangle(cx, 8, 200, 40, 0x000000, 0.7)
      .setScrollFactor(0).setOrigin(0.5, 0).setDepth(100).setVisible(false);

    this.districtLabel = this.add.text(cx, 14, '', {
      fontFamily: 'Cinzel, serif',
      fontSize: '12px',
      fontStyle: 'bold',
      color: '#F2F2F2',
      align: 'center',
    }).setScrollFactor(0).setOrigin(0.5, 0).setDepth(101).setVisible(false);

    this.districtDescText = this.add.text(cx, 28, '', {
      fontFamily: 'Inter, sans-serif',
      fontSize: '7px',
      color: '#A6A6A6',
      align: 'center',
    }).setScrollFactor(0).setOrigin(0.5, 0).setDepth(101).setVisible(false);
  }

  _checkDistrict() {
    const col = Math.floor(this.player.x / TILE_SIZE);
    const row = Math.floor(this.player.y / TILE_SIZE);
    const district = getDistrictAt(col, row);
    const distId = district?.id || null;
    const prevId = this.currentDistrict?.id || null;

    if (distId !== prevId) {
      this.currentDistrict = district;
      if (district) this._showDistrictLabel(district);
      else this._hideDistrictLabel();
      this._notify('district', district);
    }
  }

  _showDistrictLabel(district) {
    const cx = this.cameras.main.width / 2;
    this.districtLabel.setText(district.name.toUpperCase());
    this.districtDescText.setText(district.desc);

    const textW = Math.max(this.districtLabel.width, this.districtDescText.width) + 24;
    this.districtLabelBg.setSize(textW, 40).setPosition(cx, 8);
    this.districtLabel.setPosition(cx, 14);
    this.districtDescText.setPosition(cx, 28);

    [this.districtLabelBg, this.districtLabel, this.districtDescText].forEach(o => {
      o.setVisible(true).setAlpha(1);
    });

    if (this.labelTween) this.labelTween.stop();
    this.labelTween = this.tweens.add({
      targets: [this.districtLabelBg, this.districtLabel, this.districtDescText],
      alpha: 0,
      delay: 3000,
      duration: 1000,
      onComplete: () => {
        [this.districtLabelBg, this.districtLabel, this.districtDescText].forEach(o => o.setVisible(false));
      },
    });
  }

  _hideDistrictLabel() {
    if (this.labelTween) this.labelTween.stop();
    [this.districtLabelBg, this.districtLabel, this.districtDescText].forEach(o => o?.setVisible(false));
  }

  // ─────────────────────────────────────────────
  // NPCs
  // ─────────────────────────────────────────────

  _placeNPCs() {
    const npcDefs = [
      { x: 15, y: 30, key: 'npc_guard', name: 'Praetorian Guard', dialog: 'Halt! The Curia is reserved for STEEL+ rank citizens.' },
      { x: 65, y: 30, key: 'npc_guard', name: 'Basilica Guard', dialog: 'Welcome to the Basilica Julia. Pin your Scrolls to the pillars.' },
      { x: 40, y: 25, key: 'npc_merchant', name: 'Marcus the Merchant', dialog: 'Buy low, sell high — the oldest strategy in Rome.' },
      { x: 40, y: 35, key: 'npc_scholar', name: 'Seneca the Scholar', dialog: 'The Archives hold great wisdom. Study the data before you forge.' },
      { x: 15, y: 48, key: 'npc_merchant', name: 'Market Vendor', dialog: 'Fresh analysis, hot off the scroll! Visit the Anvil for options plays.' },
      { x: 65, y: 48, key: 'npc_scholar', name: 'Archivist', dialog: 'The Tabularium stores all records. Backtest your strategies here.' },
    ];

    for (const def of npcDefs) {
      const npc = this.add.sprite(
        def.x * TILE_SIZE + TILE_SIZE / 2,
        def.y * TILE_SIZE + TILE_SIZE / 2,
        def.key
      );
      npc.setDepth(8);
      npc.setData('name', def.name);
      npc.setData('dialog', def.dialog);
      npc.setData('type', 'npc');

      this.tweens.add({
        targets: npc,
        y: npc.y - 2,
        duration: 1500 + Math.random() * 500,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });

      this.npcs.push(npc);
    }

    // Interactive pillars in Basilica Julia
    const pillarPositions = [
      { x: 59, y: 8 }, { x: 63, y: 8 }, { x: 67, y: 8 }, { x: 71, y: 8 },
      { x: 59, y: 14 }, { x: 63, y: 14 }, { x: 67, y: 14 }, { x: 71, y: 14 },
    ];

    for (let i = 0; i < pillarPositions.length; i++) {
      const pos = pillarPositions[i];
      const pillar = this.add.sprite(
        pos.x * TILE_SIZE + TILE_SIZE / 2,
        pos.y * TILE_SIZE + TILE_SIZE / 2,
        `tile_${TILE.PILLAR}`
      );
      pillar.setDepth(7);
      pillar.setData('name', `Scroll Pillar ${i + 1}`);
      pillar.setData('dialog', 'Press E to pin a Scroll of Truth here. (Coming soon)');
      pillar.setData('type', 'pillar');
      this.npcs.push(pillar);
    }
  }

  // ─────────────────────────────────────────────
  // INTERACTION
  // ─────────────────────────────────────────────

  _createInteractPrompt() {
    this.interactPrompt = this.add.container(0, 0).setDepth(50).setVisible(false);
    const bg = this.add.rectangle(0, 0, 80, 16, 0x000000, 0.8).setOrigin(0.5, 1);
    this.interactPromptText = this.add.text(0, -8, '[E] Talk', {
      fontFamily: 'monospace',
      fontSize: '6px',
      color: '#DDBB44',
      align: 'center',
    }).setOrigin(0.5, 0.5);
    this.interactPrompt.add([bg, this.interactPromptText]);
  }

  _checkInteractionProximity() {
    const px = this.player.x;
    const py = this.player.y;
    const range = TILE_SIZE * 2.5;

    let nearest = null;
    let nearestDist = Infinity;

    for (const npc of this.npcs) {
      const dist = Phaser.Math.Distance.Between(px, py, npc.x, npc.y);
      if (dist < range && dist < nearestDist) {
        nearest = npc;
        nearestDist = dist;
      }
    }

    if (nearest) {
      this.interactTarget = nearest;
      this.interactPrompt.setPosition(nearest.x, nearest.y - 12);
      this.interactPrompt.setVisible(true);
      this.interactPromptText.setText(`[E] ${nearest.getData('name')}`);
    } else {
      this.interactTarget = null;
      this.interactPrompt.setVisible(false);
    }
  }

  _handleInteraction(target) {
    const dialog = target.getData('dialog');
    const name = target.getData('name');
    const type = target.getData('type');

    this._showDialogBubble(target.x, target.y - 20, dialog);
    this._notify('interact', { name, dialog, type });
  }

  _showDialogBubble(x, y, text) {
    if (this._dialogBubble) this._dialogBubble.destroy();

    const txt = this.add.text(x, y - 8, text, {
      fontFamily: 'sans-serif',
      fontSize: '6px',
      color: '#F2F2F2',
      align: 'center',
      wordWrap: { width: 108 },
    }).setOrigin(0.5, 1).setDepth(60);

    const bounds = txt.getBounds();
    const bg = this.add.rectangle(
      x, y - 8 - bounds.height / 2,
      bounds.width + 12, bounds.height + 8,
      0x1A1A1A, 0.9
    ).setOrigin(0.5, 0.5).setDepth(59);

    const border = this.add.rectangle(
      x, y - 8 - bounds.height / 2,
      bounds.width + 14, bounds.height + 10,
      0x4E0B59, 0.6
    ).setOrigin(0.5, 0.5).setDepth(58);

    const container = this.add.container(0, 0, [border, bg, txt]).setDepth(60);
    this._dialogBubble = container;

    this.time.delayedCall(4000, () => {
      this.tweens.add({
        targets: container,
        alpha: 0,
        duration: 500,
        onComplete: () => container.destroy(),
      });
    });
  }

  // ─────────────────────────────────────────────
  // MINIMAP
  // ─────────────────────────────────────────────

  _createMinimap() {
    const scale = 1.5;
    const mw = MAP_COLS * scale;
    const mh = MAP_ROWS * scale;
    const padding = 6;
    const vw = this.cameras.main.width;
    const vh = this.cameras.main.height;
    const mx = vw - mw - padding;
    const my = vh - mh - padding;

    this.add.rectangle(mx + mw / 2, my + mh / 2, mw + 4, mh + 4, 0x000000, 0.7)
      .setScrollFactor(0).setDepth(90);

    for (const d of DISTRICTS) {
      const { x, y, w, h } = d.bounds;
      this.add.rectangle(
        mx + x * scale + (w * scale) / 2,
        my + y * scale + (h * scale) / 2,
        w * scale, h * scale,
        d.color, 0.4
      ).setScrollFactor(0).setDepth(91);
    }

    this.minimapPlayer = this.add.circle(mx, my, 2, 0xFFDD44).setScrollFactor(0).setDepth(92);
    this._minimapPos = { mx, my, scale };
  }

  _updateMinimap() {
    if (!this.minimapPlayer || !this._minimapPos) return;
    const { mx, my, scale } = this._minimapPos;
    this.minimapPlayer.setPosition(
      mx + (this.player.x / TILE_SIZE) * scale,
      my + (this.player.y / TILE_SIZE) * scale
    );
  }

  // ─────────────────────────────────────────────
  // COORDINATES
  // ─────────────────────────────────────────────

  _createCoordDisplay() {
    this.coordText = this.add.text(6, 6, '', {
      fontFamily: 'monospace',
      fontSize: '6px',
      color: '#A6A6A6',
    }).setScrollFactor(0).setDepth(90);
  }

  _updateCoords() {
    const col = Math.floor(this.player.x / TILE_SIZE);
    const row = Math.floor(this.player.y / TILE_SIZE);
    this.coordText.setText(`${col}, ${row}`);
  }
}
