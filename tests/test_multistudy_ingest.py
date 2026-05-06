from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from tests._loader import load_module
from tests._workspace import workspace_tempdir


load_module("viedoc_export", "viedoc-export/viedoc_export.py")
multistudy_ingest = load_module("multistudy_ingest", "viedoc-export/multistudy_ingest.py")


class FakeResolver:
    def resolve(self, **kwargs):
        region = kwargs["region"]
        environment = kwargs["environment"]
        web_api = kwargs.get("web_api") or f"https://{region}-{environment}-api.example.test"
        sts = kwargs.get("sts") or f"https://{region}-{environment}-sts.example.test/connect/token"
        return multistudy_ingest.EndpointConfig(
            region=region,
            environment=environment,
            web_api=web_api,
            sts=sts,
            swagger=f"{web_api}/swagger/index.html",
            wcf_wsdl=f"{web_api}/HelipadService.svc?wsdl",
        )


class MultiStudyTests(unittest.TestCase):
    def test_load_study_jobs_uses_region_environment_and_defaults(self) -> None:
        with workspace_tempdir("study_jobs_defaults") as tmp_dir:
            csv_path = tmp_dir / "studies.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "study_ref,client_id,client_secret,region,environment,poll_interval_seconds,extract_zip",
                        "STUDY_A,client-a,secret-a,usa,production,15,Y",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(multistudy_ingest, "load_endpoint_resolver", return_value=FakeResolver()):
                jobs = multistudy_ingest.load_study_jobs(
                    csv_path,
                    endpoints_file="endpoints.yaml",
                    default_region="eu",
                    default_environment="training",
                    default_api_url=None,
                    default_token_url=None,
                    default_export_model_raw='{"outputFormat":"CSV"}',
                    default_timeout_seconds=60,
                    default_poll_interval_seconds=10,
                    default_max_wait_seconds=600,
                    default_extract_zip=False,
                    default_remove_prefix=True,
                )

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].region, "usa")
        self.assertEqual(jobs[0].environment, "production")
        self.assertEqual(jobs[0].api_url, "https://usa-production-api.example.test")
        self.assertEqual(jobs[0].token_url, "https://usa-production-sts.example.test/connect/token")
        self.assertEqual(jobs[0].poll_interval_seconds, 15)
        self.assertTrue(jobs[0].extract_zip)

    def test_load_study_jobs_allows_url_overrides(self) -> None:
        with workspace_tempdir("study_jobs_overrides") as tmp_dir:
            csv_path = tmp_dir / "studies.csv"
            csv_path.write_text(
                "\n".join(
                    [
                        "study_ref,client_id,client_secret,api_url,token_url",
                        "STUDY_A,client-a,secret-a,https://manual-api.example.test,https://manual-sts.example.test/connect/token",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.object(multistudy_ingest, "load_endpoint_resolver", return_value=FakeResolver()):
                jobs = multistudy_ingest.load_study_jobs(
                    csv_path,
                    endpoints_file="endpoints.yaml",
                    default_region="eu",
                    default_environment="training",
                    default_api_url=None,
                    default_token_url=None,
                    default_export_model_raw='{"outputFormat":"CSV"}',
                    default_timeout_seconds=60,
                    default_poll_interval_seconds=10,
                    default_max_wait_seconds=600,
                    default_extract_zip=False,
                    default_remove_prefix=True,
                )

        self.assertEqual(jobs[0].api_url, "https://manual-api.example.test")
        self.assertEqual(jobs[0].token_url, "https://manual-sts.example.test/connect/token")

    def test_normalize_export_model_input_resolves_relative_to_csv(self) -> None:
        with workspace_tempdir("normalize_model") as base_dir:
            model_path = base_dir / "export_model.json"
            model_path.write_text('{"outputFormat":"XML"}', encoding="utf-8")
            normalized = multistudy_ingest.normalize_export_model_input("export_model.json", base_dir)
        self.assertEqual(Path(normalized), model_path.resolve())

    def test_build_output_path_uses_expected_nesting(self) -> None:
        with workspace_tempdir("build_output") as tmp_dir:
            output_path = multistudy_ingest.build_output_path(
                root_dir=tmp_dir,
                study_ref="Study A",
                ingest_start_time="20260422T100000Z",
                nest_by="STUDY",
                nest_depth=2,
                exclude_download_name=False,
                exclude_generated_name=True,
                download_name="demo.zip",
                output_format="CSV",
            )
        self.assertEqual(output_path.name, "demo.zip")
        self.assertIn("Study_A", str(output_path))


if __name__ == "__main__":
    unittest.main()
