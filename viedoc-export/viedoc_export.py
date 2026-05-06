"""Single-study Viedoc data export helper."""

from __future__ import annotations

import argparse
import io
import json
import logging
import shutil
import sys
import time
import urllib.parse
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import requests as requests_module

try:
    import requests
except ImportError as exc:  # pragma: no cover - dependency validation only
    requests = None  # type: ignore[assignment]
    REQUESTS_IMPORT_ERROR = exc
else:
    REQUESTS_IMPORT_ERROR = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api_helpers import DEFAULT_ENDPOINTS_FILE, EndpointConfig, load_endpoint_resolver


LOGGER = logging.getLogger("viedoc_export")
DEFAULT_OUTPUT_DIR = Path("out")
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_POLL_INTERVAL_SECONDS = 10
DEFAULT_MAX_WAIT_SECONDS = 600


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s - %(levelname)s - %(message)s",
    )


def mask_value(value: str, visible_prefix: int = 3) -> str:
    if not value:
        return "***"
    if len(value) <= visible_prefix:
        return "*" * len(value)
    return value[:visible_prefix] + "*" * (len(value) - visible_prefix)


def parse_export_model(raw_value: str) -> dict[str, Any]:
    candidate = raw_value.strip()
    file_path_text = candidate[1:] if candidate.startswith("@") else candidate
    file_path = Path(file_path_text)

    if file_path.is_file():
        LOGGER.info("Reading export model from %s", file_path)
        content = file_path.read_text(encoding="utf-8")
    else:
        content = candidate

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Invalid export model JSON. Pass inline JSON or a path to a JSON file."
        ) from exc

    if not isinstance(parsed, dict):
        raise ValueError("The export model must decode to a JSON object.")

    return parsed


def extract_filename(content_disposition: str | None, export_id: str) -> str:
    if not content_disposition:
        return f"viedoc_export_{export_id}"

    filename_star = "filename*="
    if filename_star in content_disposition:
        fragment = content_disposition.split(filename_star, 1)[1].split(";", 1)[0].strip()
        if "''" in fragment:
            _, encoded_name = fragment.split("''", 1)
        else:
            encoded_name = fragment
        decoded_name = urllib.parse.unquote(encoded_name.strip('"'))
        if decoded_name:
            return Path(decoded_name).name

    filename_key = "filename="
    if filename_key in content_disposition:
        fragment = content_disposition.split(filename_key, 1)[1].split(";", 1)[0].strip()
        decoded_name = fragment.strip('"')
        if decoded_name:
            return Path(decoded_name).name

    return f"viedoc_export_{export_id}"


def move_path_contents(source_dir: Path, destination_dir: Path) -> None:
    for child in source_dir.iterdir():
        target = destination_dir / child.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        shutil.move(str(child), str(target))
    source_dir.rmdir()


def remove_extracted_prefix(output_dir: Path, zip_stem: str, archive_members: list[str]) -> None:
    if not zip_stem:
        return

    top_level_members = {
        Path(member).parts[0]
        for member in archive_members
        if member and not member.endswith("/")
    }

    for member_name in sorted(top_level_members, key=len, reverse=True):
        source = output_dir / member_name
        if not source.exists():
            continue

        if member_name == zip_stem and source.is_dir():
            move_path_contents(source, output_dir)
            continue

        if not member_name.startswith(zip_stem):
            continue

        trimmed_name = member_name[len(zip_stem) :].lstrip(" _-.")
        if not trimmed_name:
            continue

        target = output_dir / trimmed_name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        source.replace(target)


