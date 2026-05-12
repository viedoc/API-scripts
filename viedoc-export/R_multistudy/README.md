# Viedoc Multi-Study Export – How to Run

Designed to be as run-anywhere as possible. This script can be run from the command line withoutout any arguments, or run as-is in an R session

## What this does

- Reads a CSV of studies and API credentials, rather than relying on command line arguments.
- Starts a data export per study, polls the export until Ready, downloads the file, and saves it to a structured folder.
- Provides fine-grained control of export folder structure
- Allows fallbacks to default configurations when several studies have the same configuration.
- allows study-level specification of acceptable wait times and retry intervals.
- (Optional) Unzips CSV exports after saving.
- Logs progress and errors to a file.

## Prerequisits

- Live viedoc studies, with valid API clients
- R (v. 4.4.2) and non-base packages listed below (see [/renv.lock] file for additional requirements)
- csv containing export-level api parameters (e.g. study_references.csv) 


### Viedoc study-scoped API client(s)

For ***each study***, ensure you have an __active__, __unexpired__ Web API Client (NB: not a WCF API Client) set up in Viedoc Admin ([instructions](https://help.viedoc.net/c/331b7a/70102f/en/#toc-AddingaViedocWebAPIclientandobtainingtheAPIclientID3)).
The client must be associated with a role with data export permissions, with at minimum the 'Export' scope assigned. The IP address of the computer useed to run the script (or relavent proxy) must be whitelisted (if blank, all IP address are permitted).
The client secret and client ID must be stored in the `Study reference list` refered to below.

### R packages

```R
install.packages(c("logging","readr","fs","base64enc","stringr"))
```

## Configuration

### Files & paths

export_file_location: existing or creatable folder where outputs + logs go.
study_reference_client_csv: path to your input CSV (see schema below).
Windows tip: keep the path short and writable, e.g. `C:/Users/<you>/Exports.`

### Main toggles (top of the script)

- export_file_location – root folder for outputs and log.txt.
- study_reference_client_csv – CSV with study rows.
- nest_by – how to structure subfolders (refered to as "level 1" and "level 2"):
  - "STUDY" → `…/<study_ref>/<ingest_time>/...` (level_1: study_ref, level_2: ingest_time)
  - "INGEST" → `…/<ingest_time>/<study_ref>/...` (level_1: ingest_time, level_2: study_ref)
- nest_depth – how many subfolders:
  - `0` → no subfolders; generated filename includes both level_1 and level_2
  - `1` → one level (level_1), generated filename contains level_2
  - `2` → two levels (level_1/level_2)
  - `3` → three levels (level_1/level_2/<study_ref>)
- exclude_download_name – if TRUE, don’t append the server’s filename to the saved name ({study ID}__{UTC time}).
- exclude_generated_name – if TRUE, don’t prepend the generated prefix (study/local time) to the saved name.
- unzip_CSVs – if TRUE and the requested outputFormat is CSV, unzip the saved .zip next to it.
- break_on_fail – if TRUE, stop the whole run on first failing study; otherwise continue. Useful for intitial test runs

### Global defaults (top of the script)

The defaults list provides per-row fallback values if the CSV doesn’t include them:

```R
defaults <- list(
  apiURL = "https://v4apistage.viedoc.net",
  tokenURL = "https://v4stsstage.viedoc.net/connect/token",
  maximum_wait_time_in_s = 300,
  check_every_n_s = 10,
  export_model = list(
    outputFormat = "CSV"   # "CSV" | "Excel" | "XML" | "PDF"
    # (optional) add other API export options here
  )
)
```

If a column with the same name exists in the CSV and has a value for a row, it **overrides** the default for that row.

### Study reference list CSV schema

1 row == one export.
- Minimum required columns:
  - study_ref – identifier used in folder/filename (does not need to match the Viedoc GUID)
  - clientId – OAuth client id for the study.
  - clientSecret – OAuth client secret for the study.
- Optional columns (override defaults if present):
  - apiURL
  - tokenURL
  - maximum_wait_time_in_s
  - check_every_n_s
  - export_model

Study_references.csv

```plaintext
study_ref,clientId,clientSecret,apiURL,tokenURL,maximum_wait_time_in_s,check_every_n_s
STUDY_A,aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee,SECRET_A,https://v4apitraining.viedoc.net,https://v4stsstage.viedoc.net/connect/token,300,10
STUDY_B,ffffffff-1111-2222-3333-444444444444,SECRET_B,,,600,15
```

> For STUDY_B, blank apiURL/tokenURL fall back to the global defaults.

### Defining the study model

The [API export model](https://v4api.viedoc.net/swagger/index.html) is a json representation of the UI Export Tool in Viedoc Clinic.

- Commented out = optional override of default value.
  - You can “uncomment” the branch you want to enable.
- indentation shows dependencies
  - If parent is not set, the child value is ignored/invalid.
  - timePeriodOption only valid if timePeriodDateType is set.
- Option blocks `~~ if x ~~`
  - Child options are dependant on the parent value.
  - e.g. if timePeriodDateType is specified/not None, the dates that can be specified will depend on the timePeriodOption.
- Additional dependencies/constraints specified in comments (e.g. only available for certain formats)

> Defining the study model in the CSV can allow for imports at the site level.

## What gets created (output structure)

Given:
`nest_by = "STUDY"`
`nest_depth = 3`
`exclude_download_name = TRUE`
`exclude_generated_name = FALSE`
`outputFormat = "CSV"`

You will get a path like:
`<export_file_location>/<study_ref>/<ingest_time>/<study_ref>/<study_ref>.zip`
…and, if unzip_CSVs = TRUE, the .zip is unzipped next to it.

If both generated and download names are excluded, the script falls back to using <study_ref> as the basename.

## Logging

A study-specific handler is not configured, but everything is written to:

`<export_file_location>/log.txt`

Each study also logs progress in the same file. (You can easily add per-study log files if desired.)

## Error handling & control flow

- Token retrieval: if OAuth fails, the study is marked failed.
- Start export: if the API returns an error or no exportId, the study is failed.
- Polling: polls every check_every_n_s seconds up to maximum_wait_time_in_s. If never Ready, the study is failed.
- Download: binary download (no JSON parsing). If empty, the study is failed.
- Write file: wrapped in tryCatch; on failure, the study is failed.

- After each study:
  - If the returned path is NULL, the study failed. With break_on_fail = TRUE the loop stops; otherwise it moves on to the next study.
  - If unzip_CSVs = TRUE and outputFormat == "CSV", the script unzips the saved archive.

## Security considerations

- Never log clientSecret. The script avoids printing secrets.
- Store study_references.csv in a secure location with restricted permissions.
- Avoid committing credentials to version control.
- Whitelist IP addresses and limit the API client scope while setting up the API client.

## Troubleshooting

- Permission denied (package install): on Windows, restart R, delete 00LOCK in your library, or install to a user library:

```R
dir.create("~/Rlibs", showWarnings = FALSE)
.libPaths(c("~/Rlibs", .libPaths()))
install.packages("base64enc", lib="~/Rlibs")
```

- Nothing written: check log.txt for HTTP errors:
  - `401`/`403` — bad credentials/invalid client
    - the configuration specified in the CSV does not match the API client setup in Viedoc Admin, or the IP address has note been whitelisted
  - `404` — wrong URL : ensure you are using the correct Viedoc API for the study server (training/production)
  - `5xx` — server issues.

- CSV paths on Windows: use forward slashes or double backslashes:
`C:/path/to/study_references.csv` or `C:\\path\\to\\study_references.csv`.

## One-glance run steps

- Fill out study_references.csv with study_ref, clientId, clientSecret (+ optional overrides).
- Set export_file_location, nest_by, nest_depth, and flags (unzip_CSVs, break_on_fail, etc.).
- Run the script.
- Check log.txt for progress and errors.
- Find your exports under the folder structure defined by nest_by and nest_depth.
  