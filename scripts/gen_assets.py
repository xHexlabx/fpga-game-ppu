#!/usr/bin/env python3
"""gen_assets.py - the "cartridge ROM" data for project06_cavepatrol (CAVE PATROL).

CAVE PATROL is an original horizontal auto-scrolling cave shooter running on
the project05 PPU (see project05_ppu/src/ppu.v for the hardware). This script
draws every graphic, builds the cave, places the enemies and lays out the text
screens, then writes them as $readmemh files for the game logic. All art is
generated here (hand-drawn ASCII pixel art plus small procedural routines with
fixed seeds); the only external input is the Linux console font for the text.

Run from project06_cavepatrol/:   python3 scripts/gen_assets.py
Needs Python 3 + numpy + Pillow. Output is fully deterministic.

Output files (src/) - plain $readmemh text, one hex word per line, no address
markers, no comments, exactly the line count given.
--------------------------------------------------------------------------
src/palette.mem    32 lines x 2 hex digits.
    Line i = palette RAM entry i, a 6-bit RGB222 colour R*16 + G*4 + B
    (each channel 0..3). Entries 0..15: background palettes 0..3 (4 each),
    16..31: sprite palettes 4..7. Colour index 0 of every palette is
    transparent; entry 0 is the backdrop. Entries 4, 8, ..., 28 are never
    displayed and are written as 00.
      0      backdrop (open cave)          black
      1-3    pal0 rock                     dark purple / slate / lavender rim
      5-7    pal1 HUD + text               navy paper / grey / white
      9-11   pal2 arena masonry, veins,    purple / slate / amber glow
             decoration accents
      13-15  pal3 crystals                 three greens; the game rotates
                                           13<-14<-15<-13 every 8 frames
      17-19  pal4 player ship              outline / main / highlight
      21-23  pal5 enemies                  outline / main / highlight
      25-27  pal6 bolts + explosions       orange / yellow / white
      29-31  pal7 boss CORE                outline / main / highlight

src/chr_bg.mem, src/chr_spr.mem    2048 lines x 4 hex digits each.
    Pattern ROMs, 256 tiles of 8x8 pixels at 2 bits per pixel.
    Line index = tile*8 + row. Pixel p (0 = leftmost) is in bits
    [15-2p : 14-2p], so the leftmost pixel is in bits [15:14].
    Background tile ID ranges (the game uses them for collision):
      0x00        empty (all colour 0)                          non-solid
      0x01-0x1F   open-space decoration (glints, dust, roots,  non-solid
                  glowing fungus)
      0x20-0x5F   ASCII 0x20..0x5F from Lat15-VGA8, ink = ci3,  non-solid
                  paper = ci1 (white on navy with palette 1)
      0x60-0x63   HUD bar cells: depth empty/full, boss empty/full (pal 1)
      0x64-0x69   title-logo blocks (full block x2, 4 diagonals)
      0x6A-0x6C   panel frame: horizontal, vertical, corner gem (pal 1)
      0x70-0x7F   crystals, palette 3, each a self-contained    SOLID,
                  8x8 shape                                     destructible
      0x80-0xFF   rock: cave autotiles + arena masonry          SOLID
    Sprite tiles: the sheet is 16 tiles per row; a 16x16 sprite at tile T
    uses T, T+1 (top) and T+16, T+17 (bottom).
      0x00 / 0x02          player ship frames 0/1 (faces right, pal 4)
      0x04 / 0x06          drone frames 0/1 (pal 5)
      0x08 / 0x0A          dart frames 0/1 (faces left, pal 5)
      0x0C / 0x0E          floor turret, frame 1 = muzzle flash (pal 5);
                           the game v-flips it for ceiling turrets
      0x20,0x22,0x24,0x26  explosion frames 0..3 (pal 6)
      0x40,0x42,0x60,0x62  boss CORE frame 0 (TL, TR, BL, BR quarters, pal 7)
      0x44,0x46,0x64,0x66  boss CORE frame 1 (eye open, glowing)
      0x80 / 0x81          8x8 player bolt frames (pal 6)
      0x82 / 0x83          8x8 enemy orb frames (pal 6)
      everything else      0000

src/level.mem      16384 lines x 3 hex digits.
    512 level columns x 32 rows, line index = col*32 + row (column-major).
    Entry = (palette << 8) | tile. Rows 0, 1, 30, 31 are 000; rows 2..29 are
    the playfield (screen lines 16..239). The game streams level column c into
    VRAM page 0 column c mod 64. Columns 0..30 are wide open, the cave then
    narrows; crystal walls start at column 98; the entrance gate (two pillar
    pairs) is at columns 459-465; columns 468..511 are the boss arena (rock only
    in rows 2-3 and 28-29). Every column keeps a free span of at least 4 rows
    when crystals count as passable, also over any 3 neighbouring columns
    (checked below).

src/spawn.mem      128 lines x 8 hex digits (32-bit words).
    [8:0]   trigger: level column at the screen's right edge when the enemy
            appears (spawned when dist/8 + 40 == trigger)
    [10:9]  type: 0 drone, 1 dart, 2 floor turret, 3 ceiling turret
    [18:11] y: sprite top in screen pixels
    [31:19] 0
    Sorted by trigger, all triggers unique and in 45..466. After the last
    enemy every line is 000001FF (trigger 0x1FF = end of table).
    Floor turret:   y = 8*R - 16, R = topmost solid floor row, flat in
                    columns trigger and trigger+1.
    Ceiling turret: y = 8*(C+1), C = bottom-most solid ceiling row, flat in
                    columns trigger and trigger+1 (drawn v-flipped).
    Drones spawn at y 32..208 (they wobble +-16 px, so they stay clear of the
    HUD), darts at 24..208, never inside rock.

src/screens.mem    8192 lines x 3 hex digits.
    4 screens of 32 rows x 64 columns, line index = screen*2048 + row*64 + col
    (row-major). Entry = (palette << 8) | tile.
      0 TITLE, 1 GAME OVER, 2 CLEARED: rows 2..29, columns 0..39 used (the rest
        000). They are copied into VRAM page 1 and shown under the HUD.
      3 HUD: rows 0-1, palette 1, 40 columns, columns 40..63 = 0x120 (space).
        row 0 "  SCORE 000000    HI 000000    SHIPS 3  "
        row 1 "  DEPTH " + 16 x 0x60 + "  BOSS " + 8 x 0x62 + " "
        Other rows 000.

Preview images (images/, rendered by decoding the .mem files just written, so
they also check the bit and index orders):
    chr_bg.png, chr_spr.png    tile sheets, 16 per row, x4, in their palettes
    level.png                  the whole 4096x224 playfield in 4 strips of
                               1024 px (scale 1), with turrets drawn where they
                               sit and flyers drawn at their spawn point
    screens.png                title, game over, cleared and an in-game view
                               (HUD over the first screen of the cave), x2
    sprites_preview.png        every sprite and animation frame, enlarged
"""

import gzip
import math
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

PROJ = Path(__file__).resolve().parent.parent
SRC_DIR = PROJ / "src"
IMG_DIR = PROJ / "images"
FONT_PATH = "/usr/share/consolefonts/Lat15-VGA8.psf.gz"

N_COLS = 512            # level columns
ROW_TOP, ROW_BOT = 2, 29  # playfield rows (screen lines 16..239)
ARENA_COL = 468         # boss arena: columns 468..511
MASONRY_COL = 457       # carved arena stone starts here (antechamber + arena)
GATE_PILLARS = (459, 464)  # left column of each 2-wide gate pillar pair
LAST_TRIGGER = 466

