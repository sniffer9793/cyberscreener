/**
 * QUAEST.TECH — Boot Scene
 * Generates all tile textures and sprite sheets procedurally.
 * No external image assets needed.
 */

import Phaser from 'phaser';
import { TILE_SIZE, TILE, TILE_COLORS } from '../config.js';

// Deterministic pseudo-random for consistent tile variation
let _seed = 42;
function _rand() {
  _seed = (_seed * 16807 + 0) % 2147483647;
  return (_seed & 0x7fffffff) / 0x7fffffff;
}

export class BootScene extends Phaser.Scene {
  constructor() {
    super({ key: 'BootScene' });
  }

  preload() {
    // Nothing to load — all textures generated in create()
  }

  create() {
    this._generateTileTextures();
    this._generatePlayerSprite();
    this._generateNPCSprites();
    this._generateUITextures();

    this.scene.start('WorldScene');
  }

  /**
   * Generate a 16x16 texture for each tile type.
   */
  _generateTileTextures() {
    const S = TILE_SIZE;

    for (const [tileIdStr, colors] of Object.entries(TILE_COLORS)) {
      const tileId = parseInt(tileIdStr);
      const key = `tile_${tileId}`;
      const gfx = this.make.graphics({ x: 0, y: 0, add: false });

      switch (tileId) {
        case TILE.VOID:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          break;

        case TILE.STONE:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Mortar lines
          gfx.lineStyle(1, colors.border, 0.5);
          gfx.lineBetween(0, 8, S, 8);
          gfx.lineBetween(4, 0, 4, 8);
          gfx.lineBetween(12, 8, 12, S);
          // Random specks
          _seed = tileId * 100;
          for (let i = 0; i < 3; i++) {
            gfx.fillStyle(colors.detail, 0.3);
            gfx.fillRect(Math.floor(_rand() * 14) + 1, Math.floor(_rand() * 14) + 1, 1, 1);
          }
          break;

        case TILE.MARBLE:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Subtle veining
          gfx.lineStyle(1, colors.border, 0.2);
          gfx.lineBetween(3, 0, 8, S);
          gfx.lineBetween(10, 0, 14, S);
          // Tile border
          gfx.lineStyle(1, colors.border, 0.4);
          gfx.strokeRect(0, 0, S, S);
          break;

        case TILE.GRASS:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Grass blades
          _seed = tileId * 200;
          for (let i = 0; i < 6; i++) {
            const bx = Math.floor(_rand() * 14) + 1;
            const by = Math.floor(_rand() * 14) + 1;
            gfx.fillStyle(colors.detail, 0.4 + _rand() * 0.3);
            gfx.fillRect(bx, by, 1, 2);
          }
          break;

        case TILE.WALL:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Stone block pattern
          gfx.lineStyle(1, colors.border, 0.6);
          gfx.strokeRect(0, 0, S, S);
          gfx.lineBetween(0, 5, S, 5);
          gfx.lineBetween(0, 11, S, 11);
          gfx.lineBetween(8, 0, 8, 5);
          gfx.lineBetween(4, 5, 4, 11);
          gfx.lineBetween(12, 11, 12, S);
          // Highlight
          gfx.fillStyle(colors.detail, 0.15);
          gfx.fillRect(1, 1, S - 2, 2);
          break;

        case TILE.PILLAR:
          // Transparent background
          gfx.fillStyle(0x000000, 0);
          gfx.fillRect(0, 0, S, S);
          // Pillar base
          gfx.fillStyle(colors.border);
          gfx.fillRect(3, 12, 10, 4);
          // Pillar shaft
          gfx.fillStyle(colors.fill);
          gfx.fillRect(5, 2, 6, 10);
          // Capital (top)
          gfx.fillStyle(colors.detail);
          gfx.fillRect(3, 0, 10, 3);
          // Fluting lines
          gfx.lineStyle(1, colors.border, 0.3);
          gfx.lineBetween(7, 3, 7, 12);
          gfx.lineBetween(9, 3, 9, 12);
          break;

        case TILE.WATER:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Ripples
          gfx.lineStyle(1, colors.detail, 0.4);
          gfx.lineBetween(2, 5, 14, 5);
          gfx.lineBetween(4, 10, 12, 10);
          // Sparkle
          gfx.fillStyle(0xFFFFFF, 0.3);
          gfx.fillRect(6, 3, 2, 1);
          gfx.fillRect(10, 8, 2, 1);
          break;

        case TILE.ROAD:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Cobblestones
          gfx.lineStyle(1, colors.border, 0.3);
          gfx.strokeRect(1, 1, 6, 6);
          gfx.strokeRect(8, 1, 7, 6);
          gfx.strokeRect(1, 8, 7, 7);
          gfx.strokeRect(9, 8, 6, 7);
          break;

        case TILE.DOOR:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Door frame
          gfx.lineStyle(1, colors.border);
          gfx.strokeRect(2, 0, 12, S);
          // Door panels
          gfx.lineStyle(1, colors.detail, 0.3);
          gfx.lineBetween(8, 2, 8, 14);
          // Handle
          gfx.fillStyle(0xDDDD77);
          gfx.fillRect(10, 8, 2, 2);
          break;

        case TILE.COLUMN:
          gfx.fillStyle(0x000000, 0);
          gfx.fillRect(0, 0, S, S);
          // Simpler decorative column
          gfx.fillStyle(colors.fill);
          gfx.fillRect(5, 1, 6, 14);
          gfx.fillStyle(colors.detail);
          gfx.fillRect(4, 0, 8, 2);
          gfx.fillRect(4, 14, 8, 2);
          break;

        case TILE.TREE:
          gfx.fillStyle(0x000000, 0);
          gfx.fillRect(0, 0, S, S);
          // Trunk
          gfx.fillStyle(0x6B4423);
          gfx.fillRect(6, 10, 4, 6);
          // Foliage (circle)
          gfx.fillStyle(colors.fill);
          gfx.fillCircle(8, 7, 6);
          gfx.fillStyle(colors.detail, 0.5);
          gfx.fillCircle(6, 5, 3);
          break;

        case TILE.BANNER:
          gfx.fillStyle(0x000000, 0);
          gfx.fillRect(0, 0, S, S);
          // Pole
          gfx.fillStyle(0xCCCCCC);
          gfx.fillRect(7, 0, 2, S);
          // Banner cloth
          gfx.fillStyle(colors.fill);
          gfx.fillRect(3, 2, 10, 8);
          // SPQR text (simplified)
          gfx.fillStyle(0xDDBB44);
          gfx.fillRect(5, 4, 6, 1);
          gfx.fillRect(5, 6, 6, 1);
          break;

        case TILE.SHELF:
          gfx.fillStyle(colors.fill);
          gfx.fillRect(0, 0, S, S);
          // Shelves
          gfx.lineStyle(1, colors.border);
          gfx.lineBetween(0, 4, S, 4);
          gfx.lineBetween(0, 10, S, 10);
          // Items on shelves
          gfx.fillStyle(colors.detail, 0.6);
          gfx.fillRect(2, 1, 3, 3);
          gfx.fillRect(8, 1, 4, 3);
          gfx.fillRect(3, 5, 4, 5);
          gfx.fillRect(10, 6, 3, 4);
          gfx.fillRect(1, 11, 5, 4);
          gfx.fillRect(9, 11, 4, 4);
          break;

        default:
          gfx.fillStyle(0xFF00FF);
          gfx.fillRect(0, 0, S, S);
      }

      gfx.generateTexture(key, S, S);
      gfx.destroy();
    }
  }

