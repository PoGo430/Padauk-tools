"""Generated projects read cleanly in clangd (the .clangd file Studio writes)."""
import os
import shutil
import subprocess

import pytest

from padauk_studio import codegen, examples
from padauk_studio.project import Project, default_project

CLANGD = shutil.which("clangd")
CASES = [(e["key"], c) for e in examples.EXAMPLES for c in e["chips"]]


def test_clangd_file_follows_chip_unless_edited(tmp_path):
    folder = str(tmp_path)
    path = os.path.join(folder, codegen.CLANGD_FILE)
    p = Project(default_project("PFS154", "c"))
    codegen.write_project(p, folder)
    assert "-D__SDCC_pdk14" in open(path).read()
    p.set_chip("PMS150C")
    assert codegen.CLANGD_FILE in codegen.write_project(p, folder)
    assert "-D__SDCC_pdk13" in open(path).read()
    assert codegen.CLANGD_FILE not in codegen.write_project(p, folder)
    open(path, "w").write("CompileFlags:\n  Add: [-DMINE]\n")
    p.set_chip("PFS154")
    codegen.write_project(p, folder)
    assert open(path).read() == "CompileFlags:\n  Add: [-DMINE]\n"


@pytest.mark.skipif(not CLANGD, reason="clangd not found")
@pytest.mark.parametrize("key,chip", CASES)
def test_clangd_no_errors(tmp_path, key, chip):
    p, code = examples.make_project(key, chip)
    folder = str(tmp_path / f"{key}_{chip}")
    os.makedirs(folder)
    with open(os.path.join(folder, "main.c"), "w") as f:
        f.write(examples.main_with_code(code))
    codegen.write_project(p, folder)
    for name in sorted(os.listdir(folder)):
        if not name.endswith((".c", ".h")):
            continue
        res = subprocess.run([CLANGD, "--check=" + name], cwd=folder,
                             capture_output=True, text=True, timeout=120)
        log = res.stdout + res.stderr
        assert "All checks completed, 0 errors" in log, name + "\n" + log[-3000:]