def ihash(*vals):
    """Small deterministic integer hash (FNV-1a + finaliser). Used to pick
    tile variants so the choice depends only on position, never on the order
    things are generated in."""
    h = 2166136261
    for v in vals:
        h ^= v & 0xFFFFFFFF
        h = (h * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h ^= h >> 15
    return h

def c6(r, g, b):
    """RGB222 colour, channels 0..3."""
    return (r << 4) | (g << 2) | b

PALETTE = [0x00] * 32
PALETTE[0] = c6(0, 0, 0)                                  # backdrop
PALETTE[1:4] = [c6(1, 0, 1), c6(1, 1, 2), c6(2, 2, 3)]    # pal0 rock
PALETTE[5:8] = [0x01, 0x2A, 0x3F]                         # pal1 HUD text
PALETTE[9:12] = [c6(1, 0, 1), c6(1, 1, 2), c6(3, 2, 0)]   # pal2 amber accent
PALETTE[13:16] = [c6(0, 2, 1), c6(1, 3, 1), c6(2, 3, 3)]  # pal3 crystals
PALETTE[17:20] = [c6(0, 1, 2), c6(1, 3, 3), c6(3, 3, 3)]  # pal4 ship
PALETTE[21:24] = [c6(1, 0, 0), c6(3, 0, 1), c6(3, 3, 2)]  # pal5 enemies
PALETTE[25:28] = [c6(3, 1, 0), c6(3, 3, 0), c6(3, 3, 3)]  # pal6 bolts/explosions
PALETTE[29:32] = [c6(1, 0, 1), c6(2, 0, 3), c6(3, 1, 3)]  # pal7 boss

def lut_rgb(pal6):
    """64-colour index -> RGB888 table for previews (each channel v*85)."""
    return np.array([[((v >> 4) & 3) * 85, ((v >> 2) & 3) * 85, (v & 3) * 85]
                     for v in pal6], dtype=np.uint8)

LEG = {'.': 0, 'o': 1, 'm': 2, 'h': 3, '0': 0, '1': 1, '2': 2, '3': 3}

def art(rows, w=None, h=None):
    """ASCII art -> uint8 array of colour indices ('.'/0, 'o'/1, 'm'/2, 'h'/3)."""
    a = np.array([[LEG[ch] for ch in row] for row in rows], dtype=np.uint8)
    if w is not None:
        assert a.shape == (h, w), (a.shape, rows)
    return a

def put(sheet, tile, img):
    """Paste an image into a 128x128 tile sheet with its top-left at `tile`."""
    y0, x0 = (tile // 16) * 8, (tile % 16) * 8
    sheet[y0:y0 + img.shape[0], x0:x0 + img.shape[1]] = img

def sheet_tile(sheet, t):
    y0, x0 = (t // 16) * 8, (t % 16) * 8
    return sheet[y0:y0 + 8, x0:x0 + 8]

def load_psf1_8x8(path):
    """Returns {codepoint: 8 row bytes} for a PSF1 font with 8-row glyphs.
    Uses the font's unicode table, so ASCII maps to the right glyph even when
    the font's internal order is not ASCII."""
    raw = gzip.open(path, "rb").read()
    if raw[:2] != b"\x36\x04":
        sys.exit(f"{path}: not a PSF1 font")
    mode, charsize = raw[2], raw[3]
    if charsize != 8:
        sys.exit(f"{path}: charsize {charsize}, want 8 (8x8 font)")
    nglyph = 512 if (mode & 0x01) else 256
    glyphs = [raw[4 + i * 8: 4 + i * 8 + 8] for i in range(nglyph)]
    umap = {}
    if mode & 0x02:
        off, idx = 4 + nglyph * 8, 0
        while off + 1 < len(raw) and idx < nglyph:
            cp = int.from_bytes(raw[off:off + 2], "little")
            off += 2
            if cp == 0xFFFF:
                idx += 1
            elif cp not in umap:
                umap[cp] = idx
    return {cp: glyphs[gi] for cp, gi in umap.items()} if umap else \
        {i: glyphs[i] for i in range(nglyph)}

bg_sheet = np.zeros((128, 128), np.uint8)
bg_prev_pal = [0] * 256          # palette each BG tile is previewed in

DECOR = {
    0x01: ["........", "........", "........", ".....o..",
           "........", "........", "........", "........"],
    0x02: ["........", ".o......", "........", "........",
           "........", "......o.", "........", "........"],
    0x03: ["........", "........", "........", "........",
           "........", "........", "..o.....", "........"],
    0x04: ["........", "........", "...o....", "..o.o...",
           "...o....", "........", "........", "........"],
    0x05: ["........", "....o...", "....m...", "..omhmo.",
           "....m...", "....o...", "........", "........"],
    0x06: ["........", "........", "...o....", "..omo...",
           "...o....", "........", "........", "........"],
    0x07: ["........", "..oo....", ".ooo....", "..o..o..",
           ".....oo.", "........", "...o....", "........"],
    0x08: ["........", "......o.", ".o...oo.", ".oo.....",
           "..o.....", "....oo..", "....o...", "........"],
    0x09: ["...o....", "..oo....", "........", "......o.",
           ".o...ooo", ".oo.....", "........", "....o..."],
    0x0A: ["........", ".o......", "........", "...ooo..",
           "..oo.o..", "........", "o.....o.", "........"],
    0x0B: [".o...o..", ".o...o..", ".m...o..", ".o...m..",
           ".o......", ".m......", "........", "........"],
    0x0C: ["..o.....", "..o..o..", "..o..o..", "..m..o..",
           "..o..o..", "..o..m..", "..m.....", "........"],
    0x0D: ["........", "........", "........", ".hhh....",
           ".mhm..h.", "..o..hhh", "..o...o.", "..o...o."],
    0x0E: ["........", "........", "........", "........",
           "....hh..", "...hhhh.", ".h...o..", "hho..o.."],
    0x0F: ["........", "........", "...o....", "...o....",
           "...m....", "..mhm...", "...m....", "........"],
}
DECOR_PAL = {t: 0 for t in DECOR}
DECOR_PAL[0x0D] = DECOR_PAL[0x0E] = 2
for t, rows in DECOR.items():
    put(bg_sheet, t, art(rows, 8, 8))
    bg_prev_pal[t] = DECOR_PAL[t]

FONT = load_psf1_8x8(FONT_PATH)
for code in range(0x20, 0x60):
    rows = FONT[code]
    g = np.ones((8, 8), np.uint8)          # paper = ci1
    for y in range(8):
        for x in range(8):
            if rows[y] & (0x80 >> x):
                g[y, x] = 3                # ink = ci3
    put(bg_sheet, code, g)
    bg_prev_pal[code] = 1

HUDLOGO = {
    0x60: ["oooooooo", "mmmmmmmm", "oooooooo", "oooooooo",     # depth empty
           "oooooooo", "oooooooo", "mmmmmmmm", "oooooooo"],
    0x61: ["oooooooo", "mmmmmmmm", "hhhhhhho", "hhhhhhho",     # depth full
           "hhhhhhho", "mmmmmmmo", "mmmmmmmm", "oooooooo"],
    0x62: ["oooooooo", "ommmmmmo", "omoooomo", "omoooomo",     # boss empty
           "omoooomo", "omoooomo", "ommmmmmo", "oooooooo"],
    0x63: ["oooooooo", "ommmmmmo", "omhhhhmo", "omhhhhmo",     # boss full
           "omhhhhmo", "omhmmhmo", "ommmmmmo", "oooooooo"],
    0x64: ["hhhhhhhm", "hmmmmmmo", "hmmmmmmo", "hmmmmmmo",
           "hmmmmmmo", "hmmmmmmo", "hmmmmmmo", "mooooooo"],
    0x65: ["hhhhhhhm", "hmmmmmmo", "hmmmhmmo", "hmmhhhmo",
           "hmmmhmmo", "hmmmmmmo", "hmmmmmmo", "mooooooo"],
    0x6A: ["oooooooo", "oooooooo", "oooooooo", "hhhhhhhh",
           "mmmmmmmm", "oooooooo", "oooooooo", "oooooooo"],
    0x6B: ["ooohmooo", "ooohmooo", "ooohmooo", "ooohmooo",
           "ooohmooo", "ooohmooo", "ooohmooo", "ooohmooo"],
    0x6C: ["ooohmooo", "oohhhmoo", "ohhhhhmo", "hhhhhhhm",
           "mmhhhmmm", "ommhmmmo", "oommmmoo", "ooommooo"],
}
for t, rows in HUDLOGO.items():
    put(bg_sheet, t, art(rows, 8, 8))
    bg_prev_pal[t] = 1 if t < 0x64 or t >= 0x6A else 3

def logo_diag(kind):
    """Logo diagonal half-blocks. kind: 'r' filled lower-right, 'l' lower-left,
    'R' upper-right, 'L' upper-left. Up-facing slants get the highlight,
    down-facing slants the dark edge, like the block's own bevel."""
    t = np.zeros((8, 8), np.uint8)
    for y in range(8):
        for x in range(8):
            if kind == 'r':
                fill, edge = x + y >= 7, x + y == 7
            elif kind == 'l':
                fill, edge = x <= y, x == y
            elif kind == 'R':
                fill, edge = x >= y, x == y
            else:
                fill, edge = x + y <= 7, x + y == 7
            if not fill:
                continue
            v = 2
            if kind in 'rl' and edge:
                v = 3
            if kind in 'RL' and edge:
                v = 1
            if y == 0 and kind in 'RL':
                v = 3
            if y == 7 and kind in 'rl':
                v = 1
            if x == 0 and kind in 'lL' and not (kind == 'L' and edge):
                v = 3
            if x == 7 and kind in 'rR' and not (kind == 'r' and edge):
                v = 1
            t[y, x] = v
    return t

LOGO_TILE = {'#': 0x64, 'r': 0x66, 'l': 0x67, 'R': 0x68, 'L': 0x69}
for ch, t in (('r', 0x66), ('l', 0x67), ('R', 0x68), ('L', 0x69)):
    put(bg_sheet, t, logo_diag(ch))
    bg_prev_pal[t] = 3

CRYSTALS = {
    0x70: ["..h.....", ".hmo....", ".hmo..h.", ".hmo.hmo",
           "hhmmohmo", "hmmmohmo", "hmmmmmmo", ".oooooo."],
    0x71: [".....h..", ".h...ho.", ".ho..hmo", "hmo.hhmo",
           "hmohhmmo", "hmmmmmmo", "mmmmmmoo", ".mmmmoo."],
    0x74: ["...hh...", "..hhmo..", ".hhmmmo.", "hhmmmmoo",
           ".hmmmoo.", "..mmoo..", "...oo...", "........"],
    0x75: ["..hhhh..", ".hhmmmo.", "hhmmmmoo", "hmmmmmoo",
           "hmmmmmoo", ".mmmmoo.", "..oooo..", "........"],
    0x76: [".hh.....", "hhmo....", ".mo..hh.", "....hhmo",
           "....hmmo", ".....oo.", "..hh....", "..mo...."],
    0x77: ["......hh", "....hhmo", "...hmmo.", "..hmmo..",
           ".hmmo...", "hmmo....", "hmo.....", ".o......"],
    0x78: ["hhhmhhhm", "hmmohmmo", "hmmohmmo", "mooomooo",
           "hhhmhhhm", "hmmohmmo", "hmmohmmo", "mooomooo"],
    0x79: ["hhhhhhhm", "hhmmmmmo", "hmhmmmmo", "hmmmmmmo",
           "hmmmmhmo", "hmmmmmoo", "hmmmmooo", "mooooooo"],
    0x7A: ["hhhhhhmo", "hmmmmmoh", "hmmmmohm", "hmmmohmo",
           "hmmohmmo", "hmohmmmo", "hohmmmmo", "ommmmmoo"],
    0x7B: ["hhhhhhhm", "hmmhmmmo", "hmmmmmmo", "mooooooo",
           "hhhhhhhm", "hmmmmhmo", "hmmmmmmo", "mooooooo"],
    0x7C: ["..h..h..", ".hmohmo.", ".hmohmo.", "hhmohmmo",
           "hmmohmmo", "hmmohmmo", "hmmmmmmo", ".oooooo."],
    0x7D: ["...hh...", "..hmmo..", ".hhmmo..", ".hmmmoh.",
           "hhmmohmo", "hmmmohmo", "hmmmmmoo", ".ooooo.."],
}
for t, rows in CRYSTALS.items():
    put(bg_sheet, t, art(rows, 8, 8))
for src, dst in ((0x70, 0x72), (0x71, 0x73), (0x7C, 0x7E), (0x7D, 0x7F)):
    a = art(CRYSTALS[src], 8, 8)[::-1].copy()
    put(bg_sheet, dst, a)
for t in range(0x70, 0x80):
    bg_prev_pal[t] = 3
CRY_FLOOR = [0x70, 0x71]
CRY_CEIL = [0x72, 0x73]
CRY_FLOAT = [0x74, 0x75, 0x76, 0x77]
CRY_WALL = [0x78, 0x79, 0x7A, 0x7B]
CRY_STACK_F = [0x7C, 0x7D]
CRY_STACK_C = [0x7E, 0x7F]

ROCK_VARIANTS = [
    ('I_near', 6), ('I_mid', 4), ('I_deep', 6), ('I_vein', 3),
    ('U', 6), ('D', 6), ('L', 3), ('R', 3),
    ('UL', 3), ('UR', 3), ('DL', 3), ('DR', 3),
    ('LR', 3), ('ULR', 3), ('DLR', 3),
]
ROCK_IDS = {}

def bump_profile(rng, maxdip=2):
    """Surface depth per pixel column: 0 at both tile edges (so neighbouring
    tiles join), small dips (rock missing) in between."""
    p = [0] * 8
    for x in range(1, 7):
        p[x] = min(max(p[x - 1] + rng.choice([-1, 0, 0, 1]), 0), maxdip)
    p[6] = min(p[6], 1)
    p[5] = min(p[5], p[6] + 1)
    return np.array(p)

def manhattan_dist(open_mask, iters=12):
    """Per pixel, the 4-connected distance to the nearest open pixel."""
    inf = 99
    d = np.where(open_mask, 0, inf)
    for _ in range(iters):
        p = np.pad(d, 1, constant_values=inf)
        nb = np.minimum.reduce([p[:-2, 1:-1], p[2:, 1:-1],
                                p[1:-1, :-2], p[1:-1, 2:]])
        d = np.minimum(d, nb + 1)
    return d

def rock_mask(case, rng):
    ys, xs = np.mgrid[0:8, 0:8]
    m = np.ones((8, 8), bool)
    if case == 'U':
        m = ys >= bump_profile(rng)[xs]
    elif case == 'D':
        m = (7 - ys) >= bump_profile(rng)[xs]
    elif case == 'L':
        m = xs >= bump_profile(rng)[ys]
    elif case == 'R':
        m = (7 - xs) >= bump_profile(rng)[ys]
    elif case in ('UL', 'UR', 'DL', 'DR'):
        j = np.zeros(8, int)
        for k in range(2, 6):
            j[k] = rng.choice([0, 0, 0, 1, -1])
        if case == 'UL':
            m = xs + ys >= 7 + j[xs]
        elif case == 'UR':
            m = (7 - xs) + ys >= 7 + j[xs]
        elif case == 'DL':
            m = xs + (7 - ys) >= 7 + j[xs]
        else:
            m = (7 - xs) + (7 - ys) >= 7 + j[xs]
    elif case == 'LR':
        for _ in range(rng.randint(1, 2)):
            y = rng.randint(2, 5)
            m[y, 0 if rng.random() < 0.5 else 7] = False
    elif case in ('DLR', 'ULR'):
        cx = 3.5 + rng.choice([-0.5, 0.0, 0.5])
        slope = rng.choice([0.45, 0.5, 0.55])
        hw = np.maximum(4.0 - slope * np.arange(8), 0.5)
        mm = np.abs(xs - cx) <= hw[ys]
        m = mm if case == 'DLR' else mm[::-1]
    return m

def shade_rock(case, mask, rng, texture):
    """Colour a rock mask: 1-px rim (ci3) where the rock meets open space, a
    ci2 band behind it, then dark ci1 rock with specks (ci2) and pores (ci0)."""
    U, D, L, R = ('U' in case), ('D' in case), ('L' in case), ('R' in case)
    rock = np.ones((24, 24), bool)          # 3x3 tile neighbourhood
    if U:
        rock[0:8, 8:16] = False
    if D:
        rock[16:24, 8:16] = False
    if L:
        rock[8:16, 0:8] = False
    if R:
        rock[8:16, 16:24] = False
    if U and L:
        rock[0:8, 0:8] = False
    if U and R:
        rock[0:8, 16:24] = False
    if D and L:
        rock[16:24, 0:8] = False
    if D and R:
        rock[16:24, 16:24] = False
    rock[8:16, 8:16] = mask
    d = manhattan_dist(~rock)[8:16, 8:16]
    rim_p = 0.92 if U else 0.6 if D else 0.8
    speck, pore = {'near': (0.035, 0.015), 'mid': (0.025, 0.02),
                   'deep': (0.012, 0.02)}[texture]
    t = np.zeros((8, 8), np.uint8)
    for y in range(8):
        for x in range(8):
            if not mask[y, x]:
                continue
            k = d[y, x]
            r = rng.random()
            if k == 1:
                v = 3 if r < rim_p else 2
            elif k == 2:
                v = 2
            elif k == 3:
                v = 2 if r < 0.35 else 1
            else:
                v = 0 if r < pore else 2 if r < pore + speck else 1
            t[y, x] = v
    return t

def draw_rock_tile(key, rng):
    if key.startswith('I_'):
        cls = key[2:]
        t = shade_rock('I', np.ones((8, 8), bool), rng,
                       'deep' if cls == 'vein' else cls)
        for _ in range({'near': 2, 'mid': 1, 'deep': 0, 'vein': 0}[cls]):
            x, y = rng.randint(1, 5), rng.randint(1, 5)
            t[y, x] = t[y, x + 1] = 2
            t[y + 1, x] = t[y + 1, x + 1] = 0
        if cls == 'deep' and rng.random() < 0.6:
            x, y = rng.randint(1, 4), rng.randint(1, 4)
            dx = rng.choice([-1, 1])
            for k in range(3):
                xx = min(max(x + k * dx, 0), 7)
                t[y + k, xx] = 0
        if cls == 'vein':
            x, y = rng.randint(1, 3), rng.randint(1, 2)
            for _ in range(7):
                t[y, x] = 3
                if 0 < y < 7 and t[y - 1, x] == 1:
                    t[y - 1, x] = 2
                x += 1
                y += rng.choice([-1, 0, 1])
                x, y = min(x, 6), min(max(y, 1), 6)
        return t
    return shade_rock(key, rock_mask(key, rng), rng, 'near')

next_rock = 0x80
for key, n in ROCK_VARIANTS:
    ids = []
    for v in range(n):
        rng = random.Random(ihash(next_rock, 0xC0FFEE))
        put(bg_sheet, next_rock, draw_rock_tile(key, rng))
        bg_prev_pal[next_rock] = 2 if key == 'I_vein' else 0
        ids.append(next_rock)
        next_rock += 1
    ROCK_IDS[key] = ids

SHAFT = [0, 1, 2, 3, 2, 1, 2, 2, 2, 1, 2, 2, 1, 2, 1, 0]   # 16-px fluted column
assert len(SHAFT) == 16
ARENA_ART = {
    'mas_a': ["22222220", "21111110", "21111110", "00000000",
              "22202222", "11102111", "11102111", "00000000"],
    'mas_b': ["22222220", "21101110", "21111010", "00000000",
              "22202222", "11102111", "11102101", "00000000"],
    'ceil_trim_a': ["22222220", "21111110", "21111110", "00000000",
                    "11111111", "33333333", "22222222", "11111111"],
    'ceil_trim_b': ["22202222", "11102111", "11102111", "00000000",
                    "11111111", "33333333", "22222222", "11111111"],
    'floor_trim_a': ["22222222", "33333333", "11111111", "00000000",
                     "22202222", "11102111", "11102111", "00000000"],
    'floor_trim_b': ["22222222", "33333333", "11111111", "00000000",
                     "22222220", "21111110", "21111110", "00000000"],
}
ARENA_IDS = {}
for name, rows in ARENA_ART.items():
    ARENA_IDS[name] = next_rock
    put(bg_sheet, next_rock, art(rows, 8, 8))
    bg_prev_pal[next_rock] = 2
    next_rock += 1

def pillar_cap(hanging):
    rows = [SHAFT, SHAFT, SHAFT,
            [0] + [1] * 14 + [0],
            [1] * 16,
            [1] + [3] * 14 + [1],
            [1] + [2] * 14 + [1],
            [0] + [1] * 14 + [0]]
    a = np.array(rows, np.uint8)
    return a if hanging else a[::-1].copy()

shaft = np.array([SHAFT] * 8, np.uint8)
for name, img in (('shaft', shaft), ('cap_hang', pillar_cap(True)),
                  ('cap_stand', pillar_cap(False))):
    for half in (0, 1):
        ARENA_IDS[f'{name}_{half}'] = next_rock
        put(bg_sheet, next_rock, img[:, half * 8: half * 8 + 8])
        bg_prev_pal[next_rock] = 2
        next_rock += 1
assert next_rock <= 0x100, hex(next_rock)

def autotile(solid, salt, vein_ok=True):
    """solid: bool [ncols, 32]. Returns (tile ids, palettes) for solid cells.
    Rows outside the playfield count as solid, columns past the edges copy
    the edge column."""
    ncol = solid.shape[0]

    def S(c, r):
        if r < ROW_TOP or r > ROW_BOT:
            return True
        return bool(solid[min(max(c, 0), ncol - 1), r])

    tiles = np.zeros((ncol, 32), int)
    pals = np.zeros((ncol, 32), int)
    for c in range(ncol):
        for r in range(ROW_TOP, ROW_BOT + 1):
            if not solid[c, r]:
                continue
            U, D = not S(c, r - 1), not S(c, r + 1)
            L, R = not S(c - 1, r), not S(c + 1, r)
            key = ('U' if U else '') + ('D' if D else '') + \
                  ('L' if L else '') + ('R' if R else '')
            if key == '':
                dist = 3
                for rad in (1, 2):
                    if any(not S(c + dc, r + dr)
                           for dc in range(-rad, rad + 1)
                           for dr in range(-rad, rad + 1)):
                        dist = rad
                        break
                key = 'I_' + ('near', 'mid', 'deep')[dist - 1]
                if key == 'I_deep' and vein_ok and ihash(c, r, salt, 3) % 100 < 3:
                    key = 'I_vein'
            if key not in ROCK_IDS:
                raise AssertionError(f"impossible rock case {key} at col {c} row {r}")
            ids = ROCK_IDS[key]
            tiles[c, r] = ids[ihash(c, r, salt) % len(ids)]
            pals[c, r] = 2 if key == 'I_vein' else 0
    return tiles, pals

spr_sheet = np.zeros((128, 128), np.uint8)
spr_prev_pal = [4] * 256

SHIP_BODY = [
    "................",
    "................",
    "................",
    "....oo..........",
    "....ohoo........",
    ".....ommoo......",
    ".....oommmooo...",
    "..oooommmhhhmoo.",
    "..ommmmmmmmmmmho",
    "..oooommmmmmmoo.",
    ".....oommmooo...",
    ".....ommoo......",
    "....ohoo........",
    "....oo..........",
    "................",
    "................",
]

def ship_frame(f):
    a = art(SHIP_BODY, 16, 16)
    if f == 0:                      # short flame
        a[8, 0:2] = [2, 3]
    else:                           # long, flickering flame
        a[7, 1] = 2
        a[8, 0:2] = [3, 3]
        a[9, 1] = 2
    return a

DRONE0 = [
    "................",
    "......oooo......",
    "....oommmmoo....",
    "...ommmmmmmmo...",
    "..ommhhmmmmmmo..",
    "..omhmmoooommo..",
    ".ommmmohhhommmo.",
    "oommmohhhhhommoo",
    "oommmohhhhhommoo",
    ".ommmmohhhommmo.",
    "..ommmmoooommo..",
    "..ommmmmmmmmmo..",
    "...ommmmmmmmo...",
    "....oommmmoo....",
    "......oooo......",
    "................",
]
DRONE1 = [
    ".......oo.......",
    "......oooo......",
    "....oommmmoo....",
    "...ommmmmmmmo...",
    "..ommhhmmmmmmo..",
    "..omhmmoooommo..",
    ".ommmmohhhommmo.",
    ".ommmohhoohommo.",
    ".ommmohhoohommo.",
    ".ommmmohhhommmo.",
    "..ommmmoooommo..",
    "..ommmmmmmmmmo..",
    "...ommmmmmmmo...",
    "....oommmmoo....",
    "......oooo......",
    ".......oo.......",
]
DART = [
    "................",
    "................",
    "...........oo...",
    ".........oohmo..",
    ".......oommmo...",
    ".....oommmmo....",
    "...oommmmmmoo...",
    ".ohhmmmmmmmmmoo.",
    "ohmmmmmmmmmmmmo.",
    ".oommmmmmmmmmoo.",
    "...oommmmmmoo...",
    ".....oommmmo....",
    ".......oommmo...",
    ".........oohmo..",
    "...........oo...",
    "................",
]

def dart_frame(f):
    a = art(DART, 16, 16)
    if f == 0:
        a[8, 15] = 3
    else:
        a[7, 15] = 2
        a[8, 15] = 3
        a[9, 15] = 2
    return a

TURRET = [
    "................",
    "................",
    "................",
    "...oo...........",
    "..ohmo..........",
    "...ohmo.........",
    "....ohmo........",
    ".....ohmoo......",
    "....oohmmmoo....",
    "...ommhmmmmmo...",
    "..omhmmmmmmmmo..",
    "..ommmmmmmmmmo..",
    ".oooooooooooooo.",
    ".ommhmmmmmmhmmo.",
    ".ommmmmmmmmmmmo.",
    "oooooooooooooooo",
]

def turret_frame(f):
    a = art(TURRET, 16, 16)
    if f == 1:                      # muzzle flash at the barrel tip
        flash = ["h.h.", ".hh.", "hhhm", "..m."]
        fa = art(flash, 4, 4)
        a[0:4, 0:4] = np.maximum(a[0:4, 0:4], fa)
    return a

def explosion_frame(f):
    rng = random.Random(500 + f)
    a = np.zeros((16, 16), np.uint8)
    ph = 1.3 + f * 0.7
    for y in range(16):
        for x in range(16):
            dx, dy = x - 7.5, y - 7.5
            d = math.hypot(dx, dy)
            ang = math.atan2(dy, dx)
            e = d / (1 + 0.28 * math.sin(5 * ang + ph) + 0.12 * math.sin(9 * ang + 2 * ph))
            n = rng.random()
            if f == 0:
                v = 3 if e < 1.8 else 2 if e < 3.0 else 1 if e < 4.0 else 0
            elif f == 1:
                v = 3 if e < 2.6 else 2 if e < 4.4 else 1 if e < 6.0 else 0
            elif f == 2:
                if e < 2.4:
                    v = 2 if n < 0.6 else 1
                elif e < 5.2:
                    v = 3 if n < 0.25 else 2
                elif e < 7.3:
                    v = 1 if n < 0.85 else 0
                else:
                    v = 0
            else:
                if 3.5 < e < 7.8:
                    v = 1 if n < 0.32 else 2 if n < 0.38 else 0
                elif e < 3.5:
                    v = 1 if n < 0.12 else 0
                else:
                    v = 0
            a[y, x] = v
    return a

def boss_frame(eye_open):
    """32x32 armoured sphere with a big eye on its left (it faces left)."""
    a = np.zeros((32, 32), np.uint8)
    cx, cy, rad = 16.5, 16.0, 12.6
    for y in range(32):
        for x in range(32):
            dx, dy = x + 0.5 - cx, y + 0.5 - cy
            d = math.hypot(dx, dy)
            if d > rad:
                continue
            lit = (-dx - dy) / (rad * 1.414)
            if d > rad - 1.0:
                v = 1
            elif lit > 0.5 and d > rad - 3.2:
                v = 3
            elif lit < -0.4:
                v = 1 if (x + y) % 2 == 0 else 2
            else:
                v = 2
            if d < rad - 1.0 and (abs(dy + 6.5) < 0.5 or abs(dy - 6.5) < 0.5) and dx > -5:
                v = 1
            if d < rad - 1.0 and abs(dx - 5.0) < 0.5 and abs(dy) < 6.5:
                v = 1
            a[y, x] = v
    for vy in (11, 15, 19):
        a[vy, 22:27] = 1
        a[vy + 1, 22:27] = 3 if eye_open else 2
    for k in range(3):
        a[2 + k, 16 - k // 2: 17 + (k + 1) // 2] = 1 if k == 0 else 2
        a[29 - k, 16 - k // 2: 17 + (k + 1) // 2] = 1 if k == 0 else 2
    for fy0 in (8, 21):
        for k in range(3):
            a[fy0 + k, 26:31 - (k % 2)] = [1, 2, 1][k]
            a[fy0 + k, 31 - (k % 2)] = 1
    ex, ey = 10.0, 16.0
    for y in range(32):
        for x in range(32):
            r = math.hypot(x + 0.5 - ex, y + 0.5 - ey)
            if r > 5.6:
                continue
            if r > 4.6:
                v = 1
            elif eye_open:
                v = 1 if r < 1.7 else 2 if r > 3.6 else 3
                if eye_open and x == 8 and y == 14:
                    v = 3
            else:
                v = 3 if abs(y + 0.5 - ey) < 0.6 and r < 3.8 else \
                    1 if abs(y + 0.5 - ey) < 1.4 else 2
            a[y, x] = v
    return a

BOLT = [
    ["........", "........", "........", ".oommhh.",
     "oommmhhh", ".oommhh.", "........", "........"],
    ["........", "........", "........", "..oomhh.",
     ".ommmhhh", "..oomhh.", "........", "........"],
]
ORB = [
    ["........", "..oooo..", ".ommmmo.", ".omhhmo.",
     ".omhhmo.", ".ommmmo.", "..oooo..", "........"],
    ["........", "...oo...", "..omho..", ".omhhmo.",
     ".ohhhmo.", "..ommo..", "...oo...", "........"],
]

for f in (0, 1):
    put(spr_sheet, 0x00 + 2 * f, ship_frame(f))
put(spr_sheet, 0x04, art(DRONE0, 16, 16))
put(spr_sheet, 0x06, art(DRONE1, 16, 16))
for f in (0, 1):
    put(spr_sheet, 0x08 + 2 * f, dart_frame(f))
    put(spr_sheet, 0x0C + 2 * f, turret_frame(f))
for f in range(4):
    put(spr_sheet, 0x20 + 2 * f, explosion_frame(f))
put(spr_sheet, 0x40, boss_frame(False))      # 32x32 at 0x40,0x42,0x60,0x62
put(spr_sheet, 0x44, boss_frame(True))       # 32x32 at 0x44,0x46,0x64,0x66
for f in (0, 1):
    put(spr_sheet, 0x80 + f, art(BOLT[f], 8, 8))
    put(spr_sheet, 0x82 + f, art(ORB[f], 8, 8))

for t in range(256):
    r, c = t // 16, t % 16
    if r in (0, 1):
        spr_prev_pal[t] = 4 if c < 4 else 5
    elif r in (2, 3, 8):
        spr_prev_pal[t] = 6
    elif 4 <= r <= 7:
        spr_prev_pal[t] = 7

def value_noise(n, period, rng):
    knots = [rng.uniform(-1.0, 1.0) for _ in range(n // period + 3)]
    out = np.zeros(n)
    for i in range(n):
        k, f = divmod(i, period)
        t = f / period
        t = t * t * (3 - 2 * t)
        out[i] = knots[k] * (1 - t) + knots[k + 1] * t
    return out

def difficulty(c):
    """0 in the open start, ramps to 1 near the end of the cave."""
    return min(max((c - 28) / (425 - 28), 0.0), 1.0)

def window_run(Ce, Fe, c):
    """Free rows shared by columns c..c+2 (each column is one interval)."""
    top = max(Ce[c:c + 3]) + 1
    bot = min(Fe[c:c + 3]) - 1
    return bot - top + 1

def widen_until_smooth(Ce, Fe, fixed):
    """Make neighbouring ceiling/floor heights differ by at most one row, only
    ever widening the cave (so it always converges)."""
    changed = True
    while changed:
        changed = False
        for c in range(1, N_COLS):
            for H, sgn in ((Ce, 1), (Fe, -1)):
                a, b = H[c - 1], H[c]
                if sgn * (b - a) > 1 and c not in fixed:       # step into the cave
                    H[c] = a + sgn
                    changed = True
                elif sgn * (a - b) > 1 and (c - 1) not in fixed:
                    H[c - 1] = b + sgn
                    changed = True

WALLS = [(98, 1), (150, 1), (200, 2), (248, 1), (296, 2), (342, 1), (386, 2), (426, 2)]
WALL_COLS = sorted({c0 + i for c0, th in WALLS for i in range(th)})

def near_wall(c, margin):
    return any(abs(c - w) <= margin for w in WALL_COLS)

def build_level():
    rng = random.Random(0xCA7E)
    n_cen = 0.75 * value_noise(N_COLS, 27, rng) + 0.25 * value_noise(N_COLS, 10, rng)
    n_gap = value_noise(N_COLS, 19, rng)
    n_c = value_noise(N_COLS, 6, rng)
    n_f = value_noise(N_COLS, 5, rng)

    Ce = np.zeros(N_COLS, int)    # bottom-most ceiling rock row
    Fe = np.zeros(N_COLS, int)    # topmost floor rock row
    for c in range(N_COLS):
        d = difficulty(c)
        gap = max(24 - 14.0 * d ** 0.7 + 1.5 * d * n_gap[c], 9.0)  # free rows
        half = (gap + 1) / 2
        lo, hi = 3 + half, 28 - half
        m = (lo + hi) / 2 + (hi - lo) / 2 * n_cen[c] * min(1.0, 0.2 + 1.4 * d)
        jit = 0.4 + 1.1 * d
        Ce[c] = round(m - half + jit * n_c[c])
        Fe[c] = round(m + half + jit * n_f[c])
        if c >= 436:
            t = min((c - 436) / 18.0, 1.0)
            Ce[c] = round(Ce[c] * (1 - t) + 3 * t)
            Fe[c] = round(Fe[c] * (1 - t) + 28 * t)
    Ce = np.clip(Ce, 3, 24)
    Fe = np.clip(Fe, 7, 28)
    fixed = set(range(454, N_COLS))
    for c in fixed:
        Ce[c], Fe[c] = 3, 28
    for c in range(0, 31):
        Ce[c] = 3 + (1 if n_c[c] > 0.55 else 0)
        Fe[c] = 28 - (1 if n_f[c] > 0.55 else 0)

    for _ in range(200):
        widen_until_smooth(Ce, Fe, fixed)
        bad = False
        for c in range(N_COLS - 2):
            if window_run(Ce, Fe, c) < 7:
                bad = True
                cc = c + int(np.argmax(Ce[c:c + 3]))
                cf = c + int(np.argmin(Fe[c:c + 3]))
                if Ce[cc] > 3 and (Ce[cc] - 3) >= (28 - Fe[cf]):
                    Ce[cc] -= 1
                else:
                    Fe[cf] += 1
        if not bad:
            break

    for kind in ('tite', 'mite'):
        c = 36 if kind == 'tite' else 41
        while c < 448:
            d = difficulty(c)
            if not near_wall(c, 3):
                maxlen = 1 + int(round(3 * d))
                L = rng.randint(1, maxlen)
                w = rng.choice([1, 1, 2, 2, 2])
                shape = [L] if w == 1 else rng.choice([[L, L], [L, max(L - 1, 1)],
                                                       [max(L - 1, 1), L]])
                H = Ce if kind == 'tite' else Fe
                sgn = 1 if kind == 'tite' else -1
                while L > 0:
                    old = H.copy()
                    for i, ln in enumerate(shape):
                        H[c + i] = H[c + i] + sgn * min(ln, L)
                    ok = all(window_run(Ce, Fe, k) >= (5 if d < 0.8 else 4)
                             for k in range(max(c - 2, 0), min(c + len(shape) + 1, N_COLS - 2)))
                    if ok:
                        break
                    H[:] = old
                    L -= 1
            c += rng.randint(int(14 - 8 * d), int(20 - 9 * d))

    for g in GATE_PILLARS:
        for c in (g, g + 1):
            Ce[c], Fe[c] = 8, 23

    solid = np.zeros((N_COLS, 32), bool)
    for c in range(N_COLS):
        solid[c, ROW_TOP:Ce[c] + 1] = True
        solid[c, Fe[c]:ROW_BOT + 1] = True

    tiles, pals = autotile(solid, salt=1)

    for c in range(MASONRY_COL, N_COLS):
        alt = '_a' if (c // 2) % 2 == 0 else '_b'
        tiles[c, 2] = ARENA_IDS['mas_a' if c % 3 else 'mas_b']
        tiles[c, 3] = ARENA_IDS['ceil_trim' + alt]
        tiles[c, 28] = ARENA_IDS['floor_trim' + alt]
        tiles[c, 29] = ARENA_IDS['mas_b' if c % 5 == 0 else 'mas_a']
        pals[c, [2, 3, 28, 29]] = 2
    for g in GATE_PILLARS:
        for half in (0, 1):
            c = g + half
            for r in range(4, 8):
                tiles[c, r] = ARENA_IDS[f'shaft_{half}']
            tiles[c, 8] = ARENA_IDS[f'cap_hang_{half}']
            tiles[c, 23] = ARENA_IDS[f'cap_stand_{half}']
            for r in range(24, 28):
                tiles[c, r] = ARENA_IDS[f'shaft_{half}']
            pals[c, 4:9] = 2
            pals[c, 23:28] = 2

    crys = {}       # (col, row) -> tile

    def free_rows(c):
        return list(range(Ce[c] + 1, Fe[c]))

    def pick(lst, c, r):
        return lst[ihash(c, r, 11) % len(lst)]

    def floor_stack(c, k):
        for i in range(k):
            r = Fe[c] - 1 - i
            crys[(c, r)] = pick(CRY_FLOOR, c, r) if i == 0 else \
                pick(CRY_STACK_F, c, r)

    def ceil_stack(c, k):
        for i in range(k):
            r = Ce[c] + 1 + i
            crys[(c, r)] = pick(CRY_CEIL, c, r) if i == 0 else \
                pick(CRY_STACK_C, c, r)

    def floater(c, r, shape):
        for dc, dr in shape:
            if Ce[c + dc] < r + dr < Fe[c + dc]:
                crys[(c + dc, r + dr)] = pick(CRY_FLOAT, c + dc, r + dr)

    floor_stack(42, 1)
    floor_stack(43, 2)
    ceil_stack(52, 2)
    floater(60, (Ce[60] + Fe[60]) // 2, [(0, 0), (1, 0), (0, 1)])
    for c, frac, side in ((68, 0.45, 'f'), (69, 0.35, 'f'), (77, 0.5, 'c'),
                          (86, 0.65, 'f'), (87, 0.55, 'f')):
        k = max(1, int(len(free_rows(c)) * frac))
        (floor_stack if side == 'f' else ceil_stack)(c, k)
    for c in WALL_COLS:
        for r in free_rows(c):
            crys[(c, r)] = pick(CRY_WALL, c, r)
    c = 104
    while c < 446:
        if not near_wall(c, 3) and all(Ce[c + i] < Fe[c + i] - 5 for i in range(3)):
            kind = rng.choice(['floor', 'ceil', 'float', 'floor_big', 'ceil_big', 'pair'])
            n = len(free_rows(c))
            if kind == 'floor':
                floor_stack(c, rng.randint(1, 2))
                if Fe[c + 1] == Fe[c]:
                    floor_stack(c + 1, 1)
            elif kind == 'ceil':
                ceil_stack(c, rng.randint(1, 2))
                if Ce[c + 1] == Ce[c]:
                    ceil_stack(c + 1, 1)
            elif kind == 'float':
                r = rng.randint(Ce[c] + 2, Fe[c] - 3)
                floater(c, r, rng.choice([[(0, 0), (1, 0)], [(0, 0), (0, 1)],
                                          [(0, 0), (1, 0), (1, 1)], [(0, 0), (1, 1)]]))
            elif kind == 'floor_big':
                floor_stack(c, max(1, int(n * rng.uniform(0.4, 0.7))))
            elif kind == 'ceil_big':
                ceil_stack(c, max(1, int(n * rng.uniform(0.4, 0.7))))
            else:
                floor_stack(c, max(1, int(n * 0.35)))
                ceil_stack(c, max(1, int(n * 0.35)))
        c += rng.randint(int(15 - 7 * difficulty(c)), int(22 - 8 * difficulty(c)))

    for (c, r), t in crys.items():
        assert not solid[c, r] and tiles[c, r] == 0
        tiles[c, r] = t
        pals[c, r] = 3
    return tiles, pals, Ce, Fe

def place_decor(tiles, pals, occupied):
    """Sprinkle non-solid decoration into open cells (after the spawn table,
    so turret cells stay clear)."""
    for c in range(N_COLS):
        for r in range(ROW_TOP, ROW_BOT + 1):
            if tiles[c, r] != 0 or (c, r) in occupied:
                continue
            h = ihash(c, r, 77) % 1000
            above = tiles[c, r - 1] if r > ROW_TOP else 0x80
            below = tiles[c, r + 1] if r < ROW_BOT else 0x80
            if c >= ARENA_COL - 11:
                if h < 8:
                    tiles[c, r], pals[c, r] = 0x06, 2
                continue
            if above >= 0x80 and h < 110:
                t = 0x0B + (h % 2)
            elif below >= 0x80 and h < 90 and c > 20:
                t = 0x0D + (h % 2)
            elif h < 28:
                t = 0x01 + (h % 4)
            elif h < 40:
                t = 0x07 + (h % 4)
            elif h < 46:
                t = 0x05 + (h % 2)
            elif h < 48 and below == 0:
                t = 0x0F
            else:
                continue
            tiles[c, r] = t
            pals[c, r] = DECOR_PAL[t]

DRONE, DART, FTUR, CTUR = 0, 1, 2, 3
ON_SCREEN = {DRONE: 28, DART: 12, FTUR: 42, CTUR: 42}
MAX_ON_SCREEN = 6
MAX_PER_LINE = 3

def band(e):
    t, typ, y = e
    if typ == DRONE:
        return y - 16, y + 32
    if typ == DART:
        return y - 8, y + 24
    return y, y + 16

def concurrency(entries):
    """(max enemies on screen at once, max enemies sharing one scanline)."""
    max_on, max_line = 0, 0
    for p in range(0, 480):
        act = [e for e in entries if e[0] - 40 <= p < e[0] - 40 + ON_SCREEN[e[1]]]
        max_on = max(max_on, len(act))
        for y in range(16, 240, 2):
            n = sum(1 for e in act if band(e)[0] <= y < band(e)[1])
            max_line = max(max_line, n)
    return max_on, max_line

def solid_top_run(tiles, c):
    """Bottom-most row of the solid run hanging from the top (ceiling)."""
    r = ROW_TOP
    while r <= ROW_BOT and tiles[c, r] >= 0x70:
        r += 1
    return r - 1

def solid_bottom_run(tiles, c):
    """Topmost row of the solid run standing on the bottom (floor)."""
    r = ROW_BOT
    while r >= ROW_TOP and tiles[c, r] >= 0x70:
        r -= 1
    return r + 1

def is_rock(t):
    return t >= 0x80

def turret_site(tiles, t, ceiling):
    """y for a turret at trigger t, or None if the spot is not valid."""
    if t + 2 >= MASONRY_COL - 2 or near_wall(t, 3):
        return None
    if ceiling:
        C0, C1 = solid_top_run(tiles, t), solid_top_run(tiles, t + 1)
        if C0 != C1 or C0 < ROW_TOP or not is_rock(tiles[t, C0]):
            return None
        surf = C0
        rows, y = (C0 + 1, C0 + 2), 8 * (C0 + 1)
        F0 = solid_bottom_run(tiles, t)
        gap = min(F0, solid_bottom_run(tiles, t + 1)) - C0 - 1
    else:
        R0, R1 = solid_bottom_run(tiles, t), solid_bottom_run(tiles, t + 1)
        if R0 != R1 or R0 > ROW_BOT or not is_rock(tiles[t, R0]):
            return None
        surf = R0
        rows, y = (R0 - 2, R0 - 1), 8 * R0 - 16
        C0 = max(solid_top_run(tiles, t), solid_top_run(tiles, t + 1))
        gap = R0 - C0 - 1
    if gap < 7:
        return None
    if not (is_rock(tiles[t - 1, surf]) and is_rock(tiles[t + 2, surf])):
        return None
    near = range(rows[0] - 1, rows[1] + 2)     # the turret's cells +- 1 row
    for c in range(t - 1, t + 3):
        for r in rows:
            if tiles[c, r] != 0:
                return None
        for r in near:
            if ROW_TOP <= r <= ROW_BOT and 0x70 <= tiles[c, r] < 0x80:
                return None
    if not (24 <= y <= 208):
        return None
    return y

def box_free(tiles, cols, y0, y1):
    """True if screen lines y0..y1-1 hold no rock in the given columns."""
    r0, r1 = max(y0 // 8, ROW_TOP), min((y1 - 1) // 8, ROW_BOT)
    if y0 < 16 or y1 > 240:
        return False
    for c in cols:
        if not (0 <= c < N_COLS):
            continue
        for r in range(r0, r1 + 1):
            if is_rock(tiles[c, r]):
                return False
    return True

def flyer_ys(tiles, t, typ, rng, prefer=None):
    """Candidate spawn heights for a flyer at trigger t, best first."""
    if typ == DRONE:
        cands = [y for y in range(32, 209, 4)
                 if box_free(tiles, range(t - 10, t + 2), y - 16, y + 32)]
        if not cands:
            cands = [y for y in range(32, 209, 4)
                     if box_free(tiles, range(t - 2, t + 2), y - 8, y + 24)]
    else:
        cands = [y for y in range(24, 209, 4)
                 if box_free(tiles, range(t - 3, t + 2), y, y + 16)]
    rng.shuffle(cands)
    if prefer is not None:
        cands.sort(key=lambda y: abs(y - prefer))
    return cands

def gen_spawns(tiles):
    """Two passes: turrets first, on chosen flat ledges about every 19
    columns (alternating floor / ceiling), then flyers fill the gaps on a
    schedule that gets denser with depth. Every enemy must pass the on-screen
    and per-scanline limits given everything placed so far."""
    rng = random.Random(0x5EED)
    entries = []

    def fits(e):
        trial = entries + [e]
        lo, hi = e[0] - 40, e[0] - 40 + ON_SCREEN[e[1]]
        b0, b1 = band(e)
        for p in range(lo, hi):
            act = [x for x in trial if x[0] - 40 <= p < x[0] - 40 + ON_SCREEN[x[1]]]
            if len(act) > MAX_ON_SCREEN:
                return False
            for y in range(max(b0, 16), min(b1, 240), 2):
                if sum(1 for x in act if band(x)[0] <= y < band(x)[1]) > MAX_PER_LINE:
                    return False
        return True

    def add(e):
        if not (45 <= e[0] <= LAST_TRIGGER) or any(x[0] == e[0] for x in entries):
            return False
        if not fits(e):
            return False
        entries.append(e)
        entries.sort()
        return True

    turret_cols = []
    target, want_ceiling = 112, False
    while target < MASONRY_COL - 10:
        kinds = [CTUR, FTUR] if (want_ceiling and target >= 150) else [FTUR, CTUR]
        if target < 150:
            kinds = [FTUR]
        done = False
        for typ in kinds:
            for off in sorted(range(-8, 9), key=abs):
                tt = target + off
                if any(abs(tt - tc) < 8 for tc in turret_cols):
                    continue
                y = turret_site(tiles, tt, typ == CTUR)
                if y is not None and add((tt, typ, y)):
                    turret_cols.append(tt)
                    done = True
                    break
            if done:
                break
        want_ceiling = not want_ceiling
        target += 19 + rng.randint(-3, 3)

    t = 45
    while t <= LAST_TRIGGER:
        d = difficulty(t)
        p_dart = 0.0 if t < 105 else 0.3 + 0.25 * d
        typ = DART if rng.random() < p_dart else DRONE
        placed = False
        if typ == DRONE and t >= 80 and rng.random() < 0.12 + 0.2 * d:
            bases = flyer_ys(tiles, t, DRONE, rng)
            if bases:
                last = t
                for k in range(3):
                    tt = t + 3 * k
                    for y in flyer_ys(tiles, tt, DRONE, rng,
                                      prefer=bases[0] + (24 if k % 2 else -24))[:4]:
                        if add((tt, DRONE, y)):
                            placed = True
                            last = tt
                            break
                t = last
        if not placed:
            for typ2 in ([typ, DART] if typ == DRONE else [DART, DRONE]):
                for y in flyer_ys(tiles, t, typ2, rng):
                    if add((t, typ2, y)):
                        placed = True
                        break
                if placed:
                    break
        t += max(2, int(round(12.0 - 8.0 * d + rng.uniform(-1.5, 1.5))))
    return entries

BLOCK_FONT = {
    'C': ["r###", "#...", "#...", "#...", "R###"],
    'A': ["r##l", "#..#", "####", "#..#", "#..#"],
    'V': ["#..#", "#..#", "#lr#", "R##L", ".RL."],
    'E': ["####", "#...", "###.", "#...", "####"],
    'P': ["###l", "#..#", "###L", "#...", "#..."],
    'T': ["#####", "..#..", "..#..", "..#..", "..#.."],
    'R': ["###l", "#..#", "###L", "#.#l", "#.R#"],
    'O': ["r##l", "#..#", "#..#", "#..#", "R##L"],
    'L': ["#...", "#...", "#...", "#...", "####"],
    'G': ["r###", "#...", "#.##", "#..#", "R##L"],
    'M': ["#l.r#", "#####", "#R#L#", "#...#", "#...#"],
    'D': ["###l", "#..#", "#..#", "#..#", "###L"],
    '!': ["#", "#", "#", ".", "#"],
    ' ': ["..", "..", "..", "..", ".."],
}

def block_word_width(word, gap=1):
    return sum(len(BLOCK_FONT[ch][0]) for ch in word) + gap * (len(word) - 1)

def put_block_word(scr, word, row, pal, gap=1):
    x = (40 - block_word_width(word, gap)) // 2
    for ch in word:
        g = BLOCK_FONT[ch]
        for dy, line in enumerate(g):
            for dx, k in enumerate(line):
                if k == '.':
                    continue
                t = LOGO_TILE[k]
                if k == '#' and ihash(x + dx, row + dy, 99) % 6 == 0:
                    t = 0x65
                assert scr[row + dy, x + dx] == 0, (word, row + dy, x + dx)
                scr[row + dy, x + dx] = (pal << 8) | t
        x += len(g[0]) + gap

def put_text(scr, row, text, col=None, pad=True):
    if pad:
        text = " " + text + " "
    if col is None:
        col = (40 - len(text)) // 2
    for i, ch in enumerate(text):
        assert 0x20 <= ord(ch) < 0x60, ch
        scr[row, col + i] = 0x100 | ord(ch)

def panel(scr, r0, c0, r1, c1):
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            er, ec = r in (r0, r1), c in (c0, c1)
            t = 0x6C if er and ec else 0x6A if er else 0x6B if ec else 0x20
            scr[r, c] = 0x100 | t

def screen_cave(scr, seed, tites, mites, crystals):
    """Draw a strip of cave ceiling/floor on a 40-column screen.
    tites/mites: {col: length}; crystals: list of floor columns."""
    rng = random.Random(seed)
    nc = value_noise(40, 5, rng)
    nf = value_noise(40, 6, rng)
    Ce = [3 if nc[c] > -0.2 else 2 for c in range(40)]
    Fe = [28 if nf[c] > -0.2 else 29 for c in range(40)]
    for c, ln in tites.items():
        Ce[c] += ln
    for c, ln in mites.items():
        Fe[c] -= ln
    solid = np.zeros((40, 32), bool)
    for c in range(40):
        solid[c, ROW_TOP:Ce[c] + 1] = True
        solid[c, Fe[c]:ROW_BOT + 1] = True
    tiles, pals = autotile(solid, salt=seed)
    for c in range(40):
        for r in range(ROW_TOP, ROW_BOT + 1):
            if solid[c, r]:
                scr[r, c] = (pals[c, r] << 8) | tiles[c, r]
    for c in crystals:
        r = Fe[c] - 1
        scr[r, c] = 0x300 | CRY_FLOOR[c % 2]
        if c % 3 == 0:
            scr[r - 1, c] = 0x300 | CRY_FLOAT[c % 4]

def build_screens():
    scr = np.zeros((4, 32, 64), int)

    s = scr[0]
    screen_cave(s, 10, {1: 1, 4: 2, 5: 1, 33: 1, 34: 2, 37: 1},
                {2: 1, 4: 2, 35: 1, 36: 2}, [0, 3, 38])
    put_block_word(s, "CAVE", 5, 3)
    put_block_word(s, "PATROL", 11, 3)
    put_text(s, 18, "PRESS START")
    panel(s, 20, 7, 26, 32)
    put_text(s, 21, "ARROWS: MOVE   A: FIRE", pad=False)
    put_text(s, 23, "SHOOT THE CRYSTALS", pad=False)
    put_text(s, 25, "DESTROY THE CORE", pad=False)

    s = scr[1]
    screen_cave(s, 20, {3: 2, 4: 3, 5: 1, 15: 1, 26: 2, 27: 1, 36: 3, 37: 2},
                {1: 2, 2: 1, 12: 1, 30: 2, 31: 1}, [8, 20, 34])
    put_block_word(s, "GAME", 7, 0)
    put_block_word(s, "OVER", 13, 0)
    put_text(s, 20, "GAME OVER")
    put_text(s, 23, "PRESS START")

    s = scr[2]
    screen_cave(s, 30, {2: 1, 9: 2, 10: 1, 30: 1, 31: 2},
                {5: 1, 6: 2, 33: 1, 34: 2}, [1, 3, 12, 15, 24, 27, 36, 38])
    put_block_word(s, "CAVE", 5, 3)
    put_block_word(s, "CLEARED!", 11, 3)
    panel(s, 18, 8, 21, 31)
    put_text(s, 19, "CAVE CLEARED!", pad=False)
    put_text(s, 20, "THE CORE IS DESTROYED", pad=False)
    put_text(s, 24, "PRESS START")

    s = scr[3]
    row0 = "  SCORE 000000    HI 000000    SHIPS 3  "
    assert len(row0) == 40
    for i, ch in enumerate(row0):
        s[0, i] = 0x100 | ord(ch)
    row1 = [ord(ch) for ch in "  DEPTH "] + [0x60] * 16 + \
           [ord(ch) for ch in "  BOSS "] + [0x62] * 8 + [ord(' ')]
    assert len(row1) == 40
    for i, t in enumerate(row1):
        s[1, i] = 0x100 | t
    s[0:2, 40:64] = 0x120
    return scr

def write_mem(path, words, digits):
    with open(path, "w") as f:
        for w in words:
            assert 0 <= w < (1 << (4 * digits)), (path, w)
            f.write(f"{w:0{digits}X}\n")

def read_mem(path, n, digits):
    lines = Path(path).read_text().split("\n")
    assert lines[-1] == "" and len(lines) == n + 1, (path, len(lines))
    assert all(len(l) == digits for l in lines[:-1]), path
    return [int(l, 16) for l in lines[:-1]]

def encode_chr(sheet):
    words = []
    for t in range(256):
        tile = sheet_tile(sheet, t)
        for y in range(8):
            w = 0
            for p in range(8):
                w |= int(tile[y, p]) << (14 - 2 * p)
            words.append(w)
    return words

def decode_chr(words):
    tiles = np.zeros((256, 8, 8), np.uint8)
    for t in range(256):
        for y in range(8):
            w = words[t * 8 + y]
            for p in range(8):
                tiles[t, y, p] = (w >> (14 - 2 * p)) & 3
    return tiles

def render_map(entries, chr_tiles, lut):
    """entries [rows, cols] of (pal << 8) | tile -> RGB image."""
    rows, cols = entries.shape
    img = np.zeros((rows * 8, cols * 8, 3), np.uint8)
    for r in range(rows):
        for c in range(cols):
            e = int(entries[r, c])
            ci = chr_tiles[e & 0xFF]
            idx = np.where(ci == 0, 0, ((e >> 8) & 3) * 4 + ci)
            img[r * 8:r * 8 + 8, c * 8:c * 8 + 8] = lut[idx]
    return img

def sprite_img(spr_tiles, tile, big, pal):
    """16x16 (big) or 8x8 sprite -> (colour-index image, palette)."""
    if not big:
        return spr_tiles[tile].copy()
    a = np.zeros((16, 16), np.uint8)
    a[0:8, 0:8] = spr_tiles[tile]
    a[0:8, 8:16] = spr_tiles[tile + 1]
    a[8:16, 0:8] = spr_tiles[tile + 16]
    a[8:16, 8:16] = spr_tiles[tile + 17]
    return a

def blit(img, ci, x, y, pal, lut):
    h, w = ci.shape
    for yy in range(h):
        for xx in range(w):
            v = ci[yy, xx]
            X, Y = x + xx, y + yy
            if v and 0 <= X < img.shape[1] and 0 <= Y < img.shape[0]:
                img[Y, X] = lut[16 + (pal - 4) * 4 + v]

def sheet_png(chr_tiles, pals, lut, path, sprite):
    s, g = 4, 2
    cell = 8 * s + g
    img = np.full((16 * cell + g, 16 * cell + g, 3), 40, np.uint8)
    for t in range(256):
        ci = chr_tiles[t]
        p = pals[t]
        if sprite:
            idx = np.where(ci == 0, 0, 16 + (p - 4) * 4 + ci)
        else:
            idx = np.where(ci == 0, 0, p * 4 + ci)
        tile = lut[idx].repeat(s, 0).repeat(s, 1)
        y0, x0 = g + (t // 16) * cell, g + (t % 16) * cell
        img[y0:y0 + 8 * s, x0:x0 + 8 * s] = tile
    Image.fromarray(img).save(path)

def make_previews(bg_tiles, sp_tiles, lut, level_e, spawns, screens):
    IMG_DIR.mkdir(exist_ok=True)
    sheet_png(bg_tiles, bg_prev_pal, lut, IMG_DIR / "chr_bg.png", False)
    sheet_png(sp_tiles, spr_prev_pal, lut, IMG_DIR / "chr_spr.png", True)

    play = np.array([[level_e[c * 32 + r] for c in range(N_COLS)]
                     for r in range(ROW_TOP, ROW_BOT + 1)])
    lv = render_map(play, bg_tiles, lut)            # 224 x 4096
    for trig, typ, y in spawns:
        if typ == DRONE:
            ci = sprite_img(sp_tiles, 0x04, True, 5)
        elif typ == DART:
            ci = sprite_img(sp_tiles, 0x08, True, 5)
        else:
            ci = sprite_img(sp_tiles, 0x0C, True, 5)
            if typ == CTUR:
                ci = ci[::-1]
        blit(lv, ci, trig * 8, y - 16, 5, lut)
    blit(lv, sprite_img(sp_tiles, 0x00, True, 4), 24, 120 - 16, 4, lut)
    strip_w, label_h = 1024, 14
    out = np.full((4 * (224 + label_h), strip_w, 3), 24, np.uint8)
    im = Image.fromarray(out)
    dr = ImageDraw.Draw(im)
    for k in range(4):
        y0 = k * (224 + label_h)
        im.paste(Image.fromarray(lv[:, k * strip_w:(k + 1) * strip_w]), (0, y0 + label_h))
        for c in range(0, 128, 16):
            col = k * 128 + c
            dr.line([(c * 8, y0 + label_h - 4), (c * 8, y0 + label_h - 1)], fill=(150, 150, 150))
            dr.text((c * 8 + 2, y0 + 1), f"col {col}", fill=(170, 170, 170))
    im.save(IMG_DIR / "level.png")

    def full_screen(sidx):
        m = np.zeros((30, 40), int)
        for r in range(30):
            for c in range(40):
                src = 3 if r < 2 else sidx
                m[r, c] = screens[src * 2048 + r * 64 + c]
        return m

    panels = [render_map(full_screen(i), bg_tiles, lut) for i in range(3)]
    m = full_screen(0)
    for r in range(ROW_TOP, 30):
        for c in range(40):
            m[r, c] = level_e[c * 32 + r]
    game = render_map(m, bg_tiles, lut)
    blit(game, sprite_img(sp_tiles, 0x00, True, 4), 24, 120, 4, lut)
    blit(game, sp_tiles[0x80], 52, 124, 6, lut)
    blit(game, sp_tiles[0x80], 84, 124, 6, lut)
    panels.append(game)
    s, g = 2, 8
    W, H = 320 * s, 240 * s
    out = np.full((2 * H + 3 * g, 2 * W + 3 * g, 3), 60, np.uint8)
    for i, p in enumerate(panels):
        y0, x0 = g + (i // 2) * (H + g), g + (i % 2) * (W + g)
        out[y0:y0 + H, x0:x0 + W] = p.repeat(s, 0).repeat(s, 1)
    Image.fromarray(out).save(IMG_DIR / "screens.png")

    items = [("ship f0", 0x00, True, 4), ("ship f1", 0x02, True, 4),
             ("drone f0", 0x04, True, 5), ("drone f1", 0x06, True, 5),
             ("dart f0", 0x08, True, 5), ("dart f1", 0x0A, True, 5),
             ("turret f0", 0x0C, True, 5), ("turret f1", 0x0E, True, 5),
             ("expl f0", 0x20, True, 6), ("expl f1", 0x22, True, 6),
             ("expl f2", 0x24, True, 6), ("expl f3", 0x26, True, 6),
             ("bolt f0", 0x80, False, 6), ("bolt f1", 0x81, False, 6),
             ("orb f0", 0x82, False, 6), ("orb f1", 0x83, False, 6)]
    s = 6
    cw, chh = 16 * s + 16, 16 * s + 28
    W = 8 * cw + 8
    boss_h = 32 * s + 28
    out = Image.new("RGB", (W, 2 * chh + boss_h + 16), (20, 20, 28))
    dr = ImageDraw.Draw(out)
    for i, (name, t, big, pal) in enumerate(items):
        ci = sprite_img(sp_tiles, t, big, pal)
        tile = np.zeros(ci.shape + (3,), np.uint8)
        tile[:] = (20, 20, 28)
        blit(tile, ci, 0, 0, pal, lut)
        x0, y0 = 8 + (i % 8) * cw, 8 + (i // 8) * chh
        sz = ci.shape[0] * s
        out.paste(Image.fromarray(tile.repeat(s, 0).repeat(s, 1)), (x0, y0 + 14))
        dr.rectangle([x0 - 1, y0 + 13, x0 + 16 * s, y0 + 14 + 16 * s], outline=(60, 60, 70))
        dr.text((x0, y0), f"{name} ${t:02X}", fill=(200, 200, 200))
    for f, (t0, label) in enumerate(((0x40, "boss f0 $40/$42/$60/$62"),
                                     (0x44, "boss f1 $44/$46/$64/$66"))):
        ci = np.zeros((32, 32), np.uint8)
        for qy in (0, 1):
            for qx in (0, 1):
                ci[qy * 16:qy * 16 + 16, qx * 16:qx * 16 + 16] = \
                    sprite_img(sp_tiles, t0 + qy * 0x20 + qx * 2, True, 7)
        tile = np.zeros((32, 32, 3), np.uint8)
        tile[:] = (20, 20, 28)
        blit(tile, ci, 0, 0, 7, lut)
        x0, y0 = 8 + f * (32 * s + 24), 8 + 2 * chh
        out.paste(Image.fromarray(tile.repeat(s, 0).repeat(s, 1)), (x0, y0 + 14))
        dr.text((x0, y0), label, fill=(200, 200, 200))
    x0, y0 = 8 + 2 * (32 * s + 24), 8 + 2 * chh
    dr.text((x0, y0), "crystals, 3 colour-cycle phases", fill=(200, 200, 200))
    for ph in range(3):
        p6 = list(PALETTE)
        trio = PALETTE[13:16]
        p6[13:16] = trio[ph:] + trio[:ph]
        lut2 = lut_rgb(p6)
        crow = np.zeros((8, 8 * 8), int)
        sample = [0x70, 0x71, 0x74, 0x75, 0x78, 0x79, 0x7A, 0x7C]
        img = np.zeros((16, 8 * 8 + 16, 3), np.uint8)
        img[:] = lut2[0]
        for k, t in enumerate(sample):
            ci = bg_tiles[t]
            idx = np.where(ci == 0, 0, 12 + ci)
            img[4:12, k * 8 + 8:k * 8 + 16] = lut2[idx]
        rk = bg_tiles[ROCK_IDS['U'][0]]
        for k in range(10):
            img[12:16, k * 8:k * 8 + 8] = lut2[np.where(rk[:4] == 0, 0, rk[:4])]
        out.paste(Image.fromarray(img.repeat(4, 0).repeat(4, 1)), (x0, y0 + 14 + ph * 66))
    out.save(IMG_DIR / "sprites_preview.png")

def validate_level(lev):
    tiles = np.zeros((N_COLS, 32), int)
    pals = np.zeros((N_COLS, 32), int)
    for c in range(N_COLS):
        for r in range(32):
            e = lev[c * 32 + r]
            tiles[c, r], pals[c, r] = e & 0xFF, e >> 8
            if r < ROW_TOP or r > ROW_BOT:
                assert e == 0, (c, r)
            t, p = tiles[c, r], pals[c, r]
            if t >= 0x80:
                assert p in (0, 2), (c, r, t, p)
            elif t >= 0x70:
                assert p == 3, (c, r)
            elif t >= 0x20:
                raise AssertionError(f"font/HUD tile {t:#x} in level at {c},{r}")
            elif t == 0:
                assert p == 0
    runs, wins = [], []
    for c in range(N_COLS):
        free = [r for r in range(ROW_TOP, ROW_BOT + 1) if tiles[c, r] < 0x80]
        assert free == list(range(free[0], free[-1] + 1)), f"column {c} has two open spans"
        runs.append(len(free))
    for c in range(N_COLS - 2):
        top = max(min(r for r in range(ROW_TOP, ROW_BOT + 1) if tiles[k, r] < 0x80)
                  for k in range(c, c + 3))
        bot = min(max(r for r in range(ROW_TOP, ROW_BOT + 1) if tiles[k, r] < 0x80)
                  for k in range(c, c + 3))
        wins.append(bot - top + 1)
    assert min(runs) >= 4 and min(wins) >= 4, (min(runs), min(wins))
    for c in range(ARENA_COL, N_COLS):
        for r in (2, 3, 28, 29):
            assert tiles[c, r] >= 0x80, (c, r)
        for r in range(4, 28):
            assert tiles[c, r] < 0x70, (c, r)
    for c in range(0, 31):
        assert all(not (0x70 <= tiles[c, r] < 0x80) for r in range(32))
    for c in (3, 4):
        assert tiles[c, 15] < 0x70 and tiles[c, 16] < 0x70
    return tiles, runs, wins

def validate_spawns(words, tiles):
    ents = []
    for i, w in enumerate(words):
        trig = w & 0x1FF
        if trig == 0x1FF:
            assert all(x == 0x1FF for x in words[i:]), "table tail must be 000001FF"
            break
        assert w >> 19 == 0
        ents.append((trig, (w >> 9) & 3, (w >> 11) & 0xFF))
    trigs = [e[0] for e in ents]
    assert trigs == sorted(trigs) and len(set(trigs)) == len(trigs)
    assert 45 <= trigs[0] and trigs[-1] <= LAST_TRIGGER
    turrets = []
    for trig, typ, y in ents:
        if typ in (DRONE, DART):
            assert (32 if typ == DRONE else 24) <= y <= 208, (trig, y)
            assert box_free(tiles, (trig, trig + 1), y, y + 16), (trig, typ, y)
        elif typ == FTUR:
            R0, R1 = solid_bottom_run(tiles, trig), solid_bottom_run(tiles, trig + 1)
            assert R0 == R1 and is_rock(tiles[trig, R0]) and is_rock(tiles[trig + 1, R0])
            assert y == 8 * R0 - 16, (trig, y, R0)
            for c in (trig, trig + 1):
                assert tiles[c, R0 - 1] == 0 and tiles[c, R0 - 2] == 0
            turrets.append(trig)
        else:
            C0, C1 = solid_top_run(tiles, trig), solid_top_run(tiles, trig + 1)
            assert C0 == C1 and is_rock(tiles[trig, C0]) and is_rock(tiles[trig + 1, C0])
            assert y == 8 * (C0 + 1), (trig, y, C0)
            for c in (trig, trig + 1):
                assert tiles[c, C0 + 1] == 0 and tiles[c, C0 + 2] == 0
            turrets.append(trig)
    turrets.sort()
    assert all(b - a >= 2 for a, b in zip(turrets, turrets[1:])), "turrets share columns"
    return ents

def main():
    SRC_DIR.mkdir(exist_ok=True)

    tiles, pals, Ce, Fe = build_level()
    spawns = gen_spawns(tiles)
    occupied = set()
    for trig, typ, y in spawns:
        if typ in (FTUR, CTUR):
            for c in (trig, trig + 1):
                for r in (y // 8, y // 8 + 1):
                    occupied.add((c, r))
    place_decor(tiles, pals, occupied)
    level_words = [((int(pals[c, r]) << 8) | int(tiles[c, r])) if ROW_TOP <= r <= ROW_BOT else 0
                   for c in range(N_COLS) for r in range(32)]
    spawn_words = [(y << 11) | (typ << 9) | trig for trig, typ, y in spawns]
    assert len(spawn_words) < 128
    spawn_words += [0x1FF] * (128 - len(spawn_words))

    screens = build_screens()
    screen_words = [int(screens[s, r, c]) for s in range(4) for r in range(32) for c in range(64)]

    write_mem(SRC_DIR / "palette.mem", PALETTE, 2)
    write_mem(SRC_DIR / "chr_bg.mem", encode_chr(bg_sheet), 4)
    write_mem(SRC_DIR / "chr_spr.mem", encode_chr(spr_sheet), 4)
    write_mem(SRC_DIR / "level.mem", level_words, 3)
    write_mem(SRC_DIR / "spawn.mem", spawn_words, 8)
    write_mem(SRC_DIR / "screens.mem", screen_words, 3)

    pal = read_mem(SRC_DIR / "palette.mem", 32, 2)
    assert all(pal[i] == 0 for i in range(4, 32, 4)) and all(v < 64 for v in pal)
    bg_tiles = decode_chr(read_mem(SRC_DIR / "chr_bg.mem", 2048, 4))
    sp_tiles = decode_chr(read_mem(SRC_DIR / "chr_spr.mem", 2048, 4))
    assert not bg_tiles[0].any()
    lev = read_mem(SRC_DIR / "level.mem", 16384, 3)
    scr = read_mem(SRC_DIR / "screens.mem", 8192, 3)
    spw = read_mem(SRC_DIR / "spawn.mem", 128, 8)
    ltiles, runs, wins = validate_level(lev)
    ents = validate_spawns(spw, ltiles)
    max_on, max_line = concurrency(ents)
    for s in range(3):
        for r in range(32):
            for c in range(64):
                if not (ROW_TOP <= r <= ROW_BOT and c < 40):
                    assert scr[s * 2048 + r * 64 + c] == 0
    for r in range(32):
        for c in range(64):
            v = scr[3 * 2048 + r * 64 + c]
            assert (v >> 8 == 1) if r < 2 else v == 0

    lut = lut_rgb(pal)
    make_previews(bg_tiles, sp_tiles, lut, lev, ents, scr)

    def used(lo, hi, tiles_):
        return sum(1 for t in range(lo, hi + 1) if tiles_[t].any())
    print("BG tiles used: decor 0x01-1F %d, font 0x20-5F %d, HUD/logo 0x60-6F %d, "
          "crystal 0x70-7F %d, rock 0x80-FF %d" % (
              used(0x01, 0x1F, bg_tiles), 64, used(0x60, 0x6F, bg_tiles),
              used(0x70, 0x7F, bg_tiles), used(0x80, 0xFF, bg_tiles)))
    print("sprite tiles used: %d" % used(0, 255, sp_tiles))
    names = ["drone", "dart", "floor turret", "ceiling turret"]
    counts = [sum(1 for e in ents if e[1] == k) for k in range(4)]
    print("enemies: %d total (%s), triggers %d..%d" % (
        len(ents), ", ".join(f"{n} {c}" for n, c in zip(names, counts)),
        ents[0][0], ents[-1][0]))
    print("max enemies on screen %d, max sharing a scanline %d" % (max_on, max_line))
    print("free path (crystals passable): min per column %d rows, "
          "min over any 3 neighbouring columns %d rows (%d px)" % (
              min(runs), min(wins), 8 * min(wins)))
    print("narrowest windows:", sorted(range(len(wins)), key=lambda c: wins[c])[:8])
    n_cry = sum(1 for c in range(N_COLS) for r in range(32) if 0x70 <= ltiles[c, r] < 0x80)
    print("crystal tiles in level: %d; crystal walls at columns %s" % (n_cry, WALL_COLS))
    print("wrote", ", ".join(p.name for p in sorted(SRC_DIR.glob("*.mem"))))

if __name__ == "__main__":
    main()
