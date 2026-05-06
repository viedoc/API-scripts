import requests
import json
import pandas as pd
import datetime
import os.path
import re
import sys
from pathlib import Path
from site_user_import.timezones import tz_conversion

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api_helpers import DEFAULT_ENDPOINTS_FILE, load_endpoint_resolver


def get_available_endpoint_options(endpoints_file = None):
    """
    Returns available region/environment combinations from the endpoint YAML.
    """
    resolver = load_endpoint_resolver(endpoints_file or DEFAULT_ENDPOINTS_FILE)
    options = []
    for region in resolver.list_regions():
        for environment in resolver.list_environments(region):
            resolved = resolver.resolve(region = region, environment = environment)
            if resolved.web_api and resolved.sts:
                options.append((region, environment, resolved))
    return options


def get_server(region, environment, api_url = "", token_url = "", endpoints_file = None):
    """
    Resolve API URLs from the endpoint YAML with optional overrides.
    Args:
        region (str): Region key from the endpoint YAML.
        environment (str): Environment key from the endpoint YAML.
        api_url (str): Optional API URL override.
        token_url (str): Optional token URL override.
        endpoints_file (str): Optional custom endpoint YAML path.
    Returns:
        (tuple): [0] Token URL, [1] API URL.
    """
    resolver = load_endpoint_resolver(endpoints_file or DEFAULT_ENDPOINTS_FILE)
    resolved = resolver.resolve(
        region = region,
        environment = environment,
        web_api = api_url or None,
        sts = token_url or None,
    )
    if not resolved.sts or not resolved.web_api:
        raise ValueError("Could not determine both token and API URLs.")
    sts = resolved.sts
    api = resolved.web_api
    return sts, api


def get_token(url, path, clientid, secret):
    """
    Obtains a token from the STS server.
    Args:
        url (str): Token URL obtained from Viedoc Admin.
        path (str): Path where the log file should be saved.
        clientid (str): The Web API client GUID obtained from Viedoc Admin.
        secret (str): The Web API client secret obtained from Viedoc Admin.
    Returns:
        (str): The authentication token. Empty string if unsuccessful.
    """
    # Define the data to be transmitted to the API endpoint and make the call
    params = {"grant_type": "client_credentials",
              "client_id": clientid,
              "client_secret": secret}
    response = requests.post(url, data = params)
    
    # Check the status code in the response; if successful, parse the token
    if response.status_code == 200:
        token = response.json().get("access_token")
        writelog("Token successfully obtained.\n", path)
        return token
    elif response.status_code == 500:
        writelog("Status code: 500 - failure. Could not obtain token. Is the client ID correct?", path)
        return ""
    elif response.status_code == 400:
        writelog("Status code: 400 - failure. Could not obtain token. Is the client secret correct?", path)
        return ""


def get_sites(token, url, path):
    """
    Retrieves sites from Viedoc and saves to Excel.
    Args:
        token (str): Authentication token obtained from the STS server.
        url (str): API URL obtained from Viedoc Admin.
        path (str): Path where the log and Excel file should be saved.
    Returns:
        None
    """
    writelog("Retrieving list of study sites from " + url + "/admin/studysites.", path)
    
    # Define the request headers and make the API call
    header = {"Accept" : "application/json", "Authorization" : "Bearer " + token}
    response = requests.get(url + "/admin/studysites", headers = header)
    
    # Check the status code in the response
    if(response.status_code == 200):
        writelog("Status code: 200 - Success.", path)
        
        # Convert the response contents to a data frame; end this function if no sites exist
        sites = pd.DataFrame(response.json())
        if sites.empty:
            writelog("No study sites were obtained\n", path)
            return
        
        # Delete not needed columns
        del sites["siteType"]
        del sites["tzOffset"]
        
        # Write the output to Excel
        try:  # Using a try statement, as permission may be denied
            writer = pd.ExcelWriter(path + "export_studySites.xlsx", engine = "openpyxl")
            sites.to_excel(writer, index = False, sheet_name = "Export")
            ws = writer.sheets["Export"]
            columnwidths = {"A": 37, "B": 10, "C": 15, "D": 60, "E": 10, "F": 25,
                "G": 12, "H": 30, "I": 35, "J": 35, "K": 35, "L": 16, "M": 19}
            for column in columnwidths.keys():  # Set the column widths in the Excel file
                ws.column_dimensions[column].width = columnwidths[column]
            writer.close()
            writelog("Output saved: " + path + "export_studySites.xlsx.\n", path)
        except:
            writelog("Unable to write Excel file. Permission denied.\n", path)
    
    # If the status code indicates failure
    elif(response.status_code == 403):
        writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin. Ending execution of this function.\n", path)
        return
    
    writelog("Returning to user input.", path, disp = False)


