"""Project workspaces: one notebook, one Docker kernel and one files folder per project.

Plan: docs/plans/done/notebook-workspace-plan.md
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
    # NB-3 dataset downloads (docs/plans/done/NB-3-dataset-download-plan.md §4.3)
    BAD_REF = "BAD_REF"  # empty or malformed dataset ref, or a URL on another host
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"  # a catalog without a file API (Kaggle, DataCite)
    NOT_PUBLIC = "NOT_PUBLIC"  # gated / private Hugging Face, restricted Zenodo
    NO_FILES = "NO_FILES"  # the file filter matched nothing, or the record has no files
    TOO_MANY_FILES = "TOO_MANY_FILES"  # more than max_files in one request
    NO_SPACE = "NO_SPACE"  # not enough free disk; details carry the sizes
    BUSY = "BUSY"  # delete while the dataset is downloading
    DECLINED = "DECLINED"  # the user pressed Skip / Keep or didn't answer
    DOWNLOAD_FAILED = "DOWNLOAD_FAILED"  # checksum, network, stall or disk full


class WorkspaceError(Exception):
    """A rejected workspace action, with a code the panel can show.

    `details` carries structured data for the model, e.g. NO_SPACE sizes.
    """

    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
