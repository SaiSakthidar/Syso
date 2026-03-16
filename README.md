# Syso - AI System Caretaker

Syso is an AI-powered system management agent that uses Gemini Multimodal Live API to control your computer via voice, text and video (via screen recording). It is a multi-tiered RAG system that customises to your needs over time and gives you real time updates on your system health. 


## Features 
1. Continuous system monitoring in the background.
2. Automatically alerts system metrics cross a threshold. 
3. Changes system settings with just a voice command.
4. Remembers and learns over time system preferences of the user via advanced RAG infra.
5. Users can view a system dashboard whenever they enquire.
  
### Functionalities 

- high ram/cpu usage: RAM/CPU usage exceeds threshold
- low storage: Disk space below threshold
- high temperature: System temperature critical
- heavy process detected: Individual process using excessive resources and suggests app closing
- brightness change: Display brightness adjustment suggestion
- volume change: Audio volume adjustment suggestion
- network usage high: Network bandwidth spike detected
- battery low: Battery level critical
- theme_preference change: Auto-suggest dark/light theme based on time
- notification fatigue: Too many notifications suggest muting
- update available: OS or app updates available
- malware scan suggestion: Suggest running security scan
- connectivity issue: WiFi/network/bluetooth reliability problems

## Architecture 

<img width="1600" height="672" alt="image" src="https://github.com/user-attachments/assets/a0034451-3d98-470d-af6c-16316afdbb39" />

## Spin-up Instructions

### Prerequisites
- Python 3.11+
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Picovoice Access Key (for wake word)
- Gemini API Key

### Configuration
Create a `.env` file in the root directory:
```env
GEMINI_API_KEY=your_gemini_api_key
PICOVOICE_ACCESS_KEY=your_picovoice_access_key
BACKEND_WS_URL=ws://localhost:8000/ws
DATA_PATH=./data
```

### Running the App

1. **Start the Backend:**
   ```bash
   uv run python -m backend.main
   ```

2. **Start the GUI:**
   ```bash
   uv run python app/main.py
   ```

## How to Use
1. **Wake Word:** Say "Hello Syso" to start speaking.
2. **Dashboard:** Say "Dashboard" or "Show me the dashboard" to view the current sytem metrics. 

## Cloud Deployment (Terraform)
1. **Init:** `cd terraform && terraform init`
2. **Setup:** Update `terraform.tfvars` with your `project_id`.
3. **Deploy:** `terraform apply`
4. **Push:** `./terraform/scripts/push_to_cloud.sh`

See [DEPLOYMENT.md](terraform/DEPLOYMENT.md) for more.