def get_users(token, url, path):
    """
    Retrieves users from Viedoc and saves to Excel.
    Args:
        token (str): Authentication token obtained from the STS server.
        url (str): API URL obtained from Viedoc Admin.
        path (str): Path where the log and Excel file should be saved.
    Returns:
        None
    """
    # Retrieve list of users from the API
    writelog("Retrieving list of users from " + url + "/admin/users.", path)
    header = { "Accept" : "application/json", "Authorization" : "Bearer " + token, "Content-type" : "application/json" }
    response = requests.post(url + "/admin/users",headers = header, json = {})
    if(response.status_code == 200):
        writelog("Status code: 200 - Success.", path)
        response = response.json()
    elif(response.status_code == 403):
        writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin. Ending execution of this function.\n", path)
        return
    
    # Retrieve list of sites from the API for the siteName and siteCode
    writelog("Retrieving list of sites from " + url + "/admin/studysites (for siteName and siteCode).", path)
    response_sites = requests.get(url + "/admin/studysites", headers = header)
    if(response_sites.status_code == 200):
        writelog("Status code: 200 - Success.", path)
        response_sites = response_sites.json()
        sites = pd.DataFrame(response_sites)
        if sites.empty:
            sites = pd.DataFrame({"siteGuid": [], "siteName": [], "siteCode": []})
    elif(response_sites.status_code == 403):
        writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin. Ending execution of this function.\n", path)
        return
    
    # Retrieve the detailed role info per user
    writelog("Retrieving role info per user.", path)
    userExcel = pd.DataFrame({"userGuid":[], "displayName":[], "email":[], "roleName":[], "siteGuid":[], "siteName":[], "siteCode":[], "access_to_siteGroup":[]})
    for i in range(0, len(response["userInfos"])):
        # If a user has no email, or it is the same is userGuid, it is an API client
        if((response["userInfos"][i]["email"] == None) | (response["userInfos"][i]["email"] == response["userInfos"][i]["userGuid"])):
            response["userInfos"][i]["displayName"] = "<<API CLIENT>>"
            response["userInfos"][i]["email"] = "<<API CLIENT>>"
            writelog("Retrieving info for API client user from " + url + "/admin/users/" + response["userInfos"][i]["userGuid"] + "/roles.", path)
        else:
            writelog("Retrieving info for user " + response["userInfos"][i]["email"] + " from " + url + "/admin/users/" + response["userInfos"][i]["userGuid"] + "/roles.", path)
        response2 = requests.get(url + "/admin/users/" + response["userInfos"][i]["userGuid"] + "/roles", headers = header)
        if(response2.status_code == 200):
            writelog("Status code: 200 - Success.", path)
        elif(response2.status_code == 403):
            writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin. Ending execution of this function\n.", path)
            return
        
        # Transform the role info per user and append to the userExcel variable
        # Convert the roles information from the API response to a data frame
        roles = pd.DataFrame(response2.json()["roles"])
        roles["siteGuids"] = roles["siteGuids"].fillna("").apply(list)
        # Expand the siteGuids column (which may contain a list with multiple values) to separate columns for each list element
        siteGuids = pd.DataFrame([pd.Series(x) for x in roles.siteGuids])
        siteGuids.columns = ["site_{}".format(x+1) for x in siteGuids.columns]
        if siteGuids.empty:
            roles["site_1"] = ""
        else:
            roles = roles.join(siteGuids)
        # Pivot the roles data frame to one row per role-siteGuid combination
        roles = pd.melt(roles, id_vars = [col for col in roles if not col.startswith('site_')], value_vars = [col for col in roles if col.startswith('site_')], var_name = "sitenr", value_name = "siteGuid")
        # Remove duplicate rows without siteGuid
        roles = roles[(roles.sitenr == "site_1") | (~roles.siteGuid.isna())]
        # Add columns userGuid, email and displayName
        user = pd.DataFrame(response["userInfos"]).loc[i,["userGuid","email","displayName"]]
        [roles.insert(0, x, user[x]) for x in reversed(user.index)]
        # Add columns siteName and siteCode
        roles = roles.merge(sites[["siteGuid","siteName","siteCode"]], on="siteGuid", how="left")
        # Add whether the role has access to a site group
        # siteGroupGuids may be None, [] or have an actual value. None and [] evaluate to boolean False
        roles["access_to_siteGroup"] = ["Yes" if x==True else "No" for x in roles.siteGroupGuids.astype(bool)]
        # Drop not needed columns
        roles = roles.drop(columns=["roleId","siteGuids","sitenr","siteGroupGuids"])
        # Add to the userExcel variable created outside the loop
        userExcel = pd.concat([userExcel, roles])
    
    # Write the userExcel variable to Excel
    try:  # Writing the Excel file within try statement, as permission may be denied.
        writer = pd.ExcelWriter(path + "export_studyUsers.xlsx", engine = "openpyxl")
        userExcel.to_excel(writer, index = False, sheet_name = "Export")
        ws = writer.sheets["Export"]
        columnwidths = {"A": 37, "B": 25, "C": 35, "D": 25, "E": 37, "F": 25, "G": 12, "H": 20}
        for column in columnwidths.keys():
            ws.column_dimensions[column].width = columnwidths[column]
        writer.close()
        writelog("Output saved: " + path + "export_studyUsers.xlsx.\n", path)
    except:
        writelog("Unable to write Excel file. Permission denied.", path)
    writelog("Returning to user input.", path, disp = False)


