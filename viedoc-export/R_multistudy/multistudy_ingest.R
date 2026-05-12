install.packages(c("httr","jsonlite","logging","readr","fs","tools","base64enc","stringr", "rlang"))
library(httr)
library(jsonlite)
library(logging)
library(readr)
library(fs)
library(tools)
library(base64enc)
library(stringr)

export_file_location <- "C:/Users/SylviaVanBelle/w/ViedocExports"
study_api_client_csv <- "viedoc-export/study_list.csv"
nest_by <- "STUDY" # export_file_location/study_ref/yymmddhhmm.file
unzip_CSVs <- TRUE
# nest_by <- "INGEST"   # export_file_location/yymmddhhmm/study_ref.file
nest_depth <- 3 # 0: export_file_location/name.file. 3:  file_location/study_ref/yymmddhhmm/{STUDY_GUID__YYYYMMDD_HHmmss}/{STUDY_GUID__YYYYMMDD_HHmmss}.file
exclude_download_name <- TRUE # export_file_location/study_ref/yymmddhhmm_{STUDY_GUID__YYYYMMDD_HHmmss}.file <- nest depth 1
exclude_generated_name <- FALSE # export_file_location/study_ref/{STUDY_GUID__YYYYMMDD_HHmmss}.file  <- nest depth 1
# note: generated name uses local time, download file shows UTC time.
# global defaults / overrides
break_on_fail <- TRUE # exit or continue if a study export fails. Exit during intitial testing
defaults <- list( # if not specified in csv for study
  apiURL = "https://v4api.viedoc.net",
  tokenURL = "https://v4sts.viedoc.net/connect/token",
  maximum_wait_time_in_s = 300,
  check_every_n_s = 10,
  export_model = list(
    ## -- Record (length)) --filters ##
    # "siteIds"=list("SE-3-001"),                     # Default: All
    # "eventDefIds"=list("V1", "V2"),                 # Default: All
    # "timePeriodDateType"="SystemDate"|"EventDate",   # Default: NULL
    #   # ~~ if timePeriodDateType: ~~
    #    "timePeriodOption"="Between"|"Until"|"From", # Required
    #   # ~~ if "Between":
    ##     "fromDate"="1970-01-01T00:00:00Z",          # Default: 00:00 today
    ##     "toDate"="1970-01-01T00:00:00Z",            # Default: 00:00 today
    #   # ~~ if "Until":
    ##     "toDate"="1970-01-01T00:00:00Z",            # Default: 00:00 today
    #   # ~~ if "From":
    ##     "fromDate"="1970-01-01T00:00:00Z",          # Default: 00:00 today
    # "includeSignedOnly"=FALSE,                      # Default TRUE. If FALSE, includeNotSigned must be TRUE  # NOT AVAILABLE IN ODM/XML
    # "includeNotSigned"=FALSE,                       # Default TRUE, If FALSE, includeSignedOnly must be TRUE # NOT AVAILABLE IN ODM/XML
    # "includeSDVPerformedOrNA"=FALSE,                # Default TRUE. If FALSE, includeSDVPending must be TRUE       # NOT AVAILABLE IN ODM/XML
    # "includeSDVPending"=FALSE,                      # Default TRUE, If FALSE, includeSDVPerformedOrNA must be TRUE # NOT AVAILABLE IN ODM/XML
    # "includePendingForms"=TRUE,                     # Default False  # NOT AVAILABLE IN ODM/XML

    ## -- Content (breadth) filters --##
    # "formDefIds"=list("AE"),                        # Default All
    #   # ~~ if formDefIds are listed: ~~
    ##   "itemDefIds"=list("AE1"),                    # Default All
    # "includeQueries=TRUE,                           # Default False
    # "includeReviewStatus=TRUE,                      # Default False
    #   # ~~ if includeReviewStatus: ~~
    ##   "includeSignatures=TRUE,                     # Default FALSE  # ODM/XML ONLY
    # "includeVisitDates"=TRUE,                       # Default False  # NOT AVAILABLE IN PDF
    # "includeMedicalCoding"=TRUE,                    # Default FALSE
    # "includeEditStatus"=TRUE,                       # Default FALSE  # NOT AVAILABLE IN PDF
    # "includeSubjectStatus"=TRUE,                    # Default FALSE  # NOT AVAILABLE IN PDF
    # "includeSdv"=TRUE,                              # Default FALSE
    # "includeHistory"="True",                        # Default FALSE
    # "includeBookletStatus"=TRUE,                    # Default FALSE PMS studies ONLY
    # "includeBookletStatusHistory"=TRUE,             # Default FALSE PMS studies ONLY

    ## -- Generation settings --##
    "outputFormat" = "CSV" #|"Excel" |'XML'              # Required
    #   # ~~ if outputFormat CSV OR Excel: ~~
    # "rowLayout" = "RowPerPatient"|"RowPerValue"|"RowPerActivity"  # Default RowPerActivity
    # "grouping" = "None" |"GroupByForm"              # Default GroupByForm
    # ~~ if outputFormat CSV : ~~
    #     "includeSasScript" = TRUE,                  # Default FALSE
    #   # ~~ if outputFormat XML : ~~
    ##  "includeViedocExtensions" = TRUE               # Default FALSE
    # "exportVersion" = "4.51"                          # Default lastest
  )
)

