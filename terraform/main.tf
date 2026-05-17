terraform {
  required_version = ">= 1.7"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project
  region  = var.region
}

# ── APIs ──────────────────────────────────────────────────────────────────────

resource "google_project_service" "run" {
  service            = "run.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "artifact_registry" {
  service            = "artifactregistry.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_service" "cloud_build" {
  service            = "cloudbuild.googleapis.com"
  disable_on_destroy = false
}

# ── Artifact Registry ─────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "orchestra" {
  location      = var.region
  repository_id = "orchestra"
  format        = "DOCKER"
  description   = "Orchestra TPRM container images"
  depends_on    = [google_project_service.artifact_registry]
}

# ── Cloud Run service ─────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "tprm" {
  name     = "orchestra-tprm"
  location = var.region

  template {
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project}/orchestra/tprm:${var.image_tag}"

      env {
        name  = "GOOGLE_API_KEY"
        value = var.google_api_key
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project
      }

      resources {
        limits = {
          memory = "2Gi"
          cpu    = "2"
        }
      }

      ports {
        container_port = 8080
      }
    }

    timeout     = "900s"
    max_instance_request_concurrency = 80
  }

  depends_on = [
    google_project_service.run,
    google_artifact_registry_repository.orchestra,
  ]
}

# ── Public access ─────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service_iam_member" "public" {
  project  = var.project
  location = var.region
  name     = google_cloud_run_v2_service.tprm.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
