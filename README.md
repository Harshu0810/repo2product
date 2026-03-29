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

# ⚡ Repo2Product AI — Project-to-Product Converter

Transform any GitHub repository into a fully runnable, resource-aware, and user-adapted product setup.

## Features

- 📦 **Dependency Analysis** — Detects Python, Node.js, Go, Rust, Java dependencies
- ⚡ **CPU Optimization** — Adapts GPU-heavy projects to run on CPU-only systems
- 🐳 **Docker Compose** — Auto-generates containerized deployment configs
- 🚀 **One-Click Setup** — Generates setup scripts for Linux, macOS, and Windows
- 🤖 **AI Explanations** — Uses Hugging Face Inference API for smart project summaries

## How It Works

1. Paste a GitHub repository URL
2. The system analyzes structure, dependencies, and resource requirements
3. Downloads a ready-to-run setup package with:
   - `setup.sh` / `setup.bat` — automated setup
   - `run.sh` / `run.bat` — launch scripts
   - `docker-compose.yml` — containerized deployment
   - `requirements_adapted.txt` — CPU-optimized dependencies
   - `README_ADAPTED.md` — complete setup guide

## Constraints

- **Zero cost** — No paid APIs required
- **CPU-only** — Works on systems without GPU
- **Lightweight** — Uses only Python stdlib + Streamlit + requests