`%||%` <- function(a, b) if (!is.null(a)) a else b # "use a if it isn’t NULL, otherwise use b

extension_from_output_format <- function(fmt) {
  fmt <- toupper(fmt %||% "EXCEL")
  switch(fmt,
    "CSV" = ".zip", # CSV exports often come zipped
    "XML" = ".xml",
    "PDF" = ".pdf",
    "EXCEL" = ".xlsx",
    ".bin" # fallback
  )
}

build_output_path <- function(
    root_dir,
    study_ref,
    ingest_start_time,
    nest_by = c("STUDY", "INGEST"),
    nest_depth = 2,
    exclude_download_name = FALSE,
    exclude_generated_name = FALSE,
    download_name = NULL,
    extension = ".bin") {
  safe_study <- gsub("[^[:alnum:]_.-]", "_", study_ref)
  # build subdir + file_prefix
  subdir <- root_dir
  file_prefix <- "" # what we prepend to the base name (if any)


  # decide level order
  # validate arg
  nest_by <- match.arg(nest_by)
  if (nest_by == "STUDY") {
    level_1 <- safe_study
    level_2 <- ingest_start_time
  }
  if (nest_by == "INGEST") {
    level_1 <- ingest_start_time
    level_2 <- safe_study
  }
  # validate nest_depth
  if (!is.numeric(nest_depth) || length(nest_depth) != 1 || nest_depth < 0 || nest_depth > 3) {
    warning("nest_depth must be 0..3; defaulting to 2")
    nest_depth <- 2L
  } else {
    nest_depth <- as.integer(nest_depth)
  }


  if (nest_depth == 0) {
    subdir <- file.path(subdir)
    file_prefix <- paste(level_1, level_2, sep = "_")
  } else if (nest_depth == 1) {
    subdir <- file.path(subdir, level_1)
    file_prefix <- level_2
  } else if (nest_depth == 2) {
    subdir <- file.path(subdir, level_1, level_2)
    file_prefix <- ""
  } else { # (nest_depth == 3)
    subdir <- file.path(subdir, level_1, level_2, safe_study)
    file_prefix <- ""
  }

  # optionally remove the generated prefix
  if (isTRUE(exclude_generated_name)) {
    file_prefix <- ""
  }

  # if (isTRUE(exclude_generated_name)){
  #    subdir <- file.path(subdir, file_prefix)
  #    file_prefix <- ""
  # }
  # create folders if they don't exist
  if (!fs::dir_exists(subdir)) fs::dir_create(subdir, recurse = TRUE)

  # choose basename
  base <- file_prefix

  # if including download name and download name is valid
  if (!isTRUE(exclude_download_name) && !is.null(download_name) && !is.na(download_name) && nzchar(download_name)) {
    dl_name <- tools::file_path_sans_ext(basename(download_name))
    # name = prefix_download_name or downloadname
    base <- if (nzchar(file_prefix)) {
      paste(file_prefix, dl_name, sep = "_")
    } else {
      dl_name
    }
  }
  if (!nzchar(base)) base <- safe_study # final fallback
  return(file.path(subdir, paste0(base, extension)))
}

