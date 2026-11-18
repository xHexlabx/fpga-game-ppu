#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

#include "Vtt_um_hextex_cavepatrol.h"
#include "Vtt_um_hextex_cavepatrol___024root.h"
#include "verilated.h"

#define R(sig) (top->rootp->tt_um_hextex_cavepatrol__DOT__##sig)
#define G(sig) R(u_game__DOT__##sig)

enum { B_B = 1 << 0, B_Y = 1 << 1, B_SEL = 1 << 2, B_START = 1 << 3, B_UP = 1 << 4,
       B_DOWN = 1 << 5, B_LEFT = 1 << 6, B_RIGHT = 1 << 7, B_A = 1 << 8, B_X = 1 << 9 };
enum { G_TITLE = 0, G_PLAY = 1, G_OVER = 2, G_CLEAR = 3 };

static Vtt_um_hextex_cavepatrol* top;
static int errors = 0;
static const char* OUT = "../sim/out/";

static uint16_t pad_buttons = 0;
static int pad_counter = 0;
static int prev_hs = 1;
static uint64_t frames = 0;
static bool cheat_invuln = false;

static bool cap_on = false;
static int cap_n = 0;
static std::vector<uint8_t> cap(640 * 480);

static void pad_step() {
    int cyc = pad_counter % 400;
    pad_counter++;
    uint32_t data = (uint32_t)pad_buttons << 12;
    int idx = cyc < 49 ? (cyc >> 1) : 0;
    int clkb = cyc < 48 ? (cyc & 1) : 0;
    int datab = (data >> idx) & 1;
    int latch = cyc == 49;
    top->ui_in = (top->ui_in & ~0x70) | (latch << 4) | (clkb << 5) | (datab << 6);
}

static void tick() {
    top->clk = 0;
    top->eval();
    top->clk = 1;
    top->eval();
    int hs = (top->uo_out >> 7) & 1;
    if (hs && !prev_hs) pad_step();
    prev_hs = hs;
    if (cap_on && R(u_ppu__DOT__de) && cap_n < 640 * 480) {
        uint8_t u = top->uo_out;
        uint8_t r = ((u >> 0) & 1) << 1 | ((u >> 4) & 1);
        uint8_t g = ((u >> 1) & 1) << 1 | ((u >> 5) & 1);
        uint8_t b = ((u >> 2) & 1) << 1 | ((u >> 6) & 1);
        cap[cap_n++] = (r << 4) | (g << 2) | b;
    }
    if (R(u_ppu__DOT__frame_start)) {
        frames++;
        if (cheat_invuln && G(palive)) G(pinv) = 200;
    }
}

static void next_frame() {          // run to the next frame_start
    do tick(); while (!R(u_ppu__DOT__frame_start));
}

static void frames_n(int n) { for (int k = 0; k < n; k++) next_frame(); }

static void capture(const std::string& name) {
    while (!(R(u_ppu__DOT__y) == 524 && R(u_ppu__DOT__x) == 799)) tick();
    cap_n = 0;
    cap_on = true;
    while (cap_n < 640 * 480) tick();
    cap_on = false;
    int bad = 0;
    FILE* f = fopen((std::string(OUT) + name + ".hex").c_str(), "w");
    for (int y = 0; y < 480; y += 2)
        for (int x = 0; x < 640; x += 2) {
            uint8_t p = cap[y * 640 + x];
            if (cap[y * 640 + x + 1] != p || cap[(y + 1) * 640 + x] != p ||
                cap[(y + 1) * 640 + x + 1] != p)
                bad++;
            fprintf(f, "%02x\n", p);
        }
    fclose(f);
    if (bad) {
        printf("FAIL %s: %d 2x2 blocks not one colour\n", name.c_str(), bad);
        errors++;
    } else {
        printf("ok   captured %s (frame %llu)\n", name.c_str(), (unsigned long long)frames);
    }
}

static void press(uint16_t b) {     // hold 3 frames, release 3 frames
    pad_buttons = b;
    frames_n(3);
    pad_buttons = 0;
    frames_n(3);
}

