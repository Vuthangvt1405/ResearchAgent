"""The risky-code check.

Plan: docs/plans/notebook-workspace-plan.md section 7.
"""

import pytest

from researchchat.workspace import risk
from researchchat.workspace.risk import check

BASELINE = 'import pandas as pd\ndf = pd.read_csv("data.csv")\ndf.describe()'


# ---- Group 7: Risk check (AC11) · unit
# Baseline: Given `risk.check` · When it reads `df = pd.read_csv("data.csv"); df.describe()`


def test_normal_data_code_is_safe():
    # G7✅1 (baseline) · Demonstrates: everyday code never asks
    assert check(BASELINE) == []
    # Everyday methods that share names with risky ones
    assert check('s = "a-b".replace("-", "_")\ndf = df.rename(columns={"a": "b"})\n%matplotlib inline') == []


def test_web_download_is_safe():
    # G7✅2 (edge) · Demonstrates: reading the web is allowed (Q8)
    assert check('import requests\nhtml = requests.get("https://example.com").text') == []


def test_saving_chart_in_work_dir_is_safe():
    # G7✅3 (edge)
    assert check('import matplotlib.pyplot as plt\nplt.plot([1, 2])\nplt.savefig("a.png")\nopen("out.txt", "w").write("x")') == []


def test_danger_words_in_strings_are_safe():
    # G7✅4 (edge) · Demonstrates: the check reads code, not text
    assert check('print("rm -rf / os.system")  # os.system("x")') == []


def test_shell_line_is_risky():
    # G7❌1 (negative)
    assert check("!rm -rf data") == [risk.SHELL]
    assert check("files = !ls") == [risk.SHELL]


def test_bash_cell_magic_is_risky():
    # G7❌2 (negative)
    assert check("%%bash\nrm -rf data") == [risk.SHELL]


def test_subprocess_and_os_system_are_risky():
    # G7❌3 (negative)
    assert risk.SHELL in check('import subprocess\nsubprocess.run(["ls"])')
    assert risk.SHELL in check('import os\nos.system("ls")')
    assert risk.SHELL in check('from os import popen\npopen("ls")')


@pytest.mark.parametrize(
    "code",
    ['import os\nos.remove("a.csv")', 'import shutil\nshutil.rmtree("data")', 'from pathlib import Path\nPath(p).unlink()'],
)
def test_deleting_files_is_risky(code):
    # G7❌4 (negative)
    assert risk.DELETES in check(code)


@pytest.mark.parametrize(
    "code",
    ['import shutil\nshutil.move("a", "b")', 'import os\nos.rename("a", "b")', 'from pathlib import Path\nPath("a").rename("b")'],
)
def test_moving_files_is_risky(code):
    # G7❌5 (negative)
    assert risk.MOVES in check(code)


@pytest.mark.parametrize(
    "code",
    ['open("/etc/x", "w")', 'open("../x", "w")', 'open("C:\\\\x.txt", mode="a")', 'df.to_csv("../../leak.csv")'],
)
def test_write_outside_work_dir_is_risky(code):
    # G7❌6 (negative)
    assert risk.WRITES_OUTSIDE in check(code)


def test_package_install_is_risky():
    # G7❌7 (negative)
    assert check("%pip install requests") == [risk.INSTALLS]
    assert risk.INSTALLS in check("!pip install requests")


@pytest.mark.parametrize(
    "code",
    ["eval(s)", "exec(s)", '__import__("os")', "import importlib\nimportlib.import_module(n)", 'getattr(os, name)("ls")'],
)
def test_dynamic_code_is_risky(code):
    # G7❌8 (negative) · Demonstrates: obfuscation is caught (#12)
    assert risk.HIDDEN_CODE in check(code)


@pytest.mark.parametrize("code", ["import ctypes", "import os\nos.fork()", "import socket\ns = socket.socket()\ns.bind(('', 80))"])
def test_low_level_access_is_risky(code):
    # G7❌9 (negative)
    assert risk.LOW_LEVEL in check(code)


@pytest.mark.parametrize(
    "code",
    [
        'import requests\nrequests.post(url, data=open("data.csv").read())',
        "import requests\ns = requests.Session()\ns.put(url, data=b)",
        "import smtplib",
    ],
)
def test_upload_is_risky(code):
    # G7❌10 (negative) · Demonstrates: (#13)
    assert risk.SENDS_DATA in check(code)


def test_unparseable_code_is_risky():
    # G7❌11 (negative) · Demonstrates: unknown means ask
    assert check("def (:") == [risk.UNPARSEABLE]


def test_alias_import_is_still_caught():
    # G7❌12 (negative) · Demonstrates: simple renames don't hide calls
    assert risk.SHELL in check('import subprocess as sp\nsp.run(["ls"])')
    assert risk.DELETES in check('from shutil import rmtree as nuke\nnuke("data")')
