"""What each tool needs from the app's services, as small Protocols.

The app passes DatasetService and NotebookService; tests pass fakes that have
only the methods a tool calls.
"""

from collections.abc import Awaitable, Callable
from typing import Protocol

from sillytherin.workspace.datasets.service import (
    Approve,
    DatasetRecordView,
    DeleteResult,
    DownloadStarted,
)


class DatasetLister(Protocol):
    def list_for_model(self, project_id: str) -> list[DatasetRecordView]: ...


class UndescribedDatasets(Protocol):
    def needs_description(self, project_id: str) -> list[DatasetRecordView]: ...


class ProjectDatasetLookup(UndescribedDatasets, Protocol):
    def project_refs(self, project_id: str) -> dict[str, DatasetRecordView]: ...


class DatasetDownloader(ProjectDatasetLookup, Protocol):
    async def request(
        self,
        project_id: str,
        session_id: str,
        ref: str,
        files: list[str] | None = None,
        update: bool = False,
        *,
        approve: Approve,
        pasted_links: frozenset[str] = frozenset(),
    ) -> DownloadStarted: ...


class DatasetDescriber(Protocol):
    def view_for_model(self, project_id: str, dataset_id: str) -> DatasetRecordView: ...

    async def save_description(self, project_id: str, dataset_id: str, text: str) -> DatasetRecordView: ...


class DatasetDeleter(Protocol):
    def describe(self, project_id: str, dataset_id: str) -> DatasetRecordView: ...

    async def delete(self, project_id: str, dataset_id: str) -> DeleteResult: ...


class NotebookReader(Protocol):
    async def read_for_model(self, project_id: str) -> str: ...


class NotebookRunner(Protocol):
    async def run_for_model(self, project_id: str, code: str) -> str: ...


ConfirmRetry = Callable[[str, str | None], Awaitable[bool]]  # (name, reason) -> Download again?
ApproveDelete = Callable[[str, int, int], Awaitable[bool]]  # (name, frees_bytes, shared_with) -> Delete?
ApproveRun = Callable[[str, list[str]], Awaitable[bool]]  # (code, risk reasons) -> Run?
