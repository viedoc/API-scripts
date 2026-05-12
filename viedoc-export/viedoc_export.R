# Run the following command to install the required packages
# Rscript -e 'install.packages(c("httr", "jsonlite", "logging", "argparse", "stringr", "tools", "zip"), repos = "https://cran.r-project.org")'

library(httr)  # For HTTP requests
library(jsonlite)  # For JSON handling
library(logging)  # For logging
library(argparse)  # For parsing command-line arguments
library(stringr)  # For string operations
library(tools)  # For file operations
library(zip)  # For handling zip files

# Configure logging to display info messages with a specific format
basicConfig(level = "INFO")

get_token <- function(url, client_id, client_secret) {
  # Request an access token from the authentication server.
  # Args:
  # - url (str): URL to get the token from.
  # - client_id (str): Client ID for authentication.
  # - client_secret (str): Client secret for authentication.
  # Returns:
  # - str: Access token.
  loginfo("Getting token...")
  payload <- list(
    grant_type = "client_credentials",
    client_id = client_id,
    client_secret = client_secret
  )
  response <- POST(url, body = payload, encode = "form")
  stop_for_status(response)  # Raise an exception for HTTP errors
  return(content(response, "parsed")$access_token)
}

start_export <- function(url, token, export_model) {
  # Start the export process.
  # Args:
  # - url (str): URL to start the export.
  # - token (str): Access token for authorization.
  # - export_model (str): JSON string representing the export model.
  # Returns:
  # - str: Export ID.
  loginfo("Starting export...")
  headers <- add_headers(Authorization = paste("Bearer", token), `Content-Type` = "application/json")
  response <- POST(url, headers, body = export_model)
  
  if (status_code(response) > 399) {
    loginfo("Error: %s", content(response, "text"))
    stop_for_status(response)  # Raise an exception for HTTP errors
  }
  
  return(content(response, "parsed")$exportId)
}

check_export_status <- function(url, token, export_id) {
  # Check the status of the export until it's ready.
  # Args:
  # - url (str): URL to check the export status.
  # - token (str): Access token for authorization.
  # - export_id (str): ID of the export to check.
  loginfo("Checking export status...")
  headers <- add_headers(Authorization = paste("Bearer", token))
  while (TRUE) {
    response <- GET(url, headers, query = list(exportId = export_id))
    stop_for_status(response)  # Raise an exception for HTTP errors
    status <- content(response, "parsed")$exportStatus
    
    loginfo("Export status: %s", status)
    
    if (status == "Error") {
      stop("Export failed")  # Raise an exception if the export failed
    }
    
    if (status == "Ready") {
      return()  # Exit the loop if the export is ready
    }
    loginfo("Sleeping...")
    Sys.sleep(10)  # Wait for 10 seconds before checking again
  }
}

download_export <- function(url, token, export_id, output_path, extract_zip, remove_prefix) {
  # Download the export file and optionally extract it.
  # Args:
  # - url (str): URL to download the export.
  # - token (str): Access token for authorization.
  # - export_id (str): ID of the export to download.
  # - extract_zip (bool): Whether to extract the zip file.
  # - remove_prefix (bool): Whether to remove the prefix from extracted files.
  headers <- add_headers(Authorization = paste("Bearer", token))
  response <- GET(url, headers, query = list(exportId = export_id))
  stop_for_status(response)  # Raise an exception for HTTP errors
  
  # Extract the filename from the Content-Disposition header
  content_disposition_header <- headers(response)$`content-disposition`
  filename <- str_match(content_disposition_header, "filename=(.+)")[,2]
  
  # Create the 'out' folder if it doesn't exist
  if (!dir.exists(output_path)) {
    dir.create(output_path, recursive = TRUE)
  }
  
  loginfo("Folder path: %s", output_path)
  
  # If the filename is .zip and extract_zip is TRUE, extract the file
  if (endsWith(filename, ".zip") && extract_zip) {
    loginfo("Extracting zip file...")
    temp_file <- tempfile(fileext = ".zip")
    writeBin(content(response, "raw"), temp_file)
    unzip(temp_file, exdir = output_path)
    loginfo("File extracted successfully!")
    
    # Remove the prefix from the extracted files if required
    if (remove_prefix) {
      zip_filename_without_extension <- file_path_sans_ext(filename)
      extracted_files <- list.files(output_path)
      
      for (file in extracted_files) {
        # find index of folder name, else return -1
        prefix_finder <- regexpr(file, zip_filename_without_extension)[1]
        if (prefix_finder > 0) {
          new_filename <- substr(
            zip_filename_without_extension,
            # calculate index of end of folder name
            prefix_finder + nchar(file),  
            # get index of end of file name
            nchar(zip_filename_without_extension)
          )
          new_file_path <- file.path(output_path, new_filename)
          if (file.exists(new_file_path)) {
            file.remove(new_file_path)
          }
          file.rename(file.path(output_path, file), new_file_path)
        }
      }
    }
  } else {
    # Save the file to out/filename
    writeBin(content(response, "raw"), file.path(output_path, filename))
  }
}