def create_sites(token, url, path, excelfile):
    """
    Creates sites in Viedoc from an Excel input.
    Args:
        token (str): Authentication token obtained from the STS server.
        url (str): API URL obtained from Viedoc Admin.
        path (str): Path where the log file should be saved.
        excelfile (str): Path to the Excel file.
    Returns:
        None
    """
    writelog("Loading data from Excel.", path)
    try:  # Reading the Excel file within try statement, as permission may be denied
        sitesToAdd = pd.read_excel(excelfile, dtype = str)
    except:
        writelog("Unable to read Excel file. Permission denied.\n", path)
        return
    
    # Check if correct Excel template was used
    colnames = sitesToAdd.columns
    cols = ["siteCode", "siteName", "countryCode", "timeZoneId", "expectedNumberOfSubjectsScreened", 
        "expectedNumberOfSubjectsEnrolled", "maximumNumberOfSubjectsScreened","isTrainingEnabled", "isProductionEnabled"]
    if not all(value in colnames for value in cols):
        writelog("Invalid data layout. Use the import template. Ending execution of this function.\n", path)
        return
    writelog("Correct Excel template was used.", path)
    
    # Check if all sites have a value for the required fields
    requiredcols = ["siteCode", "siteName", "countryCode", "timeZoneId", "isTrainingEnabled", "isProductionEnabled"]
    for i in requiredcols:
        if(sitesToAdd[i].isna().any()):
            writelog(i + " is missing for at least one site! Ending execution of this function.\n", path)
            return
    writelog("All sites have data for the required fields.", path)
    
    # Check if Excel file does not contain duplicates
    if(len(sitesToAdd["siteCode"].unique()) != len(sitesToAdd["siteCode"])):
        writelog("Duplicate siteCode detected in the Excel file! Ending execution of this function.\n", path)
        return
    if(len(sitesToAdd["siteName"].unique()) != len(sitesToAdd["siteName"])):
        writelog("Duplicate siteName detected in the Excel file! Ending execution of this function.\n", path)
        return
    writelog("No duplicates detected within the Excel file.", path)
    
    # Retrieve existing sites from the API to check later if siteName or siteCode are already in the system
    writelog("Retrieving existing sites from " + url + "/admin/studysites to check for duplicates.", path)
    header = { "Accept" : "application/json", "Authorization" : "Bearer " + token}
    response = requests.get(url + "/admin/studysites", headers = header)
    if(response.status_code == 200):
        writelog("Status code: 200 - Success.", path)
    elif(response.status_code == 403):
        writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin. Ending execution of this function.\n", path)
        return
    sites = pd.DataFrame(response.json())
    
    # Loop over all rows, perform checks, then proceed to importing the sites
    sitesCreated = 0
    failed = []
    notinvited = []
    for i in range(0, sitesToAdd.shape[0]):
        params = sitesToAdd.iloc[i][cols].to_dict()
        writelog("Working on Excel row " + str(i+2) + " - siteName: '" + params["siteName"] + "', siteCode: '" + params["siteCode"] + "'.", path)
        
        # Check if siteName or siteCode already exist in the system, if so: skip the Excel row
        if(not sites.empty):
            if(params["siteCode"] in sites["siteCode"].values):
                writelog("SiteCode " + params["siteCode"] + " already exists in the study. Skipping this Excel row.\n", path)
                failed.append(i+2)
                continue
            if(params["siteName"] in sites["siteName"].values):
                writelog("SiteName " + params["siteName"] + " already exists in the study. Skipping this Excel row.\n", path)
                failed.append(i+2)
                continue
        
        # Remove optional fields if they were blank in the Excel file
        optionalcols = ["expectedNumberOfSubjectsScreened", "expectedNumberOfSubjectsEnrolled", "maximumNumberOfSubjectsScreened"]
        for j in optionalcols:
            if(pd.isnull(sitesToAdd.iloc[i][j])):
                del params[j]
            
            # Remove optional fields also if they were not numeric in the Excel file
            elif(not params[j].isdigit()):
                writelog("Value " + params[j] + " ignored as it is not numeric (" + j +").", path)
                del params[j]
        
        # Check the timeZoneId. If provided in "Viedoc format" instead of "API import format", convert it
        if(params["timeZoneId"] in tz_conversion.keys()):
            writelog(params["timeZoneId"] + " converted to " + tz_conversion[params["timeZoneId"]] + " for import.", path)
            params["timeZoneId"] = tz_conversion[params["timeZoneId"]]
        
        # Check isTrainingEnabled and isProductionEnabled: Convert their value to True or False
        params["isTrainingEnabled"] = toTrueFalse(params["isTrainingEnabled"])
        params["isProductionEnabled"] = toTrueFalse(params["isProductionEnabled"])
        
        # Make sure the countryCode is in uppercase
        params["countryCode"] = params["countryCode"].upper()
        
        # Create the site
        writelog("Sending the following site details to " + url + "/admin/studysites:", path)
        for j in params:
            writelog("- " + j + ": " + params[j], path, option = "notimestamp")
        header = { "Accept" : "application/json", "Authorization" : "Bearer " + token, "Content-type" : "application/json"}
        response = requests.post(url + "/admin/studysites", json = params, headers = header)
        
        # Check whether the site was successfully created
        if(response.status_code == 201):
            sitesCreated += 1
            writelog("Status code: 201 - Success. Site created.", path)
        elif(response.status_code == 400):
            if(response.content.startswith(b'{"errorMessage":"Study does not have a valid license.')):
                writelog("Status code: 400 - Failure. License required to enable Production status.\n", path)
                failed.append(i+2)
                continue
            if(response.content.startswith(b'{"errorMessage":"Combined production and training mode is not allowed in this study.')):
                 writelog("Status code: 400 - Failure. Study settings do not allow a site with both Training and Production status.\n", path)
                 failed.append(i+2)
                 continue
            if(response.content.startswith(b'[\n  "CountryCode is not valid:')):
                writelog("Error creating site " + params["siteCode"] + ". The countryCode was not recognized.\n", path)
                failed.append(i+2)
                continue
            if(response.content.startswith(b'[\n  "TimeZoneId is not valid:')):
                writelog("Error creating site " + params["siteCode"] + ". The timeZoneId was not recognized.\n", path)
                failed.append(i+2)
                continue
            else:
                writelog("Status code: 400 - Failure. Site not added. Details:\n", path)
                writelog(response.json(), path, disp = True, option = "error")
                failed.append(i+2)
                continue
        elif(response.status_code == 403):
            if(response.content == b'Production client required'):
                writelog("Status code: 403 - Failure. Cannot create a Production site when API client is in Demo mode.\n", path)
                failed.append(i+2)
                continue
            else:
                writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin. Site not added.\n", path)
                failed.append(i+2)
                continue
        
        # Get the siteGuid of the created site
        siteGuid = re.search("[a-z0-9-]+$",response.json())
        siteGuid = siteGuid.group(0)
        writelog("Created site has siteGuid: " + siteGuid + ".", path)
        
        # Add site manager as defined in Excel file
        if("roleSiteManager" in colnames and not pd.isnull(sitesToAdd.iloc[i]["roleSiteManager"])):
            writelog("Adding '" + sitesToAdd.iloc[i]["roleSiteManager"] + "' with role RoleSiteManager to site " + siteGuid + ".", path)
            writelog("Sending the following user details to " + url + "/admin/adminusers:", path)
            writelog("- email: " + sitesToAdd.iloc[i]["roleSiteManager"], path, option = "notimestamp")
            writelog("- roleOID: RoleSiteManager", path, option = "notimestamp")
            writelog("- siteGuid: " + siteGuid, path, option = "notimestamp")
            header = { "Accept" : "application/json","Content-type": "application/json", "Authorization" : "Bearer " + token }
            body = '[\n{\n"email":"' + sitesToAdd.iloc[i]["roleSiteManager"] + '",\n"roles":[\n{\n"roleOID":"RoleSiteManager",\n"siteGuid":"' + siteGuid + '"\n}\n]\n}\n]'
            response = requests.post(url + "/admin/adminusers", data = body, headers = header)
            notinvited = check_response_status(response, sitesToAdd.iloc[i]["roleSiteManager"], i+2, notinvited, 0, "admin", path)[0]
        writelog("", path, option = "notimestamp")
        
    # Show the number of sites created and list the failures
    if(sitesCreated == 0):
        writelog("No sites were created.\n", path)
    elif(sitesCreated == 1):
        writelog("One site was successfully created.\n", path)
    else:
        writelog(str(sitesCreated) + " sites were successfully created.\n", path)
    if(len(failed) > 0):
        writelog("Failed to create site in Excel row: " + ", ".join(str(x) for x in failed) + ".\n", path)
    if(len(notinvited) > 0):
        writelog("Failed to invite site manager in Excel row: " + ", ".join(str(x) for x in notinvited) + ".\n", path)
    writelog("Returning to user input.", path, disp = False)


