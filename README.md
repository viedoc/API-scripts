# API Scripts Repository

## Purpose and scope
Welcome to the Scripts repository for the Viedoc organization. This repository is dedicated to hosting various scripts that interact with Viedoc EDC APIs to automate tasks and facilitate data management.

## Viedoc API overview
This repository uses two Viedoc API families:

- Viedoc Web API: REST endpoints used by the export scripts and the site/user import tool. This requires Web API clients to be set up in Viedoc Admin for a given study, and API client ID and client secret with appropriate permissions ("scope") is needed. The endpoints available are listed in the Swagger page for the given server instance (see [viedoc-api-endpoints.yaml](./viedoc-api-endpoints.yaml))
  
- Viedoc WCF API: SOAP/WSDL endpoints used together with the Data Import Application or the import helper. This requires WCF API clients to be set up in Viedoc Admin for a given study, and username and password credientials with appropriate permissions is needed. The endpoints available are described [here](https://help.viedoc.net/c/331b7a/76935f/)

API client configuration is described in the documentation found [here](https://help.viedoc.net/c/331b7a/70102f/)

The API endpoints are specific to the Viedoc "[server instances](https://help.viedoc.net/l/debc54/)". 

This means that an API call for a given study must be directed to the correct URL, which is related to, but not identical to, the URL a user sees in the browser.

For example, a live study hosted on Viedoc EU servers might be accessed in the UI at `https://v4.viedoc.net/`, while the corresponding production Web API base URL is `https://v4api.viedoc.net`, the STS endpoint (for Web API authenticatrion) is `https://v4sts.viedoc.net`, the WCF WSDL is `https://v4api.viedoc.net/HelipadService.svc?wsdl`, and the Swagger UI is `https://v4api.viedoc.net/swagger/index.html`.

A study that is in the training environment/server instance (normally accessed at `v4training.viedoc.net`) will have a  base API URL of `https://v4apitraining.viedoc.net`.

The source of truth for these endpoints remains:
- the exact values shown during API client setup in Viedoc Admin
- the endpoint lists published by Viedoc Help: <https://help.viedoc.net/l/debc54/)>

For a centralized reference used by this repository, see [viedoc-api-endpoints.yaml](./viedoc-api-endpoints.yaml).

## Overview of the repository
- [API helpers](./api_helpers/): Shared Python helpers that resolve Viedoc endpoints from [viedoc-api-endpoints.yaml](./viedoc-api-endpoints.yaml) using region/environment selection plus optional URL overrides.
- [Import helper](./import-helper/README.md): 
  - Python script to assist with local setup when using the [Viedoc Data Import Application](https://help.viedoc.net/c/331b7a/cf6a45/en/) (requires a Viedoc WCF API client).
- [Viedoc site & user import tool](./add-sites-and-users/README.md): 
  - Python script that allows for sites and users to be imported from an Excel file, using a [Viedoc Web API client](https://help.viedoc.net/c/331b7a/6fd31a/en/). 
  - To be used during initial study setup when many sites and users need to be added to the study. Has Excel template generating feature.
- [Viedoc export](./viedoc-export/README.md): Python and R scripts to trigger and downloads exports from Viedoc EDC using a Viedoc Web API client.

## Script reference

### `import-helper/importHelper.py`
- Purpose: Creates the `config.xml` and folder structure used by the Viedoc Data Import Application.
- Main inputs: mapping XML files, one representative CSV file, WCF API endpoint selection, study GUID, user email, and import permissions.
- Main outputs: `config.xml` plus one subfolder per mapping file.

### `add-sites-and-users/site_user_app.py`
- Purpose: Interactive tool for exporting study sites/users to Excel and importing sites/users from Excel into Viedoc.
- Main inputs: output folder, region/environment selection, Web API client credentials, and Excel import files when creating sites or users.
- Main outputs: `log.txt`, `export_studySites.xlsx`, `export_studyUsers.xlsx`, and generated import templates.

### `viedoc-export/viedoc_export.py`
- Purpose: Runs one Viedoc data export for one study.
- Main inputs: region/environment or API URL overrides, Web API client credentials, export model JSON, and output settings.
- Main outputs: a downloaded export file or extracted export contents in the selected output folder.

### `viedoc-export/multistudy_ingest.py`
- Purpose: Runs repeated Viedoc exports from a CSV containing one row per study export job.
- Main inputs: study CSV, default region/environment or URL overrides, per-study credentials, export model, and output settings.
- Main outputs: exported files, `log.txt`, and a per-run summary CSV.

### `viedoc-export/viedoc_export.R`
- Purpose: R equivalent of the single-study export helper.
- Main inputs: token URL, API URL, Web API client credentials, export model, and output settings.
- Main outputs: a downloaded export file or extracted export contents in the selected output folder.

## Changelog
- 2024 May: initial repo creation, upload of export script.
- 2025 Feb: Addition of site/user import tool & import helper scripts from internal archive
