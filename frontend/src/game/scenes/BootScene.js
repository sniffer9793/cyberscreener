/**
 * QUAEST.TECH — Boot Scene (Enhanced Visual Pass)
 * Rich procedural tile textures with variants, animated water,
 * and detailed character/NPC sprites. All textures generated at runtime.
 */

import Phaser from 'phaser';
import { TILE_SIZE, TILE, TILE_COLORS, TILE_VARIANTS, WATER_FRAMES, CHAR_W, CHAR_H, RANKS } from '../config.js';

// ── Deterministic PRNG for consistent tile variation ──
let _seed = 42;
function _rand() {
  _seed = (_seed * 16807 + 0) % 2147483647;
  return (_seed & 0x7fffffff) / 0x7fffffff;
}
function _randInt(min, max) {
  return Math.floor(_rand() * (max - min + 1)) + min;
}
function _lerpColor(a, b, t) {
  const ar = (a >> 16) & 0xff, ag = (a >> 8) & 0xff, ab = a & 0xff;
  const br = (b >> 16) & 0xff, bg = (b >> 8) & 0xff, bb = b & 0xff;
  return (Math.round(ar + (br - ar) * t) << 16) |
         (Math.round(ag + (bg - ag) * t) << 8) |
         Math.round(ab + (bb - ab) * t);
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

  /** Helper: create a texture from a draw function */
  _tex(key, w, h, fn) {
    const g = this.make.graphics({ x: 0, y: 0, add: false });
    fn(g);
    g.generateTexture(key, w, h);
    g.destroy();
  }

  // ═══════════════════════════════════════════════════════
  // TILE TEXTURES — Multi-pass layered procedural generation
  // ═══════════════════════════════════════════════════════

  _generateTileTextures() {
    const S = TILE_SIZE; // 16

    // ── VOID (1 variant) ──
    this._tex('tile_0_v0', S, S, g => {
      g.fillStyle(0x0D0D0D);
      g.fillRect(0, 0, S, S);
      _seed = 1;
      for (let i = 0; i < 4; i++) {
        g.fillStyle(0x181818, 0.4);
        g.fillRect(_randInt(0, 14), _randInt(0, 14), 1, 1);
      }
    });

    // ── STONE (4 variants) — Running bond brickwork ──
    for (let v = 0; v < TILE_VARIANTS[TILE.STONE]; v++) {
      this._tex(`tile_${TILE.STONE}_v${v}`, S, S, g => {
        _seed = 100 + v * 73;
        const c = TILE_COLORS[TILE.STONE];
        // Base fill
        g.fillStyle(c.fill);
        g.fillRect(0, 0, S, S);

        // 3 brick courses: heights 5, 5, 6 with offset bonding
        const courses = [
          { y: 0, h: 5, xOff: 0 },
          { y: 5, h: 5, xOff: 4 },
          { y: 10, h: 6, xOff: 0 },
        ];
        for (const course of courses) {
          for (let bx = -course.xOff; bx < S; bx += 8) {
            const x0 = Math.max(0, bx);
            const x1 = Math.min(S, bx + 8);
            if (x1 <= x0) continue;
            // Per-brick brightness variation
            const bri = _rand() * 0.5;
            g.fillStyle(_lerpColor(c.border, c.detail, bri), 0.22);
            g.fillRect(x0 + 1, course.y + 1, x1 - x0 - 1, course.h - 1);
            // Top-edge highlight
            g.fillStyle(c.detail, 0.06);
            g.fillRect(x0 + 1, course.y + 1, x1 - x0 - 1, 1);
          }
          // Horizontal mortar
          g.fillStyle(0x4A4A4A, 0.45);
          g.fillRect(0, course.y, S, 1);
          // Vertical mortar
          for (let bx = -course.xOff; bx < S; bx += 8) {
            if (bx > 0 && bx < S) {
              g.fillStyle(0x4A4A4A, 0.45);
              g.fillRect(bx, course.y, 1, course.h);
            }
          }
        }
        // Weathering specks
        for (let i = 0; i < 3 + v; i++) {
          g.fillStyle(_rand() > 0.5 ? 0x888888 : 0x505050, 0.15);
          g.fillRect(_randInt(1, 14), _randInt(1, 14), 1, 1);
        }
      });
    }

    // ── MARBLE (3 variants) — Polished cream with wavy veins ──
    for (let v = 0; v < TILE_VARIANTS[TILE.MARBLE]; v++) {
      this._tex(`tile_${TILE.MARBLE}_v${v}`, S, S, g => {
        _seed = 200 + v * 37;
        const c = TILE_COLORS[TILE.MARBLE];
        // Cream base
        g.fillStyle(c.fill);
        g.fillRect(0, 0, S, S);
        // Polished inner glow
        g.fillStyle(c.detail, 0.1);
        g.fillRect(1, 1, S - 2, S - 2);
        g.fillStyle(0xFFFFF8, 0.04);
        g.fillRect(2, 2, S - 4, S - 4);

        // Vein patterns — unique per variant
        const veins = [
          [[2, 0, 6, 16], [10, 0, 14, 12], [12, 8, 16, 16]],
          [[0, 5, 16, 10], [4, 0, 11, 16]],
          [[0, 2, 10, 0], [4, 16, 15, 4], [0, 13, 7, 16]],
        ][v];
        for (const [x1, y1, x2, y2] of veins) {
          g.lineStyle(1, c.border, 0.12 + _rand() * 0.06);
          g.lineBetween(x1, y1, x2, y2);
        }
        // Thin secondary vein
        g.lineStyle(1, c.border, 0.06);
        g.lineBetween(_randInt(0, 6), _randInt(0, 15), _randInt(10, 15), _randInt(0, 15));

        // Shimmer highlights
        g.fillStyle(0xFFFFFF, 0.06);
        for (let i = 0; i < 5; i++) {
          g.fillRect(_randInt(1, 14), _randInt(1, 14), 1, 1);
        }
        // Border inset
        g.lineStyle(1, c.border, 0.18);
        g.strokeRect(0, 0, S, S);
      });
    }

    // ── GRASS (4 variants) — Earthy patches, blade tufts, wildflowers ──
    for (let v = 0; v < TILE_VARIANTS[TILE.GRASS]; v++) {
      this._tex(`tile_${TILE.GRASS}_v${v}`, S, S, g => {
        _seed = 300 + v * 53;
        const c = TILE_COLORS[TILE.GRASS];
        // Green base
        g.fillStyle(c.fill);
        g.fillRect(0, 0, S, S);
        // Darker earth patch
        g.fillStyle(0x3D6B2D, 0.2);
        g.fillRect(_randInt(0, 8), _randInt(0, 8), _randInt(4, 7), _randInt(4, 7));
        // Lighter sun patch
        g.fillStyle(c.detail, 0.12);
        g.fillRect(_randInt(2, 10), _randInt(2, 10), _randInt(3, 5), _randInt(3, 5));

        // Grass blades (10-13 per variant)
        const count = 10 + v;
        for (let i = 0; i < count; i++) {
          const bx = _randInt(0, 15);
          const by = _randInt(0, 13);
          const shade = _lerpColor(0x3A7A3A, 0x6AAB5A, _rand());
          g.fillStyle(shade, 0.5 + _rand() * 0.4);
          g.fillRect(bx, by, 1, _randInt(2, 3));
        }

        // Wildflower accents on variants 2, 3
        if (v >= 2) {
          const flower = v === 2 ? 0xFFDD44 : 0xDD5577;
          g.fillStyle(flower, 0.5);
          g.fillRect(_randInt(2, 13), _randInt(2, 13), 1, 1);
          if (_rand() > 0.4) g.fillRect(_randInt(2, 13), _randInt(2, 13), 1, 1);
        }
      });
    }

    // ── WALL (3 variants) — Fortress blocks with highlight/shadow ──
    for (let v = 0; v < TILE_VARIANTS[TILE.WALL]; v++) {
      this._tex(`tile_${TILE.WALL}_v${v}`, S, S, g => {
        _seed = 400 + v * 67;
        const c = TILE_COLORS[TILE.WALL];
        // Dark base
        g.fillStyle(c.fill);
        g.fillRect(0, 0, S, S);

        // Irregular stone blocks
        const blocks = [
          [0, 0, 8, 5], [8, 0, 8, 5],
          [0, 5, 5, 6], [5, 5, 6, 6], [11, 5, 5, 6],
          [0, 11, 9, 5], [9, 11, 7, 5],
        ];
        for (const [bx, by, bw, bh] of blocks) {
          // Block face variation
          g.fillStyle(c.detail, 0.06 + _rand() * 0.12);
          g.fillRect(bx + 1, by + 1, bw - 2, bh - 2);
          // Top highlight
          g.fillStyle(c.detail, 0.1);
          g.fillRect(bx + 1, by + 1, bw - 2, 1);
          // Left highlight
          g.fillStyle(c.detail, 0.06);
          g.fillRect(bx + 1, by + 1, 1, bh - 2);
          // Bottom shadow
          g.fillStyle(0x111111, 0.15);
          g.fillRect(bx + 1, by + bh - 1, bw - 1, 1);
          // Right shadow
          g.fillStyle(0x111111, 0.1);
          g.fillRect(bx + bw - 1, by + 1, 1, bh - 1);
        }

        // Moss specks on variant 1+
        if (v >= 1) {
          g.fillStyle(0x3A5A2A, 0.25);
          for (let i = 0; i < 2 + v; i++)
            g.fillRect(_randInt(1, 14), _randInt(1, 14), 1, 1);
        }
        // Crack on variant 2
        if (v === 2) {
          g.lineStyle(1, 0x1A1A1A, 0.25);
          g.lineBetween(_randInt(3, 7), 0, _randInt(9, 13), S);
        }
      });
    }

    // ── PILLAR (1 variant) — Corinthian, fluted shaft, gold capital ──
    this._tex(`tile_${TILE.PILLAR}_v0`, S, S, g => {
      const c = TILE_COLORS[TILE.PILLAR];
      g.fillStyle(0x000000, 0);
      g.fillRect(0, 0, S, S);

      // Ground shadow
      g.fillStyle(0x000000, 0.12);
      g.fillRect(2, 14, 12, 2);
      // Base plinth
      g.fillStyle(c.border);
      g.fillRect(2, 12, 12, 3);
      g.fillStyle(c.fill, 0.5);
      g.fillRect(3, 12, 10, 1);

      // Fluted shaft
      g.fillStyle(c.fill);
      g.fillRect(4, 3, 8, 9);
      for (let x = 5; x <= 10; x++) {
        g.fillStyle(x % 2 === 0 ? c.border : c.detail, x % 2 === 0 ? 0.15 : 0.12);
        g.fillRect(x, 4, 1, 7);
      }

      // Ornate capital
      g.fillStyle(c.detail);
      g.fillRect(2, 0, 12, 3);
      // Volute scrolls
      g.fillStyle(0xDDBB44, 0.35);
      g.fillRect(2, 0, 2, 2);
      g.fillRect(12, 0, 2, 2);
      // Gold capital band
      g.fillStyle(0xDDBB44, 0.25);
      g.fillRect(4, 2, 8, 1);
      // Abacus top line
      g.fillStyle(c.border, 0.5);
      g.fillRect(2, 0, 12, 1);
    });

    // ── WATER (4 animation frames) — Depth gradient, ripples, sparkles ──
    const waveData = [
      { rip: [4, 10], sp: [[6, 3], [11, 8], [3, 13]] },
      { rip: [5, 11], sp: [[9, 2], [4, 9], [13, 12]] },
      { rip: [4, 10], sp: [[12, 4], [7, 10], [2, 14]] },
      { rip: [5, 11], sp: [[5, 2], [10, 7], [8, 13]] },
    ];
    for (let f = 0; f < WATER_FRAMES; f++) {
      this._tex(`tile_${TILE.WATER}_f${f}`, S, S, g => {
        const c = TILE_COLORS[TILE.WATER];
        // Base water
        g.fillStyle(c.fill);
        g.fillRect(0, 0, S, S);
        // Depth gradient: darker edges
        g.fillStyle(c.border, 0.12);
        g.fillRect(0, 0, S, 2);
        g.fillRect(0, 14, S, 2);
        g.fillRect(0, 0, 2, S);
        g.fillRect(14, 0, 2, S);
        // Lighter center
        g.fillStyle(c.detail, 0.08);
        g.fillRect(4, 4, 8, 8);

        // Ripple lines (shift vertically per frame)
        const wd = waveData[f];
        g.lineStyle(1, c.detail, 0.3);
        g.lineBetween(2, wd.rip[0], 14, wd.rip[0] + 1);
        g.lineStyle(1, c.detail, 0.2);
        g.lineBetween(4, wd.rip[1], 12, wd.rip[1] + 1);
        // Subtle mid-ripple
        g.lineStyle(1, c.detail, 0.12);
        g.lineBetween(5, 7 + (f % 2), 11, 7 + (f % 2));

        // Sparkles (migrate per frame)
        g.fillStyle(0xFFFFFF, 0.3 - (f % 2) * 0.05);
        for (const [sx, sy] of wd.sp) {
          g.fillRect(sx, sy, 1, 1);
        }
      });
    }

    // ── ROAD (3 variants) — Cobblestone with mortar and wear ──
    for (let v = 0; v < TILE_VARIANTS[TILE.ROAD]; v++) {
      this._tex(`tile_${TILE.ROAD}_v${v}`, S, S, g => {
        _seed = 700 + v * 41;
        const c = TILE_COLORS[TILE.ROAD];
        // Tan base
        g.fillStyle(c.fill);
        g.fillRect(0, 0, S, S);

        // Cobblestones (4 irregular stones)
        const stones = [
          [0, 0, 7, 7], [8, 0, 8, 7],
          [0, 8, 8, 8], [9, 8, 7, 8],
        ];
        for (const [sx, sy, sw, sh] of stones) {
          // Stone face variation
          g.fillStyle(_lerpColor(c.border, c.detail, _rand() * 0.4), 0.2);
          g.fillRect(sx + 1, sy + 1, sw - 2, sh - 2);
          // Mortar gap
          g.lineStyle(1, c.border, 0.35);
          g.strokeRect(sx, sy, sw, sh);
          // Top highlight on stone
          g.fillStyle(c.detail, 0.08);
          g.fillRect(sx + 1, sy + 1, sw - 2, 1);
          // Wear mark
          if (_rand() > 0.5) {
            g.fillStyle(c.detail, 0.1);
            g.fillRect(sx + 2, sy + 2, _randInt(1, 2), 1);
          }
        }
        // Mortar dirt specks
        for (let i = 0; i < 2; i++) {
          g.fillStyle(0x6B5B40, 0.12);
          g.fillRect(_randInt(0, 14), _randInt(0, 14), 1, 1);
        }
        // Puddle tint on variant 2
        if (v === 2) {
          g.fillStyle(0x5588AA, 0.12);
          g.fillRect(_randInt(3, 8), _randInt(3, 8), 3, 2);
        }
      });
    }

    // ── DOOR (1 variant) — Wooden planks, iron studs, gold handle ──
    this._tex(`tile_${TILE.DOOR}_v0`, S, S, g => {
      const c = TILE_COLORS[TILE.DOOR];
      // Wood base
      g.fillStyle(c.fill);
      g.fillRect(0, 0, S, S);
      // Wood grain lines
      g.fillStyle(c.detail, 0.12);
      for (let y = 0; y < S; y += 3) g.fillRect(0, y, S, 1);
      // Plank divide
      g.fillStyle(c.border, 0.5);
      g.fillRect(8, 2, 1, 14);

      // Dark frame
      g.fillStyle(c.border);
      g.fillRect(1, 0, 1, S);   // left
      g.fillRect(14, 0, 1, S);  // right
      // Arch top
      g.fillRect(2, 0, 12, 1);
      g.fillRect(3, 1, 10, 1);

      // Iron studs
      g.fillStyle(0x555555);
      g.fillRect(4, 4, 1, 1);
      g.fillRect(11, 4, 1, 1);
      g.fillRect(4, 10, 1, 1);
      g.fillRect(11, 10, 1, 1);

      // Gold handle
      g.fillStyle(0xDDBB44);
      g.fillRect(10, 8, 2, 2);
      g.fillStyle(0xFFDD66, 0.5);
      g.fillRect(10, 8, 1, 1);
    });

    // ── COLUMN (1 variant) — Decorative, thinner than pillar ──
    this._tex(`tile_${TILE.COLUMN}_v0`, S, S, g => {
      const c = TILE_COLORS[TILE.COLUMN];
      g.fillStyle(0x000000, 0);
      g.fillRect(0, 0, S, S);

      // Ground shadow
      g.fillStyle(0x000000, 0.1);
      g.fillRect(3, 14, 10, 2);
      // Shaft
      g.fillStyle(c.fill);
      g.fillRect(5, 2, 6, 12);
      // Fluting
      g.fillStyle(c.border, 0.15);
      g.fillRect(6, 3, 1, 10);
      g.fillRect(9, 3, 1, 10);
      g.fillStyle(c.detail, 0.1);
      g.fillRect(7, 3, 1, 10);
      // Top capital
      g.fillStyle(c.detail);
      g.fillRect(4, 0, 8, 2);
      g.fillStyle(c.border, 0.4);
      g.fillRect(4, 0, 8, 1);
      // Bottom base
      g.fillStyle(c.detail);
      g.fillRect(4, 14, 8, 2);
    });

    // ── TREE (3 variants) — Bark trunk, roots, layered canopy ──
    for (let v = 0; v < TILE_VARIANTS[TILE.TREE]; v++) {
      this._tex(`tile_${TILE.TREE}_v${v}`, S, S, g => {
        _seed = 1000 + v * 59;
        const c = TILE_COLORS[TILE.TREE];
        g.fillStyle(0x000000, 0);
        g.fillRect(0, 0, S, S);

        // Ground shadow
        g.fillStyle(0x000000, 0.1);
        g.fillRect(3, 14, 10, 2);
        // Trunk with bark texture
        g.fillStyle(0x6B4423);
        g.fillRect(6, 9, 4, 7);
        g.fillStyle(0x7B5433, 0.4);
        g.fillRect(7, 10, 1, 5);
        // Root extensions
        g.fillStyle(0x5B3413);
        g.fillRect(5, 14, 1, 2);
        g.fillRect(10, 14, 1, 2);

        // Canopy — multiple overlapping circles
        const canopyColors = [c.fill, 0x2D7B2D, 0x357535];
        g.fillStyle(canopyColors[v]);
        g.fillCircle(8, 6, 6);
        // Highlight layer
        g.fillStyle(_lerpColor(canopyColors[v], 0x5ABA5A, 0.3), 0.5);
        g.fillCircle(6, 4, 3);
        // Shadow layer
        g.fillStyle(0x1D4B1D, 0.3);
        g.fillCircle(10, 8, 3);
        // Detail specks
        for (let i = 0; i < 4; i++) {
          g.fillStyle(c.detail, 0.25);
          g.fillRect(_randInt(3, 12), _randInt(1, 10), 1, 1);
        }
      });
    }

    // ── BANNER (1 variant) — Pole with finial, cloth folds, SPQR ──
    this._tex(`tile_${TILE.BANNER}_v0`, S, S, g => {
      const c = TILE_COLORS[TILE.BANNER];
      g.fillStyle(0x000000, 0);
      g.fillRect(0, 0, S, S);

      // Pole
      g.fillStyle(0xAAAAAA);
      g.fillRect(7, 0, 2, S);
      g.fillStyle(0xCCCCCC, 0.4);
      g.fillRect(7, 0, 1, S);
      // Gold finial ball
      g.fillStyle(0xDDBB44);
      g.fillRect(6, 0, 4, 2);
      g.fillStyle(0xFFDD66, 0.5);
      g.fillRect(7, 0, 2, 1);

      // Banner cloth
      g.fillStyle(c.fill);
      g.fillRect(2, 3, 12, 8);
      // Fold shadows
      g.fillStyle(c.border, 0.3);
      g.fillRect(4, 3, 1, 8);
      g.fillRect(9, 3, 1, 8);
      // Fold highlights
      g.fillStyle(c.detail, 0.2);
      g.fillRect(6, 3, 1, 8);
      g.fillRect(11, 3, 1, 8);

      // Gold insignia stripes (SPQR suggestion)
      g.fillStyle(0xDDBB44, 0.6);
      g.fillRect(4, 5, 8, 1);
      g.fillRect(5, 7, 6, 1);
      g.fillRect(4, 9, 8, 1);

      // Gold tassels
      g.fillStyle(0xDDBB44, 0.5);
      g.fillRect(2, 11, 1, 2);
      g.fillRect(13, 11, 1, 2);
    });

    // ── SHELF (2 variants) — Wood grain, distinct items ──
    for (let v = 0; v < TILE_VARIANTS[TILE.SHELF]; v++) {
      this._tex(`tile_${TILE.SHELF}_v${v}`, S, S, g => {
        const c = TILE_COLORS[TILE.SHELF];
        // Wood base
        g.fillStyle(c.fill);
        g.fillRect(0, 0, S, S);
        // Wood grain
        g.fillStyle(c.detail, 0.08);
        for (let y = 0; y < S; y += 2) g.fillRect(0, y, S, 1);
        // 3 shelf boards
        g.fillStyle(c.border);
        g.fillRect(0, 4, S, 1);
        g.fillRect(0, 9, S, 1);
        g.fillRect(0, 14, S, 1);
        // Shelf board highlight
        g.fillStyle(c.detail, 0.12);
        g.fillRect(0, 5, S, 1);
        g.fillRect(0, 10, S, 1);

        if (v === 0) {
          // Scrolls (parchment cylinders)
          g.fillStyle(0xE8DCC0);
          g.fillRect(2, 1, 4, 3);
          g.fillRect(9, 1, 3, 3);
          g.fillStyle(0xD8CCA8, 0.5);
          g.fillRect(3, 2, 2, 1);
          // Lower shelf scrolls
          g.fillStyle(0xE8DCC0);
          g.fillRect(3, 6, 5, 3);
          g.fillRect(10, 6, 4, 3);
          // Small terra-cotta pots
          g.fillStyle(0xBB7744);
          g.fillRect(1, 11, 3, 3);
          g.fillRect(7, 11, 2, 3);
          g.fillRect(12, 11, 3, 3);
          g.fillStyle(0xAA6633, 0.5);
          g.fillRect(2, 11, 1, 1);
        } else {
          // Colored books
          g.fillStyle(0x883322);
          g.fillRect(1, 1, 2, 3);
          g.fillStyle(0x224488);
          g.fillRect(4, 1, 2, 3);
          g.fillStyle(0x228844);
          g.fillRect(7, 1, 2, 3);
          g.fillStyle(0x884422);
          g.fillRect(11, 1, 3, 3);
          // Amphora
          g.fillStyle(0xBB7744);
          g.fillRect(3, 6, 3, 3);
          g.fillRect(4, 5, 1, 1); // neck
          g.fillStyle(0x996633);
          g.fillRect(9, 6, 4, 3);
          g.fillRect(10, 5, 2, 1);
          // Codex
          g.fillStyle(0xDDBB88);
          g.fillRect(1, 11, 4, 3);
          g.fillRect(8, 11, 5, 3);
          g.fillStyle(0xCCAA77, 0.5);
          g.fillRect(2, 12, 2, 1);
        }
      });
    }
  }

  // ═══════════════════════════════════════════════════════
  // PLAYER SPRITE — 16x24, 5 ranks, 4 dirs × 4 walk frames
  // ═══════════════════════════════════════════════════════

  /**
   * Generate player textures for ALL ranks.
   * Keys: player_rank{N}_{dir}_{frame}  (e.g., player_rank0_down_0)
   * Also generates legacy keys for default rank: player_down_0 etc.
   */
  _generatePlayerSprite() {
    const W = CHAR_W, H = CHAR_H;
    const dirs = ['down', 'up', 'left', 'right'];
    const skin = 0xE8C8A0;

    for (let rankIdx = 0; rankIdx < RANKS.length; rankIdx++) {
      const rank = RANKS[rankIdx];
      for (let d = 0; d < dirs.length; d++) {
        for (let f = 0; f < 4; f++) {
          const key = `player_rank${rankIdx}_${dirs[d]}_${f}`;
          this._tex(key, W, H, g => {
            this._drawCharacter(g, W, H, dirs[d], f, skin, rank);
          });

          // Legacy keys for default (rank 0 / plebeian)
          if (rankIdx === 0 && f < 2) {
            this._tex(`player_${dirs[d]}_${f}`, W, H, g => {
              this._drawCharacter(g, W, H, dirs[d], f, skin, rank);
            });
          }
        }
      }
    }
  }

  /**
   * Draw a character at 16x24 with rank-specific gear.
   * Head: rows 0-6, Torso: rows 7-16, Legs: rows 17-23
   */
  _drawCharacter(g, W, H, dir, frame, skinColor, rank) {
    // ── Walk cycle leg offsets (4-frame) ──
    // frame 0: standing, 1: step-right, 2: mid-stride(bob), 3: step-left
    const legOffsets = [
      { lx: 4, rx: 9, ly: 0, ry: 0 },   // standing
      { lx: 3, rx: 10, ly: 0, ry: 1 },   // step right
      { lx: 4, rx: 9, ly: 0, ry: 0 },    // mid (bob - body shifts up 1px)
      { lx: 5, rx: 8, ly: 1, ry: 0 },    // step left
    ];
    const leg = legOffsets[frame];
    const bob = frame === 2 ? -1 : 0;

    // ── Legs (rows 17-23) ──
    g.fillStyle(0x553322);
    g.fillRect(leg.lx, 18 + leg.ly, 3, 6 - leg.ly);
    g.fillRect(leg.rx, 18 + leg.ry, 3, 6 - leg.ry);
    // Sandal detail
    g.fillStyle(0x443322);
    g.fillRect(leg.lx, 22 + leg.ly, 3, 2 - leg.ly);
    g.fillRect(leg.rx, 22 + leg.ry, 3, 2 - leg.ry);

    // ── Torso (rows 7-17) ──
    const toga = rank.toga;
    g.fillStyle(toga);
    g.fillRect(3, 8 + bob, 10, 10);

    // Belt
    if (rank.belt) {
      g.fillStyle(rank.belt);
      g.fillRect(3, 14 + bob, 10, 1);
    }

    // Armor overlay
    if (rank.armor) {
      g.fillStyle(rank.armor, 0.6);
      g.fillRect(4, 9 + bob, 8, 5);
      // Armor highlight
      g.fillStyle(rank.armor, 0.3);
      g.fillRect(5, 9 + bob, 6, 1);
      // Armor studs for master+
      if (rank.id === 'master' || rank.id === 'senator') {
        g.fillStyle(0xDDBB44, 0.5);
        g.fillRect(5, 11 + bob, 1, 1);
        g.fillRect(10, 11 + bob, 1, 1);
      }
    }

    // Trim line
    g.fillStyle(rank.trim, 0.6);
    g.fillRect(3, 8 + bob, 10, 1);

    // Cape (master, senator)
    if (rank.cape) {
      if (dir === 'up') {
        g.fillStyle(rank.cape);
        g.fillRect(3, 8 + bob, 10, 9);
        g.fillStyle(rank.cape, 0.7);
        g.fillRect(4, 9 + bob, 8, 7);
      } else if (dir === 'left') {
        g.fillStyle(rank.cape, 0.5);
        g.fillRect(12, 9 + bob, 2, 8);
      } else if (dir === 'right') {
        g.fillStyle(rank.cape, 0.5);
        g.fillRect(2, 9 + bob, 2, 8);
      }
      // down — cape hidden behind character
    }

    // Arms
    g.fillStyle(skinColor);
    if (dir === 'left') {
      g.fillRect(2, 9 + bob, 1, 5);
      if (rank.armor) { g.fillStyle(rank.armor, 0.4); g.fillRect(2, 9 + bob, 1, 2); }
    } else if (dir === 'right') {
      g.fillRect(13, 9 + bob, 1, 5);
      if (rank.armor) { g.fillStyle(rank.armor, 0.4); g.fillRect(13, 9 + bob, 1, 2); }
    } else {
      g.fillRect(2, 9 + bob, 1, 5);
      g.fillRect(13, 9 + bob, 1, 5);
      if (rank.armor) {
        g.fillStyle(rank.armor, 0.4);
        g.fillRect(2, 9 + bob, 1, 2);
        g.fillRect(13, 9 + bob, 1, 2);
      }
    }

    // ── Head (rows 0-7) ──
    g.fillStyle(skinColor);
    g.fillRect(4, 1 + bob, 8, 6);

    // Hair (if not helmeted)
    if (rank.hair && !rank.helmet) {
      g.fillStyle(rank.hair);
      g.fillRect(4, 0 + bob, 8, 2);
      if (dir === 'left') g.fillRect(4, 2 + bob, 2, 2);
      else if (dir === 'right') g.fillRect(10, 2 + bob, 2, 2);
      else { g.fillRect(4, 2 + bob, 1, 2); g.fillRect(11, 2 + bob, 1, 2); }
    }

    // Helmet
    if (rank.helmet) {
      g.fillStyle(rank.helmet);
      g.fillRect(3, 0 + bob, 10, 3);
      g.fillRect(4, 3 + bob, 8, 1);
      // Nose guard (master+)
      if (dir === 'down' && (rank.id === 'master' || rank.id === 'senator')) {
        g.fillStyle(rank.helmet, 0.7);
        g.fillRect(7, 4 + bob, 2, 2);
      }
      // Plume (senator)
      if (rank.id === 'senator') {
        g.fillStyle(0xDD3333);
        g.fillRect(6, -1 + bob, 4, 2);
        g.fillRect(7, -2 + bob, 2, 1);
      }
    }

    // Eyes
    g.fillStyle(0x222222);
    if (dir === 'down') {
      g.fillRect(5, 4 + bob, 1, 1);
      g.fillRect(10, 4 + bob, 1, 1);
    } else if (dir === 'left') {
      g.fillRect(4, 4 + bob, 1, 1);
    } else if (dir === 'right') {
      g.fillRect(11, 4 + bob, 1, 1);
    }

    // Mouth (front-facing only)
    if (dir === 'down') {
      g.fillStyle(skinColor, 0.5);
      g.fillRect(7, 6 + bob, 2, 1);
    }
  }

  // ═══════════════════════════════════════════════════════
  // NPC SPRITES — 16x24, distinct silhouettes
  // ═══════════════════════════════════════════════════════

  _generateNPCSprites() {
    const W = CHAR_W, H = CHAR_H;

    // ── Guard — Dark red armor, helmet, spear ──
    this._tex('npc_guard', W, H, g => {
      // Legs
      g.fillStyle(0x553322);
      g.fillRect(4, 18, 3, 6);
      g.fillRect(9, 18, 3, 6);
      // Greaves
      g.fillStyle(0x888888);
      g.fillRect(4, 20, 3, 2);
      g.fillRect(9, 20, 3, 2);
      // Torso — dark red armor
      g.fillStyle(0x8B2500);
      g.fillRect(3, 8, 10, 10);
      // Armor plate
      g.fillStyle(0xAA3311, 0.5);
      g.fillRect(4, 9, 8, 4);
      g.fillStyle(0x777777);
      g.fillRect(3, 14, 10, 1);
      // Arms
      g.fillStyle(0xD4A574);
      g.fillRect(2, 9, 1, 5);
      g.fillRect(13, 9, 1, 5);
      // Head
      g.fillStyle(0xD4A574);
      g.fillRect(4, 1, 8, 6);
      // Helmet with cheek guards
      g.fillStyle(0x777777);
      g.fillRect(3, 0, 10, 3);
      g.fillRect(3, 3, 2, 2);
      g.fillRect(11, 3, 2, 2);
      g.fillStyle(0xDD3333, 0.6);
      g.fillRect(6, -1, 4, 2); // plume
      // Eyes
      g.fillStyle(0x222222);
      g.fillRect(5, 4, 1, 1);
      g.fillRect(10, 4, 1, 1);
      // Spear (extends above head)
      g.fillStyle(0x8B6914);
      g.fillRect(14, 0, 1, 24);
      g.fillStyle(0xAAAAAA);
      g.fillRect(13, 0, 3, 3);
      g.fillRect(14, 0, 1, 1);
    });

    // ── Merchant — Colorful robes, wider body, coin purse ──
    this._tex('npc_merchant', W, H, g => {
      // Legs (hidden under robe)
      g.fillStyle(0x553322);
      g.fillRect(5, 20, 2, 4);
      g.fillRect(9, 20, 2, 4);
      // Wide robe body
      g.fillStyle(0x665D1E);
      g.fillRect(2, 8, 12, 12);
      // Robe pattern stripes
      g.fillStyle(0x887744, 0.3);
      g.fillRect(2, 11, 12, 1);
      g.fillRect(2, 14, 12, 1);
      g.fillRect(2, 17, 12, 1);
      // Sash
      g.fillStyle(0xDDBB44, 0.5);
      g.fillRect(3, 8, 10, 1);
      // Coin purse at belt
      g.fillStyle(0xBB8844);
      g.fillRect(11, 13, 3, 3);
      g.fillStyle(0xDDBB44, 0.5);
      g.fillRect(12, 13, 1, 1);
      // Arms (wider robe sleeves)
      g.fillStyle(0x665D1E, 0.8);
      g.fillRect(1, 9, 1, 6);
      g.fillRect(14, 9, 1, 6);
      g.fillStyle(0xE8C8A0);
      g.fillRect(1, 14, 1, 2);
      g.fillRect(14, 14, 1, 2);
      // Head
      g.fillStyle(0xE8C8A0);
      g.fillRect(4, 1, 8, 6);
      // Hat
      g.fillStyle(0x665D1E);
      g.fillRect(3, 0, 10, 2);
      g.fillStyle(0x887744);
      g.fillRect(5, 0, 6, 1);
      // Eyes
      g.fillStyle(0x222222);
      g.fillRect(5, 4, 1, 1);
      g.fillRect(10, 4, 1, 1);
      // Smile
      g.fillStyle(0xCC9977);
      g.fillRect(7, 6, 2, 1);
    });

    // ── Scholar — Long hooded robe, scroll in hand ──
    this._tex('npc_scholar', W, H, g => {
      // Legs (barely visible)
      g.fillStyle(0x443322);
      g.fillRect(5, 21, 2, 3);
      g.fillRect(9, 21, 2, 3);
      // Long flowing robe
      g.fillStyle(0x336699);
      g.fillRect(3, 6, 10, 15);
      // Robe shading
      g.fillStyle(0x224477, 0.3);
      g.fillRect(3, 6, 2, 15);
      g.fillRect(11, 6, 2, 15);
      // Belt
      g.fillStyle(0x554422);
      g.fillRect(3, 14, 10, 1);
      // Arms
      g.fillStyle(0x336699);
      g.fillRect(2, 8, 1, 7);
      g.fillRect(13, 8, 1, 7);
      // Scroll in left hand
      g.fillStyle(0xE8DCC0);
      g.fillRect(0, 12, 3, 4);
      g.fillStyle(0xD4C8A8, 0.6);
      g.fillRect(1, 13, 1, 2);
      // Head
      g.fillStyle(0xE8C8A0);
      g.fillRect(5, 2, 6, 5);
      // Hood
      g.fillStyle(0x336699);
      g.fillRect(3, 0, 10, 4);
      g.fillRect(4, 4, 1, 2);
      g.fillRect(11, 4, 1, 2);
      g.fillStyle(0x224477, 0.5);
      g.fillRect(4, 1, 8, 2);
      // Eyes (shadowed under hood)
      g.fillStyle(0x222222);
      g.fillRect(6, 4, 1, 1);
      g.fillRect(9, 4, 1, 1);
    });
  }

  // ═══════════════════════════════════════════════════════
  // UI TEXTURES
  // ═══════════════════════════════════════════════════════

  /**
   * Generate UI textures (interaction prompt, particles, atmosphere).
   */
  _generateUITextures() {
    // Interaction indicator (floating diamond)
    this._tex('interact_icon', 16, 16, g => {
      g.fillStyle(0xDDBB44);
      g.fillTriangle(8, 0, 0, 8, 8, 16);
      g.fillTriangle(8, 0, 16, 8, 8, 16);
      g.fillStyle(0xFFDD66, 0.5);
      g.fillTriangle(8, 2, 2, 8, 8, 14);
    });

    // Dust particle (2x2 warm speck)
    this._tex('dust_particle', 2, 2, g => {
      g.fillStyle(0xD4B896, 0.6);
      g.fillRect(0, 0, 2, 2);
    });

    // Torch glow (32x32 radial gradient approximation)
    this._tex('torch_glow', 32, 32, g => {
      const cx = 16, cy = 16;
      // Outer glow
      g.fillStyle(0xFF8800, 0.03);
      g.fillCircle(cx, cy, 15);
      g.fillStyle(0xFF8800, 0.05);
      g.fillCircle(cx, cy, 12);
      g.fillStyle(0xFFAA22, 0.08);
      g.fillCircle(cx, cy, 9);
      g.fillStyle(0xFFCC44, 0.12);
      g.fillCircle(cx, cy, 6);
      g.fillStyle(0xFFDD66, 0.15);
      g.fillCircle(cx, cy, 3);
    });

    // Torch flame (4x8 animated-feel)
    this._tex('torch_flame', 4, 8, g => {
      g.fillStyle(0xFF6600);
      g.fillRect(1, 4, 2, 4);
      g.fillStyle(0xFF8800);
      g.fillRect(0, 2, 4, 4);
      g.fillStyle(0xFFCC00);
      g.fillRect(1, 1, 2, 3);
      g.fillStyle(0xFFEE88, 0.7);
      g.fillRect(1, 0, 2, 2);
    });
  }
}
