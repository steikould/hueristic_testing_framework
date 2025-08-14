variable "gcp_project_id" {
  description = "The GCP project ID."
  type        = string
  default     = "gcp-project-id-placeholder"
}

variable "gcp_region" {
  description = "The GCP region to deploy resources in."
  type        = string
  default     = "us-central1"
}
