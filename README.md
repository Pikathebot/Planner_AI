# Local AI Planner Agent v2.0

A powerful, locally-hosted planning and chat agent powered by LM Studio. It features smart model selection based on task type, integrated web search, and a modern custom web interface.

## ✨ Features

- **Dual Modes**: 
  - **Planning Mode**: Generates detailed, structured plans for complex goals.
  - **Chat Mode**: General conversational assistant with context awareness.
- **Smart Model Routing**: Automatically selects the best model for the task.
- **Web Search**: Integrates DuckDuckGo search to provide up-to-date information.
- **Custom Web UI**: A sleek, glassmorphic FastAPI-based web interface.
- **CLI Interface**: A robust terminal interface with rich markdown rendering and session management.
- **Session Control**: Save and load conversation history and plans.
- **Model Unloading**: Automatically releases GPU memory (VRAM) by unloading unused LLMs using the `lms` CLI.

## 🛠️ Setup

### Prerequisites

1.  **LM Studio**: Install [LM Studio](https://lmstudio.ai/) and ensure the Local Server is running (usually on port `1234`). Make sure the `lms` CLI is initialized.
2.  **Models**: Download the required models in LM Studio:
    - `unsloth/gemma-4-12B-it-qat-GGUF` (LLM)
    - `text-embedding-nomic-embed-text-v1.5` (Embedding)
3.  **Python**: Version 3.10 or higher.

### Installation

1.  Clone the repository:
    ```bash
    git clone <repository-url>
    cd Planner_Agent
    ```
2.  Create and activate a virtual environment:
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

### Configuration

Create a `.env` file in the root directory (copy from `.env.example` if available):
```env
AUTH_USERNAME=admin
AUTH_PASSWORD=your_secure_password
```

## 🚀 Running the Application

### Web Interface (Recommended)

Start the FastAPI server:
```bash
python server.py
```
Then visit `http://localhost:8000` in your browser.

### CLI Interface

Run the terminal-based agent:
```bash
python main.py
```

### Remote Access (Cloudflare Tunnel)

If you have `cloudflared.exe` in the root (or installed), you can expose the server securely:
```bash
start_tunnel.bat
```

## 📂 Project Structure

- `server.py`: FastAPI backend management.
- `main.py`: Interactive CLI application.
- `static/`: Frontend assets (UI).
- `agent/`: Core logic (Planner, Classifier, Model Manager).
- `config.py`: Model registry and task definitions.
- `log/`: Automated chat and session logging.

## 📝 License

MIT
