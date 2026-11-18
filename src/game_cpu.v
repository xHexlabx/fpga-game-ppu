`default_nettype none

module game_cpu (
    input  wire        clk,
    input  wire        rst,
    input  wire        frame_start,
    input  wire [11:0] pad,      // held: {b, y, select, start, up, down, left, right, a, x, l, r}
    input  wire [4:0]  sw,       // held: {fire, right, left, down, up}
    output reg         we,
    output reg  [12:0] waddr,
    output reg  [31:0] wdata,
    output wire [11:0] nt_raddr,
    input  wire [9:0]  nt_rdata
);

    reg [9:0]  level_rom  [0:16383];
    reg [9:0]  screen_rom [0:8191];
    reg [31:0] spawn_rom  [0:127];
    reg [5:0]  pal_rom    [0:31];
    initial $readmemh("level.mem",   level_rom);
    initial $readmemh("screens.mem", screen_rom);
    initial $readmemh("spawn.mem",   spawn_rom);
    initial $readmemh("palette.mem", pal_rom);

    localparam G_TITLE = 2'd0, G_PLAY = 2'd1, G_OVER = 2'd2, G_CLEAR = 2'd3;

    localparam S_BOOT_PAL = 5'd0,  S_BOOT_HUD = 5'd1,  S_BOOT_TITLE = 5'd2,
               S_COPY     = 5'd3,  S_WAIT     = 5'd4,  S_INPUT      = 5'd5,
               S_START    = 5'd6,  S_SCROLL   = 5'd7,  S_PLAYER     = 5'd8,
               S_OBJ      = 5'd9,  S_BOSS     = 5'd10, S_SPAWN      = 5'd11,
               S_COLL     = 5'd12, S_TERR     = 5'd13, S_OAM        = 5'd14,
               S_HUD      = 5'd15, S_PAL      = 5'd16, S_REGS       = 5'd17,
               S_POST     = 5'd18;

    localparam [11:0] DIST_END = 12'd3776;     // camera stops: columns 472..511
    localparam [31:0] HIDE     = {15'd0, 8'd240, 9'd0};

    reg [4:0]  st;
    reg [1:0]  gstate;
    reg [12:0] c;
    reg [12:0] c_d;
    reg        v_d;

    reg [11:0] pad_prev;
    reg        fire_sw_prev;
    reg [7:0]  fcnt;
    reg [4:0]  rot;
    reg [1:0]  cph;                 // crystal colour phase
    reg [5:0]  bd0, cr0, cr1, cr2, bo0, bo1, bo2;   // palette.mem colours kept

    reg [11:0] camx;
    reg        scrolled;            // the camera moved this frame
    reg [23:0] score, hi;           // BCD, 6 digits
    reg [3:0]  ships;
    reg [6:0]  sp_ptr;

    reg [8:0]  px;
    reg [7:0]  py;
    reg        palive;
    reg [6:0]  ptimer;              // frames since the ship blew up
    reg [7:0]  pinv;                // invulnerable frames left after a respawn
    reg [2:0]  pcool;               // frames until the next bolt

    reg [8:0]  bx  [0:3];
    reg [7:0]  by  [0:3];
    reg        bon [0:3];

    reg [8:0]  qx  [0:3];
    reg [7:0]  qy  [0:3];
    reg [1:0]  qvy [0:3];           // 0 straight, 1 down, 2 up
    reg        qon [0:3];

    reg [8:0]  ex    [0:7];
    reg [7:0]  ey    [0:7];
    reg [7:0]  ebase [0:7];
    reg [1:0]  etype [0:7];         // 0 drone, 1 dart, 2 floor turret, 3 ceiling turret
    reg [1:0]  est   [0:7];         // 0 free, 1 alive, 2 exploding
    reg [6:0]  et    [0:7];

    reg [1:0]  bst;                 // 0 none, 1 entering, 2 fighting, 3 dying
    reg [8:0]  bsx;
    reg [7:0]  bsy;
    reg        bsup;
    reg [5:0]  bhp;
    reg [6:0]  btimer;
    reg [5:0]  bfire;
    reg [2:0]  bflash;

    reg        pend;
    reg [1:0]  pend_scr;

    function [4:0] bcd_digit;       // {carry, digit}
        input [3:0] a, b;
        input       cin;
        reg   [4:0] s;
        begin
            s = {1'b0, a} + {1'b0, b} + {4'd0, cin};
            bcd_digit = (s > 5'd9) ? {1'b1, s[3:0] + 4'd6} : s;
        end
    endfunction

    function [23:0] bcd_add;
        input [23:0] a, b;
        reg   [4:0]  d0, d1, d2, d3, d4, d5;
        begin
            d0 = bcd_digit(a[3:0],   b[3:0],   1'b0);
            d1 = bcd_digit(a[7:4],   b[7:4],   d0[4]);
            d2 = bcd_digit(a[11:8],  b[11:8],  d1[4]);
            d3 = bcd_digit(a[15:12], b[15:12], d2[4]);
            d4 = bcd_digit(a[19:16], b[19:16], d3[4]);
            d5 = bcd_digit(a[23:20], b[23:20], d4[4]);
            bcd_add = {d5[3:0], d4[3:0], d3[3:0], d2[3:0], d1[3:0], d0[3:0]};
        end
    endfunction

    function overlap;
        input [9:0] ax0, ay0, ax1, ay1, bx0, by0, bx1, by1;
        overlap = (ax0 <= bx1) && (bx0 <= ax1) && (ay0 <= by1) && (by0 <= ay1);
    endfunction

    function [31:0] spr;            // build an OAM entry
        input [8:0] x;
        input [7:0] y;
        input [7:0] tile;
        input [1:0] pl;
        input       vflip, big;
        spr = {1'b0, big, 1'b0, vflip, 1'b0, pl, tile, y, x};
    endfunction

    wire [11:0] pad_edge  = pad & ~pad_prev;
    wire        in_up     = pad[7] | sw[0];
    wire        in_down   = pad[6] | sw[1];
    wire        in_left   = pad[5] | sw[2];
    wire        in_right  = pad[4] | sw[3];
    wire        in_fire   = pad[3] | pad[11] | sw[4];
    wire        menu_go   = pad_edge[8] | pad_edge[3] | (sw[4] ^ fire_sw_prev);

    reg        cp_level;
    reg [9:0]  cp_col;
    reg [1:0]  cp_scr;
    reg [4:0]  cp_row;
    reg [12:0] cp_count;
    reg [4:0]  cp_ret;

    wire [9:0]  cp_lcol   = cp_col + {4'd0, c[10:5]};
    wire [9:0]  cp_lcol_d = cp_col + {4'd0, c_d[10:5]};
    wire [4:0]  cp_srow   = cp_row + c[10:6];
    wire [4:0]  cp_srow_d = cp_row + c_d[10:6];

    reg [9:0] level_q, screen_q;
    always @(posedge clk) begin
        level_q  <= level_rom[{cp_lcol[8:0], c[4:0]}];
        screen_q <= screen_rom[{cp_scr, cp_srow, c[5:0]}];
    end

    reg [5:0]  pal_q;
    reg [31:0] spawn_q;
    always @(posedge clk) begin
        pal_q   <= pal_rom[c[4:0]];
        spawn_q <= spawn_rom[sp_ptr];
    end

    wire       b_free_any = !bon[0] | !bon[1] | !bon[2] | !bon[3];
    wire [1:0] b_free     = !bon[0] ? 2'd0 : !bon[1] ? 2'd1 : !bon[2] ? 2'd2 : 2'd3;
    wire       q_free_any = !qon[0] | !qon[1] | !qon[2] | !qon[3];
    wire [1:0] q_free     = !qon[0] ? 2'd0 : !qon[1] ? 2'd1 : !qon[2] ? 2'd2 : 2'd3;
    wire       e_free_any = (est[0] == 2'd0) | (est[1] == 2'd0) | (est[2] == 2'd0) |
                            (est[3] == 2'd0) | (est[4] == 2'd0) | (est[5] == 2'd0) |
                            (est[6] == 2'd0) | (est[7] == 2'd0);
    wire [2:0] e_free     = (est[0] == 2'd0) ? 3'd0 : (est[1] == 2'd0) ? 3'd1 :
                            (est[2] == 2'd0) ? 3'd2 : (est[3] == 2'd0) ? 3'd3 :
                            (est[4] == 2'd0) ? 3'd4 : (est[5] == 2'd0) ? 3'd5 :
                            (est[6] == 2'd0) ? 3'd6 : 3'd7;

    function [1:0] aim;
        input [7:0] y0, ship_y;
        aim = ({1'b0, ship_y} > {1'b0, y0} + 9'd24) ? 2'd1 :
              ({1'b0, ship_y} + 9'd24 < {1'b0, y0}) ? 2'd2 : 2'd0;
    endfunction

    wire [3:0] ok = c[3:0];         // 0..3 bolts, 4..7 orbs, 8..15 enemies
    wire [1:0] ob = ok[1:0];
    wire [2:0] oe = ok[2:0];

    wire [7:0] wob_base = (ebase[oe] < 8'd32) ? 8'd32 : (ebase[oe] > 8'd207) ? 8'd207 : ebase[oe];
    wire [4:0] wob_tri  = et[oe][5] ? ~et[oe][4:0] : et[oe][4:0];
    wire [8:0] e_dx     = (etype[oe] == 2'd0) ? 9'd2 : (etype[oe] == 2'd1) ? 9'd3 :
                          {8'd0, scrolled};
    wire [8:0] e_nx     = ex[oe] - e_dx;
    wire       e_gone   = (e_nx >= 9'd336) && (e_nx <= 9'd496);

    wire [5:0] j  = c[5:0];
    wire [1:0] jb = (j[5] == 1'b0) ? j[4:3] : j[1:0];
    wire [2:0] je = j[2:0];
    wire [1:0] jq = j[1:0];

    wire [9:0] pbx0 = {1'b0, px} + 10'd3,  pby0 = {2'd0, py} + 10'd4;
    wire [9:0] pbx1 = {1'b0, px} + 10'd12, pby1 = {2'd0, py} + 10'd11;
    wire [9:0] bbx0 = {1'b0, bx[jb]},          bby0 = {2'd0, by[jb]} + 10'd2;
    wire [9:0] bbx1 = {1'b0, bx[jb]} + 10'd7,  bby1 = {2'd0, by[jb]} + 10'd5;
    wire [9:0] ebx0 = {1'b0, ex[je]} + 10'd2,  eby0 = {2'd0, ey[je]} + 10'd2;
    wire [9:0] ebx1 = {1'b0, ex[je]} + 10'd13, eby1 = {2'd0, ey[je]} + 10'd13;
    wire [9:0] qbx0 = {1'b0, qx[jq]} + 10'd2,  qby0 = {2'd0, qy[jq]} + 10'd2;
    wire [9:0] qbx1 = {1'b0, qx[jq]} + 10'd5,  qby1 = {2'd0, qy[jq]} + 10'd5;
    wire [9:0] cbx0 = {1'b0, bsx} + 10'd4,     cby0 = {2'd0, bsy} + 10'd4;
    wire [9:0] cbx1 = {1'b0, bsx} + 10'd27,    cby1 = {2'd0, bsy} + 10'd27;

    wire ship_ok   = palive && (pinv == 8'd0);
    wire enemy_ok  = (est[je] == 2'd1) && (ex[je] < 9'd320);
    wire core_ok   = ((bst == 2'd1) || (bst == 2'd2)) && (bsx < 9'd300);

    wire hit_be = bon[jb] && enemy_ok && overlap(bbx0, bby0, bbx1, bby1, ebx0, eby0, ebx1, eby1);
    wire hit_pe = ship_ok && enemy_ok && overlap(pbx0, pby0, pbx1, pby1, ebx0, eby0, ebx1, eby1);
    wire hit_bc = bon[jb] && core_ok  && overlap(bbx0, bby0, bbx1, bby1, cbx0, cby0, cbx1, cby1);
    wire hit_pq = ship_ok && qon[jq] && (qx[jq] < 9'd320) &&
                  overlap(pbx0, pby0, pbx1, pby1, qbx0, qby0, qbx1, qby1);
    wire hit_pc = ship_ok && core_ok  && overlap(pbx0, pby0, pbx1, pby1, cbx0, cby0, cbx1, cby1);

    reg [23:0] e_pts;
    always @(*) begin
        case (etype[je])
            2'd0:    e_pts = 24'h000100;
            2'd1:    e_pts = 24'h000150;
            default: e_pts = 24'h000200;
        endcase
    end

    wire [3:0] t  = c[3:0];
    reg  [8:0] t_sx;
    reg  [7:0] t_sy;
    reg        t_ok;
    always @(*) begin
        if (t < 4'd8) begin
            t_sx = px + ((t[1:0] == 2'd0) ? 9'd3 : (t[1:0] == 2'd1) ? 9'd8 : 9'd12);
            t_sy = py + (t[2] ? 8'd11 : 8'd4);
            t_ok = ship_ok;
        end else if (t < 4'd12) begin
            t_sx = bx[t[1:0]] + 9'd7;
            t_sy = by[t[1:0]] + 8'd3;
            t_ok = bon[t[1:0]];
        end else begin
            t_sx = qx[t[1:0]] + 9'd3;
            t_sy = qy[t[1:0]] + 8'd3;
            t_ok = qon[t[1:0]] && (qx[t[1:0]] < 9'd312);
        end
    end
    wire [8:0] t_wx = camx[8:0] + t_sx;
    assign nt_raddr = {1'b0, t_sy[7:3], t_wx[8:3]};

    reg        tr_v;                // a read issued last clock
    reg [3:0]  tr_t;
    reg [11:0] tr_addr;
    wire [7:0] tr_tile    = nt_rdata[7:0];
    wire       tr_solid   = tr_tile[7] | (tr_tile[7:4] == 4'h7);
    wire       tr_crystal = (tr_tile[7:4] == 4'h7);

    always @(posedge clk) begin
        tr_v    <= (st == S_TERR) && (c < 13'd16) && t_ok;
        tr_t    <= t;
        tr_addr <= nt_raddr;
    end

    wire [5:0] s   = c[5:0];
    wire [5:0] sm1 = s - 6'd1;
    wire [4:0] ent = sm1[4:0] - rot;
    wire [1:0] eq  = ent[1:0];
    wire [2:0] ee  = ent[2:0];

    reg [31:0] oam_e;
    reg [7:0]  e_tile;
    always @(*) begin
        oam_e = HIDE;
        case (etype[ee])
            2'd0:    e_tile = {5'b00000, 1'b1, fcnt[3], 1'b0};               // drone 0x04/0x06
            2'd1:    e_tile = {4'b0000, 1'b1, 1'b0, fcnt[3], 1'b0};          // dart 0x08/0x0A
            default: e_tile = (et[ee] >= 7'd88) ? 8'h0E : 8'h0C;             // turret
        endcase
        if (gstate == G_PLAY) begin
            if (s == 6'd0) begin
                if (palive) begin
                    if (pinv == 8'd0 || !pinv[2])
                        oam_e = spr(px, py, {6'd0, fcnt[2], 1'b0}, 2'd0, 1'b0, 1'b1);
                end else if (ptimer < 7'd32) begin
                    oam_e = spr(px, py, {5'b00100, ptimer[4:3], 1'b0}, 2'd2, 1'b0, 1'b1);
                end
            end else if (s <= 6'd32) begin
                if (ent < 5'd4) begin
                    if (bon[eq]) oam_e = spr(bx[eq], by[eq], {7'b1000000, fcnt[1]}, 2'd2, 1'b0, 1'b0);
                end else if (ent < 5'd8) begin
                    if (qon[eq]) oam_e = spr(qx[eq], qy[eq], {7'b1000001, fcnt[2]}, 2'd2, 1'b0, 1'b0);
                end else if (ent < 5'd16) begin
                    if (est[ee] == 2'd1)
                        oam_e = spr(ex[ee], ey[ee], e_tile, 2'd1, etype[ee] == 2'd3, 1'b1);
                    else if (est[ee] == 2'd2)
                        oam_e = spr(ex[ee], ey[ee], {5'b00100, et[ee][4:3], 1'b0}, 2'd2, 1'b0, 1'b1);
                end else if (ent < 5'd20) begin
                    if (bst == 2'd1 || bst == 2'd2)
                        oam_e = spr(bsx + {4'd0, eq[0], 4'd0}, bsy + {3'd0, eq[1], 4'd0},
                                    {3'b010, eq[1], 1'b0, (bfire >= 6'd36) || (bflash != 3'd0), eq[0], 1'b0},
                                    2'd3, 1'b0, 1'b1);
                    else if (bst == 2'd3 && btimer < 7'd96)
                        oam_e = spr(bsx + {4'd0, eq[0], 4'd0} + {6'd0, btimer[3] ^ eq[1], 2'd0},
                                    bsy + {3'd0, eq[1], 4'd0} + {5'd0, btimer[4] ^ eq[0], 2'd0},
                                    {5'b00100, btimer[4:3] + eq, 1'b0}, 2'd2, 1'b0, 1'b1);
                end
            end
        end
    end

    wire [5:0] h = c[5:0];
    reg  [11:0] hud_a;              // VRAM address in page 1
    reg  [7:0]  hud_t;
    reg  [3:0]  hd;
    reg  [3:0]  hcell;
    always @(*) begin
        hd    = 4'd0;
        hcell = 4'd0;
        hud_a = 12'd0;
        hud_t = 8'h20;
        if (h < 6'd6) begin
            case (h[2:0])
                3'd0: hd = score[23:20]; 3'd1: hd = score[19:16]; 3'd2: hd = score[15:12];
                3'd3: hd = score[11:8];  3'd4: hd = score[7:4];   default: hd = score[3:0];
            endcase
            hud_a = {1'b1, 5'd0, 6'd8 + h};
            hud_t = 8'h30 + {4'd0, hd};
        end else if (h < 6'd12) begin
            case (h - 6'd6)
                6'd0: hd = hi[23:20]; 6'd1: hd = hi[19:16]; 6'd2: hd = hi[15:12];
                6'd3: hd = hi[11:8];  6'd4: hd = hi[7:4];   default: hd = hi[3:0];
            endcase
            hud_a = {1'b1, 5'd0, 6'd21 + h - 6'd6};
            hud_t = 8'h30 + {4'd0, hd};
        end else if (h == 6'd12) begin
            hud_a = {1'b1, 5'd0, 6'd37};
            hud_t = 8'h30 + {4'd0, ships};
        end else if (h < 6'd29) begin
            hcell = h[3:0] - 4'd13;               // h 13..28 -> 0..15
            hud_a = {1'b1, 5'd1, 6'd8 + {2'd0, hcell}};
            hud_t = ((hcell < camx[11:8]) || (camx == DIST_END)) ? 8'h61 : 8'h60;
        end else begin
            hcell = {1'b0, h[2:0] - 3'd5};        // h 29..36 -> 0..7
            hud_a = {1'b1, 5'd1, 6'd31 + {2'd0, hcell}};
            hud_t = (bst != 2'd0 && bhp > {1'b0, hcell[2:0], 2'd0}) ? 8'h63 : 8'h62;
        end
    end

    function [5:0] cyc;             // crystal colour for entry 13 + n
        input [1:0] n, ph;
        input [5:0] a, b, d;
        reg   [2:0] k;
        begin
            k = {1'b0, n} + {1'b0, ph};
            if (k >= 3'd3) k = k - 3'd3;
            cyc = (k == 3'd0) ? a : (k == 3'd1) ? b : d;
        end
    endfunction

    wire flash_red = (gstate == G_PLAY) && !palive && (ptimer < 7'd3);
    reg [4:0] pal_a;
    reg [5:0] pal_v;
    always @(*) begin
        case (c[2:0])
            3'd0:    begin pal_a = 5'd0;  pal_v = flash_red ? 6'h30 : bd0; end
            3'd1:    begin pal_a = 5'd13; pal_v = cyc(2'd0, cph, cr0, cr1, cr2); end
            3'd2:    begin pal_a = 5'd14; pal_v = cyc(2'd1, cph, cr0, cr1, cr2); end
            3'd3:    begin pal_a = 5'd15; pal_v = cyc(2'd2, cph, cr0, cr1, cr2); end
            3'd4:    begin pal_a = 5'd29; pal_v = (bflash != 3'd0) ? 6'h3F : bo0; end
            3'd5:    begin pal_a = 5'd30; pal_v = (bflash != 3'd0) ? 6'h3F : bo1; end
            default: begin pal_a = 5'd31; pal_v = (bflash != 3'd0) ? 6'h3F : bo2; end
        endcase
    end

    wire [11:0] camx_n  = (camx < DIST_END) ? (camx + 12'd1) : camx;
    wire [9:0]  new_col = {1'b0, camx_n[11:3]} + 10'd40;
    wire [9:0]  cur_col = {1'b0, camx[11:3]} + 10'd40;

    always @(posedge clk) begin
        we <= 1'b0;
        if (rst) begin
            st           <= S_BOOT_PAL;
            gstate       <= G_TITLE;
            c            <= 13'd0;
            v_d          <= 1'b0;
            pad_prev     <= 12'd0;
            fire_sw_prev <= 1'b0;
            fcnt         <= 8'd0;
            rot          <= 5'd0;
            cph          <= 2'd0;
            hi           <= 24'd0;
            score        <= 24'd0;
            ships        <= 4'd3;
            camx         <= 12'd0;
            palive       <= 1'b0;
            bst          <= 2'd0;
            bhp          <= 6'd0;
            bflash       <= 3'd0;
            pend         <= 1'b0;
            sp_ptr       <= 7'd0;
            bon[0] <= 1'b0; bon[1] <= 1'b0; bon[2] <= 1'b0; bon[3] <= 1'b0;
            qon[0] <= 1'b0; qon[1] <= 1'b0; qon[2] <= 1'b0; qon[3] <= 1'b0;
            est[0] <= 2'd0; est[1] <= 2'd0; est[2] <= 2'd0; est[3] <= 2'd0;
            est[4] <= 2'd0; est[5] <= 2'd0; est[6] <= 2'd0; est[7] <= 2'd0;
        end else begin
            case (st)
                S_BOOT_PAL: begin
                    c   <= c + 13'd1;
                    c_d <= c;
                    v_d <= !c[5];
                    if (v_d) begin
                        we    <= 1'b1;
                        waddr <= 13'h1040 | {8'd0, c_d[4:0]};
                        wdata <= {26'd0, pal_q};
                        case (c_d[4:0])
                            5'd0:  bd0 <= pal_q;
                            5'd13: cr0 <= pal_q;
                            5'd14: cr1 <= pal_q;
                            5'd15: cr2 <= pal_q;
                            5'd29: bo0 <= pal_q;
                            5'd30: bo1 <= pal_q;
                            5'd31: bo2 <= pal_q;
                            default: ;
                        endcase
                    end
                    if (c == 13'd33) st <= S_BOOT_HUD;
                end

                S_BOOT_HUD: begin           // HUD labels: screen 3 rows 0-1
                    cp_level <= 1'b0; cp_scr <= 2'd3; cp_row <= 5'd0;
                    cp_count <= 13'd128;      cp_ret <= S_BOOT_TITLE;
                    c <= 13'd0; v_d <= 1'b0;
                    st <= S_COPY;
                end

                S_BOOT_TITLE: begin         // title screen: screen 0 rows 2-29
                    cp_level <= 1'b0; cp_scr <= 2'd0; cp_row <= 5'd2;
                    cp_count <= 13'd1792;     cp_ret <= S_WAIT;
                    c <= 13'd0; v_d <= 1'b0;
                    st <= S_COPY;
                end

                S_COPY: begin
                    c   <= c + 13'd1;
                    c_d <= c;
                    v_d <= (c < cp_count);
                    if (v_d) begin
                        we    <= 1'b1;
                        if (cp_level) begin
                            waddr <= {2'b00, c_d[4:0], cp_lcol_d[5:0]};
                            wdata <= {22'd0, level_q};
                        end else begin
                            waddr <= {2'b01, cp_srow_d, c_d[5:0]};
                            wdata <= {22'd0, screen_q};
                        end
                    end
                    if (c == cp_count + 13'd1) begin
                        st <= cp_ret;
                        c  <= 13'd0;
                    end
                end

                S_WAIT: begin
                    c <= 13'd0;
                    if (frame_start) st <= S_INPUT;
                end

                S_INPUT: begin
                    pad_prev     <= pad;
                    fire_sw_prev <= sw[4];
                    fcnt         <= fcnt + 8'd1;
                    rot          <= rot + 5'd7;
                    if (fcnt[2:0] == 3'd0)
                        cph <= (cph == 2'd2) ? 2'd0 : (cph + 2'd1);
                    if (bflash != 3'd0) bflash <= bflash - 3'd1;
                    if (gstate == G_PLAY)  st <= S_SCROLL;
                    else if (menu_go)      st <= S_START;
                    else                   st <= S_OAM;
                    c <= 13'd0;
                end

                S_START: begin              // new game
                    gstate <= G_PLAY;
                    score  <= 24'd0;
                    ships  <= 4'd3;
                    camx   <= 12'd0;
                    sp_ptr <= 7'd0;
                    px     <= 9'd24;
                    py     <= 8'd120;
                    palive <= 1'b1;
                    ptimer <= 7'd0;
                    pinv   <= 8'd60;
                    pcool  <= 3'd0;
                    bst    <= 2'd0;
                    bhp    <= 6'd0;
                    bon[0] <= 1'b0; bon[1] <= 1'b0; bon[2] <= 1'b0; bon[3] <= 1'b0;
                    qon[0] <= 1'b0; qon[1] <= 1'b0; qon[2] <= 1'b0; qon[3] <= 1'b0;
                    est[0] <= 2'd0; est[1] <= 2'd0; est[2] <= 2'd0; est[3] <= 2'd0;
                    est[4] <= 2'd0; est[5] <= 2'd0; est[6] <= 2'd0; est[7] <= 2'd0;
                    cp_level <= 1'b1; cp_col <= 10'd0;
                    cp_count <= 13'd1312;     cp_ret <= S_OAM;
                    c <= 13'd0; v_d <= 1'b0;
                    st <= S_COPY;
                end

                S_SCROLL: begin
                    camx     <= camx_n;
                    scrolled <= (camx < DIST_END);
                    if (camx_n == DIST_END && bst == 2'd0) begin
                        bst    <= 2'd1;
                        bsx    <= 9'd320;
                        bsy    <= 8'd96;
                        bsup   <= 1'b0;
                        bhp    <= 6'd32;
                        bfire  <= 6'd0;
                        btimer <= 7'd0;
                    end
                    c <= 13'd0; v_d <= 1'b0;
                    if (camx < DIST_END && camx_n[2:0] == 3'd0 && new_col <= 10'd511) begin
                        cp_level <= 1'b1; cp_col <= new_col;
                        cp_count <= 13'd32;       cp_ret <= S_PLAYER;
                        st <= S_COPY;
                    end else begin
                        st <= S_PLAYER;
                    end
                end

                S_PLAYER: begin
                    if (palive) begin
                        if (in_up && py > 8'd17)           py <= py - 8'd2;
                        else if (in_down && py < 8'd223)   py <= py + 8'd2;
                        if (in_left && px > 9'd1)          px <= px - 9'd2;
                        else if (in_right && px < 9'd295)  px <= px + 9'd2;
                        if (pinv != 8'd0) pinv <= pinv - 8'd1;
                        if (pcool != 3'd0) pcool <= pcool - 3'd1;
                        else if (in_fire && b_free_any) begin
                            bx[b_free]  <= px + 9'd12;
                            by[b_free]  <= py + 8'd4;
                            bon[b_free] <= 1'b1;
                            pcool       <= 3'd7;
                        end
                    end else begin
                        if (ptimer != 7'd127) ptimer <= ptimer + 7'd1;
                        if (ptimer == 7'd90) begin
                            if (ships != 4'd0) begin
                                palive <= 1'b1;
                                px     <= 9'd24;
                                py     <= 8'd120;
                                pinv   <= 8'd120;
                            end else begin
                                gstate   <= G_OVER;
                                pend     <= 1'b1;
                                pend_scr <= 2'd1;
                                if (score > hi) hi <= score;
                            end
                        end
                    end
                    st <= S_OBJ;
                    c  <= 13'd0;
                end

                S_OBJ: begin
                    if (ok < 4'd4) begin
                        if (bon[ob]) begin
                            if (bx[ob] >= 9'd308) bon[ob] <= 1'b0;
                            else                  bx[ob]  <= bx[ob] + 9'd4;
                        end
                    end else if (ok < 4'd8) begin
                        if (qon[ob]) begin
                            qx[ob] <= qx[ob] - 9'd2;
                            if (qvy[ob] == 2'd1)      qy[ob] <= qy[ob] + 8'd1;
                            else if (qvy[ob] == 2'd2) qy[ob] <= qy[ob] - 8'd1;
                            if (((qx[ob] - 9'd2) >= 9'd328 && (qx[ob] - 9'd2) <= 9'd500) ||
                                qy[ob] < 8'd16 || qy[ob] > 8'd232)
                                qon[ob] <= 1'b0;
                        end
                    end else begin
                        if (est[oe] == 2'd1) begin
                            ex[oe] <= e_nx;
                            if (e_gone) est[oe] <= 2'd0;
                            case (etype[oe])
                                2'd0: begin         // drone: wobble
                                    et[oe] <= et[oe] + 7'd1;
                                    ey[oe] <= wob_base - 8'd16 + {3'd0, wob_tri};
                                end
                                2'd1: begin         // dart: steer toward the ship
                                    if (ey[oe] + 8'd1 < py)      ey[oe] <= ey[oe] + 8'd1;
                                    else if (ey[oe] > py + 8'd1) ey[oe] <= ey[oe] - 8'd1;
                                end
                                default: begin      // turret: fire every 96 frames
                                    if (et[oe] >= 7'd95) begin
                                        if (ex[oe] < 9'd300 && ex[oe] > 9'd40 && q_free_any && palive) begin
                                            qx[q_free]  <= ex[oe];
                                            qy[q_free]  <= ey[oe] + 8'd4;
                                            qvy[q_free] <= aim(ey[oe] + 8'd4, py);
                                            qon[q_free] <= 1'b1;
                                        end
                                        et[oe] <= 7'd0;
                                    end else begin
                                        et[oe] <= et[oe] + 7'd1;
                                    end
                                end
                            endcase
                        end else if (est[oe] == 2'd2) begin
                            ex[oe] <= ex[oe] - {8'd0, scrolled};
                            if (et[oe] >= 7'd31) est[oe] <= 2'd0;
                            else                 et[oe]  <= et[oe] + 7'd1;
                        end
                    end
                    c <= c + 13'd1;
                    if (ok == 4'd15) begin
                        st <= S_BOSS;
                        c  <= 13'd0;
                    end
                end

                S_BOSS: begin
                    case (bst)
                        2'd1: begin
                            if (bsx > 9'd256) bsx <= bsx - 9'd1;
                            else              bst <= 2'd2;
                        end
                        2'd2: begin
                            if (bsup) begin
                                if (bsy <= 8'd36) bsup <= 1'b0;
                                else              bsy  <= bsy - 8'd1;
                            end else begin
                                if (bsy >= 8'd188) bsup <= 1'b1;
                                else               bsy  <= bsy + 8'd1;
                            end
                            if (bfire >= 6'd47) begin
                                bfire <= 6'd0;
                                if (q_free_any && palive) begin
                                    qx[q_free]  <= bsx;
                                    qy[q_free]  <= bsy + 8'd12;
                                    qvy[q_free] <= aim(bsy + 8'd12, py);
                                    qon[q_free] <= 1'b1;
                                end
                            end else begin
                                bfire <= bfire + 6'd1;
                            end
                        end
                        2'd3: begin
                            if (btimer != 7'd127) btimer <= btimer + 7'd1;
                            if (btimer == 7'd120 && gstate == G_PLAY) begin
                                gstate   <= G_CLEAR;
                                pend     <= 1'b1;
                                pend_scr <= 2'd2;
                                if (score > hi) hi <= score;
                            end
                        end
                        default: ;
                    endcase
                    st <= S_SPAWN;
                end

                S_SPAWN: begin
                    if (spawn_q[8:0] != 9'h1FF) begin
                        if ({1'b0, spawn_q[8:0]} == cur_col && camx[2:0] == 3'd0 && scrolled) begin
                            if (e_free_any) begin
                                ex[e_free]    <= 9'd320;
                                ey[e_free]    <= spawn_q[18:11];
                                ebase[e_free] <= spawn_q[18:11];
                                etype[e_free] <= spawn_q[10:9];
                                est[e_free]   <= 2'd1;
                                et[e_free]    <= 7'd40;
                            end
                            sp_ptr <= sp_ptr + 7'd1;
                        end else if ({1'b0, spawn_q[8:0]} < cur_col) begin
                            sp_ptr <= sp_ptr + 7'd1;    // missed: skip it
                        end
                    end
                    st <= S_COLL;
                    c  <= 13'd0;
                end

                S_COLL: begin
                    if (j[5] == 1'b0) begin
                        if (hit_be) begin
                            bon[jb] <= 1'b0;
                            est[je] <= 2'd2;
                            et[je]  <= 7'd0;
                            score   <= bcd_add(score, e_pts);
                        end
                    end else if (j[5:3] == 3'b100) begin
                        if (hit_pe) begin
                            palive  <= 1'b0;
                            ptimer  <= 7'd0;
                            ships   <= ships - 4'd1;
                            est[je] <= 2'd2;
                            et[je]  <= 7'd0;
                        end
                    end else if (j[5:2] == 4'b1010) begin
                        if (hit_bc) begin
                            bon[jb] <= 1'b0;
                            bflash  <= 3'd4;
                            if (bhp <= 6'd1) begin
                                bhp    <= 6'd0;
                                bst    <= 2'd3;
                                btimer <= 7'd0;
                                score  <= bcd_add(score, 24'h005000);
                            end else begin
                                bhp   <= bhp - 6'd1;
                                score <= bcd_add(score, 24'h000010);
                            end
                        end
                    end else if (j[5:2] == 4'b1011) begin
                        if (hit_pq) begin
                            palive  <= 1'b0;
                            ptimer  <= 7'd0;
                            ships   <= ships - 4'd1;
                            qon[jq] <= 1'b0;
                        end
                    end else begin
                        if (hit_pc) begin
                            palive <= 1'b0;
                            ptimer <= 7'd0;
                            ships  <= ships - 4'd1;
                        end
                    end
                    c <= c + 13'd1;
                    if (j == 6'd48) begin
                        st <= S_TERR;
                        c  <= 13'd0;
                    end
                end

                S_TERR: begin
                    if (tr_v && tr_solid) begin
                        if (tr_t < 4'd8) begin
                            if (palive) begin
                                palive <= 1'b0;
                                ptimer <= 7'd0;
                                ships  <= ships - 4'd1;
                            end
                        end else if (tr_t < 4'd12) begin
                            bon[tr_t[1:0]] <= 1'b0;
                            if (tr_crystal) begin
                                we    <= 1'b1;
                                waddr <= {1'b0, tr_addr};
                                wdata <= 32'd0;
                                score <= bcd_add(score, 24'h000050);
                            end
                        end else begin
                            qon[tr_t[1:0]] <= 1'b0;
                        end
                    end
                    c <= c + 13'd1;
                    if (c == 13'd16) begin
                        st <= S_OAM;
                        c  <= 13'd0;
                    end
                end

                S_OAM: begin
                    we    <= 1'b1;
                    waddr <= 13'h1000 | {7'd0, s};
                    wdata <= oam_e;
                    c     <= c + 13'd1;
                    if (s == 6'd63) begin
                        st <= S_HUD;
                        c  <= 13'd0;
                    end
                end

                S_HUD: begin
                    we    <= 1'b1;
                    waddr <= {1'b0, hud_a};
                    wdata <= {22'd0, 2'b01, hud_t};
                    c     <= c + 13'd1;
                    if (h == 6'd36) begin
                        st <= S_PAL;
                        c  <= 13'd0;
                    end
                end

                S_PAL: begin
                    we    <= 1'b1;
                    waddr <= 13'h1040 | {8'd0, pal_a};
                    wdata <= {26'd0, pal_v};
                    c     <= c + 13'd1;
                    if (c[2:0] == 3'd6) begin
                        st <= S_REGS;
                        c  <= 13'd0;
                    end
                end

                S_REGS: begin
                    we    <= 1'b1;
                    waddr <= 13'h1060 + {11'd0, c[1:0]};
                    case (c[1:0])
                        2'd0:    wdata <= {14'd0, 1'b1, 8'd0, 9'd0};                 // HUD
                        2'd1:    wdata <= (gstate == G_PLAY) ? {14'd0, 1'b0, 8'd0, camx[8:0]}
                                                             : {14'd0, 1'b1, 8'd0, 9'd0};
                        2'd2:    wdata <= 32'd16;
                        default: wdata <= 32'd7;
                    endcase
                    c <= c + 13'd1;
                    if (c[1:0] == 2'd3) st <= S_POST;
                end

                default: begin              // S_POST: a text screen to copy?
                    c   <= 13'd0;
                    v_d <= 1'b0;
                    if (pend) begin
                        pend     <= 1'b0;
                        cp_level <= 1'b0; cp_scr <= pend_scr; cp_row <= 5'd2;
                        cp_count <= 13'd1792;     cp_ret <= S_WAIT;
                        st <= S_COPY;
                    end else begin
                        st <= S_WAIT;
                    end
                end
            endcase
        end
    end

endmodule

`default_nettype wire
