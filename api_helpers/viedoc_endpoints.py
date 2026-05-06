"""Resolve Viedoc endpoints from the repository YAML reference file."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml
except ImportError as exc:  # pragma: no cover - dependency validation only
    yaml = None  # type: ignore[assignment]
    YAML_IMPORT_ERROR = exc
else:
    YAML_IMPORT_ERROR = None


DEFAULT_ENDPOINTS_FILE = Path(__file__).resolve().parents[1] / "viedoc-api-endpoints.yaml"
ENVIRONMENT_ALIASES = {
    "prod": "production",
    "production": "production",
    "live": "production",
    "train": "training",
    "training": "training",
    "demo": "training",
    "stage": "stage",
    "staging": "stage",
}
REGION_ALIASES = {
    "eu": "eu",
    "europe": "eu",
    "jp": "japan",
    "japan": "japan",
    "cn": "china",
    "china": "china",
    "us": "usa",
    "usa": "usa",
    "united states": "usa",
}


@dataclass(frozen=True)
class EndpointSelection:
    region: str
    environment: str


@dataclass(frozen=True)
class EndpointConfig:
    region: str
    environment: str
    clinic: str | None = None
    web_api: str | None = None
    sts: str | None = None
    swagger: str | None = None
    wcf_wsdl: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "clinic": self.clinic,
            "web_api": self.web_api,
            "sts": self.sts,
            "swagger": self.swagger,
            "wcf_wsdl": self.wcf_wsdl,
        }


def ensure_yaml_available() -> None:
    if YAML_IMPORT_ERROR is not None:
        raise RuntimeError(
            "Missing dependency: PyYAML. Install it with `pip install pyyaml` or `pip install -r requirements.txt`."
        )


def normalize_region(value: str | None) -> str:
    if not value or not value.strip():
        raise ValueError("region is required")
    normalized = REGION_ALIASES.get(value.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported region: {value}")
    return normalized


def normalize_environment(value: str | None) -> str:
    if not value or not value.strip():
        raise ValueError("environment is required")
    normalized = ENVIRONMENT_ALIASES.get(value.strip().lower())
    if normalized is None:
        raise ValueError(f"Unsupported environment: {value}")
    return normalized


def normalize_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned.rstrip("/")


def normalize_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned


class EndpointResolver:
    def __init__(self, raw_data: dict[str, Any], source_path: Path) -> None:
        self.raw_data = raw_data
        self.source_path = source_path

    @property
    def regions(self) -> dict[str, Any]:
        regions = self.raw_data.get("region")
        if not isinstance(regions, dict):
            raise ValueError("Endpoint YAML must contain a top-level 'region' mapping.")
        return regions

    def list_regions(self) -> list[str]:
        return sorted(self.regions.keys())

    def list_environments(self, region: str) -> list[str]:
        region_data = self.regions.get(region)
        if not isinstance(region_data, dict):
            return []
        environments = region_data.get("environment")
        if not isinstance(environments, dict):
            return []
        return sorted(environments.keys())

    def selection(self, region: str, environment: str) -> EndpointSelection:
        return EndpointSelection(
            region=normalize_region(region),
            environment=normalize_environment(environment),
        )

    def _environment_mapping(self, selection: EndpointSelection) -> dict[str, Any]:
        region_data = self.regions.get(selection.region)
        if not isinstance(region_data, dict):
            raise ValueError(f"Region '{selection.region}' is not defined in {self.source_path}.")
        environments = region_data.get("environment")
        if not isinstance(environments, dict):
            raise ValueError(
                f"Region '{selection.region}' does not contain an 'environment' mapping in {self.source_path}."
            )
        environment_data = environments.get(selection.environment)
        if not isinstance(environment_data, dict):
            raise ValueError(
                f"Environment '{selection.environment}' is not defined for region '{selection.region}' in {self.source_path}."
            )
        return environment_data

    def resolve(
        self,
        *,
        region: str,
        environment: str,
        clinic: str | None = None,
        web_api: str | None = None,
        sts: str | None = None,
        swagger: str | None = None,
        wcf_wsdl: str | None = None,
    ) -> EndpointConfig:
        selection = self.selection(region, environment)
        environment_data = self._environment_mapping(selection)

        resolved = EndpointConfig(
            region=selection.region,
            environment=selection.environment,
            clinic=normalize_base_url(clinic) or normalize_base_url(_string_or_none(environment_data.get("clinic"))),
            web_api=normalize_base_url(web_api) or normalize_base_url(_string_or_none(environment_data.get("web_api"))),
            sts=normalize_url(sts) or normalize_url(_string_or_none(environment_data.get("sts"))),
            swagger=normalize_url(swagger) or normalize_url(_string_or_none(environment_data.get("swagger"))),
            wcf_wsdl=normalize_url(wcf_wsdl) or normalize_url(_string_or_none(environment_data.get("wcf_wsdl"))),
        )
        return self._infer_missing(resolved)

    def _infer_missing(self, config: EndpointConfig) -> EndpointConfig:
        web_api = normalize_base_url(config.web_api)
        sts = normalize_url(config.sts)
        swagger = normalize_url(config.swagger)
        wcf_wsdl = normalize_url(config.wcf_wsdl)

        if web_api:
            swagger = swagger or f"{web_api}/swagger/index.html"
            wcf_wsdl = wcf_wsdl or f"{web_api}/HelipadService.svc?wsdl"

        if sts:
            sts = self._normalize_token_url(sts)

        if not sts and web_api:
            inferred_sts = self._infer_sts_from_web_api(web_api)
            if inferred_sts:
                sts = inferred_sts

        if not web_api and wcf_wsdl:
            web_api = normalize_base_url(wcf_wsdl.removesuffix("/HelipadService.svc?wsdl"))
            swagger = swagger or f"{web_api}/swagger/index.html"

        return EndpointConfig(
            region=config.region,
            environment=config.environment,
            clinic=normalize_base_url(config.clinic),
            web_api=web_api,
            sts=sts,
            swagger=swagger,
            wcf_wsdl=wcf_wsdl,
        )

    @staticmethod
    def _normalize_token_url(value: str) -> str:
        cleaned = value.rstrip("/")
        if cleaned.endswith("/connect/token"):
            return cleaned
        return f"{cleaned}/connect/token"

    @staticmethod
    def _infer_sts_from_web_api(web_api: str) -> str | None:
        parsed = urlparse(web_api)
        host = parsed.netloc
        if not host:
            return None

        replacements = [
            ("api", "sts"),
        ]
        for old, new in replacements:
            if old in host:
                inferred_host = host.replace(old, new, 1)
                scheme = parsed.scheme or "https"
                return f"{scheme}://{inferred_host}/connect/token"
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def load_endpoint_resolver(path: str | Path | None = None) -> EndpointResolver:
    ensure_yaml_available()
    source_path = Path(path or DEFAULT_ENDPOINTS_FILE).expanduser().resolve()
    raw_text = source_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw_text)
    if not isinstance(loaded, dict):
        raise ValueError(f"Endpoint YAML must decode to a mapping: {source_path}")
    return EndpointResolver(loaded, source_path)
