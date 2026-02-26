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

// Tile variant counts (for procedural variation)
export const TILE_VARIANTS = {
  [TILE.VOID]:   1,
  [TILE.STONE]:  4,
  [TILE.MARBLE]: 3,
  [TILE.GRASS]:  4,
  [TILE.WALL]:   3,
  [TILE.PILLAR]: 1,
  [TILE.WATER]:  1,  // water uses animation frames instead
  [TILE.ROAD]:   3,
  [TILE.DOOR]:   1,
  [TILE.COLUMN]: 1,
  [TILE.TREE]:   3,
  [TILE.BANNER]: 1,
  [TILE.SHELF]:  2,
};

// Water animation
export const WATER_FRAMES = 4;
export const WATER_FRAME_MS = 400;

// Character sprite dimensions
export const CHAR_W = 16;
export const CHAR_H = 24;

// Rank tiers — visual progression based on player level
export const RANKS = [
  { id: 'plebeian',  minLevel: 1,  name: 'Plebeian',
    toga: 0xDDD8CC, trim: 0xAAAAAA, hair: 0x664422, belt: null, armor: null, cape: null, helmet: null },
  { id: 'equite',    minLevel: 6,  name: 'Equite',
    toga: 0x3366AA, trim: 0xDDBB44, hair: 0x553311, belt: 0x8B5A2B, armor: null, cape: null, helmet: null },
  { id: 'quaestor',  minLevel: 16, name: 'Quaestor',
    toga: 0x996633, trim: 0xDDBB44, hair: 0x553311, belt: 0x665533, armor: 0xBB8844, cape: null, helmet: 0xBB8844 },
  { id: 'master',    minLevel: 31, name: 'Master',
    toga: 0x555555, trim: 0xDDBB44, hair: null, belt: 0x444444, armor: 0x888888, cape: 0x8B2500, helmet: 0x777777 },
  { id: 'senator',   minLevel: 51, name: 'Senator',
    toga: 0x4E0B59, trim: 0xFFDD66, hair: null, belt: 0xDDBB44, armor: 0xDDBB44, cape: 0x8B2500, helmet: 0xDDBB44 },
];

// NPC ambient speech lines (stock-market-Roman themed)
export const NPC_SPEECH_LINES = [
  'Buy the dip, citizen!',
  'CRWD looks strong today...',
  'The Forum whispers of gains.',
  'Sell before the Ides!',
  'Patience is the way of the Quaestor.',
  'The scrolls foretold this rally.',
  'Volatility is opportunity.',
  'PANW holds the line.',
  'Trust the data, not the crowd.',
  'My options plays are forging well.',
  'The Tabularium never lies.',
  'Steel-grade conviction needed here.',
  'Markets favor the prepared.',
  'Another scan, another signal...',
];

// Scrolling ticker text
export const TICKER_TEXT = 'QUAEST \u00b7 ANCIENT INTELLIGENCE \u00b7 MODERN GAINS \u00b7 CYBER \u00b7 ENERGY \u00b7 DEFENSE \u00b7 FORGE YOUR CONVICTION \u00b7 ';

// Torch positions (building entrances — derived from district door locations)
export const TORCH_POSITIONS = [
  // Curia door (bottom side, doorOffset=10)
  { x: 13, y: 19 }, { x: 16, y: 19 },
  // Basilica Julia door (bottom side, doorOffset=10)
  { x: 65, y: 19 }, { x: 68, y: 19 },
  // Subura door (top side, doorOffset=11)
  { x: 14, y: 41 }, { x: 17, y: 41 },
  // Tabularium door (top side, doorOffset=11)
  { x: 64, y: 41 }, { x: 67, y: 41 },
];

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