class ViedocExportClient:
    def __init__(
        self,
        *,
        token_url: str,
        api_url: str,
        client_id: str,
        client_secret: str,
        timeout_seconds: int,
    ) -> None:
        self.token_url = token_url
        self.api_url = api_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self._token: str | None = None

    def _fetch_token(self) -> str:
        LOGGER.info("Requesting access token from %s", self.token_url)
        response = self.session.post(
            self.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout_seconds,
        )
        self._raise_for_status("token request", self.token_url, response)

        payload = response.json()
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not token:
            raise RuntimeError("Token response did not include 'access_token'.")

        self._token = str(token)
        return self._token

    def _request_with_auth(
        self,
        method: str,
        url: str,
        action: str,
        **kwargs: Any,
    ) -> "requests_module.Response":
        for attempt in (1, 2):
            token = self._token or self._fetch_token()
            headers = dict(kwargs.pop("headers", {}))
            headers["Authorization"] = f"Bearer {token}"
            response = self.session.request(
                method,
                url,
                headers=headers,
                timeout=self.timeout_seconds,
                **kwargs,
            )
            if response.status_code != 401 or attempt == 2:
                return response

            LOGGER.warning("%s returned 401. Refreshing token and retrying once.", action)
            self._token = None

        raise RuntimeError("Unreachable auth retry state.")

    @staticmethod
    def _raise_for_status(action: str, url: str, response: "requests_module.Response") -> None:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            details = response.text.strip()
            raise RuntimeError(
                f"{action} failed for {url} with status {response.status_code}: {details}"
            ) from exc

    def start_export(self, export_model: dict[str, Any]) -> str:
        url = f"{self.api_url}/clinic/dataexport/start"
        LOGGER.info("Starting export at %s", url)
        response = self._request_with_auth(
            "POST",
            url,
            "start export",
            headers={"Content-Type": "application/json"},
            json=export_model,
        )
        self._raise_for_status("start export", url, response)

        payload = response.json()
        export_id = payload.get("exportId") if isinstance(payload, dict) else None
        if not export_id:
            raise RuntimeError("Export start response did not include 'exportId'.")
        return str(export_id)

    def wait_for_export(
        self,
        export_id: str,
        *,
        poll_interval_seconds: int,
        max_wait_seconds: int,
    ) -> None:
        status_url = f"{self.api_url}/clinic/dataexport/status"
        deadline = time.monotonic() + max_wait_seconds
        attempt = 0

        while True:
            attempt += 1
            response = self._request_with_auth(
                "GET",
                status_url,
                "check export status",
                params={"exportId": export_id},
            )
            self._raise_for_status("check export status", status_url, response)

            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError("Export status response was not a JSON object.")

            status = payload.get("exportStatus")
            LOGGER.info("Export %s status on poll %s: %s", export_id, attempt, status)

            if status == "Ready":
                return
            if status in {"Error", "Failed"}:
                raise RuntimeError(f"Export {export_id} failed: {payload}")

            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                raise TimeoutError(
                    f"Export {export_id} did not reach Ready within {max_wait_seconds} seconds."
                )

            time.sleep(min(poll_interval_seconds, max(1, int(remaining_seconds))))

    def download_export(self, export_id: str) -> tuple[str, bytes]:
        download_url = f"{self.api_url}/clinic/dataexport/download"
        response = self._request_with_auth(
            "GET",
            download_url,
            "download export",
            params={"exportId": export_id},
        )
        self._raise_for_status("download export", download_url, response)

        filename = extract_filename(response.headers.get("Content-Disposition"), export_id)
        return filename, response.content


