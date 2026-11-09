"""Project workspaces: one notebook, one Docker kernel and one files folder per project.

Plan: docs/plans/notebook-workspace-plan.md
"""


class ErrorCode:
    """Error codes returned to the panel and the model (plan §4.2)."""

    NOT_FOUND = "NOT_FOUND"  # unknown project or cell id
    STALE = "STALE"  # the panel's version is out of date
    TOO_LARGE = "TOO_LARGE"  # cell source over 100 KB
    BAD_TYPE = "BAD_TYPE"  # cell type is not code or markdown
    BAD_NAME = "BAD_NAME"  # project name can't become a valid id
    BAD_PAYLOAD = "BAD_PAYLOAD"  # missing or wrongly typed action field
    NOT_CODE = "NOT_CODE"  # tried to run a note
    KERNEL_DEAD = "KERNEL_DEAD"  # the kernel container crashed
    KERNEL_UNAVAILABLE = "KERNEL_UNAVAILABLE"  # Docker isn't running
    TIMEOUT = "TIMEOUT"  # cell ran past the time limit


class WorkspaceError(Exception):
    """A rejected workspace action, with a code the panel can show."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message
