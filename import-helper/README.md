# Import helper

This application helps with the setup of data imports via the Data Import Application.

## Script summary

### `importHelper.py`
- Purpose: Creates the Viedoc Data Import Application configuration file and import folder structure from existing mapping files.
- Inputs:
  - a folder containing mapping XML files
  - one representative CSV file so the delimiter can be detected
  - region/environment selection and optional WCF endpoint override
  - study GUID from Viedoc Admin
  - email address for the importing account
  - whether imports may create subjects and initiate events
- Outputs:
  - `config.xml` in the selected import root folder
  - one subfolder per mapping XML file, with the mapping file moved into that subfolder
  - console warnings for common mapping-file issues

## Endpoint reference

This tool uses the Viedoc WCF API, not the Viedoc Web API.

The source of truth for WCF endpoints remains:

- the exact values shown during API client setup in Viedoc Admin
- the endpoint lists published by Viedoc Help: <https://help.viedoc.net/l/debc54/>

For the repository reference list of Viedoc UI, Web API, STS, Swagger, and WCF URLs, see [../viedoc-api-endpoints.yaml](../viedoc-api-endpoints.yaml).

- Create your data mappings in Viedoc Designer - Global Design Settings.
- Publish your Global Design Settings and download the mapping files.
- Create one main folder for your imports and place all your mapping files in it.
- Create a WCF API client in Viedoc Admin. Copy the GUID.
- Run this application (requires [python installation](https://www.python.org/downloads/)).
  - Open a terminal in the directory containing importHelper.py.
  - Install dependencies using `pip install -r requirements.txt`
  - run the application using `python importHelper.py`
  - input the information as requested
- Download the Data Import Application from Viedoc Designer.
- Place your CSV data files in the correct subfolders.
- Run the Data Import Application.
- (Optional) Set up Task Scheduler: https://help.viedoc.net/l/5b5c16/en/'''
