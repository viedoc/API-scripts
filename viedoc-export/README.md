# Viedoc Export Python Script

This script:
- gets an access token
- starts a Viedoc export
- polls until the export is ready
- downloads the result into the `out` directory
- extracts zip exports by default

Run commands from the `viedoc-export` directory.

## Tested Scope

Checked in this repo on Windows on April 27, 2026:
- `pip install requests`
- `python viedoc_export.py --help`
- PowerShell run examples against the stage API
- `cmd.exe` run examples against the stage API
- `py -m venv .venv` was attempted, but this Microsoft Store Python installation created a partial environment without activation scripts or `pip`

Bash examples below use standard Unix shell syntax for Linux/macOS.

## Supported Arguments

| Argument | Description | Required |
|----------|-------------|----------|
| `--token_url` | Token endpoint | Yes |
| `--api_url` | Viedoc API base URL | Yes |
| `--client_id` | Client ID | Yes |
| `--client_secret` | Client secret | Yes |
| `--export_model` | Inline JSON or `.json` file path | No |
| `--extract_zip` | `Y` or `N` | No |
| `--remove_prefix` | `Y` or `N` | No |

If `--export_model` is omitted, the script loads [`export_model.example.json`](./export_model.example.json).

## Virtual Environment Setup

These are the standard `venv` commands. In this Windows environment, `py -m venv .venv` did not complete cleanly, so prefer an existing environment or a non-Microsoft-Store Python install if you need a fresh virtual environment here.

### Bash on Linux/macOS

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install requests
```

### Windows PowerShell

Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install requests
```

If script activation is blocked, use:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

### Windows `cmd.exe`

Create and activate a virtual environment:

```cmd
py -m venv .venv
.\.venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install requests
```

### Without a Virtual Environment

```powershell
pip install requests
```

## Usage

General form:

```text
python viedoc_export.py --token_url <TOKEN_URL> --api_url <API_URL> --client_id <CLIENT_ID> --client_secret <CLIENT_SECRET> [--export_model <INLINE_JSON_OR_JSON_FILE>] [--extract_zip Y|N] [--remove_prefix Y|N]
```

## Export Model Behavior

- If the `--export_model` value ends with `.json`, the script treats it as a file path
- Relative `.json` paths are resolved from the current directory first, then from the script directory
- Any non-`.json` value is treated as inline JSON
- Using a `.json` file is the safest option across shells

## Bash Examples (Unix OS e.g. Linux or MacOS)

Use the bundled example file:

```bash
python3 viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret" --export_model ./export_model.example.json
```

Use the default bundled example file by omitting `--export_model`:

```bash
python3 viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret"
```

Pass inline JSON:

```bash
python3 viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret" --export_model '{"outputFormat":"CSV","includeVisitDates":true}'
```

## PowerShell Examples

Use the bundled example file:

```powershell
python viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret" --export_model .\export_model.example.json
```

Use the default bundled example file by omitting `--export_model`:

```powershell
python viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret"
```

Pass inline JSON:

```powershell
python viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret" --export_model '{\"outputFormat\":\"CSV\",\"includeVisitDates\":true}'
```

## `cmd.exe` Examples

Use the bundled example file:

```cmd
python viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret" --export_model .\export_model.example.json
```

Pass inline JSON:

```cmd
python viedoc_export.py --token_url "https://v4ststraining.viedoc.net/connect/token" --api_url "https://v4apitraining.viedoc.net" --client_id "your-client-id" --client_secret "your-client-secret" --export_model "{\"outputFormat\":\"CSV\"}"
```

## Output

- Files are written to the `out` directory under the current working directory
- There is no `--output_path` argument in `viedoc_export.py` so output path cannot be customised
