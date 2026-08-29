"""Stable project paths for the application."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    """Workspace-aware paths without changing process state or relying on CWD."""

    project_root: Path
    backend_dir: Path
    runtime_dir: Path
    config_dir: Path
    data_dir: Path
    raw_data_dir: Path
    processed_data_dir: Path
    metadata_dir: Path
    snapshots_dir: Path
    logs_dir: Path

    @classmethod
    def from_project_root(cls, project_root: Path | None = None) -> "AppPaths":
        """Construct application paths from an explicit or package-derived root."""
        root = project_root.resolve() if project_root is not None else cls._default_root()
        backend_dir = root / "backend"
        runtime_dir = root / "runtime"
        data_dir = runtime_dir / "data"
        return cls(
            project_root=root,
            backend_dir=backend_dir,
            runtime_dir=runtime_dir,
            config_dir=backend_dir / "config",
            data_dir=data_dir,
            raw_data_dir=data_dir / "raw",
            processed_data_dir=data_dir / "processed",
            metadata_dir=data_dir / "metadata",
            snapshots_dir=runtime_dir / "snapshots",
            logs_dir=runtime_dir / "logs",
        )

    @staticmethod
    def _default_root() -> Path:
        """Derive the editable-install project root from this module's location."""
        return Path(__file__).resolve().parents[4]

    def ensure_runtime_directories(self) -> None:
        """Create only directories intended for local runtime output."""
        for directory in (
            self.data_dir,
            self.raw_data_dir,
            self.processed_data_dir,
            self.metadata_dir,
            self.snapshots_dir,
            self.logs_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
