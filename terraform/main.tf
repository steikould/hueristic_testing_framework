# --- Basic Setup ---
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.40"
    }
    random = {
      source = "hashicorp/random"
      version = "~> 3.1"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
}

# --- Unique Suffix for Resources ---
resource "random_id" "suffix" {
  byte_length = 4
}

# --- Service Accounts ---
resource "google_service_account" "cloud_run_sa" {
  account_id   = "cloud-run-sa-${random_id.suffix.hex}"
  display_name = "Service Account for Cloud Run services"
}

resource "google_service_account" "cloud_function_sa" {
  account_id   = "cloud-function-sa-${random_id.suffix.hex}"
  display_name = "Service Account for Test Runner Cloud Function"
}

# --- GCS Buckets ---
resource "google_storage_bucket" "shared_module_bucket" {
  name          = "shared-module-bucket-${random_id.suffix.hex}"
  location      = var.gcp_region
  force_destroy = true
}

resource "google_storage_bucket" "config_bucket" {
  name          = "config-bucket-${random_id.suffix.hex}"
  location      = var.gcp_region
  force_destroy = true
}

resource "google_storage_bucket" "results_bucket" {
  name          = "results-bucket-${random_id.suffix.hex}"
  location      = var.gcp_region
  force_destroy = true
}

# --- Upload initial files to GCS ---
resource "google_storage_bucket_object" "shared_module_object" {
  name   = "helper.py"
  bucket = google_storage_bucket.shared_module_bucket.name
  source = "../src/shared_module/helper.py"
}

resource "google_storage_bucket_object" "config_object" {
  name   = "config.json"
  bucket = google_storage_bucket.config_bucket.name
  source = "../config/config.json"
}

# --- Prepare Cloud Function Source ---
# This zips the source directory for the test runner function.
data "archive_file" "function_source" {
  type        = "zip"
  source_dir  = "../src/test_runner"
  output_path = "/tmp/test_runner_source.zip"
}

# This uploads the zipped source code to GCS for the function to use.
resource "google_storage_bucket_object" "function_source_zip" {
  name   = "source/${data.archive_file.function_source.output_md5}.zip"
  bucket = google_storage_bucket.config_bucket.name
  source = data.archive_file.function_source.output_path
}

# --- IAM Permissions for Service Accounts ---

# Allow Cloud Run SA to read from the shared module bucket
resource "google_project_iam_member" "cloud_run_storage_reader" {
  project = var.gcp_project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.cloud_run_sa.email}"
}

# Allow Cloud Function SA to read from the config bucket
resource "google_project_iam_member" "function_config_reader" {
  project = var.gcp_project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.cloud_function_sa.email}"
}

# Allow Cloud Function SA to write to the results bucket
resource "google_project_iam_member" "function_results_writer" {
  project = var.gcp_project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${google_service_account.cloud_function_sa.email}"
}

# --- Cloud Run Services ---

resource "google_cloud_run_v2_service" "service_a" {
  name     = "service-a"
  location = var.gcp_region

  template {
    service_account = google_service_account.cloud_run_sa.email
    containers {
      # IMPORTANT: Replace this with the actual path to your container image in Artifact Registry.
      image = "us-central1-docker.pkg.dev/${var.gcp_project_id}/my-repo/service-a:latest"
      env {
        name  = "MODULE_BUCKET"
        value = google_storage_bucket.shared_module_bucket.name
      }
      env {
        name = "MODULE_NAME"
        value = google_storage_bucket_object.shared_module_object.name
      }
    }
  }

  depends_on = [google_project_iam_member.cloud_run_storage_reader]
}

resource "google_cloud_run_v2_service" "service_b" {
  name     = "service-b"
  location = var.gcp_region

  template {
    service_account = google_service_account.cloud_run_sa.email
    containers {
      # IMPORTANT: Replace this with the actual path to your container image in Artifact Registry.
      image = "us-central1-docker.pkg.dev/${var.gcp_project_id}/my-repo/service-b:latest"
      env {
        name  = "MODULE_BUCKET"
        value = google_storage_bucket.shared_module_bucket.name
      }
      env {
        name = "MODULE_NAME"
        value = google_storage_bucket_object.shared_module_object.name
      }
    }
  }

  depends_on = [google_project_iam_member.cloud_run_storage_reader]
}


# --- Cloud Function ---
resource "google_cloudfunctions2_function" "test_runner_function" {
  name     = "test-runner-function"
  location = var.gcp_region

  build_config {
    runtime     = "python311"
    entry_point = "run_tests"
    source {
      storage_source {
        bucket = google_storage_bucket_object.function_source_zip.bucket
        object = google_storage_bucket_object.function_source_zip.name
      }
    }
  }

  service_config {
    service_account_email = google_service_account.cloud_function_sa.email
    environment_variables = {
      CONFIG_BUCKET  = google_storage_bucket.config_bucket.name
      RESULTS_BUCKET = google_storage_bucket.results_bucket.name
      CONFIG_NAME    = google_storage_bucket_object.config_object.name
      SERVICE_A_URL  = google_cloud_run_v2_service.service_a.uri
      SERVICE_B_URL  = google_cloud_run_v2_service.service_b.uri
    }
  }

  depends_on = [
    google_project_iam_member.function_config_reader,
    google_project_iam_member.function_results_writer
  ]
}

# --- IAM for invoking services ---

# Allow public access to Cloud Run services
resource "google_cloud_run_v2_service_iam_member" "service_a_invoker" {
  project  = var.gcp_project_id
  location = google_cloud_run_v2_service.service_a.location
  name     = google_cloud_run_v2_service.service_a.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "service_b_invoker" {
  project  = var.gcp_project_id
  location = google_cloud_run_v2_service.service_b.location
  name     = google_cloud_run_v2_service.service_b.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Allow Cloud Function to invoke Cloud Run services
resource "google_project_iam_member" "function_run_invoker" {
  project = var.gcp_project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.cloud_function_sa.email}"
}

# Allow public access to the Cloud Function
resource "google_cloudfunctions2_function_iam_member" "function_invoker" {
  project  = var.gcp_project_id
  location = google_cloudfunctions2_function.test_runner_function.location
  name     = google_cloudfunctions2_function.test_runner_function.name
  role     = "roles/cloudfunctions.invoker"
  member   = "allUsers"
}


# --- Outputs ---
output "test_runner_function_url" {
  description = "The URL of the test runner Cloud Function."
  value       = google_cloudfunctions2_function.test_runner_function.service_config[0].uri
}

output "config_bucket_name" {
  description = "Name of the GCS bucket for test configurations."
  value       = google_storage_bucket.config_bucket.name
}

output "results_bucket_name" {
  description = "Name of the GCS bucket for test results."
  value       = google_storage_bucket.results_bucket.name
}
