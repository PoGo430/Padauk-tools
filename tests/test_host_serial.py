"""Run the generated serial code on the PC: a timer signal plays the timer
interrupt, every interrupt records the PA7 level, and the recording is decoded
like a UART would. Checks the framing (start bit, 8 data bits LSB first, stop
bit), the sync character and the number printing.

ucsim doesn't simulate the Padauk timers, so this is how the bit-banging gets
tested. Needs a host C compiler (gcc or cc); skipped otherwise.
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

from padauk_studio import codegen, examples
from padauk_studio.gen_header import header_name

CC = shutil.which("gcc") or shutil.which("cc")
pytestmark = pytest.mark.skipif(not CC or sys.platform == "win32", reason="needs a POSIX C compiler")

HARNESS = r"""
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include "pdk_init.h"

static volatile unsigned char trace[100000];
static volatile int n;

static void tick(int sig)
{
  (void)sig;
  if (n >= (int)sizeof(trace))
    return;
  if (INTEN & INTEN_SERIAL) {          /* the timer interrupt is enabled */
    INTRQ &= (uint8_t)~INTRQ_SERIAL;
    pdk_serial_isr();
  }
  trace[n++] = (PA >> 7) & 1;           /* line level during this bit time */
}

int main(void)
{
  struct itimerval it = {{0, 50}, {0, 50}};
  signal(SIGALRM, tick);
  pdk_init();                           /* sends the 0x55 sync character */
  setitimer(ITIMER_REAL, &it, 0);
  serial_print("Hi ");
  serial_print_uint(0);
  serial_putc(' ');
  serial_print_uint(65535);
  serial_putc(' ');
  serial_print_uint(1203);
  serial_putc(' ');
  serial_print_hex(0x5A);
  serial_println("!");
  while (serial_bits_busy())
    ;
  for (int i = 0; i < 40; i++) {        /* some idle time at the end */
    int m = n;
    while (n == m)
      ;
  }
  it.it_value.tv_usec = it.it_interval.tv_usec = 0;
  setitimer(ITIMER_REAL, &it, 0);
  for (int i = 0; i < n; i++)
    putchar('0' + trace[i]);
  putchar('\n');
  return 0;
}
"""


def host_sources(folder, chip):
    """Turn the generated SDCC code into plain C: registers become variables."""
    h = open(os.path.join(folder, header_name(chip))).read()
    h = re.sub(r"__sfr __at\(0x[0-9a-f]+\) (\w+);", r"volatile uint8_t \1;", h)
    h = h.replace("__sfr16 _t16c;", "volatile uint16_t _t16c;")
    open(os.path.join(folder, header_name(chip)), "w").write(h)
    c = open(os.path.join(folder, "pdk_init.c")).read()
    c = re.sub(r"__asm\n.*?__endasm;", "", c, flags=re.S)
    c = re.sub(r"#if defined\(__SDCC_REVISION\).*?\n#endif\n\{.*?\n\}\n", "", c, flags=re.S)
    c += "\nint serial_bits_busy(void) { return serial_bits != 0; }\n"
    open(os.path.join(folder, "pdk_init.c"), "w").write(c)


def decode(bits):
    """UART decode, one sample per bit time."""
    out, i = [], 0
    while i < len(bits):
        if bits[i] == "0" and i + 9 < len(bits):
            byte = sum(1 << k for k in range(8) if bits[i + 1 + k] == "1")
            assert bits[i + 9] == "1", f"no stop bit after {byte:#x} at {i}"
            out.append(byte)
            i += 10
        else:
            i += 1
    return bytes(out)


@pytest.mark.parametrize("chip,timer", [("PFS154", "TM2"), ("PFS154", "TM3"), ("PMS150C", "TM2")])
def test_serial_output(tmp_path, chip, timer):
    p, code = examples.make_project("serial_hello", chip)
    p.data["serial"]["timer"] = timer
    p._sync_timers()
    folder = str(tmp_path)
    codegen.write_project(p, folder)
    host_sources(folder, p.chip)
    with open(os.path.join(folder, "harness.c"), "w") as f:
        f.write(HARNESS.replace("INTEN_SERIAL", f"INTEN_{timer}").replace("INTRQ_SERIAL", f"INTRQ_{timer}"))
    exe = os.path.join(folder, "harness")
    defines = ["-D__SDCC_" + p.chip.arch, "-D__asm__(x)=", "-D__interrupt(x)=", "-fcommon"]
    r = subprocess.run([CC, "-std=gnu99", "-w", "-I", folder, *defines, "-o", exe,
                        os.path.join(folder, "harness.c"), os.path.join(folder, "pdk_init.c")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    out = subprocess.run([exe], capture_output=True, text=True, timeout=60).stdout.strip()
    assert out.endswith("1" * 20), "line must idle high after sending"
    text = decode(out)
    assert text == b"\x55Hi 0 65535 1203 5A!\r\n", text