static void reset() {
    top->rst_n = 0;
    top->ui_in = 0;
    top->ena = 1;
    top->uio_in = 0;
    for (int k = 0; k < 20; k++) tick();
    top->rst_n = 1;
    pad_counter = 0;
    pad_buttons = 0;
}

static void check(const char* what, bool ok) {
    printf("%s %s\n", ok ? "ok  " : "FAIL", what);
    if (!ok) errors++;
}

static unsigned bcd(uint32_t v) {   // 6 BCD digits -> number
    unsigned n = 0;
    for (int d = 5; d >= 0; d--) n = n * 10 + ((v >> (4 * d)) & 15);
    return n;
}

static bool solid_tile(int entry) {
    int t = entry & 0xff;
    return (t & 0x80) || ((t >> 4) == 7);
}
static bool rock_tile(int entry) { return (entry & 0x80) != 0; }

static uint16_t autopilot(bool boss_mode) {
    int px = G(px), py = G(py);
    int camx = G(camx);
    uint16_t b = B_A;
    int target;
    if (boss_mode && (G(bst) == 1 || G(bst) == 2)) {
        target = G(bsy) + 8;        // line the ship up with the CORE's middle
    } else {
        bool free_row[32];
        for (int r = 0; r < 32; r++) free_row[r] = (r >= 2 && r <= 29);
        for (int dx = 0; dx <= 40; dx += 8) {
            int wx = (camx + px + dx) & 511;
            int col = wx >> 3;
            for (int r = 2; r <= 29; r++) {
                int e = R(u_ppu__DOT__vram)[(r << 6) | col];
                if (rock_tile(e)) free_row[r] = false;
            }
        }
        int mid = (py + 8) >> 3, best_lo = -1, best_hi = -1, best_d = 1000;
        for (int r = 2; r <= 29;) {
            if (!free_row[r]) { r++; continue; }
            int lo = r;
            while (r <= 29 && free_row[r]) r++;
            int hi = r - 1;
            if (hi - lo + 1 >= 3) {
                int d = (mid < lo) ? lo - mid : (mid > hi) ? mid - hi : 0;
                if (d < best_d) { best_d = d; best_lo = lo; best_hi = hi; }
            }
        }
        target = (best_lo < 0) ? 120 : ((best_lo + best_hi + 1) * 4) - 8;
    }
    if (py + 2 < target) b |= B_DOWN;
    else if (py > target + 2) b |= B_UP;
    if (px < 40) b |= B_RIGHT;
    else if (px > 56) b |= B_LEFT;
    return b;
}

static void scenario_gameover() {
    printf("--- gameover\n");
    reset();
    frames_n(3);
    capture("game_title");
    check("power-on state is TITLE", G(gstate) == G_TITLE);
    press(B_START);
    check("START begins a game", G(gstate) == G_PLAY);
    check("three ships", G(ships) == 3);
    frames_n(30);
    capture("game_start");
    pad_buttons = B_UP;
    int deaths = 0, was_alive = 1;
    for (int f = 0; f < 1500 && G(gstate) == G_PLAY; f++) {
        next_frame();
        if (was_alive && !G(palive)) {
            deaths++;
            if (deaths == 1) { pad_buttons = 0; capture("game_crash"); pad_buttons = B_UP; }
        }
        was_alive = G(palive);
    }
    pad_buttons = 0;
    printf("info %d crash(es) into the ceiling\n", deaths);
    check("three crashes end the game", deaths == 3 && G(gstate) == G_OVER);
    frames_n(2);
    capture("game_over");
    press(B_START);
    check("START from GAME OVER begins a new game", G(gstate) == G_PLAY && G(ships) == 3);
}

static void scenario_pilot() {
    printf("--- pilot (no cheats)\n");
    reset();
    frames_n(3);
    press(B_START);
    int deaths = 0, was_alive = 1, shots_seen = 0;
    unsigned max_cam = 0;
    bool took_mid = false;
    for (int f = 0; f < 5000 && G(gstate) == G_PLAY; f++) {
        pad_buttons = G(palive) ? autopilot(true) : 0;
        next_frame();
        if (was_alive && !G(palive)) deaths++;
        was_alive = G(palive);
        if (G(camx) > max_cam) max_cam = G(camx);
        if (!took_mid && G(camx) >= 1200 && G(palive)) { capture("game_mid"); took_mid = true; }
        shots_seen++;
    }
    printf("info autopilot: %d crash(es), reached camera x %u of 3776, score %u, state %d\n",
           deaths, max_cam, bcd(G(score)), (int)G(gstate));
    check("the cave can be flown into (autopilot passes x 600)", max_cam > 600);
}