def create_users(token, url, path, excelfile):
    """
    Creates users in Viedoc from an Excel input.
    Args:
        token (str): Authentication token obtained from the STS server.
        url (str): API URL obtained from Viedoc Admin.
        path (str): Path where the log file should be saved.
        excelfile (str): Path to the Excel file.
    Returns:
        None
    """
    writelog("Loading data from Excel.", path)
    try:  # Reading the Excel file within try statement, as permission may be denied.
        usersToAdd = pd.read_excel(excelfile, dtype = str)
    except:
        writelog("Unable to read Excel file. Permission denied.\n", path)
        return
    # Check if correct Excel template was used:
    colnames = usersToAdd.columns
    if not((colnames[0] == "email") and (colnames[1] == "roleOID") and (colnames[2] == "siteGuid") and (colnames[3] == "siteName") and (colnames[4] == "siteCode") ):
        writelog("Invalid data layout. Use the import template. Ending execution of this function.\n", path)
        return
    # Retrieve list of sites from the API to convert siteName/siteCode in the Excel to siteGuid:
    writelog("Retrieving sites from " + url + "/admin/studysites to convert siteCode/siteName to siteGuid.", path)
    header = { "Accept" : "application/json", "Authorization" : "Bearer " + token }
    response_sites = requests.get(url + "/admin/studysites", headers = header)
    if(response_sites.status_code == 200):
        writelog("Status code: 200 - Success.", path)
    elif(response_sites.status_code == 403):
        writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin. Ending execution of this function.\n", path)
        return
    response_sites = response_sites.json()
    sites = pd.DataFrame(response_sites)
    # Start creating users / adding roles to users:
    header = { "Accept" : "application/json","Content-type": "application/json", "Authorization" : "Bearer " + token }
    usersAdded = 0
    failed = []  # To track failed Excel rows.
    for i in range(0, usersToAdd.shape[0]):
        params = usersToAdd.iloc[i][0:5].to_dict()
        if((not isinstance(params["email"], str)) or (not isinstance(params["roleOID"], str))):
            writelog("Skipping Excel row " + str(i+2) + " as required data is missing (email or roleOID).", path)
            failed.append(i+2)
            continue
        writelog("Working on Excel row " + str(i+2) + ". Email: " + params["email"] + ", roleOID: " + params["roleOID"] + ".", path)
        # Check siteGuid, siteName and siteCode. Obtain siteGuid if needed and possible:
        sysRoles = {
            "study manager": "RoleStudyManager",
            "site manager": "RoleSiteManager",
            "api manager": "ApiManager",
            "designer": "RoleDesigner",
            "unblinded statistician": "UnblindedStatistician",
            "dictionary manager": "DictionaryManager",
            "reference data source manager": "RefDataSourceManager",
            "etmf manager": "EtmfManager",
            "design impact analyst": "DesignImpactAnalyst"}
        if(params["roleOID"].lower() in sysRoles.keys()):
            writelog("Role " + params["roleOID"] + " converted to " + sysRoles[params["roleOID"].lower()] + " for import.", path)
            params["roleOID"] = sysRoles[params["roleOID"].lower()]
        # Check if the role requires a siteGuid (i.e. not a system role except Site Manager)
        if(not params["roleOID"] in ["RoleStudyManager","ApiManager","RoleDesigner","UnblindedStatistician","DictionaryManager","RefDataSourceManager","EtmfManager","DesignImpactAnalyst"]):
            writelog("The provided role (" + params["roleOID"] + ") requires a siteGuid.", path)
            # If a siteGuid is provided in the Excel
            if(isinstance(params["siteGuid"],str)):
                # If the provided siteGuid does not exist in the study, the row is skipped
                if(not params["siteGuid"] in sites["siteGuid"].values):
                    writelog("Invalid siteGuid provided (" + params["siteGuid"] + ")! Skipping this Excel row.", path)
                    failed.append(i+2)
                    continue
                writelog("SiteGuid " + params["siteGuid"] + " provided in Excel file.", path)
            # If no siteGuid was provided
            else: writelog("SiteGuid not provided in Excel file. Trying to obtain from (1) siteCode or (2) siteName.", path)
            # If a siteCode was provided
            if((not isinstance(params["siteGuid"], str)) and (isinstance(params["siteCode"], str))):
                # If the siteCode does not exist in the study, the row is skipped
                if(not params["siteCode"] in sites["siteCode"].values):
                    writelog("Provided siteCode (" + params["siteCode"] + ") does not exist in Viedoc! Skipping this Excel row.", path)
                    failed.append(i+2)
                    continue
                # If the siteCode does exist in the study and is unique
                if(len(sites.loc[sites["siteCode"] == params["siteCode"]]["siteGuid"].values) == 1):
                    # If provided, the siteName must match the siteCode, else the row is skipped
                    if(isinstance(params["siteName"], str) and not sites.loc[sites["siteCode"] == params["siteCode"]]["siteName"].values == params["siteName"]):
                        writelog("The combination of siteCode '" + params["siteCode"] + "' and siteName '" + params["siteName"] + "' does not exist. Skipping this Excel row.", path)
                        failed.append(i+2)
                        continue
                    # If no siteName provided, or siteCode and siteName match, then obtain the siteGuid
                    params["siteGuid"] = sites.loc[sites["siteCode"] == params["siteCode"]]["siteGuid"].values[0]
                    writelog("Obtained siteGuid " + params["siteGuid"] + " from siteCode '" + params["siteCode"] + "' for import.", path)
                # If the siteCode does exist, but is not unique
                elif(len(sites.loc[sites["siteCode"] == params["siteCode"]]["siteGuid"].values) > 1):
                    # If a siteName is provided and matches the siteCode, then obtain the siteGuid
                    if(isinstance(params["siteName"], str) and params["siteName"] in sites.loc[sites["siteCode"] == params["siteCode"]]["siteName"].values):
                        params["siteGuid"] = sites.loc[sites["siteCode"] == params["siteCode"]][sites.loc[sites["siteCode"] == params["siteCode"]]["siteName"].values == params["siteName"]]["siteGuid"].values[0]
                        writelog("Obtained siteGuid " + params["siteGuid"] + " from siteCode '" + params["siteCode"] + "' and siteName '" + params["siteName"] + "' for import.", path)
                    # If no siteName is provided, the row is skipped
                    elif(not isinstance(params["siteName"], str)):
                        writelog("SiteCode '" + params["siteCode"] + "' is not unique and no siteName was provided to distinguish sites. Skipping this Excel row.", path)
                        failed.append(i+2)
                        continue
                    # If a siteName is provided, but does not match the siteCode, the row is skipped
                    elif(not params["siteName"] in sites.loc[sites["siteCode"] == params["siteCode"]]["siteName"].values):
                        writelog("The combination of siteCode '" + params["siteCode"] + "' and siteName '" + params["siteName"] + "' does not exist. Skipping this Excel row.", path)
                        failed.append(i+2)
                        continue
            # If no siteGuid siteCode are provided, but siteName is provided
            elif((not isinstance(params["siteGuid"], str)) and (isinstance(params["siteName"], str))):
                # If siteName does not exist, the row is skipped
                if(not params["siteName"].upper() in sites["siteName"].astype(str).str.upper().values):
                    writelog("Provided siteName (" + params["siteName"] + ") does not exist in Viedoc! Skipping this Excel row.", path)
                    failed.append(i+2)
                    continue
                # If siteName does exist, then obtain the siteGuid
                params["siteGuid"] = sites.loc[sites["siteName"].astype(str).str.upper() == params["siteName"].upper()]["siteGuid"].values[0]
                writelog("Obtained siteGuid " + params["siteGuid"] + " from siteName '" + params["siteName"] + "' for import.", path)
            # Any other cases, no siteGuid is obtained
            else: writelog("SiteGuid was not obtained.", path)
        # Check if the provided roleOID belongs to a system role
        if(params["roleOID"] in sysRoles.values()):
            writelog("Provided roleOID is a system role. Using system role import routine.", path)
            # Import specifically for Site Manager, as the API requires a siteGuid here
            if(params["roleOID"] == "RoleSiteManager" and isinstance(params["siteGuid"], str)):
                writelog("Adding '" + params["email"] + "' with role RoleSiteManager to site " + params["siteGuid"] + ".", path)
                writelog("Sending the following user details to " + url + "/admin/adminusers:", path)
                writelog("- email: " + params["email"], path, option = "notimestamp")
                writelog("- roleOID: RoleSiteManager", path, option = "notimestamp")
                writelog("- siteGuid: " + params["siteGuid"], path, option = "notimestamp")
                body = '[\n{\n"email":"' + params["email"] + '",\n"roles":[\n{\n"roleOID":"RoleSiteManager",\n"siteGuid":"' + params["siteGuid"] + '"\n}\n]\n}\n]'
                response = requests.post(url + "/admin/adminusers", data = body, headers = header)
                failed, usersAdded = check_response_status(response, params["email"], i+2, failed, usersAdded, "admin", path)
            elif(params["roleOID"] == "RoleSiteManager" and not isinstance(params["siteGuid"], str)):
                writelog("Trying to add a site manager (" + params["email"] + "), but siteGuid, siteName and siteCode are all missing!", path)
                failed.append(i+2)
            # Import for all other system roles, which do not require assignment to a siteGuid
            else:
                writelog("Adding '" + params["email"] + "' with role " + params["roleOID"] + ".", path)
                writelog("Sending the following user details to " + url + "/admin/adminusers:", path)
                writelog("- email: " + params["email"], path, option = "notimestamp")
                writelog("- roleOID: " + params["roleOID"], path, option = "notimestamp")
                body = '[\n{\n"email":"' + params["email"] + '",\n"roles":[\n{\n"roleOID":"' + params["roleOID"] + '"\n}\n]\n}\n]'
                response = requests.post(url + "/admin/adminusers", data = body, headers = header)
                failed, usersAdded = check_response_status(response, params["email"], i+2, failed, usersAdded, "admin", path)
        # If not a system role, then the siteGuid is required
        elif(not isinstance(params["siteGuid"],str)):
            writelog("Trying to add a clinic user (" + params["email"] + ", role '" + params["roleOID"] + "'), but siteGuid, siteName and siteCode are all missing!", path)
            failed.append(i+2)
            continue
        # If the siteGuid is provided, then proceed with inviting the clinic role
        else:
            writelog("Provided roleOID is not a system role. Trying to import as a clinic role.", path)
            writelog("Sending the following user details to " + url + "/admin/clinicusers:", path)
            writelog("- email: " + params["email"], path, option = "notimestamp")
            writelog("- roleOID: " + params["roleOID"].upper(), path, option = "notimestamp")
            writelog("- siteGuid: " + params["siteGuid"], path, option = "notimestamp")
            body = '[\n{\n"email":"' + params["email"] + '",\n"roles":[\n{\n"roleOID":"' + params["roleOID"].upper() + '",\n"siteGuid":"' + params["siteGuid"] + '"\n}\n]\n}\n]'
            response = requests.post(url + "/admin/clinicusers", data = body, headers = header)
            failed, usersAdded = check_response_status(response, params["email"], i+2, failed, usersAdded, "clinic", path)
            # If failed to add user, maybe roleOID not provided as a Role ID (R1, R2, etc). Try to convert using response content:
            if response.status_code == 400 and "availableRoles" in response.json():
                response = response.json()
                writelog("Status code: 400 - Failure. The provided roleOID is not a valid Role ID. Trying to convert.", path)
                availableRoles = {}
                for j in range(0, len(response["availableRoles"])):
                    availableRoles[response["availableRoles"][j]["roleName"].lower()] = response["availableRoles"][j]["roleOID"]
                if(params["roleOID"].lower() in availableRoles.keys()):
                    writelog(params["roleOID"] + " converted to " + availableRoles[params["roleOID"].lower()] + " for import.", path)
                    params["roleOID"] = availableRoles[params["roleOID"].lower()]
                    writelog("Sending the following user details to " + url + "/admin/clinicusers:", path)
                    writelog("- email: " + params["email"], path, option = "notimestamp")
                    writelog("- roleOID: " + params["roleOID"], path, option = "notimestamp")
                    writelog("- siteGuid: " + params["siteGuid"], path, option = "notimestamp")
                    body = '[\n{\n"email":"' + params["email"] + '",\n"roles":[\n{\n"roleOID":"' + params["roleOID"] + '",\n"siteGuid":"' + params["siteGuid"] + '"\n}\n]\n}\n]'
                    response = requests.post(url + "/admin/clinicusers", data = body, headers = header)
                    failed, usersAdded = check_response_status(response, params["email"], i+2, failed, usersAdded, "clinic", path)
                    if(response.status_code == 400 and response.content != b'The given key was not present in the dictionary'):
                        writelog("Status code: 400 - Failure. User not added. Details:", path)
                        writelog(response.json(), path, option = "notimestamp")
                        failed.append(i+2)
                # If not possible to convert, print information on valid roleOIDs
                else:
                    writelog("Unable to convert. " + params["roleOID"] + " is an invalid roleOID in this study.", path)
                    print("For clinic roles: see Role ID in Viedoc Designer.\nFor system roles, the following are valid: RoleStudyManager, RoleSiteManager, ApiManager,")
                    print("RoleDesigner, UnblindedStatistician, DictionaryManager, RefDataSourceManager, EtmfManager, DesignImpactAnalyst.")
                    failed.append(i+2)
            # If the API response does not contain availableRoles, then likely something caused the failure
            elif response.status_code == 400 and not "availableRoles" in response.json():
                writelog("Status code: 400 - Failure. Is '" + params["email"] + "' a valid email?", path)
                failed.append(i+2)
    if(usersAdded == 0):
        writelog("No users were created or roles assigned.\n", path)
    elif(usersAdded == 1):
        writelog("One role was successfully assigned.\n", path)
    else:
        writelog(str(usersAdded) + " roles were successfully assigned.\n", path)
    if(len(failed) > 0):
        writelog("Failed Excel rows: " + str(failed)[1:len(str(failed))-1] + ".\n", path)
    writelog("Returning to user input.", path)