  /**
   * Generate individual player textures for each direction + walk frame.
   * Keys: player_down_0, player_down_1, player_up_0, player_up_1, etc.
   */
  _generatePlayerSprite() {
    const S = TILE_SIZE;
    const dirs = ['down', 'up', 'left', 'right'];

    for (let d = 0; d < dirs.length; d++) {
      for (let f = 0; f < 2; f++) {
        const key = `player_${dirs[d]}_${f}`;
        const gfx = this.make.graphics({ x: 0, y: 0, add: false });

        // Body (purple toga)
        gfx.fillStyle(0x4E0B59);
        gfx.fillRect(4, 6, 8, 8);

        // Head
        gfx.fillStyle(0xE8C8A0);
        gfx.fillRect(5, 1, 6, 5);

        // Eyes (direction-dependent)
        gfx.fillStyle(0x222222);
        if (dirs[d] === 'down') {
          gfx.fillRect(6, 3, 1, 1);
          gfx.fillRect(9, 3, 1, 1);
        } else if (dirs[d] === 'left') {
          gfx.fillRect(5, 3, 1, 1);
        } else if (dirs[d] === 'right') {
          gfx.fillRect(10, 3, 1, 1);
        }
        // 'up' = no eyes visible from behind

        // Feet (walk animation)
        gfx.fillStyle(0x553322);
        if (f === 0) {
          gfx.fillRect(5, 14, 3, 2);
          gfx.fillRect(9, 14, 3, 2);
        } else {
          gfx.fillRect(4, 14, 3, 2);
          gfx.fillRect(10, 14, 3, 2);
        }

        // Toga gold trim
        gfx.fillStyle(0xDDBB44, 0.6);
        gfx.fillRect(4, 6, 8, 1);

        // Arms
        gfx.fillStyle(0xE8C8A0);
        if (dirs[d] === 'left') {
          gfx.fillRect(3, 7, 1, 4);
        } else if (dirs[d] === 'right') {
          gfx.fillRect(12, 7, 1, 4);
        } else {
          gfx.fillRect(3, 7, 1, 4);
          gfx.fillRect(12, 7, 1, 4);
        }

        gfx.generateTexture(key, S, S);
        gfx.destroy();
      }
    }
  }

