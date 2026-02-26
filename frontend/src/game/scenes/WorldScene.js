/**
 * QUAEST.TECH — World Scene
 * Main game scene: tile rendering via RenderTexture, player movement,
 * district detection, NPC interaction, and UI overlays.
 */

import Phaser from 'phaser';
import {
  TILE_SIZE, MAP_COLS, MAP_ROWS, WORLD_W, WORLD_H,
  TILE, SOLID_TILES, DISTRICTS, SPAWN, PLAYER_SPEED,
  TILE_VARIANTS, WATER_FRAMES, WATER_FRAME_MS,
  NPC_SPEECH_LINES, TICKER_TEXT, TORCH_POSITIONS,
  CHAR_W, CHAR_H, RANKS,
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

    // ── Atmospheric effects ──
    this._createDustParticles();
    this._createVignette();
    this._createTorchGlows();
    this._createScrollingTicker();
    this._startAmbientSpeech();

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

  update(time, delta) {
    if (!this.player) return;

    // ── Water animation ──
    if (this.waterTiles && this.waterTiles.length > 0) {
      this.waterTimer += delta;
      if (this.waterTimer >= WATER_FRAME_MS) {
        this.waterTimer -= WATER_FRAME_MS;
        this.waterFrame = (this.waterFrame + 1) % WATER_FRAMES;
        const wKey = `tile_${TILE.WATER}_f${this.waterFrame}`;
        for (const pos of this.waterTiles) {
          this.mapRT.drawFrame(wKey, undefined, pos.col * TILE_SIZE, pos.row * TILE_SIZE);
        }
      }
    }

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

    // Direction + 4-frame walk animation
    const moving = vx !== 0 || vy !== 0;
    const rk = this.playerRank;
    if (moving) {
      this._idleTime = 0;
      const walkFrame = Math.floor(time / 150) % 4;
      let dir = 'down';
      if (vy < 0) dir = 'up';
      else if (vy > 0) dir = 'down';
      else if (vx < 0) dir = 'left';
      else if (vx > 0) dir = 'right';
      this._lastDir = dir;
      this.player.setTexture(`player_rank${rk}_${dir}_${walkFrame}`);
    } else {
      // Idle animation — gentle sway every 800ms after 500ms idle
      this._idleTime += delta;
      if (this._idleTime > 500) {
        const idleFrame = Math.floor(time / 800) % 2 === 0 ? 0 : 2;
        this.player.setTexture(`player_rank${rk}_${this._lastDir}_${idleFrame}`);
      }
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

    // Scroll ticker
    this._updateTicker();
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
    this.mapRT = this.add.renderTexture(0, 0, WORLD_W, WORLD_H).setOrigin(0, 0).setDepth(0);
    this.waterTiles = [];
    this.waterFrame = 0;
    this.waterTimer = 0;

    for (let r = 0; r < MAP_ROWS; r++) {
      for (let c = 0; c < MAP_COLS; c++) {
        const tileId = this.mapData[r][c];
        let key;
        if (tileId === TILE.WATER) {
          key = `tile_${TILE.WATER}_f0`;
          this.waterTiles.push({ col: c, row: r });
        } else {
          const vc = TILE_VARIANTS[tileId] || 1;
          const v = (c * 7 + r * 13) % vc;
          key = `tile_${tileId}_v${v}`;
        }
        this.mapRT.drawFrame(key, undefined, c * TILE_SIZE, r * TILE_SIZE);
      }
    }
  }

  // ─────────────────────────────────────────────
  // PLAYER
  // ─────────────────────────────────────────────

  _createPlayer() {
    // Determine player rank from profile (passed via game registry)
    const profile = this.game.registry.get('playerProfile');
    const level = profile?.level || 1;
    this.playerRank = 0;
    for (let i = RANKS.length - 1; i >= 0; i--) {
      if (level >= RANKS[i].minLevel) { this.playerRank = i; break; }
    }

    // Player starts facing down, frame 0 (16x24 sprite)
    const startKey = `player_rank${this.playerRank}_down_0`;
    this.player = this.physics.add.sprite(SPAWN.x, SPAWN.y, startKey);
    this.player.setOrigin(0.5, 0.75); // anchor at feet
    this.player.setDepth(10);
    this.player.body.setSize(10, 10);
    this.player.body.setOffset(3, 12); // physics body at feet
    this.player.body.setCollideWorldBounds(true);

    // Idle tracking
    this._idleTime = 0;
    this._lastDir = 'down';

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

    // Gold outer border
    this.districtLabelBorder = this.add.rectangle(cx, -50, 200, 44, 0xDDBB44, 0.5)
      .setScrollFactor(0).setOrigin(0.5, 0).setDepth(99).setVisible(false);
    // Dark background
    this.districtLabelBg = this.add.rectangle(cx, -50, 196, 40, 0x0D0D0D, 0.85)
      .setScrollFactor(0).setOrigin(0.5, 0).setDepth(100).setVisible(false);

    // Laurel decorations (gold leaf motifs: left and right)
    this.laurelLeft = this.add.text(0, 0, '\u2767', {
      fontFamily: 'serif', fontSize: '14px', color: '#DDBB44',
    }).setScrollFactor(0).setOrigin(0.5, 0.5).setDepth(102).setVisible(false).setAlpha(0.6);

    this.laurelRight = this.add.text(0, 0, '\u2619', {
      fontFamily: 'serif', fontSize: '14px', color: '#DDBB44',
    }).setScrollFactor(0).setOrigin(0.5, 0.5).setDepth(102).setVisible(false).setAlpha(0.6);

    this.districtLabel = this.add.text(cx, -50, '', {
      fontFamily: 'Cinzel, serif',
      fontSize: '11px',
      fontStyle: 'bold',
      color: '#DDBB44',
      align: 'center',
    }).setScrollFactor(0).setOrigin(0.5, 0).setDepth(101).setVisible(false);

    this.districtDescText = this.add.text(cx, -50, '', {
      fontFamily: 'Inter, sans-serif',
      fontSize: '7px',
      color: '#A6A6A6',
      align: 'center',
    }).setScrollFactor(0).setOrigin(0.5, 0).setDepth(101).setVisible(false);

    // District transition overlay
    const vw = this.cameras.main.width;
    const vh = this.cameras.main.height;
    this._transitionOverlay = this.add.rectangle(vw / 2, vh / 2, vw, vh, 0x000000, 0)
      .setScrollFactor(0).setDepth(180).setVisible(false);
  }

  _checkDistrict() {
    const col = Math.floor(this.player.x / TILE_SIZE);
    const row = Math.floor(this.player.y / TILE_SIZE);
    const district = getDistrictAt(col, row);
    const distId = district?.id || null;
    const prevId = this.currentDistrict?.id || null;

    if (distId !== prevId) {
      this.currentDistrict = district;
      if (district) {
        this._showDistrictLabel(district);
        this._playTransition();
      } else {
        this._hideDistrictLabel();
      }
      this._notify('district', district);
    }
  }

  _playTransition() {
    if (!this._transitionOverlay) return;
    this._transitionOverlay.setVisible(true).setAlpha(0);
    this.tweens.add({
      targets: this._transitionOverlay,
      alpha: 0.3,
      duration: 300,
      yoyo: true,
      onComplete: () => this._transitionOverlay.setVisible(false),
    });
  }

  _showDistrictLabel(district) {
    const cx = this.cameras.main.width / 2;
    this.districtLabel.setText(district.name.toUpperCase());
    this.districtDescText.setText(district.desc);

    const textW = Math.max(this.districtLabel.width, this.districtDescText.width) + 40;

    // Position elements off-screen above, then slide down
    const allObjs = [this.districtLabelBorder, this.districtLabelBg, this.districtLabel, this.districtDescText, this.laurelLeft, this.laurelRight];
    allObjs.forEach(o => o.setVisible(true).setAlpha(1));

    this.districtLabelBorder.setSize(textW + 4, 44).setPosition(cx, -50);
    this.districtLabelBg.setSize(textW, 40).setPosition(cx, -50);
    this.districtLabel.setPosition(cx, -50);
    this.districtDescText.setPosition(cx, -50);
    this.laurelLeft.setPosition(cx - textW / 2 + 6, -50);
    this.laurelRight.setPosition(cx + textW / 2 - 6, -50);

    // Slide down
    if (this.labelTween) this.labelTween.stop();
    const targetY = 14;
    this.tweens.add({
      targets: [this.districtLabelBorder, this.districtLabelBg],
      y: targetY - 6,
      duration: 400,
      ease: 'Back.easeOut',
    });
    this.tweens.add({
      targets: this.districtLabel,
      y: targetY,
      duration: 400,
      ease: 'Back.easeOut',
    });
    this.tweens.add({
      targets: this.districtDescText,
      y: targetY + 16,
      duration: 400,
      ease: 'Back.easeOut',
    });
    this.tweens.add({
      targets: this.laurelLeft,
      y: targetY + 12,
      x: cx - textW / 2 + 6,
      duration: 400,
      ease: 'Back.easeOut',
    });
    this.tweens.add({
      targets: this.laurelRight,
      y: targetY + 12,
      x: cx + textW / 2 - 6,
      duration: 400,
      ease: 'Back.easeOut',
    });

    // Fade out after delay
    this.labelTween = this.tweens.add({
      targets: allObjs,
      alpha: 0,
      delay: 3500,
      duration: 1000,
      onComplete: () => allObjs.forEach(o => o.setVisible(false)),
    });
  }

  _hideDistrictLabel() {
    if (this.labelTween) this.labelTween.stop();
    const allObjs = [this.districtLabelBorder, this.districtLabelBg, this.districtLabel, this.districtDescText, this.laurelLeft, this.laurelRight];
    allObjs.forEach(o => o?.setVisible(false));
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
        `tile_${TILE.PILLAR}_v0`
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
    // Gold border
    const border = this.add.rectangle(0, -8, 84, 18, 0xDDBB44, 0.5).setOrigin(0.5, 0.5);
    // Dark background
    const bg = this.add.rectangle(0, -8, 80, 14, 0x0D0D0D, 0.85).setOrigin(0.5, 0.5);
    this.interactPromptText = this.add.text(0, -8, '[E] Talk', {
      fontFamily: 'monospace',
      fontSize: '6px',
      color: '#DDBB44',
      align: 'center',
    }).setOrigin(0.5, 0.5);
    this.interactPrompt.add([border, bg, this.interactPromptText]);

    // Pulse animation
    this.tweens.add({
      targets: this.interactPrompt,
      scaleX: { from: 0.95, to: 1.05 },
      scaleY: { from: 0.95, to: 1.05 },
      duration: 500,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
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
      this.interactPrompt.setPosition(nearest.x, nearest.y - 16);
      this.interactPrompt.setVisible(true);
      const action = nearest.getData('type') === 'npc' ? 'Talk' : 'Examine';
      this.interactPromptText.setText(`[E] ${action}`);
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

    // Gold border frame
    this.add.rectangle(mx + mw / 2, my + mh / 2, mw + 6, mh + 6, 0xDDBB44, 0.6)
      .setScrollFactor(0).setDepth(89);
    // Dark background
    this.add.rectangle(mx + mw / 2, my + mh / 2, mw + 2, mh + 2, 0x0D0D0D, 0.85)
      .setScrollFactor(0).setDepth(90);

    // Draw detailed minimap from mapData
    const mmGfx = this.make.graphics({ x: 0, y: 0, add: false });
    for (let r = 0; r < MAP_ROWS; r++) {
      for (let c = 0; c < MAP_COLS; c++) {
        const tid = this.mapData[r][c];
        let color = null, alpha = 0.5;
        if (tid === TILE.WALL) { color = 0x555555; alpha = 0.7; }
        else if (tid === TILE.ROAD) { color = 0x8B7B60; alpha = 0.4; }
        else if (tid === TILE.WATER) { color = 0x4488CC; alpha = 0.7; }
        else if (tid === TILE.TREE) { color = 0x2D6B2D; alpha = 0.6; }
        else if (tid === TILE.MARBLE) { color = 0xD8D0C4; alpha = 0.3; }
        else if (tid === TILE.DOOR) { color = 0xDDBB44; alpha = 0.7; }
        if (color !== null) {
          mmGfx.fillStyle(color, alpha);
          mmGfx.fillRect(c * scale, r * scale, scale, scale);
        }
      }
    }
    // Building outlines from districts
    for (const d of DISTRICTS) {
      const { x, y, w, h } = d.bounds;
      mmGfx.lineStyle(1, d.color, 0.6);
      mmGfx.strokeRect(x * scale, y * scale, w * scale, h * scale);
    }
    mmGfx.generateTexture('minimap_tex', mw, mh);
    mmGfx.destroy();

    this.add.image(mx + mw / 2, my + mh / 2, 'minimap_tex')
      .setScrollFactor(0).setDepth(91);

    // Pulsing gold player dot
    this.minimapPlayer = this.add.circle(mx, my, 2, 0xFFDD44)
      .setScrollFactor(0).setDepth(92);
    this.tweens.add({
      targets: this.minimapPlayer,
      scaleX: { from: 0.8, to: 1.3 },
      scaleY: { from: 0.8, to: 1.3 },
      alpha: { from: 1, to: 0.6 },
      duration: 600,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.easeInOut',
    });
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
    // Dark pill background
    this.coordBg = this.add.rectangle(6, 6, 70, 12, 0x0D0D0D, 0.7)
      .setScrollFactor(0).setOrigin(0, 0).setDepth(89);
    // Compass icon
    this.coordIcon = this.add.text(9, 7, '\u2316', {
      fontFamily: 'serif',
      fontSize: '8px',
      color: '#DDBB44',
    }).setScrollFactor(0).setOrigin(0, 0).setDepth(90);
    // Coordinate text
    this.coordText = this.add.text(18, 8, '', {
      fontFamily: 'monospace',
      fontSize: '6px',
      color: '#A6A6A6',
    }).setScrollFactor(0).setOrigin(0, 0).setDepth(90);
  }

  _updateCoords() {
    const col = Math.floor(this.player.x / TILE_SIZE);
    const row = Math.floor(this.player.y / TILE_SIZE);
    const abbr = this.currentDistrict ? this.currentDistrict.name.split(' ').pop().slice(0, 4).toUpperCase() : 'WILD';
    this.coordText.setText(`${abbr} ${col},${row}`);
    // Adjust pill width to text
    const tw = this.coordText.width + 20;
    this.coordBg.setSize(Math.max(70, tw), 12);
  }

  // ─────────────────────────────────────────────
  // ATMOSPHERIC EFFECTS
  // ─────────────────────────────────────────────

  /** Ambient dust particles drifting around the player */
  _createDustParticles() {
    this.dustEmitter = this.add.particles(0, 0, 'dust_particle', {
      follow: this.player,
      followOffset: { x: 0, y: 0 },
      frequency: 800,
      lifespan: 3000,
      quantity: 1,
      maxParticles: 15,
      speed: { min: 3, max: 10 },
      angle: { min: 0, max: 360 },
      alpha: { start: 0.3, end: 0 },
      scale: { start: 1, end: 0.5 },
      tint: [0xD4B896, 0xC8A882, 0xBB9970],
      blendMode: 'ADD',
      emitZone: {
        type: 'random',
        source: new Phaser.Geom.Rectangle(-40, -30, 80, 60),
      },
    });
    this.dustEmitter.setDepth(15);
  }

  /** Dark vignette around viewport edges */
  _createVignette() {
    const vw = this.cameras.main.width;
    const vh = this.cameras.main.height;
    const vignetteGfx = this.make.graphics({ x: 0, y: 0, add: false });

    // Concentric dark rectangles increasing in alpha toward edges
    const steps = 8;
    for (let i = 0; i < steps; i++) {
      const t = i / steps;
      const inset = Math.floor((1 - t) * Math.min(vw, vh) * 0.35);
      const alpha = t * t * 0.4; // quadratic falloff
      vignetteGfx.fillStyle(0x000000, alpha);
      vignetteGfx.fillRect(0, 0, vw, inset);               // top
      vignetteGfx.fillRect(0, vh - inset, vw, inset);       // bottom
      vignetteGfx.fillRect(0, 0, inset, vh);                // left
      vignetteGfx.fillRect(vw - inset, 0, inset, vh);       // right
    }

    vignetteGfx.generateTexture('vignette_tex', vw, vh);
    vignetteGfx.destroy();

    this.add.image(vw / 2, vh / 2, 'vignette_tex')
      .setScrollFactor(0)
      .setDepth(200)
      .setAlpha(1);
  }

  /** Torch glow sprites at building entrances with flickering */
  _createTorchGlows() {
    for (const tp of TORCH_POSITIONS) {
      const wx = tp.x * TILE_SIZE + TILE_SIZE / 2;
      const wy = tp.y * TILE_SIZE + TILE_SIZE / 2;

      // Glow halo
      const glow = this.add.image(wx, wy, 'torch_glow')
        .setDepth(5)
        .setAlpha(0.6)
        .setBlendMode(Phaser.BlendModes.ADD);

      // Flickering alpha + scale tween
      this.tweens.add({
        targets: glow,
        alpha: { from: 0.4, to: 0.7 },
        scaleX: { from: 0.9, to: 1.1 },
        scaleY: { from: 0.9, to: 1.1 },
        duration: 300 + Math.random() * 200,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });

      // Small flame sprite
      const flame = this.add.image(wx, wy - 6, 'torch_flame')
        .setDepth(6)
        .setAlpha(0.8);

      this.tweens.add({
        targets: flame,
        alpha: { from: 0.6, to: 0.9 },
        y: flame.y - 1,
        duration: 200 + Math.random() * 150,
        yoyo: true,
        repeat: -1,
        ease: 'Sine.easeInOut',
      });
    }
  }

  /** Scrolling ticker banner at top of viewport */
  _createScrollingTicker() {
    const vw = this.cameras.main.width;
    // Dark backdrop bar
    this.tickerBg = this.add.rectangle(vw / 2, 5, vw, 10, 0x0D0D0D, 0.85)
      .setScrollFactor(0)
      .setDepth(150)
      .setOrigin(0.5, 0.5);

    // Gold text — repeat twice for seamless wrapping
    const fullText = TICKER_TEXT + TICKER_TEXT;
    this.tickerText = this.add.text(0, 1, fullText, {
      fontFamily: 'monospace',
      fontSize: '7px',
      color: '#DDBB44',
    }).setScrollFactor(0).setDepth(151).setAlpha(0.8);

    this.tickerWidth = this.tickerText.width / 2; // half because we doubled text
  }

  _updateTicker() {
    if (!this.tickerText) return;
    this.tickerText.x -= 0.5;
    // Wrap when first copy scrolls fully off screen
    if (this.tickerText.x < -this.tickerWidth) {
      this.tickerText.x += this.tickerWidth;
    }
  }

  /** Random NPCs show ambient stock-market-Roman quips */
  _startAmbientSpeech() {
    this._speechTimer = this.time.addEvent({
      delay: 6000 + Math.random() * 4000,
      callback: () => this._showRandomSpeech(),
      loop: true,
    });
  }

  _showRandomSpeech() {
    // Pick a random NPC that's an actual NPC (not pillar) and in viewport
    const npcOnly = this.npcs.filter(n => n.getData('type') === 'npc');
    if (npcOnly.length === 0) return;

    const cam = this.cameras.main;
    const visible = npcOnly.filter(n => {
      const sx = (n.x - cam.scrollX) * cam.zoom;
      const sy = (n.y - cam.scrollY) * cam.zoom;
      return sx > -50 && sx < cam.width + 50 && sy > -50 && sy < cam.height + 50;
    });

    const target = visible.length > 0
      ? visible[Math.floor(Math.random() * visible.length)]
      : npcOnly[Math.floor(Math.random() * npcOnly.length)];

    const line = NPC_SPEECH_LINES[Math.floor(Math.random() * NPC_SPEECH_LINES.length)];

    // Create small speech bubble
    const bx = target.x;
    const by = target.y - 16;

    const txt = this.add.text(bx, by, line, {
      fontFamily: 'sans-serif',
      fontSize: '5px',
      color: '#F2F2F2',
      align: 'center',
      wordWrap: { width: 80 },
    }).setOrigin(0.5, 1).setDepth(55);

    const bounds = txt.getBounds();
    const bg = this.add.rectangle(
      bx, by - bounds.height / 2,
      bounds.width + 8, bounds.height + 4,
      0x1A1A1A, 0.85
    ).setOrigin(0.5, 0.5).setDepth(54);

    const bubble = this.add.container(0, 0, [bg, txt]).setDepth(55);

    // Fade out after 3 seconds
    this.time.delayedCall(3000, () => {
      this.tweens.add({
        targets: bubble,
        alpha: 0,
        duration: 500,
        onComplete: () => bubble.destroy(),
      });
    });
  }
}