static void scenario_win() {
    printf("--- win (invulnerable ship)\n");
    reset();
    frames_n(3);
    press(B_START);
    cheat_invuln = true;
    bool shot_boss = false, shot_fight = false, crystal_gone = false;
    int crystals_at_start = -1;
    int frames_play = 0;
    for (int f = 0; f < 6000 && G(gstate) == G_PLAY; f++) {
        pad_buttons = autopilot(true);
        next_frame();
        frames_play++;
        if (!shot_fight && G(camx) >= 2000) { capture("game_deep"); shot_fight = true; }
        if (!shot_boss && G(bst) == 2 && G(bhp) < 24) { capture("game_boss"); shot_boss = true; }
        if (G(bst) == 3 && G(btimer) == 20) capture("game_boss_down");
    }
    (void)crystals_at_start; (void)crystal_gone;
    cheat_invuln = false;
    pad_buttons = 0;
    printf("info reached state %d after %d frames, camera %u, score %u, hi %u\n",
           (int)G(gstate), frames_play, (unsigned)G(camx), bcd(G(score)), bcd(G(hi)));
    check("the camera stops at the arena (3776)", G(camx) == 3776);
    check("the CORE is destroyed and the cave CLEARED", G(gstate) == G_CLEAR);
    check("score counts up", bcd(G(score)) > 5000);
    check("hi score keeps the best score", G(hi) == G(score));
    frames_n(2);
    capture("game_clear");
}

static void scenario_crystal() {
    printf("--- crystal\n");
    reset();
    frames_n(3);
    press(B_START);
    cheat_invuln = true;
    for (int f = 0; f < 3000 && G(gstate) == G_PLAY; f++) {
        int camx = G(camx), px = G(px);
        int found = -1, frow = 0;
        for (int sx = px + 24; sx < 300 && found < 0; sx += 8) {
            int col = ((camx + sx) & 511) >> 3;
            for (int r = 3; r <= 28; r++) {
                int e = R(u_ppu__DOT__vram)[(r << 6) | col];
                if (((e & 0xff) >> 4) == 7) { found = (r << 6) | col; frow = r; break; }
            }
        }
        if (found >= 0) {
            int target = frow * 8 - 1;
            pad_buttons = 0;
            for (int k = 0; k < 120 && G(gstate) == G_PLAY; k++) {
                int py = G(py);
                uint16_t b = 0;
                if (py + 1 < target) b |= B_DOWN;
                else if (py > target + 1) b |= B_UP;
                else b |= B_A;
                pad_buttons = b;
                next_frame();
                int e = R(u_ppu__DOT__vram)[found];
                if (((e & 0xff) >> 4) != 7) {
                    pad_buttons = 0;
                    check("a bolt turns a crystal tile into empty space", (e & 0x3ff) == 0);
                    printf("info crystal at row %d shot at camera x %u, score %u\n", frow,
                           (unsigned)G(camx), bcd(G(score)));
                    capture("game_crystal");
                    cheat_invuln = false;
                    return;
                }
            }
        } else {
            pad_buttons = autopilot(false) & ~B_A;
            next_frame();
        }
    }
    cheat_invuln = false;
    check("found and shot a crystal", false);
}

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    top = new Vtt_um_hextex_cavepatrol;
    std::string which = argc > 1 ? argv[1] : "all";
    if (which == "all" || which == "gameover") scenario_gameover();
    if (which == "all" || which == "crystal") scenario_crystal();
    if (which == "all" || which == "pilot") scenario_pilot();
    if (which == "all" || which == "win") scenario_win();
    top->final();
    delete top;
    printf(errors ? "FAILED: %d error(s)\n" : "PASS\n", errors);
    return errors ? 1 : 0;
}