def writelog(logtxt, path, disp = True, option = "standard"):
    """
    Writes message to log file and optionally prints it to the console.
    """
    # For option "firstentry"
    if option == "firstentry":
        # If a log file exists, then continue in the same file after a line of dashes -----
        if os.path.isfile(path + "log.txt"):
            with open(path + "log.txt", "a") as f:
                f.write("\n" + "-" * 100 + "\n\n" + str(datetime.datetime.now()) + ": " + logtxt + "\n")
        else:
            with open(path + "log.txt", "a") as f:
                f.write(str(datetime.datetime.now()) + ": " + logtxt + "\n")
    
    # For option "notimestamp"
    elif option == "notimestamp":
        with open(path + "log.txt", "a") as f:
            f.write(" " * 28 + logtxt + "\n")
    
    # For option "error"
    elif option == "error":
        with open(path + "log.txt", "a") as f:
            f.write(str(logtxt) + "\n")
    
    # For option "standard"
    elif option == "standard":
        with open(path + "log.txt", "a") as f:
            f.write(str(datetime.datetime.now()) + ": " + logtxt + "\n")
    
    # Print message to the console if specified
    if disp:
        print(logtxt)


def check_response_status(response, email, row, failed, usersAdded, userType, path):
    """
    Checks the response status code for adding users.
    """
    if(response.status_code == 400):
        if(response.content == b'The given key was not present in the dictionary'):
            writelog("Status code: 400 - 'The given key was not present in the dictionary.' Cannot check if user invite was successful. Please check in Viedoc Admin.", path)
        elif(userType == "admin"):
            writelog("Status code: 400 - Failure. Is '" + email + "' a valid email?", path)
            failed.append(row)
    elif(response.status_code == 403):
        writelog("Status code: 403 - Failure. Check API configuration in Viedoc Admin.", path)
        failed.append(row)
    elif(response.status_code == 200):
        usersAdded += 1
        writelog("Status code: 200 - Success. User added.", path)
    return failed, usersAdded


