# Syso GCP Deployment Guide

This guide covers how to deploy the Syso backend to Google Cloud using Terraform.

## Prerequisites

1.  **Google Cloud Project**: You need an active GCP project.
2.  **gcloud CLI**: Installed and authenticated.
3.  **Terraform**: Installed on your local machine.

## 1. Install Terraform (if not installed)

On most Linux systems, you can install Terraform via Snap:
```bash
sudo snap install terraform --classic
```

Or follow the [official HashiCorp instructions](https://developer.hashicorp.com/terraform/downloads).

## 2. Authenticate with GCP

Run these commands to ensure Terraform can access your GCP account:

```bash
gcloud auth login
gcloud auth application-default login
```

## 3. Configure Variables

Create a `terraform/terraform.tfvars` file and add your Project ID:

```hcl
project_id = "your-gcp-project-id"
region     = "us-central1"
zone       = "us-central1-a"
```

## 4. Deploy

Navigate to the `terraform` directory and run:

```bash
# Initialize Terraform
terraform init

# Plan the deployment
terraform plan

# Apply changes (type 'yes' when prompted)
terraform apply
```

## 5. Push Code to Cloud

Terraform only creates the machine. Now you need to move your code there. Run the helper script from the root directory:

```bash
./terraform/scripts/push_to_cloud.sh
```

## 6. Start Cloud Backend

SSH into the machine and start the server:

```bash
gcloud compute ssh syso-backend --zone=asia-south1-a --project=gemini-489210 --command="cd /opt/syso && uv run python -m backend.main"
```

## 7. Verify & Run App

Once the cloud server is running:
1.  Run your local app: `uv run python -m app.main`
2.  Login or Skip.
3.  The app will now connect to the cloud IP!

## Cleanup

To stop the server and delete all resources (save costs):
```bash
terraform destroy
```
