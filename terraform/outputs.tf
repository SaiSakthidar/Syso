output "external_ip" {
  description = "The public IP address of the Syso server"
  value       = google_compute_instance.syso_server.network_interface[0].access_config[0].nat_ip
}

output "instance_self_link" {
  description = "Self-link of the compute instance"
  value       = google_compute_instance.syso_server.self_link
}
