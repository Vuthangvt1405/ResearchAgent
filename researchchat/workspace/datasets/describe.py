"""Which datasets say nothing about themselves, so the assistant should look and describe them.

A ready row that has no catalog description, no assistant description and no
known column names needs a description ("write"). Every file in the project may
be read without asking the user, whoever added it. Pure functions, no I/O.
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from researchchat.workspace.datasets.service import DatasetRecordView

DescribeNeed = Literal["write"]
DESCRIPTION_MAX = 300  # one line, like catalog descriptions
def describe_need(view: "DatasetRecordView", *, is_link: bool = False, created_by: str | None = None) -> DescribeNeed | None:
    """"write" for a ready row that says nothing about itself; None when it already does or isn't ready.

    `is_link` and `created_by` are kept for callers; they no longer change the answer, since any file may be read.
    """
    if view["status"] != "ready" or view.get("description") or view.get("assistant_description"):
        return None
    if view["origin"] == "created" and view.get("columns") != []:  # names known, or not read yet
        return None
    return "write"


def one_line_description(text: str) -> str:
    """Printable characters only, whitespace runs as one space, at most DESCRIPTION_MAX chars ("…" when cut)."""
    printable = "".join(c if c.isprintable() else " " for c in str(text))
    line = " ".join(printable.split())
    if len(line) <= DESCRIPTION_MAX:
        return line
    return line[: DESCRIPTION_MAX - 1].rstrip() + "…"