get_token <- function(token_url, clientId, clientSecret) {
  auth_params <- list(
    "grant_type" = "client_credentials",
    "client_id" = clientId,
    "client_secret" = clientSecret
  )
  tryCatch(
    {
      response <- POST(url = token_url, body = auth_params, encode = "form")

      # if http error, return null
      if (http_error(response)) {
        # Capture response text (avoid parsing binary)
        logerror(
          "HTTP error %s: %s", status_code(response),
          content(response, "text", encoding = "UTF-8")
        )
        return(NULL)
      }

      resp_parsed <- fromJSON(content(response, "text", encoding = "UTF-8"))
      if (!"access_token" %in% names(resp_parsed)) {
        logerror(
          "Unexpexted response: did not contain 'access_token': %s",
          paste(names(resp_parsed), collapse = ", ")
        )
        return(NULL)
      }

      token <- resp_parsed$access_token
      loginfo("Successfully retrieved access token")
      return(token)
    },
    error = function(e) {
      logerror("Transport/parse error: %s", e$message)
      return(NULL)
    }
  )
}

start_data_export <- function(api_url, auth, params) {
  tryCatch(
    {
      resp <- POST(
        url = paste(api_url, "/clinic/dataexport/start", sep = ""),
        accept_json(),
        add_headers(Authorization = auth),
        body = params,
        encode = "json"
      )
      if (http_error(resp)) {
        logerror(
          "HTTP error %s: %s", status_code(resp),
          content(resp, "text", encoding = "UTF-8")
        )
        return(NULL)
      }

      # Parse response text into JSON
      resp_parsed <- fromJSON(content(resp, "text", encoding = "UTF-8"))

      if (!"exportId" %in% names(resp_parsed)) {
        logerror(
          "Response did not contain 'exportId': %s",
          paste(names(resp_parsed), collapse = ", ")
        )
        return(NULL)
      }

      export_id <- resp_parsed$exportId
      loginfo("Successfully started export")
      return(export_id)
    },
    error = function(e) {
      logerror("Transport/parse error: %s", e$message)
      return(NULL)
    }
  )
}

get_data_export_task <- function(api_url, auth, export_id, task = "status") {
  url <- paste(api_url, "/clinic/dataexport/", task, "?exportId=", export_id, sep = "")

  response <- GET(
    url = url,
    accept_json(),
    add_headers(Authorization = auth)
  )
  if (http_error(response)) {
    logerror(
      "HTTP error %s: %s", status_code(response),
      content(response, "text", encoding = "UTF-8")
    )
    return(NULL)
  } else {
    return(response)
  }
}

get_export_status <- function(api_url, auth, export_id) {
  tryCatch(
    {
      response <- get_data_export_task(api_url, auth, export_id, task = "status")

      # Parse response text into JSON
      resp_parsed <- fromJSON(content(response, "text", encoding = "UTF-8"))

      if (!"exportStatus" %in% names(resp_parsed)) {
        logerror(
          "Response did not contain 'exportStatus': %s",
          paste(names(resp_parsed), collapse = ", ")
        )
        return(NULL)
      }
      export_status <- resp_parsed$exportStatus
      loginfo(paste("export status:", export_status, ""))
      return(export_status)
    },
    error = function(e) {
      logerror("Transport/parse error: %s", e$message)
      return(NULL)
    }
  )
}

get_export_data <- function(api_url, auth, export_id) {
  tryCatch(
    {
      response <- get_data_export_task(api_url, auth, export_id, task = "download")
      if (is.null(response)) {
        return(list(content_raw = NULL, download_name = NULL))
      }

      content_raw <- httr::content(response, "raw")
      cd <- headers(response)[["content-disposition"]]
      download_name <- ""
      if (!is.null(cd)) {
        m <- stringr::str_match(cd, "filename=\"?([^\";]+)\"?")
        if (!is.na(m[1, 2])) download_name <- m[1, 2]
      }

      list(content_raw = content_raw, download_name = download_name %||% "")
    },
    error = function(e) {
      logerror("Transport/parse error (download): %s", e$message)
      list(content_raw = NULL, download_name = NULL)
    }
  )
}


