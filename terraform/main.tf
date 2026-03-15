provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# --- Enable Required Services ---
resource "google_project_service" "compute" {
  service = "compute.googleapis.com"
  disable_on_destroy = false
}

# --- VPC Network ---
resource "google_compute_network" "syso_vpc" {
  name                    = "syso-vpc"
  auto_create_subnetworks = false
  depends_on              = [google_project_service.compute]
}

resource "google_compute_subnetwork" "syso_subnet" {
  name          = "syso-subnet"
  ip_cidr_range = "10.0.1.0/24"
  network       = google_compute_network.syso_vpc.id
  region        = var.region
}

# --- Firewall Rules ---
resource "google_compute_firewall" "allow_http" {
  name    = "syso-allow-http"
  network = google_compute_network.syso_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["80", "8000"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["syso-backend"]
}

resource "google_compute_firewall" "allow_ssh" {
  name    = "syso-allow-ssh"
  network = google_compute_network.syso_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

# --- Persistent Disk for User Data ---
resource "google_compute_disk" "syso_data_disk" {
  name       = "syso-user-data"
  type       = "pd-standard"
  zone       = var.zone
  size       = 50 # 50 GB
  depends_on = [google_project_service.compute]
}

# --- Compute Instance ---
resource "google_compute_instance" "syso_server" {
  name         = var.instance_name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = ["syso-backend"]
  depends_on   = [google_project_service.compute]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 20
    }
  }

  attached_disk {
    source      = google_compute_disk.syso_data_disk.id
    device_name = "user-data"
  }

  network_interface {
    subnetwork = google_compute_subnetwork.syso_subnet.id
    access_config {
      # Ephemeral public IP
    }
  }

  metadata_startup_script = file("${path.module}/scripts/startup.sh")

  service_account {
    scopes = ["cloud-platform"]
  }
}
