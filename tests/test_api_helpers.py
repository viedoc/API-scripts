from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from api_helpers.viedoc_endpoints import (
    EndpointResolver,
    load_endpoint_resolver,
    normalize_environment,
    normalize_region,
)
from tests._workspace import workspace_tempdir


RAW_ENDPOINTS = {
    "region": {
        "eu": {
            "environment": {
                "production": {
                    "clinic": "https://v4.viedoc.net",
                    "web_api": "https://v4api.viedoc.net",
                    "sts": "https://v4sts.viedoc.net",
                    "swagger": "https://v4api.viedoc.net/swagger/index.html",
                    "wcf_wsdl": "https://v4api.viedoc.net/HelipadService.svc?wsdl",
                },
                "training": {
                    "clinic": "https://v4training.viedoc.net",
                    "web_api": "https://v4apitraining.viedoc.net",
                    "sts": "https://v4ststraining.viedoc.net",
                    "swagger": "https://v4apitraining.viedoc.net/swagger/index.html",
                    "wcf_wsdl": "https://v4apitraining.viedoc.net/HelipadService.svc?wsdl",
                },
            }
        },
        "usa": {
            "environment": {
                "production": {
                    "clinic": "https://clinic.us.viedoc.com",
                    "web_api": "https://api.us.viedoc.com",
                    "sts": "https://sts.us.viedoc.com",
                    "swagger": "https://api.us.viedoc.com/swagger/index.html",
                    "wcf_wsdl": "https://api.us.viedoc.com/HelipadService.svc?wsdl",
                }
            }
        },
    }
}


class EndpointResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = EndpointResolver(RAW_ENDPOINTS, Path("endpoints.yaml"))

    def test_normalize_aliases(self) -> None:
        self.assertEqual(normalize_region("US"), "usa")
        self.assertEqual(normalize_region("Europe"), "eu")
        self.assertEqual(normalize_environment("prod"), "production")
        self.assertEqual(normalize_environment("train"), "training")

    def test_resolve_from_yaml_appends_token_suffix(self) -> None:
        resolved = self.resolver.resolve(region="eu", environment="production")
        self.assertEqual(resolved.web_api, "https://v4api.viedoc.net")
        self.assertEqual(resolved.sts, "https://v4sts.viedoc.net/connect/token")
        self.assertEqual(resolved.swagger, "https://v4api.viedoc.net/swagger/index.html")

    def test_resolve_infers_sts_from_web_api_override(self) -> None:
        local_resolver = EndpointResolver(
            {
                "region": {
                    "eu": {
                        "environment": {
                            "production": {
                                "web_api": None,
                                "sts": None,
                                "swagger": None,
                                "wcf_wsdl": None,
                            }
                        }
                    }
                }
            },
            Path("endpoints.yaml"),
        )
        resolved = local_resolver.resolve(
            region="eu",
            environment="production",
            web_api="https://apitraining.us.viedoc.com",
            sts="",
        )
        self.assertEqual(resolved.web_api, "https://apitraining.us.viedoc.com")
        self.assertEqual(resolved.sts, "https://ststraining.us.viedoc.com/connect/token")

    def test_resolve_infers_web_api_from_wcf_wsdl_override(self) -> None:
        local_resolver = EndpointResolver(
            {
                "region": {
                    "eu": {
                        "environment": {
                            "production": {
                                "web_api": None,
                                "sts": None,
                                "swagger": None,
                                "wcf_wsdl": None,
                            }
                        }
                    }
                }
            },
            Path("endpoints.yaml"),
        )
        resolved = local_resolver.resolve(
            region="eu",
            environment="production",
            web_api="",
            wcf_wsdl="https://api.us.viedoc.com/HelipadService.svc?wsdl",
            sts="https://sts.us.viedoc.com",
        )
        self.assertEqual(resolved.web_api, "https://api.us.viedoc.com")
        self.assertEqual(resolved.swagger, "https://api.us.viedoc.com/swagger/index.html")
        self.assertEqual(resolved.sts, "https://sts.us.viedoc.com/connect/token")

    def test_list_regions_and_environments(self) -> None:
        self.assertEqual(self.resolver.list_regions(), ["eu", "usa"])
        self.assertEqual(self.resolver.list_environments("eu"), ["production", "training"])

    def test_load_endpoint_resolver_uses_yaml_loader(self) -> None:
        with workspace_tempdir("endpoints_yaml") as tmp_dir:
            yaml_path = tmp_dir / "endpoints.yaml"
            yaml_path.write_text("region: {}\n", encoding="utf-8")

            class FakeYaml:
                @staticmethod
                def safe_load(_: str):
                    return RAW_ENDPOINTS

            with patch("api_helpers.viedoc_endpoints.YAML_IMPORT_ERROR", None), patch(
                "api_helpers.viedoc_endpoints.yaml", FakeYaml
            ):
                resolver = load_endpoint_resolver(yaml_path)

        self.assertIsInstance(resolver, EndpointResolver)
        self.assertEqual(resolver.resolve(region="eu", environment="training").web_api, "https://v4apitraining.viedoc.net")


if __name__ == "__main__":
    unittest.main()