ingest_study_data <- function(study_ref,
                              clientId,
                              clientSecret,
                              api_url,
                              token_url,
                              params,
                              maximum_wait_time_in_s,
                              check_every_n_s,
                              export_file_location,
                              ingest_time,
                              nest_by,
                              nest_depth,
                              exclude_download_name,
                              exclude_generated_name) {
  token <- get_token(token_url, clientId, clientSecret)
  if (is.null(token)) {
    logerror(paste("unable to retrieve token for study", study_ref, sep = " "))
    return
  }
  auth <- paste("Bearer", token, sep = " ")
  export_id <- start_data_export(api_url, auth, params)
  if (is.null(export_id)) {
    logerror(paste("unable to start export for study", study_ref, sep = " "))
    return
  }
  n_checks <- round(maximum_wait_time_in_s / check_every_n_s)
  for (i in seq(1, n_checks, 1)) {
    Sys.sleep(check_every_n_s)
    loginfo("check: %d", i)
    export_status <- get_export_status(api_url, auth, export_id)
    if (is.null(export_status)) next
    if (identical(export_status, "Ready")) break
  }
  if (is.null(export_status)) {
    logerror("%d checks without a successful status response", n_checks)
    return(invisible(NULL))
  }
  if (!identical(export_status, "Ready")) {
    logerror("Export not available after %d checks (last status: %s)", n_checks, export_status)
    return(invisible(NULL))
  }
  download <- get_export_data(api_url, auth, export_id)
  if (is.null(download$content_raw)) {
    logerror("No content returned for study %s", study_ref)
    return(invisible(NULL))
  }
  extension <- extension_from_output_format(params$outputFormat)
  out_path <- build_output_path(
    root_dir = export_file_location,
    study_ref = study_ref,
    ingest_start_time = ingest_time,
    nest_by = nest_by,
    nest_depth = nest_depth,
    exclude_download_name = exclude_download_name,
    exclude_generated_name = exclude_generated_name,
    download_name = download$download_name,
    extension = extension
  )
  tryCatch(
    {
      writeBin(download$content_raw, out_path)
      loginfo("Wrote export to %s", out_path)
      invisible(out_path)
    },
    error = function(e) {
      logerror(
        "Failed to write export for study %s to %s: %s",
        study_ref, out_path, e$message
      )
      invisible(NULL)
    }
  )
}

# manage logging
if (!dir_exists(export_file_location)) dir_create(export_file_location, recurse = TRUE)
logfile <- file.path(export_file_location, "log.txt")
basicConfig()
addHandler(writeToFile, file = logfile, level = "INFO")


################# --MAIN-######################

ingest_start_time <- format(Sys.time(), "%y%m%d%H%M")
# get per-study values from CSV
studies <- readr::read_csv(study_api_client_csv)
for (i in seq_len(nrow(studies))) {
  study_ref <- studies$study_ref[i]
  clientId <- studies$clientId[i]
  clientSecret <- studies$clientSecret[i]

  # build a params list by merging defaults with CSV values if present
  ## Column name must match the default parameter label
  default_values <- defaults
  for (nm in names(defaults)) {
    if (nm %in% names(studies)) {
      val <- studies[[nm]][i]
      if (!is.na(val) && nzchar(as.character(val))) {
        default_values[[nm]] <- val
      }
    }
  }
  if (is.null(clientId) || is.na(clientId) || !nzchar(clientId) ||
    is.null(clientSecret) || is.na(clientSecret) || !nzchar(clientSecret)) {
    logerror("Missing client credentials for study %s", study_ref)
    if (isTRUE(break_on_fail)) break else next
  }
  loginfo(
    "Processing study: %s (apiURL=%s, tokenURL=%s, maxwait=%s, check=%s)",
    study_ref, default_values$apiURL, default_values$tokenURL,
    default_values$maximum_wait_time_in_s, default_values$check_every_n_s
  )

  out_path <- ingest_study_data(
    study_ref = study_ref,
    clientId = clientId,
    clientSecret = clientSecret,
    api_url = default_values$apiURL,
    token_url = default_values$tokenURL,
    params = default_values$export_model,
    maximum_wait_time_in_s = default_values$maximum_wait_time_in_s,
    check_every_n_s = default_values$check_every_n_s,
    export_file_location = export_file_location,
    ingest_time = ingest_start_time,
    nest_by = nest_by,
    nest_depth = nest_depth,
    exclude_download_name = exclude_download_name,
    exclude_generated_name = exclude_generated_name
  )
  if (isTRUE(unzip_CSVs) && toupper(default_values$export_model$outputFormat) == "CSV" && file.exists(out_path)) {
    unzip(out_path, exdir = dirname(out_path))
    loginfo("Unzipped CSV to %s", dirname(out_path))
  }
  if (is.null(out_path)) {
    logerror("Study %s failed — stopping loop", study_ref)
    if (isTRUE(break_on_fail)) {
      break # or use next to skip and continue
    }
  } else {
    loginfo("Study %s succeeded, file at %s", study_ref, out_path)
  }
}
