# Heuristic Testing Framework for Cloud Run Services

This project provides a complete, deployable testing framework for Cloud Run services. It uses a configuration-driven approach, where tests are defined in a JSON file stored in a GCS bucket. A central Cloud Function acts as a test runner, executing tests against the specified services and logging the results to another GCS bucket.

The framework is provisioned using Terraform and includes a local Python script to compare test results over time.

## Prerequisites

Before you begin, ensure you have the following installed and configured:
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud`)
- [Terraform](https://learn.hashicorp.com/tutorials/terraform/install-cli) (v1.0 or later)
- [Python](https://www.python.org/downloads/) (v3.8 or later)
- A Google Cloud project with billing enabled.

You also need to be authenticated with Google Cloud:
```bash
gcloud auth login
gcloud auth application-default login
```

## Project Structure

```
.
├── README.md
├── compare_results.py      # Local script to compare test results
├── config
│   └── config.json         # Test definitions
├── requirements.txt        # Python requirements for the comparison script
├── src
│   ├── service_a/          # Source for placeholder service A
│   ├── service_b/          # Source for placeholder service B
│   ├── shared_module/      # A shared module used by the services
│   └── test_runner/        # Source for the main test runner Cloud Function
└── terraform/
    ├── main.tf             # Main Terraform infrastructure definition
    └── variables.tf        # Terraform variable definitions
```

## Deployment

The entire infrastructure is managed by Terraform.

### 1. Configure Project ID

In the `terraform/` directory, create a file named `terraform.tfvars` and set your GCP project ID:

**`terraform/terraform.tfvars`:**
```tfvars
gcp_project_id = "your-gcp-project-id"
```
Replace `"your-gcp-project-id"` with your actual Google Cloud project ID.

### 2. Build and Push Service Images (Important!)

The provided Terraform script uses placeholder images for the Cloud Run services. You must build and push your own service images to a container registry like Artifact Registry.

For each service (`service_a`, `service_b`):
1. **Enable Artifact Registry:**
   ```bash
   gcloud services enable artifactregistry.googleapis.com
   ```
2. **Create a repository:**
   ```bash
   gcloud artifacts repositories create my-repo --repository-format=docker --location=us-central1
   ```
3. **Build and push the image using Cloud Build:**
   ```bash
   # For service-a
   gcloud builds submit src/service_a --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-repo/service-a:latest

   # For service-b
   gcloud builds submit src/service_b --tag us-central1-docker.pkg.dev/your-gcp-project-id/my-repo/service-b:latest
   ```
4. **Update Terraform:**
   Open `terraform/main.tf` and replace the placeholder image URLs in the `google_cloud_run_v2_service` resources with the URLs of the images you just pushed.

### 3. Apply Terraform Configuration

Navigate to the `terraform` directory and run the following commands:
```bash
cd terraform

# Initialize Terraform
terraform init

# (Optional) See what resources will be created
terraform plan

# Apply the configuration to create the resources
terraform apply
```
Terraform will provision all the necessary resources. At the end of the process, it will output the URL of the test runner Cloud Function.

## Running Tests

To run the tests, simply invoke the HTTP trigger URL of the `test-runner-function`. You can get this URL from the output of `terraform apply`.

Use a tool like `curl` to trigger the tests:
```bash
curl -X GET $(terraform output -raw test_runner_function_url)
```
This will trigger the Cloud Function, which will read `config/config.json`, run all defined tests, and store the results in the GCS results bucket.

## Comparing Results

A Python script, `compare_results.py`, is provided to help you analyze test results.

### 1. Install Dependencies
From the root of the project, install the necessary Python packages:
```bash
pip install -r requirements.txt
```

### 2. Run the Comparison Script

The script can automatically compare the two most recent result files. You need to provide the name of the results bucket, which you can get from the Terraform output.

```bash
# Get the results bucket name
RESULTS_BUCKET=$(cd terraform && terraform output -raw results_bucket_name)

# Run the comparison
python compare_results.py $RESULTS_BUCKET
```

To compare two specific result files, provide their names as additional arguments:
```bash
python compare_results.py $RESULTS_BUCKET --files results-file-1.json results-file-2.json
```

## Customizing Tests

To add, remove, or modify tests, edit the `config/config.json` file. The test runner Cloud Function will automatically pick up the changes on its next run. After modifying the config, you may need to re-upload it to the GCS bucket if you are not re-running `terraform apply`.
```bash
# Get the config bucket name
CONFIG_BUCKET=$(cd terraform && terraform output -raw config_bucket_name)

# Upload the new config
gsutil cp config/config.json gs://$CONFIG_BUCKET/config.json
```
