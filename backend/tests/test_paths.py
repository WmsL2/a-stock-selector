"""Tests for deterministic application paths."""

from pathlib import Path

from stock_selector.config.paths import AppPaths


def test_paths_are_built_from_explicit_root(tmp_path: Path) -> None:
    """All application paths are derived from the provided project root."""
    paths = AppPaths.from_project_root(tmp_path)
    assert paths.project_root == tmp_path.resolve()
    assert paths.backend_dir == tmp_path / "backend"
    assert paths.runtime_dir == tmp_path / "runtime"
    assert paths.config_dir == tmp_path / "backend" / "config"
    assert paths.data_dir == tmp_path / "runtime" / "data"
    assert paths.raw_data_dir == tmp_path / "runtime" / "data" / "raw"
    assert paths.processed_data_dir == tmp_path / "runtime" / "data" / "processed"
    assert paths.metadata_dir == tmp_path / "runtime" / "data" / "metadata"
    assert paths.snapshots_dir == tmp_path / "runtime" / "snapshots"
    assert paths.logs_dir == tmp_path / "runtime" / "logs"


def test_path_construction_does_not_create_directories(tmp_path: Path) -> None:
    """Constructing paths is side-effect free."""
    paths = AppPaths.from_project_root(tmp_path)
    assert not paths.data_dir.exists()
    assert not paths.logs_dir.exists()
    assert not paths.snapshots_dir.exists()


def test_ensure_runtime_directories_creates_expected_paths(tmp_path: Path) -> None:
    """Runtime directory creation is an explicit operation."""
    paths = AppPaths.from_project_root(tmp_path)
    paths.ensure_runtime_directories()
    assert paths.data_dir.is_dir()
    assert paths.raw_data_dir.is_dir()
    assert paths.processed_data_dir.is_dir()
    assert paths.metadata_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert paths.snapshots_dir.is_dir()
    assert not paths.config_dir.exists()


def test_paths_do_not_change_current_working_directory(tmp_path: Path) -> None:
    """Path utilities never mutate the process working directory."""
    original_cwd = Path.cwd()
    paths = AppPaths.from_project_root(tmp_path)
    paths.ensure_runtime_directories()
    assert Path.cwd() == original_cwd


def test_default_workspace_root_is_package_derived_and_cwd_independent(
    monkeypatch, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """Default paths resolve the workspace rather than whichever directory invoked Python."""
    initial = AppPaths.from_project_root()
    monkeypatch.chdir(tmp_path)
    changed = AppPaths.from_project_root()
    assert initial.project_root == changed.project_root
    assert initial.backend_dir == initial.project_root / "backend"
    assert initial.runtime_dir == initial.project_root / "runtime"
