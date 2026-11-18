#!/bin/sh
set -e
here=$(dirname "$0")
proj=$(cd "$here/.." && pwd)
V=${VERILATOR:-verilator}
mkdir -p "$proj/sim/out"
cd "$proj/src"
"$V" --cc --exe --build -O3 -j 4 --x-assign fast --x-initial unique \
    -MAKEFLAGS "CXX=${CXX:-g++} LINK=${CXX:-g++} AR=${AR:-ar} OPT_FAST=-O2" \
    -Wno-fatal -Wno-EOFNEWLINE -Wno-DECLFILENAME -Wno-WIDTHEXPAND -Wno-UNUSEDSIGNAL \
    --public-flat-rw --top-module tt_um_hextex_cavepatrol \
    --Mdir "$proj/sim/out/obj" -o sim_game \
    tt_um_hextex_cavepatrol.v game_cpu.v ppu.v vga_timing.v chr_rom.v gamepad_pmod_rx.v \
    "$proj/sim/sim_game.cpp" > "$proj/sim/out/verilator_build.log" 2>&1 \
    || { tail -30 "$proj/sim/out/verilator_build.log"; exit 1; }
"$proj/sim/out/obj/sim_game" "${1:-all}"
python3 "$proj/sim/frames_to_png.py"
