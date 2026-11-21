"""The Python that loads a dataset, the same as the panel's "Copy load code".

Kept equal to frontend/src/panel/lib/loadCode.ts by tests (tests/datasets/test_load_code.py): a pandas
reader per file extension, at most five tables, a folder listing when there
is no table file. Paths are written as quoted string literals, so a file name
can never become code.
"""

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from researchchat.workspace.datasets.service import DatasetRecordView

TABLES_MAX = 5  # same as loadCode.ts
# (file name suffixes, reader call with {path} for the quoted path) — same order as READERS in loadCode.ts
READERS: list[tuple[tuple[str, ...], str]] = [
    ((".csv", ".csv.gz"), "pd.read_csv({path})"),
    ((".tsv", ".tsv.gz"), 'pd.read_csv({path}, sep="\\t")'),
    ((".parquet",), "pd.read_parquet({path})"),
    ((".jsonl",), "pd.read_json({path}, lines=True)"),
    ((".json",), "pd.read_json({path})"),
    ((".xlsx", ".xls"), "pd.read_excel({path})"),
    ((".feather",), "pd.read_feather({path})"),
]


def load_code(view: "DatasetRecordView") -> str:
    """Load code for one dataset_list row: created files by their /work path, downloads by their files."""
    if view["origin"] == "created":
        return _created_load_code(view["path"])
    tables = [(path, template) for path in view["files"] if (template := _reader(path)) is not None]
    if not tables:
        return f"import os\n\nfolder = {_quoted(view['path'])}\nprint(sorted(os.listdir(folder)))\n"
    lines = ["import pandas as pd", ""]
    for i, (path, template) in enumerate(tables[:TABLES_MAX]):
        lines.append(f"{'df' if i == 0 else f'df{i + 1}'} = {template.format(path=_quoted(path))}")
    if len(tables) > TABLES_MAX:
        lines.append(f"# {len(tables) - TABLES_MAX} more data files in {view['path']}/")
    lines.append("df.head()")
    return "\n".join(lines) + "\n"


def _created_load_code(path: str) -> str:
    template = _reader(path)
    if template is None:
        return f"print(open({_quoted(path)}).read(2000))\n"
    return "\n".join(["import pandas as pd", "", f"df = {template.format(path=_quoted(path))}", "df.head()"]) + "\n"


def _reader(path: str) -> str | None:
    lowered = path.lower()
    return next((template for suffixes, template in READERS if lowered.endswith(suffixes)), None)


def _quoted(path: str) -> str:
    """A Python string literal for the path (json.dumps, like JSON.stringify in the panel): a name can't become code."""
    return json.dumps(path)