def download_and_save_export(
    *,
    client: ViedocExportClient,
    export_id: str,
    output_dir: Path,
    extract_zip: bool,
    remove_prefix: bool,
) -> Path:
    filename, content = client.download_export(export_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    if extract_zip and filename.lower().endswith(".zip"):
        LOGGER.info("Extracting %s into %s", filename, output_dir)
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            archive_members = archive.namelist()
            archive.extractall(output_dir)
        if remove_prefix:
            remove_extracted_prefix(output_dir, Path(filename).stem, archive_members)
        LOGGER.info("Export extracted successfully into %s", output_dir)
        return output_dir

    target_path = output_dir / filename
    target_path.write_bytes(content)
    LOGGER.info("Export saved to %s", target_path)
    return target_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Download a single Viedoc export.")
    parser.add_argument(
        "--endpoints_file",
        default=str(DEFAULT_ENDPOINTS_FILE),
        help="Path to the Viedoc endpoint YAML reference file",
    )
    parser.add_argument("--region", help="Region key from the endpoint YAML, for example eu, usa, japan, china")
    parser.add_argument(
        "--environment",
        help="Environment key from the endpoint YAML, for example production or training",
    )
    parser.add_argument("--token_url", help="OAuth token endpoint URL override")
    parser.add_argument("--api_url", help="Base Viedoc Web API URL override")
    parser.add_argument("--swagger_url", help="Swagger URL override")
    parser.add_argument("--client_id", required=True, help="API client ID")
    parser.add_argument("--client_secret", required=True, help="API client secret")
    parser.add_argument(
        "--export_model",
        required=True,
        help="Inline JSON, a JSON file path, or @path/to/export_model.json",
    )
    parser.add_argument(
        "--output_path",
        "--output_dir",
        dest="output_dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where the export file or extracted files will be written",
    )
    parser.add_argument(
        "--extract_zip",
        default="Y",
        choices=["Y", "N"],
        help="Extract zip exports after download (default: Y)",
    )
    parser.add_argument(
        "--remove_prefix",
        default="Y",
        choices=["Y", "N"],
        help="Remove the zip filename prefix from extracted items when possible (default: Y)",
    )
    parser.add_argument(
        "--timeout_seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout per request in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--poll_interval_seconds",
        type=int,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        help=f"Seconds between export status checks (default: {DEFAULT_POLL_INTERVAL_SECONDS})",
    )
    parser.add_argument(
        "--max_wait_seconds",
        type=int,
        default=DEFAULT_MAX_WAIT_SECONDS,
        help=f"Maximum total wait time for export readiness (default: {DEFAULT_MAX_WAIT_SECONDS})",
    )
    parser.add_argument(
        "--log_level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO)",
    )
    return parser


def validate_positive_integer(name: str, value: int) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0.")


def ensure_requests_available() -> None:
    if REQUESTS_IMPORT_ERROR is not None:
        raise SystemExit(
            "Missing dependency: requests. Install it with `pip install requests` and rerun."
        )


def resolve_web_api_endpoints(args: argparse.Namespace) -> EndpointConfig:
    has_region_and_environment = bool(args.region and args.environment)
    has_direct_urls = bool(args.api_url or args.token_url or args.swagger_url)
    if not has_region_and_environment and not has_direct_urls:
        raise ValueError(
            "Provide --region and --environment, or explicit URL overrides such as --api_url/--token_url."
        )

    region = args.region if has_region_and_environment else "eu"
    environment = args.environment if has_region_and_environment else "production"

    resolver = load_endpoint_resolver(args.endpoints_file)
    config = resolver.resolve(
        region=region,
        environment=environment,
        web_api=args.api_url,
        sts=args.token_url,
        swagger=args.swagger_url,
    )
    if not config.web_api or not config.sts:
        raise ValueError(
            "Could not determine both Web API and token URLs from the endpoint YAML and provided overrides."
        )
    return config


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    configure_logging(args.log_level)
    ensure_requests_available()
    validate_positive_integer("timeout_seconds", args.timeout_seconds)
    validate_positive_integer("poll_interval_seconds", args.poll_interval_seconds)
    validate_positive_integer("max_wait_seconds", args.max_wait_seconds)

    export_model = parse_export_model(args.export_model)
    output_dir = Path(args.output_dir).expanduser()
    endpoints = resolve_web_api_endpoints(args)

    LOGGER.info("ViedocExport@2")
    LOGGER.info("Region: %s", endpoints.region)
    LOGGER.info("Environment: %s", endpoints.environment)
    LOGGER.info("Token URL: %s", endpoints.sts)
    LOGGER.info("API URL: %s", endpoints.web_api)
    LOGGER.info("Output directory: %s", output_dir)
    LOGGER.info("Client ID: %s", mask_value(args.client_id))
    LOGGER.info("Client secret: %s", mask_value(args.client_secret))
    LOGGER.info("Export model: %s", json.dumps(export_model, separators=(",", ":")))

    client = ViedocExportClient(
        token_url=str(endpoints.sts),
        api_url=str(endpoints.web_api),
        client_id=args.client_id,
        client_secret=args.client_secret,
        timeout_seconds=args.timeout_seconds,
    )

    export_id = client.start_export(export_model)
    LOGGER.info("Export ID: %s", export_id)
    client.wait_for_export(
        export_id,
        poll_interval_seconds=args.poll_interval_seconds,
        max_wait_seconds=args.max_wait_seconds,
    )

    final_path = download_and_save_export(
        client=client,
        export_id=export_id,
        output_dir=output_dir,
        extract_zip=args.extract_zip == "Y",
        remove_prefix=args.remove_prefix == "Y",
    )
    LOGGER.info("Completed export. Output: %s", final_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
