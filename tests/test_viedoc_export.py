from __future__ import annotations

import argparse
import io
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from tests._loader import load_module
from tests._workspace import workspace_tempdir


viedoc_export = load_module("viedoc_export", "viedoc-export/viedoc_export.py")


class FakeResolver:
    def resolve(self, **kwargs):
        return viedoc_export.EndpointConfig(
            region=kwargs["region"],
            environment=kwargs["environment"],
            web_api=kwargs.get("web_api") or "https://v4api.viedoc.net",
            sts=kwargs.get("sts") or "https://v4sts.viedoc.net/connect/token",
            swagger=kwargs.get("swagger") or "https://v4api.viedoc.net/swagger/index.html",
        )


class FakeClient:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self.content = content

    def download_export(self, export_id: str):
        return self.filename, self.content


class ViedocExportTests(unittest.TestCase):
    def test_parse_export_model_inline_json(self) -> None:
        parsed = viedoc_export.parse_export_model('{"outputFormat":"CSV"}')
        self.assertEqual(parsed["outputFormat"], "CSV")

    def test_parse_export_model_from_file(self) -> None:
        with workspace_tempdir("export_model") as tmp_dir:
            model_path = tmp_dir / "export_model.json"
            model_path.write_text('{"outputFormat":"XML"}', encoding="utf-8")
            parsed = viedoc_export.parse_export_model(str(model_path))
        self.assertEqual(parsed["outputFormat"], "XML")

    def test_extract_filename_prefers_filename_star(self) -> None:
        header = 'attachment; filename="fallback.zip"; filename*=UTF-8\'\'real%20name.zip'
        self.assertEqual(viedoc_export.extract_filename(header, "abc"), "real name.zip")

    def test_extract_filename_handles_plain_filename(self) -> None:
        header = 'attachment; filename="demo.zip"'
        self.assertEqual(viedoc_export.extract_filename(header, "abc"), "demo.zip")

    def test_resolve_web_api_endpoints_uses_region_and_environment(self) -> None:
        args = argparse.Namespace(
            region="eu",
            environment="training",
            api_url=None,
            token_url=None,
            swagger_url=None,
            endpoints_file="endpoints.yaml",
        )
        with patch.object(viedoc_export, "load_endpoint_resolver", return_value=FakeResolver()):
            resolved = viedoc_export.resolve_web_api_endpoints(args)
        self.assertEqual(resolved.region, "eu")
        self.assertEqual(resolved.environment, "training")
        self.assertEqual(resolved.web_api, "https://v4api.viedoc.net")

    def test_resolve_web_api_endpoints_requires_selection_or_overrides(self) -> None:
        args = argparse.Namespace(
            region=None,
            environment=None,
            api_url=None,
            token_url=None,
            swagger_url=None,
            endpoints_file="endpoints.yaml",
        )
        with self.assertRaises(ValueError):
            viedoc_export.resolve_web_api_endpoints(args)

    def test_download_and_save_export_extracts_zip_and_removes_prefix(self) -> None:
        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w") as archive:
            archive.writestr("demo_export/file1.csv", "a,b\n1,2\n")
        client = FakeClient("demo_export.zip", archive_bytes.getvalue())

        with workspace_tempdir("extract_zip") as output_dir:
            result = viedoc_export.download_and_save_export(
                client=client,
                export_id="abc",
                output_dir=output_dir,
                extract_zip=True,
                remove_prefix=True,
            )

            self.assertEqual(result, output_dir)
            self.assertTrue((output_dir / "file1.csv").exists())

    def test_download_and_save_export_saves_binary_when_not_extracting(self) -> None:
        client = FakeClient("demo.zip", b"abc123")
        with workspace_tempdir("save_binary") as output_dir:
            result = viedoc_export.download_and_save_export(
                client=client,
                export_id="abc",
                output_dir=output_dir,
                extract_zip=False,
                remove_prefix=True,
            )
            self.assertEqual(result, output_dir / "demo.zip")
            self.assertEqual(result.read_bytes(), b"abc123")


if __name__ == "__main__":
    unittest.main()