def create_site_import_template(path):
    """
    Creates an Excel file to import sites, if it does not exist yet.
    """
    if not os.path.isfile(path + "SitesToAdd_template.xlsx"):
        writer = pd.ExcelWriter(path + "SitesToAdd_template.xlsx", engine = "openpyxl")
        sitesTemplate = pd.DataFrame({"siteCode":[], "siteName":[], "countryCode":[], "timeZoneId":[], "expectedNumberOfSubjectsScreened":[],
            "expectedNumberOfSubjectsEnrolled":[], "maximumNumberOfSubjectsScreened":[], "isTrainingEnabled":[], "isProductionEnabled":[], "roleSiteManager":[]})
        sitesTemplate.to_excel(writer, index = False, sheet_name = "Template")
        ws = writer.sheets["Template"]
        columnwidths = {"A": 10, "B": 30, "C": 12, "D": 42, "E": 35, "F": 35, "G": 35, "H": 17, "I": 19, "J": 30}
        for column in columnwidths.keys():
            ws.column_dimensions[column].width = columnwidths[column]  # Set column widths in Excel file
        for row in range(2,1001): 
            ws['A'+str(row)].number_format = "@"  # Set siteCode column to text type
        writer.close()
        print("Template for importing sites was not found in the selected folder. It has been created.")


def create_user_import_template(path):
    """
    Creates an Excel file to import users, if it does not exist yet.
    """
    if not os.path.isfile(path + "UsersToAdd_template.xlsx"):
        writer = pd.ExcelWriter(path + "UsersToAdd_template.xlsx", engine = "openpyxl")
        usersTemplate = pd.DataFrame({"email":[], "roleOID":[], "siteGuid":[], "siteName":[], "siteCode":[]})
        usersTemplate.to_excel(writer, index = False, sheet_name = "Template")
        ws = writer.sheets["Template"]
        columnwidths = {"A": 30, "B": 25, "C": 37, "D": 30, "E": 10}
        for column in columnwidths.keys():
            ws.column_dimensions[column].width = columnwidths[column]  # Set column widths in Excel file
        for row in range(2,1001):
            ws['E'+str(row)].number_format = "@"  # Set siteCode column to text type
        writer.close()
        print("Template for importing users was not found in the selected folder. It has been created.\n")


def toTrueFalse(x):
    """
    Converts various values to True or False.
    """
    if(x in ["TRUE","True","true","T","t","Yes","yes","Y","y","1"]):
        return "True"
    if(x in ["FALSE","False","false","F","f","No","no","N","n","0"]):
        return "False"
    return x
