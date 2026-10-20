# Padauk project

Settings are at the top of the `Makefile` (`DEVICE`, `F_CPU`, `TARGET_VDD_MV`).

```sh
make              # build + ROM/RAM usage
make program      # write the chip
make run          # power the chip from the programmer, show serial output (PA7)
make help         # all targets
```

- `main.c`: your program (`setup()` runs once, `loop()` forever)
- `board.h`: pin assignments and pin helper macros
- `src/`: put extra `.c` / `.h` files here, they're built automatically
- `include/`: free-pdk headers and helpers (`delay.h`, `millis.h`, `serial.h`)

Register names for your chip: `include/pdk/device/<chip>.h` and `include/pdk/device/periph/`.
