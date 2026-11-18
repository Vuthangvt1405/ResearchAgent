"""PCD-4: the app's load code is the same as the panel's "Copy load code" (loadCode.ts).
"""

import json
import re
from pathlib import Path

from researchchat.workspace.datasets.load_code import READERS, load_code

LOAD_CODE_TS = Path(__file__).resolve().parents[1] / "public/panel/src/lib/loadCode.ts"
IRIS = "/work/datasets/hf-scikit-learn--iris"


def download(*files: str, path: str = IRIS) -> dict:
    """A dataset_list row for a download: `files` are /work paths, as DatasetRecordView has them."""
    return {"origin": "downloaded", "path": path, "files": [f"{path}/{f}" for f in files]}


def created(path: str) -> dict:
    return {"origin": "created", "path": path, "files": [path]}


def panel_readers() -> list[tuple[str, str]]:
    """(regex, reader template) pairs from READERS in loadCode.ts, e.g. ('\\.csv(\\.gz)?', 'pd.read_csv(${p})')."""
    text = LOAD_CODE_TS.read_text()
    return re.findall(r"\[/(.+?)\$/i, \(p\) => `(.+?)`\]", text)


# ---- PCD-4 Group 2 — Load code is the same as the tab's  (Q2) · unit
# Plan: docs/plans/PCD-4-reuse-existing-dataset-plan.md §7
# Baseline: Given a ready download with `iris.csv` · When `load_code(view)`


def test_download_csv_load_code_matches_the_panel():
    # ✅1 · Changed: —
    # Then: `import pandas as pd\n\ndf = pd.read_csv("/work/datasets/hf-scikit-learn--iris/iris.csv")\ndf.head()\n`
    # Demonstrates: same code as the tab
    assert load_code(download("iris.csv")) == (
        'import pandas as pd\n\ndf = pd.read_csv("/work/datasets/hf-scikit-learn--iris/iris.csv")\ndf.head()\n'
    )


def test_created_file_load_code_reads_its_work_path():
    # ✅2 · Changed: created `/work/data.csv`
    # Then: `pd.read_csv("/work/data.csv")`
    assert load_code(created("/work/data.csv")) == 'import pandas as pd\n\ndf = pd.read_csv("/work/data.csv")\ndf.head()\n'


def test_every_panel_reader_is_used():
    # ✅3 · Changed: `.tsv`, `.tsv.gz`, `.parquet`, `.jsonl`, `.json`, `.xlsx`, `.feather`
    # Then: same reader as `loadCode.ts`
    # Demonstrates: no format loads differently from the tab
    readers = panel_readers()
    assert len(readers) == len(READERS)  # a reader added on one side only fails here
    for suffixes, _template in READERS:
        for suffix in suffixes:
            name = f"/work/t{suffix.upper()}"  # the panel matches without case
            pattern, ts_template = next((p, t) for p, t in readers if re.search(p + "$", name, re.IGNORECASE))
            expected_call = ts_template.replace("${p}", json.dumps(name)).replace("\\\\t", "\\t")
            assert f"df = {expected_call}\n" in load_code(created(name)), (suffix, pattern)


def test_more_than_five_tables_adds_a_comment():
    # ✅4 · Changed: 7 CSVs
    # Then: 5 `df` lines + `# 2 more data files in …/`
    code = load_code(download(*[f"t{i}.csv" for i in range(7)]))
    lines = code.splitlines()
    assert [line.split(" = ")[0] for line in lines if " = pd." in line] == ["df", "df2", "df3", "df4", "df5"]
    assert f"# 2 more data files in {IRIS}/" in lines
    assert lines[-1] == "df.head()"


def test_download_without_data_files_lists_the_folder():
    # ❌1 · Changed: only `.txt`
    # Then: `os.listdir` code
    assert load_code(download("README.txt")) == f'import os\n\nfolder = "{IRIS}"\nprint(sorted(os.listdir(folder)))\n'


def test_created_non_table_file_prints_its_start():
    # ❌2 · Changed: unknown extension
    # Then: `print(open("/work/x").read(2000))`
    assert load_code(created("/work/x")) == 'print(open("/work/x").read(2000))\n'