  /**
   * Generate simple NPC sprites for world decoration.
   */
  _generateNPCSprites() {
    const S = TILE_SIZE;
    const npcs = [
      { key: 'npc_guard', body: 0x8B2500, head: 0xD4A574 },
      { key: 'npc_merchant', body: 0x665D1E, head: 0xE8C8A0 },
      { key: 'npc_scholar', body: 0x336699, head: 0xE8C8A0 },
    ];

    for (const npc of npcs) {
      const gfx = this.make.graphics({ x: 0, y: 0, add: false });
      // Body
      gfx.fillStyle(npc.body);
      gfx.fillRect(4, 6, 8, 8);
      // Head
      gfx.fillStyle(npc.head);
      gfx.fillRect(5, 1, 6, 5);
      // Eyes
      gfx.fillStyle(0x222222);
      gfx.fillRect(6, 3, 1, 1);
      gfx.fillRect(9, 3, 1, 1);
      // Feet
      gfx.fillStyle(0x443322);
      gfx.fillRect(5, 14, 3, 2);
      gfx.fillRect(9, 14, 3, 2);

      gfx.generateTexture(npc.key, S, S);
      gfx.destroy();
    }
  }

  /**
   * Generate UI textures (interaction prompt, etc.).
   */
  _generateUITextures() {
    // Interaction indicator (floating diamond)
    const gfx = this.make.graphics({ x: 0, y: 0, add: false });
    gfx.fillStyle(0xDDBB44);
    gfx.fillTriangle(8, 0, 0, 8, 8, 16);
    gfx.fillTriangle(8, 0, 16, 8, 8, 16);
    gfx.fillStyle(0xFFDD66, 0.5);
    gfx.fillTriangle(8, 2, 2, 8, 8, 14);
    gfx.generateTexture('interact_icon', 16, 16);
    gfx.destroy();
  }
}
