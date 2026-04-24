#!/usr/bin/env python3
"""DATA-2 — batch Productivity Brain loader.

Uploads every .xlsx file in a folder to the Railway PB API one at a time,
prints per-file results, then echoes a summary block + the server's own
/stats counts as a belt-and-suspenders cross-check.

Server-side dedup (MD5 hash) means re-running this script against an
already-loaded folder is safe — duplicates are reported as
status="skipped" and counted as success for the exit code.

Usage:
    python apex/scripts/load_pb_batch.py --folder /path/to/xlsx/files
    python apex/scripts/load_pb_batch.py --folder ./pb_files --dry-run
    python apex/scripts/load_pb_batch.py --folder ./pb_files --skip-existing

Exit codes:
    0   every file ingested or skipped (duplicate)
    1   one or more files errored, OR the API was unreachable / unauthorized
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import httpx

# --------------------------------------------------------------------------
# Defaults
# --------------------------------------------------------------------------
DEFAULT_BASE_URL = "https://web-production-f87116.up.railway.app"
DEFAULT_USERNAME = "admin@summitbuilders.com"
DEFAULT_PASSWORD = "admin123"
HTTP_TIMEOUT = 120.0  # multipart upload + parse can be slow on large xlsx

EXIT_OK = 0
EXIT_FAILED = 1


# --------------------------------------------------------------------------
# Logging — same shape as validate_18_4_1.py for visual consistency
# --------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("load_pb_batch")


# --------------------------------------------------------------------------
# Data classes
# --------------------------------------------------------------------------
@dataclass
class Config:
    folder: Path
    base_url: str
    username: str
    password: str
    dry_run: bool
    skip_existing: bool


@dataclass
class FileResult:
    filename: str
    status: str  # "ingested" | "skipped" | "error" | "skipped_pre"
    project_name: str | None = None
    line_items: int = 0
    detail: str = ""  # human-readable note for the report

    @property
    def is_failure(self) -> bool:
        return self.status == "error"


@dataclass
class BatchSummary:
    folder: Path
    total_found: int
    results: list[FileResult] = field(default_factory=list)

    @property
    def ingested(self) -> list[FileResult]:
        return [r for r in self.results if r.status == "ingested"]

    @property
    def skipped(self) -> list[FileResult]:
        return [r for r in self.results if r.status in ("skipped", "skipped_pre")]

    @property
    def errored(self) -> list[FileResult]:
        return [r for r in self.results if r.status == "error"]

    @property
    def total_line_items(self) -> int:
        return sum(r.line_items for r in self.ingested)


# --------------------------------------------------------------------------
# Config + auth
# --------------------------------------------------------------------------
def parse_config() -> Config:
    parser = argparse.ArgumentParser(description="Batch Productivity Brain loader (DATA-2)")
    parser.add_argument("--folder", required=True, help="Folder containing .xlsx files")
    parser.add_argument("--base-url", default=os.getenv("APEX_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--username", default=os.getenv("APEX_USERNAME", DEFAULT_USERNAME))
    parser.add_argument("--password", default=os.getenv("APEX_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be uploaded; no POST",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Pre-filter against GET /projects to skip filenames already loaded",
    )
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        log.error("Folder does not exist or is not a directory: %s", folder)
        sys.exit(EXIT_FAILED)

    return Config(
        folder=folder,
        base_url=args.base_url.rstrip("/"),
        username=args.username,
        password=args.password,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
    )


def login(client: httpx.Client, cfg: Config) -> None:
    """POST /api/auth/login, install Authorization header on the client."""
    try:
        resp = client.post(
            "/api/auth/login",
            json={"email": cfg.username, "password": cfg.password},
        )
    except httpx.HTTPError as exc:
        log.error("Login request failed for %s: %r", cfg.base_url, exc)
        sys.exit(EXIT_FAILED)

    if resp.status_code != 200:
        log.error("Login returned HTTP %d: %s", resp.status_code, resp.text[:300])
        sys.exit(EXIT_FAILED)

    token = resp.json().get("access_token")
    if not token:
        log.error("Login response missing access_token: %r", resp.json())
        sys.exit(EXIT_FAILED)

    client.headers["Authorization"] = f"Bearer {token}"
    log.info("Authenticated as %s", cfg.username)


# --------------------------------------------------------------------------
# File discovery
# --------------------------------------------------------------------------
def discover_xlsx(folder: Path) -> list[Path]:
    """Return sorted list of .xlsx files in *folder*, excluding Office temp
    files (basenames starting with ~ — the convention productivity_brain/
    scripts/ingest.py:285 already uses)."""
    files = sorted(folder.glob("*.xlsx"))
    files = [f for f in files if not f.name.startswith("~")]
    return files


def fetch_existing_project_names(client: httpx.Client) -> set[str]:
    """GET /projects and return the set of currently-loaded project names.
    Returns empty set on transient error — the script falls through to
    server-side hash dedup which is the authoritative guard."""
    try:
        resp = client.get("/api/library/productivity-brain/projects")
        if resp.status_code != 200:
            log.warning(
                "GET /projects returned HTTP %d — falling back to server-side dedup",
                resp.status_code,
            )
            return set()
        data = resp.json().get("data") or []
        return {p.get("name") for p in data if p.get("name")}
    except httpx.HTTPError as exc:
        log.warning(
            "GET /projects failed (%r) — falling back to server-side dedup", exc
        )
        return set()


# --------------------------------------------------------------------------
# Upload
# --------------------------------------------------------------------------
def upload_one(client: httpx.Client, path: Path) -> FileResult:
    """POST a single xlsx to /upload. Returns a FileResult capturing the
    server's verdict — never raises (network/HTTP errors map to status="error")."""
    try:
        with path.open("rb") as fh:
            files = {
                "files": (
                    path.name,
                    fh,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
            resp = client.post(
                "/api/library/productivity-brain/upload", files=files
            )
    except httpx.HTTPError as exc:
        return FileResult(
            filename=path.name,
            status="error",
            detail=f"HTTP error: {exc!r}",
        )

    if resp.status_code != 200:
        return FileResult(
            filename=path.name,
            status="error",
            detail=f"HTTP {resp.status_code}: {resp.text[:200]}",
        )

    body = resp.json()
    if not body.get("success"):
        return FileResult(
            filename=path.name,
            status="error",
            detail=body.get("error", "endpoint returned success=False"),
        )

    # /upload returns a list of per-file results even when we sent one file.
    per_file = (body.get("data") or [{}])[0]
    status = per_file.get("status", "error")

    if status == "ingested":
        return FileResult(
            filename=path.name,
            status="ingested",
            project_name=per_file.get("name"),
            line_items=per_file.get("line_items", 0) or 0,
            detail=per_file.get("format", ""),
        )
    if status == "skipped":
        reason = per_file.get("reason", "duplicate")
        return FileResult(
            filename=path.name,
            status="skipped",
            project_name=per_file.get("name"),
            detail=f"{reason} (project_id={per_file.get('project_id')})",
        )
    return FileResult(
        filename=path.name,
        status="error",
        detail=per_file.get("error") or per_file.get("reason") or "unknown error",
    )


# --------------------------------------------------------------------------
# Stats echo
# --------------------------------------------------------------------------
def fetch_stats(client: httpx.Client) -> dict:
    """GET /stats; return data dict or empty on error."""
    try:
        resp = client.get("/api/library/productivity-brain/stats")
    except httpx.HTTPError as exc:
        log.warning("GET /stats failed: %r", exc)
        return {}
    if resp.status_code != 200:
        log.warning("GET /stats returned HTTP %d", resp.status_code)
        return {}
    return resp.json().get("data") or {}


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def print_summary(cfg: Config, summary: BatchSummary, stats: dict) -> None:
    sep = "=" * 65
    print()
    print(sep)
    print("PB BATCH LOAD SUMMARY")
    print(sep)
    print(f"Folder:                    {cfg.folder}")
    print(f"Total files found:         {summary.total_found}")
    print(
        f"Successfully loaded:       {len(summary.ingested):<3d}"
        f"({summary.total_line_items:,} line items)"
    )
    print(f"Skipped (duplicate):       {len(summary.skipped)}")
    print(f"Failed:                    {len(summary.errored)}")

    if summary.errored:
        print()
        print("Failed files:")
        for r in summary.errored:
            print(f"  - {r.filename}: {r.detail}")

    if stats:
        proj_count = stats.get("project_count") or stats.get("projects") or "?"
        item_count = (
            stats.get("line_item_count")
            or stats.get("total_line_items")
            or stats.get("line_items")
            or "?"
        )
        print()
        print(
            f"Post-load PB stats: GET /stats returned "
            f"{proj_count} projects, {item_count} items"
        )
    print(sep)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main() -> int:
    cfg = parse_config()
    log.info("Folder: %s", cfg.folder)
    log.info("Target: %s", cfg.base_url)
    if cfg.dry_run:
        log.info("DRY RUN — no uploads will happen")

    files = discover_xlsx(cfg.folder)
    log.info("Discovered %d .xlsx files (excluding ~temp)", len(files))
    summary = BatchSummary(folder=cfg.folder, total_found=len(files))

    if not files:
        print_summary(cfg, summary, {})
        return EXIT_OK

    if cfg.dry_run:
        for f in files:
            print(f"  would upload: {f.name}")
        print_summary(cfg, summary, {})
        return EXIT_OK

    with httpx.Client(base_url=cfg.base_url, timeout=HTTP_TIMEOUT) as client:
        login(client, cfg)

        existing_names: set[str] = set()
        if cfg.skip_existing:
            existing_names = fetch_existing_project_names(client)
            log.info(
                "skip-existing: %d project names already loaded — pre-filtering",
                len(existing_names),
            )

        for f in files:
            if f.name in existing_names:
                log.info("Loading %s ... ⤼ skipped (name already loaded, no upload)", f.name)
                summary.results.append(
                    FileResult(
                        filename=f.name,
                        status="skipped_pre",
                        detail="pre-filter: name already in /projects",
                    )
                )
                continue

            log.info("Loading %s ...", f.name)
            result = upload_one(client, f)
            summary.results.append(result)

            if result.status == "ingested":
                log.info(
                    "  ✓ %s: %d line items (%s)",
                    result.project_name or f.name,
                    result.line_items,
                    result.detail or "format unknown",
                )
            elif result.status == "skipped":
                log.info("  ⤼ %s: %s", f.name, result.detail)
            else:
                log.error("  ✗ %s: %s", f.name, result.detail)

        stats = fetch_stats(client)

    print_summary(cfg, summary, stats)
    return EXIT_FAILED if summary.errored else EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
