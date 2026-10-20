# Padauk project

Open this folder in VS Code: **Ctrl+Shift+B** builds. Use the status bar
buttons, or *Run Task*, for Flash / Monitor / Select device.

From a terminal: `pdk build`, `pdk flash`, `pdk monitor`,
`pdk set device=PFS122 clock=4M vdd=3.3` (or `make`, `make program`, `make run`, `make help`).

- `main.c`: your program (`setup()` runs once, `loop()` forever)
- `board.h`: pin assignments and pin helper macros
- `src/`: extra `.c` / `.h` files, built automatically
- `Makefile`: settings at the top (`DEVICE`, `F_CPU`, `TARGET_VDD_MV`)
- `include/`: free-pdk headers and helpers (`delay.h`, `millis.h`, `serial.h`)

Register names for your chip: `include/pdk/device/<chip>.h` and `include/pdk/device/periph/`
(or Ctrl+click a register name in VS Code).
