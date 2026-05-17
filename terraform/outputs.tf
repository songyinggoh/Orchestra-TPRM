output "url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.tprm.uri
}

output "image" {
  description = "Full image path in Artifact Registry"
  value       = "${var.region}-docker.pkg.dev/${var.project}/orchestra/tprm:${var.image_tag}"
}
