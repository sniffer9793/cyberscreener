/**
 * QUAEST.TECH — Game Configuration
 * Constants, tile types, and district definitions for the 2D Basilica world.
 */

export const TILE_SIZE = 16;
export const MAP_COLS = 80;
export const MAP_ROWS = 60;
export const WORLD_W = MAP_COLS * TILE_SIZE; // 1280
export const WORLD_H = MAP_ROWS * TILE_SIZE; // 960

// Tile type IDs (used in map array and tileset)
export const TILE = {
  VOID:     0,
  STONE:    1,
  MARBLE:   2,
  GRASS:    3,
  WALL:     4,
  PILLAR:   5,
  WATER:    6,
  ROAD:     7,
  DOOR:     8,
  COLUMN:   9,
  TREE:    10,
  BANNER:  11,
  SHELF:   12,
};

// Which tiles block movement
export const SOLID_TILES = new Set([
  TILE.VOID, TILE.WALL, TILE.PILLAR, TILE.WATER,
  TILE.COLUMN, TILE.TREE, TILE.SHELF,
]);

// District definitions — name, bounds, floor type, color theme
export const DISTRICTS = [
  {
    id: 'forum',
    name: 'The Forum',
    desc: 'Central plaza — all roads lead here.',
    bounds: { x: 25, y: 20, w: 30, h: 20 },
    floor: TILE.MARBLE,
    color: 0x4E0B59, // Imperial Purple
    labelColor: '#4E0B59',
    spawn: true,
    page: null, // No dashboard panel
  },
  {
    id: 'curia',
    name: 'The Curia',
    desc: 'Elite council chamber. STEEL+ Tempering Grade required.',
    bounds: { x: 4, y: 4, w: 20, h: 16 },
    floor: TILE.MARBLE,
    color: 0xB8860B, // Forge Amber
    labelColor: '#B8860B',
    locked: 'STEEL',
    page: 'conviction', // ConvictionPage (Scores)
  },
  {
    id: 'basilica_julia',
    name: 'Basilica Julia',
    desc: 'Hall of Scrolls — pin your strategies for all to see.',
    bounds: { x: 56, y: 4, w: 20, h: 16 },
    floor: TILE.MARBLE,
    color: 0x665D1E, // Oxidized Bronze
    labelColor: '#665D1E',
    page: 'basilica', // BasilicaPage (Overview)
  },
  {
    id: 'subura',
    name: 'The Subura',
    desc: 'Public market square. New citizens begin here.',
    bounds: { x: 4, y: 40, w: 22, h: 16 },
    floor: TILE.STONE,
    color: 0xA6A6A6, // Denarius Silver
    labelColor: '#666666',
    page: 'anvil', // AnvilPage (Plays)
  },
  {
    id: 'tabularium',
    name: 'The Tabularium',
    desc: 'Imperial archives — research and historical data.',
    bounds: { x: 54, y: 40, w: 22, h: 16 },
    floor: TILE.STONE,
    color: 0x8B2500, // Forge Red
    labelColor: '#8B2500',
    page: 'archive', // ArchivePage (Backtest)
  },
];

// Player spawn position (Forum, above the central fountain)
export const SPAWN = {
  x: 40 * TILE_SIZE,
  y: 25 * TILE_SIZE,
};

// Movement speed (pixels per frame at 60fps)
export const PLAYER_SPEED = 120;

// Tile color palette for texture generation
export const TILE_COLORS = {
  [TILE.VOID]:   { fill: 0x111111, border: 0x111111 },
  [TILE.STONE]:  { fill: 0x6B6B6B, border: 0x5A5A5A, detail: 0x7A7A7A },
  [TILE.MARBLE]: { fill: 0xE8E0D4, border: 0xD0C8BC, detail: 0xF0EAE0 },
  [TILE.GRASS]:  { fill: 0x4A8B4A, border: 0x3E7A3E, detail: 0x5A9B5A },
  [TILE.WALL]:   { fill: 0x3A3A3A, border: 0x2A2A2A, detail: 0x4A4A4A },
  [TILE.PILLAR]: { fill: 0xC9A87C, border: 0xB89868, detail: 0xD9B88C },
  [TILE.WATER]:  { fill: 0x4488CC, border: 0x3377BB, detail: 0x5599DD },
  [TILE.ROAD]:   { fill: 0xA09070, border: 0x908060, detail: 0xB0A080 },
  [TILE.DOOR]:   { fill: 0x8B5A2B, border: 0x7A4A1B, detail: 0x9B6A3B },
  [TILE.COLUMN]: { fill: 0xBBA888, border: 0xAA9878, detail: 0xCCB898 },
  [TILE.TREE]:   { fill: 0x2D6B2D, border: 0x1D5B1D, detail: 0x3D7B3D },
  [TILE.BANNER]: { fill: 0x4E0B59, border: 0x3E0049, detail: 0x6E2B79 },
  [TILE.SHELF]:  { fill: 0x8B6914, border: 0x7B5904, detail: 0x9B7924 },
};
