"""Which datasets say nothing about themselves, so the assistant should look and describe them.

A ready row that has no catalog description, no assistant description and no
known column names needs a description ("write"). Every file in the project may
be read without asking the user, whoever added it. Pure functions, no I/O.
"""

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from sillytherin.workspace.datasets.service import DatasetRecordView

DescribeNeed = Literal["write"]
DESCRIPTION_MAX = 300  # one line, like catalog descriptions
ELLIPSIS = "…"


def describe_need(view: "DatasetRecordView") -> DescribeNeed | None:
    """"write" for a ready row that says nothing about itself; None when it already does or isn't ready.

    Where the data came from (a pasted link, an upload, a cell) does not matter: any project file may be read.
    """
    if view["status"] != "ready" or view.get("description") or view.get("assistant_description"):
        return None
    if view["origin"] == "created" and view.get("columns") != []:  # names known, or not read yet
        return None
    return "write"


def one_line(text: object, limit: int) -> str:
    """Printable characters only, whitespace runs as one space, at most `limit` chars ("…" when cut).

    Names and descriptions go into what the model reads, so stored text must never add lines to it.
    """
    printable = "".join(c if c.isprintable() else " " for c in str(text))
    line = " ".join(printable.split())
    if len(line) <= limit:
        return line
    return line[: limit - 1].rstrip() + ELLIPSIS


def one_line_description(text: str) -> str:
    """A description as one line of at most DESCRIPTION_MAX chars."""
    return one_line(text, DESCRIPTION_MAX)


LOOK_FIRST_NAMES_SHOWN = 5  # enough to recognise the data; the full list is in dataset_list


def look_first_message(names: list[str]) -> str:
    """Tells the model to look at the project's undescribed data before it fetches new data."""
    shown = ", ".join(names[:LOOK_FIRST_NAMES_SHOWN])
    return (f"The project already has data that says nothing about itself: {shown}. Look at its first rows with "
            "notebook_run (its load_code is in dataset_list) before downloading anything: it may be what the user "
            "wants. If it isn't, download after that.")
