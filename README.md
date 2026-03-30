---
title: Repo2Product AI
emoji: ⚡
colorFrom: blue
colorTo: green
sdk: docker
sdk_version: "1.32.0"
app_file: app.py
pinned: true
---

<div align="center">
  <h1>⚡ Repo2Product AI</h1>
  <p><b>Transform any GitHub repository into a fully runnable, resource-aware product setup</b></p>
  
  <p>
    <a href="https://huggingface.co/spaces/Harshit-2425/repo2product"><b>Try it on Hugging Face Spaces</b></a>
  </p>
</div>

## 🎯 Overview

**Repo2Product AI** is a powerful, intelligent tool that analyzes any GitHub repository and automatically generates a ready-to-run setup package tailored dynamically to your specific hardware configuration. 

Gone are the days of struggling with broken dependencies, out-of-memory errors, and incompatible OS commands. Repo2Product AI generates automated setup scripts, containerized environments, and adapted dependency lists based on your precise system constraints (RAM, GPU availability, and Operating System).

## ✨ Key Features

- **🔗 Smart Repo Input** — Enter a full URL (`https://github.com/owner/repo`), a bare `owner/repo`, or just a GitHub **username** to browse and select from their public repositories.
- **🧠 Resource-Aware Adaptation** — Tell the tool your available RAM, OS, and GPU status. It dynamically calculates optimal worker threads, memory configurations, and generates tailored run scripts.
- **🔄 GPU-to-CPU Fallbacks** — No GPU? No problem. The system intelligently swaps GPU-bound packages for CPU-only equivalents and patches code where necessary.
- **📝 AI README Optimizer** — Improve any repository's README with AI-powered suggestions. Uses Hugging Face Cloud or local Ollama for streaming generation.
- **💬 AI Chat Assistant** — Engage in a localized, context-aware interactive chat to ask architecture or deployment questions about the processed codebase.
- **🐳 Auto-Dockerization** — Automatically generates multi-container `docker-compose.yml` and `Dockerfile` setups with appropriate exposed ports.
- **📦 Smart Dependency Analysis** — Deeply analyzes `requirements.txt`, `package.json`, and other dependency files to flag heavy packages, APIs, or missing prerequisites.
- **🤖 AI Explanation Engine** — Integrates with local LLMs (via Ollama) or Hugging Face Cloud Inference to provide natural language explanations of the codebase and optimization tips.
- **⚡ One-Click Execution** — Generates platform-specific `setup.sh`/`run.sh` for Linux/macOS and `setup.bat`/`run.bat` for Windows.

## 🚀 How It Works

1. **Provide a Repository**: Paste any GitHub URL, enter `owner/repo`, or browse a user's repos by entering their username.
2. **Define Your Hardware**: Specify your RAM capacity, Operating System, and whether you have a GPU available.
3. **Analyze**: Repo2Product AI clones the repo virtually, parses the structure, entry points, frameworks, and dependencies.
4. **Download & Run**: A complete `.zip` package is generated with environment templates, setup scripts, and a tailored `README_ADAPTED.md`. Just run the script and watch the app start!
5. **Optimize README** *(optional)*: Use the **README AI** tab to generate a professional, AI-improved version of the repo's README.

## 🛠️ Technology Stack

Repo2Product AI is built with:
- **Python 3.10+**
- **Streamlit** for the interactive frontend UI
- **Hugging Face Inference API / Ollama** for AI-driven insights and README optimization
- Custom AST and heuristic parsers for dependency and framework detection

## 🌐 Live Demo

Experience the tool live on Hugging Face Spaces:  
👉 **[Repo2Product AI on Hugging Face](https://huggingface.co/spaces/Harshit-2425/repo2product)**

## 💻 Local Installation

To run Repo2Product AI locally on your own machine:

```bash
# Clone the repository
git clone https://github.com/Harshu0810/repo2product.git
cd repo2product

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt

# Run the Streamlit app
streamlit run app.py
```

## 🤝 Contributing

Contributions, issues, and feature requests are welcome! Feel free to check the [issues page](https://github.com/Harshu0810/repo2product/issues).

## 📝 License

This project is licensed under the MIT License.
