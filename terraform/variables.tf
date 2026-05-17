variable "project" {
  description = "GCP project ID"
  type        = string
  default     = "advance-replica-496216-n6"
}

variable "region" {
  description = "GCP region for Cloud Run and Artifact Registry"
  type        = string
  default     = "us-central1"
}

variable "image_tag" {
  description = "Docker image tag to deploy (set to a commit SHA for immutable deploys)"
  type        = string
  default     = "latest"
}

variable "google_api_key" {
  description = "Google AI Studio API key (GOOGLE_API_KEY) injected as a Cloud Run env var"
  type        = string
  sensitive   = true
}
