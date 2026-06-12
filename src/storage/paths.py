"""Persistente Speicherpfade fuer lokale Box-Daten."""

import os
import shutil
import sys
from pathlib import Path
from typing import List

from src.utils.logging import get_logger

logger = get_logger(__name__)


def programdata_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("PROGRAMDATA") or os.environ.get("ALLUSERSPROFILE") or r"C:\ProgramData"
        return Path(base) / "FexoBox"
    return Path.home() / ".fexobooth"


def _fallback_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "FexoBox"
        return Path.home() / "AppData" / "Local" / "FexoBox"
    return Path.home() / ".fexobooth"


def _can_write_file_target(path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with open(path, "a", encoding="utf-8"):
                pass
            return True

        probe = path.parent / f".write_test_{os.getpid()}.tmp"
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def _writable_target(filename: str) -> Path:
    target = programdata_dir() / filename
    if _can_write_file_target(target):
        return target

    fallback = _fallback_data_dir() / filename
    fallback.parent.mkdir(parents=True, exist_ok=True)
    logger.warning(
        f"ProgramData nicht beschreibbar ({target}); nutze update-sicheren Fallback: {fallback}"
    )
    return fallback


def persistent_data_path(filename: str) -> Path:
    """Gibt den update-sicheren ProgramData-Pfad zurueck und migriert Altdateien."""
    target = _writable_target(filename)

    if not target.exists():
        migration_sources = []
        programdata_target = programdata_dir() / filename
        if programdata_target != target:
            migration_sources.append(programdata_target)
        migration_sources.extend(legacy_data_paths(filename))

        for legacy in migration_sources:
            try:
                if legacy.exists() and legacy.resolve() != target.resolve():
                    shutil.copy2(legacy, target)
                    logger.info(f"Persistente Datei migriert: {legacy} -> {target}")
                    break
            except Exception as e:
                logger.warning(f"Migration von {legacy} nach {target} fehlgeschlagen: {e}")

    return target


def legacy_data_paths(filename: str) -> List[Path]:
    """Bekannte alte Speicherorte im Installationsordner."""
    paths: List[Path] = []

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        paths.extend([
            exe_dir / filename,
            exe_dir / "_internal" / filename,
        ])

    repo_or_internal = Path(__file__).resolve().parents[2]
    paths.extend([
        repo_or_internal / filename,
        Path.cwd() / filename,
        Path("C:/FexoBooth") / filename,
        Path("C:/FexoBooth/_internal") / filename,
        Path("C:/fexobooth/fexobooth-v2") / filename,
    ])

    unique: List[Path] = []
    seen = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique
