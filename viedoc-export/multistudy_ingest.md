# Multi-Study Python Ingest

`multistudy_ingest.py` runs the Viedoc export flow for multiple studies from one CSV.

## Script summary

### `multistudy_ingest.py`
- Purpose: Run multiple Viedoc export jobs from one CSV so repeated study exports can be executed consistently.
- Inputs:
  - a study CSV with one row per export job
  - default region/environment or optional URL overrides
  - per-study client credentials
  - export model JSON, inline or file-based
  - output layout and polling settings
- Outputs:
  - one output file per study export
  - optional extracted CSV contents for zip exports
  - `log.txt`
  - `run_summary_<timestamp>.csv`

## Endpoint reference

This tool uses the Viedoc Web API and its STS token endpoint.

The source of truth for the API base URL and STS URL remains:

- the exact values shown during API client setup in Viedoc Admin
- the endpoint lists published by Viedoc Help: <https://help.viedoc.net/l/debc54/>

For the repository reference list of Viedoc UI, Web API, STS, Swagger, and WCF URLs, see [../viedoc-api-endpoints.yaml](../viedoc-api-endpoints.yaml).

## Why use this

- Less typing: credentials and per-study settings live in one sheet.
- Safer runs: every study gets logged and the run writes a summary CSV.
- Easier defaults: shared API URLs and export settings can stay on the command line, with row-level overrides only where needed.

## Required dependency

```sh
pip install requests
```

## Quick start

1. Copy [study_list.example.csv](./study_list.example.csv) and fill in your study rows.
2. Optionally copy [export_model.example.json](./export_model.example.json) and adjust the export model.
3. Run:

```sh
python multistudy_ingest.py --study_csv study_list.example.csv --region eu --environment production --export_model export_model.example.json --output_path "C:/Users/<you>/ViedocExports"
```

## Minimum CSV columns

- `study_ref`
- `client_id` or `clientId`
- `client_secret` or `clientSecret`

## Optional CSV override columns

- `region`
- `environment`
- `api_url` or `apiURL`
- `token_url` or `tokenURL`
- `export_model` or `exportModel`
- `timeout_seconds` or `timeoutSeconds`
- `poll_interval_seconds` or `pollIntervalSeconds`
- `check_every_n_s`
- `max_wait_seconds` or `maxWaitSeconds`
- `maximum_wait_time_in_s`
- `extract_zip` or `extractZip`
- `remove_prefix` or `removePrefix`

`export_model` can be inline JSON, a JSON file path, or `@path/to/file.json`.

The script first resolves endpoints from [../viedoc-api-endpoints.yaml](../viedoc-api-endpoints.yaml) using `region` and `environment`, then applies any explicit URL overrides and infers missing values where possible.

## Default output behavior

By default, files are written as:

`<output_path>/<study_ref>/<ingest_timestamp>/<download_name>`

Each run also writes:

- `<output_path>/log.txt`
- `<output_path>/run_summary_<timestamp>.csv`

## Useful flags

- `--break_on_fail Y` stops on the first failed study.
- `--nest_by INGEST` groups outputs by run timestamp first.
- `--nest_depth 0..3` adjusts folder depth.
- `--exclude_download_name Y` removes the server filename from the saved name.
- `--exclude_generated_name N` adds a generated `{study_ref}__{timestamp}` prefix to the saved name.

## Notes

- CSV exports are usually zip files. With the default settings, the zip is saved and then extracted next to itself.
- Prefix removal after extraction is best-effort and is limited to files created by that download.
- If any study fails, the script exits with a non-zero status after the summary CSV is written.