main <- function(token_url, api_url, client_id, client_secret, export_model, output_path, extract_zip, remove_prefix) {
  # Main function to execute the export process.
  # Args:
  # - token_url (str): URL to get the token.
  # - api_url (str): Base API URL.
  # - client_id (str): Client ID for authentication.
  # - client_secret (str): Client secret for authentication.
  # - export_model (str): JSON string representing the export model.
  # - extract_zip (bool): Whether to extract the zip file.
  # - remove_prefix (bool): Whether to remove the prefix from extracted files.
  # Example export model:
  # {"outputFormat":"CSV","includeVisitDates":true,"includeEditStatus":true,"includeSignatures":true,"includeReviewStatus":true,"includeSdv":true,"includeQueries":true,"includeQueryHistory":true,"includeSubjectStatus":true,"includePendingForms":true}
  loginfo("ViedocExport@1")
  
  start_export_url <- paste0(api_url, "/clinic/dataexport/start")
  check_status_url <- paste0(api_url, "/clinic/dataexport/status")
  download_url <- paste0(api_url, "/clinic/dataexport/download")
  
  loginfo("Token URL: %s", token_url)
  loginfo("Start export URL: %s", start_export_url)
  loginfo("Check status URL: %s", check_status_url)
  loginfo("Download URL: %s", download_url)
  
  # Log only the first 3 characters of the client_id and client_secret for security
  loginfo("Client ID: %s", paste0(substring(client_id, 1, 3), strrep("*", nchar(client_id) - 3)))
  loginfo("Client secret: %s", paste0(substring(client_secret, 1, 3), strrep("*", nchar(client_secret) - 3)))
  loginfo("Export model: %s", export_model)
  
  # If the output path is not provided, use the current date and time as the folder name
  if (is.null(output_path)) {
    output_path <- format(Sys.time(), "%Y%m%d_%H%M%S")
  }
  
  # Get the access token
  token <- get_token(token_url, client_id, client_secret)
  
  # Start the export process
  export_id <- start_export(start_export_url, token, export_model)
  loginfo("Export ID: %s", export_id)
  
  # Check the export status until it's ready
  check_export_status(check_status_url, token, export_id)
  
  # Download the export file
  download_export(download_url, token, export_id, output_path, extract_zip, remove_prefix)
}

# Parsing command-line arguments
parser <- ArgumentParser(description = "Viedoc export script")

# Define command-line arguments
parser$add_argument("--token_url", required = TRUE, help = "Token URL")
parser$add_argument("--api_url", required = TRUE, help = "API URL")
parser$add_argument("--client_id", required = TRUE, help = "Client ID")
parser$add_argument("--client_secret", required = TRUE, help = "Client secret")
parser$add_argument("--export_model", required = TRUE, help = "Export model")
parser$add_argument("--output_path", required = FALSE, default = NULL, help = "Output path")
parser$add_argument("--extract_zip", required = FALSE, default = "Y", choices = c("Y", "N"), help = "Extract zip file (Y/N)")
parser$add_argument("--remove_prefix", required = FALSE, default = "Y", choices = c("Y", "N"), help = "Remove prefix from extracted files (Y/N)")

args <- parser$parse_args()

# Call the main function with parsed arguments
main(args$token_url, args$api_url, args$client_id, args$client_secret, args$export_model, args$output_path, args$extract_zip == "Y", args$remove_prefix == "Y")
