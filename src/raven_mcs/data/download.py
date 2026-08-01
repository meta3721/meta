"""Auditable raw-dataset downloads with provenance and checksums."""

from __future__ import annotations

import hashlib
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from raven_mcs.utils.config import repo_root_from_here
from raven_mcs.utils.serialization import dump_json, load_json, load_yaml


class DatasetDownloadError(RuntimeError):
    """Raised when an official dataset cannot be downloaded or verified."""


@dataclass(frozen=True)
class DownloadArtifact:
    filename: str
    url: str
    md5: str | None = None
    required: bool = True


@dataclass
class DownloadResult:
    dataset: str
    raw_root: Path
    files: list[dict[str, Any]] = field(default_factory=list)
    dry_run: bool = False
    resumed: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_dataset_download_config(dataset: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root_from_here()
    path = root / "configs" / "dataset" / f"{dataset}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset config: {path}")
    cfg = load_yaml(path)
    if "download" not in cfg:
        raise DatasetDownloadError(f"{dataset} config has no download: block")
    return cfg


def md5_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_stream_download(url: str, destination: Path, *, timeout: int = 600) -> int:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "raven-mcs-phase2b/0.2 (+research reproducibility)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, tmp.open(
            "wb"
        ) as out:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise DatasetDownloadError(f"HTTP {status} for {url}")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
            out.flush()
        size = tmp.stat().st_size
        if size <= 0:
            tmp.unlink(missing_ok=True)
            raise DatasetDownloadError(f"Empty download from {url}")
        tmp.replace(destination)
        return size
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise DatasetDownloadError(f"HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        tmp.unlink(missing_ok=True)
        raise DatasetDownloadError(f"Network error for {url}: {exc.reason}") from exc
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def _is_plausible_data_artifact(url: str) -> bool:
    lowered = url.lower()
    path = urlparse(lowered).path
    name = Path(path).name
    if name in {"humans.txt", "robots.txt"}:
        return False
    if lowered.rstrip("/").endswith("/download"):
        return False
    if "wp-content/themes/" in lowered:
        return False
    return path.endswith((".zip", ".rar", ".7z", ".tar.gz", ".tgz", ".csv", ".txt", ".pdf"))


def resolve_microsoft_download_links(page_url: str, *, timeout: int = 60) -> list[str]:
    """Best-effort scrape of absolute download URLs from an MSR HTML page."""
    request = urllib.request.Request(
        page_url,
        headers={"User-Agent": "raven-mcs-phase2b/0.2 (+research reproducibility)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        raise DatasetDownloadError(
            f"Failed to fetch provenance page {page_url}: {exc}"
        ) from exc
    candidates: list[str] = []
    for match in re.finditer(
        r"""(?:href|src)=["']([^"']+\.(?:zip|rar|7z|tar\.gz|tgz|csv|txt|pdf))["']""",
        html,
        flags=re.IGNORECASE,
    ):
        absolute = urljoin(page_url, match.group(1))
        if _is_plausible_data_artifact(absolute) and absolute not in candidates:
            candidates.append(absolute)
    return candidates


def artifacts_from_microsoft_page(
    page_url: str,
    *,
    prefer_all_zips: bool = False,
    filename_hints: tuple[str, ...] = (),
) -> list[DownloadArtifact]:
    """Resolve MSR page links into concrete download artifacts."""
    links = resolve_microsoft_download_links(page_url)
    zips = [link for link in links if link.lower().endswith(".zip")]
    if not zips and not links:
        raise DatasetDownloadError(
            f"No downloadable artifact found on official page: {page_url}"
        )
    selected = zips or links
    if filename_hints:
        hinted = [
            link
            for link in selected
            if any(hint.lower() in Path(urlparse(link).path).name.lower() for hint in filename_hints)
        ]
        if hinted:
            selected = hinted
    if not prefer_all_zips:
        selected = selected[:1]
    artifacts: list[DownloadArtifact] = []
    for link in selected:
        filename = Path(urlparse(link).path).name
        if not filename:
            continue
        artifacts.append(DownloadArtifact(filename=filename, url=link, required=True))
    if not artifacts:
        raise DatasetDownloadError(
            f"No usable download artifact resolved from official page: {page_url}"
        )
    return artifacts


def _artifacts_from_config(download_cfg: Mapping[str, Any]) -> list[DownloadArtifact]:
    artifacts: list[DownloadArtifact] = []
    for item in download_cfg.get("artifacts", []):
        if not isinstance(item, Mapping):
            raise DatasetDownloadError("download.artifacts entries must be mappings")
        artifacts.append(
            DownloadArtifact(
                filename=str(item["filename"]),
                url=str(item["url"]),
                md5=item.get("md5"),
                required=bool(item.get("required", True)),
            )
        )
    return artifacts


def download_dataset(
    dataset: str,
    *,
    data_root: Path,
    resume: bool = True,
    dry_run: bool = False,
    config_root: Path | None = None,
) -> DownloadResult:
    """Download official raw artifacts into data/raw/<dataset>/."""
    cfg = load_dataset_download_config(dataset, root=config_root)
    download_cfg = cfg["download"]
    name = str(cfg.get("name", dataset))
    raw_root = Path(data_root) / "raw" / name
    result = DownloadResult(dataset=name, raw_root=raw_root, dry_run=dry_run)

    artifacts = _artifacts_from_config(download_cfg)
    if not artifacts and download_cfg.get("resolve_from_page"):
        page = str(download_cfg["source_url"])
        prefer_all = bool(download_cfg.get("prefer_all_zips", False))
        hints = tuple(str(item) for item in download_cfg.get("filename_hints", []))
        if dry_run:
            result.files.append(
                {
                    "filename": "<resolved-from-page>",
                    "url": page,
                    "prefer_all_zips": prefer_all,
                    "filename_hints": list(hints),
                    "status": "would_resolve",
                }
            )
            return result
        try:
            artifacts = artifacts_from_microsoft_page(
                page, prefer_all_zips=prefer_all, filename_hints=hints
            )
        except DatasetDownloadError as exc:
            result.errors.append(str(exc))
            return result

    if not artifacts:
        result.errors.append(f"No download artifacts configured for {name}")
        return result

    if dry_run:
        for artifact in artifacts:
            result.files.append(
                {
                    "filename": artifact.filename,
                    "url": artifact.url,
                    "md5": artifact.md5,
                    "status": "would_download",
                }
            )
        return result

    raw_root.mkdir(parents=True, exist_ok=True)
    provenance_path = raw_root / "provenance.json"
    existing = load_json(provenance_path) if provenance_path.exists() else {"files": []}
    existing_by_name = {
        item["filename"]: item for item in existing.get("files", []) if "filename" in item
    }

    for artifact in artifacts:
        destination = raw_root / artifact.filename
        record: dict[str, Any] = {
            "filename": artifact.filename,
            "url": artifact.url,
            "expected_md5": artifact.md5,
            "downloaded_at": _utc_now(),
        }
        try:
            if destination.exists() and resume:
                size = destination.stat().st_size
                digest = md5_file(destination)
                if artifact.md5 and digest.lower() != str(artifact.md5).lower():
                    raise DatasetDownloadError(
                        f"Checksum mismatch for existing {destination}: "
                        f"got {digest}, expected {artifact.md5}"
                    )
                record.update(
                    {
                        "size_bytes": size,
                        "md5": digest,
                        "status": "resumed_existing",
                        "http_status": existing_by_name.get(artifact.filename, {}).get(
                            "http_status"
                        ),
                    }
                )
                result.resumed = True
            else:
                size = _atomic_stream_download(artifact.url, destination)
                digest = md5_file(destination)
                if artifact.md5 and digest.lower() != str(artifact.md5).lower():
                    destination.unlink(missing_ok=True)
                    raise DatasetDownloadError(
                        f"Checksum mismatch for {artifact.filename}: "
                        f"got {digest}, expected {artifact.md5}"
                    )
                record.update(
                    {
                        "size_bytes": size,
                        "md5": digest,
                        "status": "downloaded",
                        "http_status": 200,
                    }
                )
            result.files.append(record)
        except DatasetDownloadError as exc:
            if artifact.required:
                result.errors.append(str(exc))
            else:
                result.files.append(
                    {
                        **asdict(artifact),
                        "status": "optional_failed",
                        "error": str(exc),
                    }
                )

    provenance = {
        "dataset": name,
        "source_name": download_cfg.get("source_name"),
        "source_url": download_cfg.get("source_url"),
        "license": download_cfg.get("license"),
        "accessed_at": _utc_now(),
        "files": result.files,
        "ok": result.ok,
        "errors": result.errors,
    }
    dump_json(provenance, provenance_path)
    return result
