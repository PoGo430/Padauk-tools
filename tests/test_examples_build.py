"""Every example, generated and compiled for every chip it supports."""
import os

import pytest

from padauk_studio import checks, codegen, examples, toolchain

SDCC, _ = toolchain.find_tool("sdcc")
CASES = [(e["key"], c) for e in examples.EXAMPLES for c in e["chips"]]


@pytest.mark.parametrize("key,chip", CASES)
def test_example(tmp_path, key, chip):
    p, code = examples.make_project(key, chip)
    errs = checks.errors(p)
    assert not errs, errs
    folder = str(tmp_path / f"{key}_{chip}")
    os.makedirs(folder)
    with open(os.path.join(folder, "main.c"), "w") as f:
        f.write(examples.main_with_code(code))
    codegen.write_project(p, folder)
    main = open(os.path.join(folder, "main.c")).read()
    for body in code.values():
        assert body in main, "example code missing from main.c"
    assert "#if 0" not in main, "example code ended up in removed sections"
    if not SDCC:
        pytest.skip("sdcc not found")
    res = toolchain.build(p)
    assert res.ok, res.log + "\n".join(f"{m.file}:{m.line}: {m.text}" for m in res.messages)
    warnings = [m for m in res.messages if m.kind == "warning"]
    assert not warnings, warnings
    assert 0 < res.rom_words <= p.chip.reserved_rom[0]
