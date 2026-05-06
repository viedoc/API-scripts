"""CSV-driven multi-study Viedoc export runner."""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api_helpers import DEFAULT_ENDPOINTS_FILE, EndpointConfig, load_endpoint_resolver

from viedoc_export import (
    DEFAULT_MAX_WAIT_SECONDS,
    DEFAULT_POLL_INTERVAL_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    ViedocExportClient,
    configure_logging,
    ensure_requests_available,
    parse_export_model,
    remove_extracted_prefix,
)


LOGGER = logging.getLogger("multistudy_ingest")
DEFAULT_REGION = "eu"
DEFAULT_ENVIRONMENT = "production"
DEFAULT_EXPORT_MODEL = '{"outputFormat":"CSV"}'
DEFAULT_OUTPUT_DIR = Path("out") / "multistudy"
TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n"}
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass
class StudyJob:
    study_ref: str
    client_id: str
    client_secret: str
    region: str
    environment: str
    api_url: str
    token_url: str
    export_model: dict[str, Any]
    timeout_seconds: int
    poll_interval_seconds: int
    max_wait_seconds: int
    extract_zip: bool
    remove_prefix: bool


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._") or "study"


def resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def parse_bool_text(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if not normalized:
        return default
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValueError(f"Unsupported boolean value: {value!r}")


def parse_positive_int_text(value: str | None, default: int, label: str) -> int:
    if value is None or not str(value).strip():
        return default
    parsed = int(str(value).strip())
    if parsed <= 0:
        raise ValueError(f"{label} must be greater than 0.")
    return parsed


def first_value(row: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if key in row and row[key] is not None and row[key].strip():
            return row[key].strip()
    return None


def extension_from_output_format(output_format: str) -> str:
    normalized = output_format.upper()
    if normalized == "CSV":
        return ".zip"
    if normalized == "XML":
        return ".xml"
    if normalized == "PDF":
        return ".pdf"
    if normalized == "EXCEL":
        return ".xlsx"
    return ".bin"


def normalize_export_model_input(raw_value: str, base_dir: Path) -> str:
    candidate = raw_value.strip()
    path_text = candidate[1:] if candidate.startswith("@") else candidate
    path = Path(path_text)
    if path.is_absolute() or path.exists():
        return candidate

    base_relative = (base_dir / path).resolve()
    if base_relative.is_file():
        return f"@{base_relative}" if candidate.startswith("@") else str(base_relative)

    return candidate


def resolve_job_endpoints(
    resolver: Any,
    *,
    default_region: str,
    default_environment: str,
    region: str | None,
    environment: str | None,
    api_url: str | None,
    token_url: str | None,
) -> EndpointConfig:
    return resolver.resolve(
        region=region or default_region,
        environment=environment or default_environment,
        web_api=api_url,
        sts=token_url,
    )


def build_output_path(
    *,
    root_dir: Path,
    study_ref: str,
    ingest_start_time: str,
    nest_by: str,
    nest_depth: int,
    exclude_download_name: bool,
    exclude_generated_name: bool,
    download_name: str,
    output_format: str,
) -> Path:
    safe_study = safe_name(study_ref)
    level_1 = safe_study if nest_by == "STUDY" else ingest_start_time
    level_2 = ingest_start_time if nest_by == "STUDY" else safe_study

    if nest_depth == 0:
        subdir = root_dir
    elif nest_depth == 1:
        subdir = root_dir / level_1
    elif nest_depth == 2:
        subdir = root_dir / level_1 / level_2
    else:
        subdir = root_dir / level_1 / level_2 / safe_study

    subdir.mkdir(parents=True, exist_ok=True)

    generated_base = f"{safe_study}__{ingest_start_time}"
    base_name = "" if exclude_generated_name else generated_base

    if not exclude_download_name and download_name:
        download_stem = Path(download_name).stem
        base_name = f"{base_name}__{download_stem}" if base_name else download_stem

    if not base_name:
        base_name = safe_study

    extension = Path(download_name).suffix or extension_from_output_format(output_format)
    return subdir / f"{base_name}{extension}"


def attach_file_logger(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logging.getLogger().addHandler(handler)


def load_study_jobs(
    csv_path: Path,
    *,
    endpoints_file: str,
    default_region: str,
    default_environment: str,
    default_api_url: str | None,
    default_token_url: str | None,
    default_export_model_raw: str,
    default_timeout_seconds: int,
    default_poll_interval_seconds: int,
    default_max_wait_seconds: int,
    default_extract_zip: bool,
    default_remove_prefix: bool,
) -> list[StudyJob]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"Study CSV was not found: {csv_path}")

    resolver = load_endpoint_resolver(endpoints_file)
    jobs: list[StudyJob] = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError("Study CSV must include a header row.")

        for row_number, row in enumerate(reader, start=2):
            if not any(value.strip() for value in row.values() if value):
                continue

            study_ref = first_value(row, "study_ref", "studyRef")
            client_id = first_value(row, "client_id", "clientId")
            client_secret = first_value(row, "client_secret", "clientSecret")
            if not study_ref or not client_id or not client_secret:
                raise ValueError(
                    f"Row {row_number} is missing one of the required fields: "
                    "study_ref, client_id/clientId, client_secret/clientSecret."
                )

            export_model_raw = first_value(row, "export_model", "exportModel") or default_export_model_raw
            try:
                resolved_endpoints = resolve_job_endpoints(
                    resolver,
                    default_region=default_region,
                    default_environment=default_environment,
                    region=first_value(row, "region"),
                    environment=first_value(row, "environment"),
                    api_url=first_value(row, "api_url", "apiURL") or default_api_url,
                    token_url=first_value(row, "token_url", "tokenURL") or default_token_url,
                )
                if not resolved_endpoints.web_api or not resolved_endpoints.sts:
                    raise ValueError("Could not determine both Web API and token URLs.")
                export_model = parse_export_model(normalize_export_model_input(export_model_raw, csv_path.parent))
                timeout_seconds = parse_positive_int_text(
                    first_value(row, "timeout_seconds", "timeoutSeconds"),
                    default_timeout_seconds,
                    "timeout_seconds",
                )
                poll_interval_seconds = parse_positive_int_text(
                    first_value(row, "poll_interval_seconds", "pollIntervalSeconds", "check_every_n_s"),
                    default_poll_interval_seconds,
                    "poll_interval_seconds",
                )
                max_wait_seconds = parse_positive_int_text(
                    first_value(row, "max_wait_seconds", "maxWaitSeconds", "maximum_wait_time_in_s"),
                    default_max_wait_seconds,
                    "max_wait_seconds",
                )
                extract_zip = parse_bool_text(first_value(row, "extract_zip", "extractZip"), default_extract_zip)
                remove_prefix = parse_bool_text(
                    first_value(row, "remove_prefix", "removePrefix"),
                    default_remove_prefix,
                )
            except Exception as exc:
                raise ValueError(f"Invalid configuration on row {row_number} for study {study_ref}: {exc}") from exc

            jobs.append(
                StudyJob(
                    study_ref=study_ref,
                    client_id=client_id,
                    client_secret=client_secret,
                    region=resolved_endpoints.region,
                    environment=resolved_endpoints.environment,
                    api_url=str(resolved_endpoints.web_api),
                    token_url=str(resolved_endpoints.sts),
                    export_model=export_model,
                    timeout_seconds=timeout_seconds,
                    poll_interval_seconds=poll_interval_seconds,
                    max_wait_seconds=max_wait_seconds,
                    extract_zip=extract_zip,
                    remove_prefix=remove_prefix,
                )
            )

    if not jobs:
        raise ValueError("No study rows were found in the CSV.")

    return jobs


def write_run_summary(summary_path: Path, rows: list[dict[str, str]]) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "study_ref",
        "status",
        "output_path",
        "download_name",
        "export_id",
        "error",
    ]
    with summary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_study_export(
    job: StudyJob,
    *,
    output_root: Path,
    ingest_label: str,
    nest_by: str,
    nest_depth: int,
    exclude_download_name: bool,
    exclude_generated_name: bool,
) -> dict[str, str]:
    client = ViedocExportClient(
        token_url=job.token_url,
        api_url=job.api_url,
        client_id=job.client_id,
        client_secret=job.client_secret,
        timeout_seconds=job.timeout_seconds,
    )

    LOGGER.info(
        "Starting study %s region=%s environment=%s api=%s",
        job.study_ref,
        job.region,
        job.environment,
        job.api_url,
    )
    export_id = client.start_export(job.export_model)
    client.wait_for_export(
        export_id,
        poll_interval_seconds=job.poll_interval_seconds,
        max_wait_seconds=job.max_wait_seconds,
    )
    download_name, content = client.download_export(export_id)

    output_format = str(job.export_model.get("outputFormat", "CSV"))
    output_path = build_output_path(
        root_dir=output_root,
        study_ref=job.study_ref,
        ingest_start_time=ingest_label,
        nest_by=nest_by,
        nest_depth=nest_depth,
        exclude_download_name=exclude_download_name,
        exclude_generated_name=exclude_generated_name,
        download_name=download_name,
        output_format=output_format,
    )
    output_path.write_bytes(content)
    LOGGER.info("Saved study %s export to %s", job.study_ref, output_path)

    if job.extract_zip and output_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(output_path) as archive:
            archive_members = archive.namelist()
            archive.extractall(output_path.parent)
        if job.remove_prefix:
            remove_extracted_prefix(output_path.parent, Path(download_name).stem, archive_members)
        LOGGER.info("Extracted zip for study %s into %s", job.study_ref, output_path.parent)

    return {
        "study_ref": job.study_ref,
        "status": "success",
        "output_path": str(output_path),
        "download_name": download_name,
        "export_id": export_id,
        "error": "",
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Viedoc exports for multiple studies from a CSV.")
    parser.add_argument(
        "--study_csv",
        default=str(SCRIPT_DIR / "study_list.example.csv"),
        help="CSV containing one row per study export (default: study_list.example.csv next to the script)",
    )
    parser.add_argument(
        "--output_path",
        "--output_dir",
        dest="output_dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Root directory for exported files, logs, and the run summary",
    )
    parser.add_argument(
        "--endpoints_file",
        default=str(DEFAULT_ENDPOINTS_FILE),
        help="Path to the Viedoc endpoint YAML reference file",
    )
    parser.add_argument(
        "--region",
        default=DEFAULT_REGION,
        help=f"Default region for study rows that do not override it (default: {DEFAULT_REGION})",
    )
    parser.add_argument(
        "--environment",
        default=DEFAULT_ENVIRONMENT,
        help=f"Default environment for study rows that do not override it (default: {DEFAULT_ENVIRONMENT})",
    )
    parser.add_argument(
        "--api_url",
        help="Default Viedoc Web API URL override when the CSV row does not override it",
    )
    parser.add_argument(
        "--token_url",
        help="Default token URL override when the CSV row does not override it",
    )
    parser.add_argument(
        "--export_model",
        default=DEFAULT_EXPORT_MODEL,
        help="Default export model as inline JSON, a JSON file path, or @path/to/export_model.json",
    )
    parser.add_argument(
        "--timeout_seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Default per-request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--poll_interval_seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Default seconds between status checks (default: {DEFAULT_POLL_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--max_wait_seconds",
        type=int,
        default=DEFAULT_MAX_WAIT_SECONDS,
        help=f"Default maximum wait time per study in seconds (default: {DEFAULT_MAX_WAIT_SECONDS})",
    )
    parser.add_argument(
        "--nest_by",
        choices=["STUDY", "INGEST"],
        default="STUDY",
        help="Whether to group output folders by study first or ingest timestamp first",
    )
    parser.add_argument(
        "--nest_depth",
        type=int,
        default=2,
        help="Folder nesting depth from 0 to 3 (default: 2)",
    )
    parser.add_argument(
        "--exclude_download_name",
        choices=["Y", "N"],
        default="N",
        help="Exclude the server-supplied filename from the saved filename (default: N)",
    )
    parser.add_argument(
        "--exclude_generated_name",
        choices=["Y", "N"],
        default="Y",
        help="Exclude the generated study/timestamp prefix from the saved filename (default: Y)",
    )
    parser.add_argument(
        "--extract_zip",
        choices=["Y", "N"],
        default="Y",
        help="Default zip extraction behavior when the CSV row does not override it (default: Y)",
    )
    parser.add_argument(
        "--remove_prefix",
        choices=["Y", "N"],
        default="Y",
        help="Default prefix removal after zip extraction when the CSV row does not override it (default: Y)",
    )
    parser.add_argument(
        "--break_on_fail",
        choices=["Y", "N"],
        default="N",
        help="Stop after the first failed study instead of continuing (default: N)",
    )
    parser.add_argument(
        "--log_level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser


def validate_args(args: argparse.Namespace) -> None:
    if args.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be greater than 0.")
    if args.poll_interval_seconds <= 0:
        raise ValueError("poll_interval_seconds must be greater than 0.")
    if args.max_wait_seconds <= 0:
        raise ValueError("max_wait_seconds must be greater than 0.")
    if args.nest_depth not in {0, 1, 2, 3}:
        raise ValueError("nest_depth must be one of: 0, 1, 2, 3.")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)
    ensure_requests_available()
    validate_args(args)

    output_root = resolve_path(args.output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    attach_file_logger(output_root / "log.txt")

    study_csv = resolve_path(args.study_csv)
    jobs = load_study_jobs(
        study_csv,
        endpoints_file=args.endpoints_file,
        default_region=args.region,
        default_environment=args.environment,
        default_api_url=args.api_url,
        default_token_url=args.token_url,
        default_export_model_raw=args.export_model,
        default_timeout_seconds=args.timeout_seconds,
        default_poll_interval_seconds=args.poll_interval_seconds,
        default_max_wait_seconds=args.max_wait_seconds,
        default_extract_zip=args.extract_zip == "Y",
        default_remove_prefix=args.remove_prefix == "Y",
    )

    ingest_label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary_rows: list[dict[str, str]] = []
    break_on_fail = args.break_on_fail == "Y"

    LOGGER.info("Loaded %s study rows from %s", len(jobs), study_csv)
    LOGGER.info("Output root: %s", output_root)
    LOGGER.info("Default region=%s environment=%s endpoints_file=%s", args.region, args.environment, args.endpoints_file)

    for job in jobs:
        try:
            summary_rows.append(
                run_study_export(
                    job,
                    output_root=output_root,
                    ingest_label=ingest_label,
                    nest_by=args.nest_by,
                    nest_depth=args.nest_depth,
                    exclude_download_name=args.exclude_download_name == "Y",
                    exclude_generated_name=args.exclude_generated_name == "Y",
                )
            )
        except Exception as exc:
            LOGGER.exception("Study %s failed", job.study_ref)
            summary_rows.append(
                {
                    "study_ref": job.study_ref,
                    "status": "failed",
                    "output_path": "",
                    "download_name": "",
                    "export_id": "",
                    "error": str(exc),
                }
            )
            if break_on_fail:
                break

    summary_path = output_root / f"run_summary_{ingest_label}.csv"
    write_run_summary(summary_path, summary_rows)

    failures = [row for row in summary_rows if row["status"] != "success"]
    LOGGER.info(
        "Completed multi-study run. Successes=%s Failures=%s Summary=%s",
        len(summary_rows) - len(failures),
        len(failures),
        summary_path,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
