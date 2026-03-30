"""
app.py — Repo2Product AI
Main Streamlit application. Production-grade developer tool UI.
Run: streamlit run app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
import time
from pathlib import Path
from analyzer.repo_fetcher import RepoFetcher
from utils.readme_optimizer import improve_readme_stream
from utils.chat_interface import chat_stream

# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Repo2Product AI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;500;600;700&display=swap');

/* ── Theme Variables ──────────────────────────────────────────────────── */
:root {
    --r2p-bg: #ffffff;
    --r2p-bg-alt: #f6f8fa;
    --r2p-bg-card: rgba(255,255,255,0.7);
    --r2p-bg-deep: #f0f2f5;
    --r2p-border: #d0d7de;
    --r2p-border-subtle: #e1e4e8;
    --r2p-text: #1f2328;
    --r2p-text-secondary: #656d76;
    --r2p-text-muted: #8b949e;
    --r2p-accent: #0969da;
    --r2p-green: #1a7f37;
    --r2p-red: #cf222e;
    --r2p-orange: #bf8700;
    --r2p-purple: #8250df;
    --r2p-shadow: rgba(31,35,40,0.08);
    --r2p-shadow-hover: rgba(31,35,40,0.15);
    --r2p-glass: rgba(255,255,255,0.6);
    --r2p-hero-bg: linear-gradient(135deg, #f6f8fa 0%, #eef1f5 100%);
    --r2p-hero-glow1: rgba(9,105,218,0.08);
    --r2p-hero-glow2: rgba(26,127,55,0.08);
    --r2p-badge-cpu-bg: rgba(26,127,55,0.1);
    --r2p-badge-cpu-border: rgba(26,127,55,0.3);
    --r2p-badge-local-bg: rgba(9,105,218,0.1);
    --r2p-badge-local-border: rgba(9,105,218,0.3);
    --r2p-badge-free-bg: rgba(130,80,223,0.1);
    --r2p-badge-free-border: rgba(130,80,223,0.3);
    --r2p-sidebar-bg: #f6f8fa;
    --r2p-gradient-bar: linear-gradient(90deg, #0969da, #1a7f37, #bf8700, #8250df);
    --r2p-issue-critical-bg: #fff5f5;
    --r2p-issue-warning-bg: #fffbeb;
    --r2p-issue-info-bg: #eff6ff;
    --r2p-tree-bg: #f6f8fa;
    --r2p-adapt-replace-bg: #eff6ff;
    --r2p-adapt-replace-border: #54aeff;
    --r2p-adapt-remove-bg: #fff5f5;
    --r2p-adapt-remove-border: #cf222e;
    --r2p-chip-bg: #eef1f5;
    --r2p-chip-color: #0969da;
    --r2p-chip-border: #d0d7de;
}

/* Dark theme (Streamlit's data-theme or browser preference) */
[data-theme="dark"], .stApp[data-theme="dark"] { color-scheme: dark; }

@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
        --r2p-bg: #0d1117;
        --r2p-bg-alt: #161b22;
        --r2p-bg-card: rgba(22,27,34,0.6);
        --r2p-bg-deep: #010409;
        --r2p-border: #30363d;
        --r2p-border-subtle: #21262d;
        --r2p-text: #e6edf3;
        --r2p-text-secondary: #8b949e;
        --r2p-text-muted: #656d76;
        --r2p-accent: #58a6ff;
        --r2p-green: #3fb950;
        --r2p-red: #f85149;
        --r2p-orange: #d29922;
        --r2p-purple: #d2a8ff;
        --r2p-shadow: rgba(0,0,0,0.2);
        --r2p-shadow-hover: rgba(0,0,0,0.35);
        --r2p-glass: rgba(22,27,34,0.6);
        --r2p-hero-bg: linear-gradient(135deg, rgba(13,17,23,0.95) 0%, rgba(22,27,34,0.95) 100%);
        --r2p-hero-glow1: rgba(88,166,255,0.1);
        --r2p-hero-glow2: rgba(63,185,80,0.1);
        --r2p-badge-cpu-bg: rgba(63,185,80,0.12);
        --r2p-badge-cpu-border: rgba(63,185,80,0.4);
        --r2p-badge-local-bg: rgba(88,166,255,0.12);
        --r2p-badge-local-border: rgba(88,166,255,0.4);
        --r2p-badge-free-bg: rgba(210,168,255,0.12);
        --r2p-badge-free-border: rgba(210,168,255,0.4);
        --r2p-sidebar-bg: #0d1117;
        --r2p-issue-critical-bg: rgba(248,81,73,0.08);
        --r2p-issue-warning-bg: rgba(210,153,34,0.08);
        --r2p-issue-info-bg: rgba(88,166,255,0.08);
        --r2p-tree-bg: #0d1117;
        --r2p-adapt-replace-bg: rgba(88,166,255,0.08);
        --r2p-adapt-replace-border: #1d4f8e;
        --r2p-adapt-remove-bg: rgba(248,81,73,0.08);
        --r2p-adapt-remove-border: #6e2020;
        --r2p-chip-bg: #1f2937;
        --r2p-chip-color: #93c5fd;
        --r2p-chip-border: #374151;
    }
}

/* Force dark when Streamlit sets dark theme */
[data-theme="dark"] {
    --r2p-bg: #0d1117; --r2p-bg-alt: #161b22; --r2p-bg-card: rgba(22,27,34,0.6);
    --r2p-bg-deep: #010409; --r2p-border: #30363d; --r2p-border-subtle: #21262d;
    --r2p-text: #e6edf3; --r2p-text-secondary: #8b949e; --r2p-text-muted: #656d76;
    --r2p-accent: #58a6ff; --r2p-green: #3fb950; --r2p-red: #f85149;
    --r2p-orange: #d29922; --r2p-purple: #d2a8ff;
    --r2p-shadow: rgba(0,0,0,0.2); --r2p-shadow-hover: rgba(0,0,0,0.35);
    --r2p-glass: rgba(22,27,34,0.6);
    --r2p-hero-bg: linear-gradient(135deg, rgba(13,17,23,0.95), rgba(22,27,34,0.95));
    --r2p-hero-glow1: rgba(88,166,255,0.1); --r2p-hero-glow2: rgba(63,185,80,0.1);
    --r2p-badge-cpu-bg: rgba(63,185,80,0.12); --r2p-badge-cpu-border: rgba(63,185,80,0.4);
    --r2p-badge-local-bg: rgba(88,166,255,0.12); --r2p-badge-local-border: rgba(88,166,255,0.4);
    --r2p-badge-free-bg: rgba(210,168,255,0.12); --r2p-badge-free-border: rgba(210,168,255,0.4);
    --r2p-sidebar-bg: #0d1117;
    --r2p-issue-critical-bg: rgba(248,81,73,0.08); --r2p-issue-warning-bg: rgba(210,153,34,0.08);
    --r2p-issue-info-bg: rgba(88,166,255,0.08); --r2p-tree-bg: #0d1117;
    --r2p-adapt-replace-bg: rgba(88,166,255,0.08); --r2p-adapt-replace-border: #1d4f8e;
    --r2p-adapt-remove-bg: rgba(248,81,73,0.08); --r2p-adapt-remove-border: #6e2020;
    --r2p-chip-bg: #1f2937; --r2p-chip-color: #93c5fd; --r2p-chip-border: #374151;
}

/* ── Animations ───────────────────────────────────────────────────────── */
@keyframes r2p-float {
    0%, 100% { transform: translateY(0px); }
    50% { transform: translateY(-12px); }
}
@keyframes r2p-fadeUp {
    from { opacity: 0; transform: translateY(18px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes r2p-gradientFlow {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
@keyframes r2p-shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
@keyframes r2p-pulse {
    0% { transform: scale(1); opacity: 0.7; }
    100% { transform: scale(1.15); opacity: 1; }
}

/* ── Base ─────────────────────────────────────────────────────────────── */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
code, pre { font-family: 'JetBrains Mono', monospace !important; }
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 1200px; }

/* ── Hero Banner ──────────────────────────────────────────────────────── */
.r2p-hero {
    background: var(--r2p-hero-bg),
                radial-gradient(circle at top right, var(--r2p-hero-glow1), transparent 400px),
                radial-gradient(circle at bottom left, var(--r2p-hero-glow2), transparent 400px);
    border: 1px solid var(--r2p-border); border-radius: 16px; padding: 2.2rem; margin-bottom: 2rem;
    position: relative; overflow: hidden;
    box-shadow: 0 8px 32px var(--r2p-shadow);
    animation: r2p-fadeUp 0.6s ease-out;
}
.r2p-hero::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, var(--r2p-accent), var(--r2p-green), var(--r2p-orange), var(--r2p-purple));
    background-size: 200% 100%;
    animation: r2p-gradientFlow 4s ease infinite;
}
.r2p-hero::after {
    content: ''; position: absolute; width: 180px; height: 180px;
    background: radial-gradient(circle, var(--r2p-hero-glow1) 0%, transparent 70%);
    top: -60px; right: -60px; border-radius: 50%;
    animation: r2p-pulse 4s infinite alternate; pointer-events: none;
}
.r2p-hero h1 { font-size: 2.2rem; font-weight: 700; color: var(--r2p-text); margin: 0 0 0.4rem 0; letter-spacing: -0.5px; }
.r2p-hero p { color: var(--r2p-text-secondary); margin: 0; font-size: 1.05rem; }

/* ── Badges ───────────────────────────────────────────────────────────── */
.r2p-badge {
    display: inline-block; padding: 3px 12px; border-radius: 100px;
    font-size: 11px; font-weight: 600; font-family: 'JetBrains Mono', monospace;
    margin: 0.5rem 0.35rem 0 0; text-transform: uppercase; letter-spacing: 0.5px;
    transition: all 0.2s ease;
}
.r2p-badge:hover { transform: translateY(-1px); filter: brightness(1.15); }
.badge-cpu { background: var(--r2p-badge-cpu-bg); color: var(--r2p-green); border: 1px solid var(--r2p-badge-cpu-border); }
.badge-local { background: var(--r2p-badge-local-bg); color: var(--r2p-accent); border: 1px solid var(--r2p-badge-local-border); }
.badge-free { background: var(--r2p-badge-free-bg); color: var(--r2p-purple); border: 1px solid var(--r2p-badge-free-border); }

/* ── Score Cards (glassmorphism) ──────────────────────────────────────── */
.score-card {
    background: var(--r2p-glass); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
    border: 1px solid var(--r2p-border); border-radius: 14px;
    padding: 1.5rem; text-align: center;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 16px var(--r2p-shadow);
    animation: r2p-fadeUp 0.5s ease-out both;
}
.score-card:hover {
    transform: translateY(-4px) scale(1.02);
    border-color: var(--r2p-accent);
    box-shadow: 0 12px 28px var(--r2p-shadow-hover);
}
.score-number {
    font-size: 2.4rem; font-weight: 700;
    font-family: 'JetBrains Mono', monospace; line-height: 1;
    color: var(--r2p-text);
}
.score-label { font-size: 0.7rem; color: var(--r2p-text-muted); margin-top: 0.3rem; text-transform: uppercase; letter-spacing: 0.5px; }

/* ── Section Headers ──────────────────────────────────────────────────── */
.section-header {
    font-size: 0.75rem; font-weight: 700; color: var(--r2p-text-muted);
    padding: 0.4rem 0; border-bottom: 1px solid var(--r2p-border-subtle);
    margin: 1rem 0 0.75rem 0; text-transform: uppercase;
    letter-spacing: 1px; font-family: 'JetBrains Mono', monospace;
}

/* ── Chips & Tags ─────────────────────────────────────────────────────── */
.fw-chip {
    display: inline-block; padding: 4px 12px; border-radius: 100px;
    font-size: 12px; font-weight: 600;
    background: var(--r2p-chip-bg); color: var(--r2p-chip-color);
    border: 1px solid var(--r2p-chip-border); margin: 2px;
    font-family: 'JetBrains Mono', monospace;
    transition: all 0.2s ease;
}
.fw-chip:hover { transform: translateY(-1px); box-shadow: 0 2px 8px var(--r2p-shadow); }
.dep-tag {
    display: inline-block; padding: 1px 6px; border-radius: 4px;
    font-size: 10px; font-family: 'JetBrains Mono', monospace;
    font-weight: 600; margin-left: 4px;
}
.tag-gpu { background: rgba(var(--r2p-red), 0.1); color: var(--r2p-red); }
.tag-api { background: rgba(var(--r2p-orange), 0.1); color: var(--r2p-orange); }
.tag-heavy { color: var(--r2p-red); }
.tag-local { color: var(--r2p-green); }

/* ── Issues ───────────────────────────────────────────────────────────── */
.issue-critical { background: var(--r2p-issue-critical-bg); border-left:3px solid var(--r2p-red); padding:0.75rem 1rem; border-radius:0 8px 8px 0; margin:0.5rem 0; transition: all 0.2s ease; }
.issue-warning  { background: var(--r2p-issue-warning-bg); border-left:3px solid var(--r2p-orange); padding:0.75rem 1rem; border-radius:0 8px 8px 0; margin:0.5rem 0; transition: all 0.2s ease; }
.issue-info     { background: var(--r2p-issue-info-bg); border-left:3px solid var(--r2p-accent); padding:0.75rem 1rem; border-radius:0 8px 8px 0; margin:0.5rem 0; transition: all 0.2s ease; }
.issue-critical:hover, .issue-warning:hover, .issue-info:hover { transform: translateX(4px); }
.issue-title { font-weight:600; font-size:0.875rem; color: var(--r2p-text); }
.issue-fix   { font-size:0.78rem; color: var(--r2p-text-secondary); margin-top:0.25rem; font-family:'JetBrains Mono',monospace; }

/* ── Adaptations ──────────────────────────────────────────────────────── */
.adapt-replace { background: var(--r2p-adapt-replace-bg); border:1px solid var(--r2p-adapt-replace-border); border-radius:8px; padding:0.6rem 0.85rem; margin:0.35rem 0; font-size:0.8rem; transition: all 0.2s ease; }
.adapt-remove  { background: var(--r2p-adapt-remove-bg); border:1px solid var(--r2p-adapt-remove-border); border-radius:8px; padding:0.6rem 0.85rem; margin:0.35rem 0; font-size:0.8rem; transition: all 0.2s ease; }
.adapt-replace:hover, .adapt-remove:hover { transform: translateX(3px); }

/* ── Checklist ────────────────────────────────────────────────────────── */
.checklist-item { display:flex; align-items:flex-start; gap:0.5rem; padding:0.4rem 0; border-bottom:1px solid var(--r2p-border-subtle); font-size:0.85rem; }

/* ── Tree View ────────────────────────────────────────────────────────── */
.tree-view {
    background: var(--r2p-tree-bg); border: 1px solid var(--r2p-border-subtle); border-radius:8px;
    padding: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    color: var(--r2p-text-secondary); max-height: 350px; overflow-y: auto; white-space: pre;
}

/* ── Risk Badges ──────────────────────────────────────────────────────── */
.risk-low    { background: var(--r2p-badge-cpu-bg); color: var(--r2p-green); border: 1px solid var(--r2p-green); }
.risk-medium { background: var(--r2p-issue-warning-bg); color: var(--r2p-orange); border: 1px solid var(--r2p-orange); }
.risk-high   { background: var(--r2p-issue-critical-bg); color: var(--r2p-red); border: 1px solid var(--r2p-red); }

/* ── Buttons ──────────────────────────────────────────────────────────── */
.stDownloadButton > button {
    background: linear-gradient(135deg, #238636, #2ea043) !important;
    color: white !important; border: 1px solid rgba(255,255,255,0.15) !important;
    padding: 0.6rem 1.5rem !important; border-radius: 10px !important;
    font-weight: 600 !important; width: 100%;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 14px rgba(46,160,67,0.25) !important;
}
.stDownloadButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 24px rgba(46,160,67,0.35) !important;
    filter: brightness(1.08);
}
.stButton > button {
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); border-radius: 10px !important;
    font-weight: 500; box-shadow: 0 2px 8px var(--r2p-shadow);
}
.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 16px var(--r2p-shadow-hover) !important;
}

/* ── Sidebar ──────────────────────────────────────────────────────────── */
[data-testid="stSidebar"] { background: var(--r2p-sidebar-bg) !important; border-right: 1px solid var(--r2p-border) !important; }

/* ── Landing Feature Cards ────────────────────────────────────────────── */
.r2p-feature-card {
    background: var(--r2p-glass); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    border: 1px solid var(--r2p-border); border-radius: 14px;
    padding: 1.2rem 1.5rem; min-width: 150px; text-align: center;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    animation: r2p-fadeUp 0.6s ease-out both;
}
.r2p-feature-card:nth-child(2) { animation-delay: 0.1s; }
.r2p-feature-card:nth-child(3) { animation-delay: 0.2s; }
.r2p-feature-card:nth-child(4) { animation-delay: 0.3s; }
.r2p-feature-card:hover {
    transform: translateY(-6px) scale(1.03);
    border-color: var(--r2p-accent);
    box-shadow: 0 12px 32px var(--r2p-shadow-hover);
}

/* ── Stagger animations for score cards ───────────────────────────────── */
.score-card:nth-child(1) { animation-delay: 0.05s; }
.score-card:nth-child(2) { animation-delay: 0.10s; }
.score-card:nth-child(3) { animation-delay: 0.15s; }
.score-card:nth-child(4) { animation-delay: 0.20s; }
.score-card:nth-child(5) { animation-delay: 0.25s; }
.score-card:nth-child(6) { animation-delay: 0.30s; }

/* ── Progress bar color override ──────────────────────────────────────── */
.stProgress > div > div > div { transition: width 0.4s ease; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Import pipeline
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def load_modules():
    from utils.orchestrator import Repo2ProductPipeline, DEFAULT_CONSTRAINTS
    from utils.llm_client import OllamaStatus
    from analyzer.structure_parser import RepoStructureParser
    return Repo2ProductPipeline, DEFAULT_CONSTRAINTS, OllamaStatus, RepoStructureParser

try:
    Repo2ProductPipeline, DEFAULT_CONSTRAINTS, OllamaStatus, RepoStructureParser = load_modules()
except Exception as e:
    st.error(f"**Import error:** {e}")
    st.code("pip install streamlit requests", language="bash")
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def score_color(s):
    return "#3fb950" if s>=80 else "#d29922" if s>=60 else "#f0883e" if s>=40 else "#f85149"

def risk_cls(r):
    return {"LOW":"risk-low","MEDIUM":"risk-medium","HIGH":"risk-high"}.get(r,"risk-medium")

def fmt_size(mb):
    return f"{mb/1024:.1f} GB" if mb>=1024 else f"{int(mb)} MB"


# ─────────────────────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="r2p-hero">
  <h1>⚡ Repo2Product AI</h1>
  <p>Transform any GitHub repository into a fully runnable, resource-aware product setup</p>
  <div style="margin-top:0.6rem">
    <span class="r2p-badge badge-cpu">CPU-only</span>
    <span class="r2p-badge badge-local">100% Local</span>
    <span class="r2p-badge badge-free">Zero Cost</span>
    <span class="r2p-badge badge-cpu">Python 3</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### ⚙️ System Constraints")
    st.caption("Describe your hardware so we adapt the project for you")
    st.divider()

    ram_gb = st.select_slider("Available RAM", options=[2,4,6,8,12,16,32,64], value=8,
                               format_func=lambda x: f"{x} GB")
    os_choice = st.selectbox("Operating System", ["linux","macos","windows"],
                              format_func=lambda x: {"linux":"🐧 Linux","macos":"🍎 macOS","windows":"🪟 Windows"}[x])
    has_gpu = st.toggle("GPU Available", value=False)
    if has_gpu:
        st.warning("GPU mode — GPU features preserved")
    else:
        st.info("CPU-only — project adapted automatically")

    python_version = st.selectbox("Python Version", ["3.8","3.9","3.10","3.11","3.12"], index=2)

    st.divider()
    st.markdown("### 🤖 AI Explanation Engine")
    # In cloud mode (HF Spaces), hide Ollama option
    import os as _os
    _is_cloud = bool(_os.environ.get("SPACE_ID") or _os.environ.get("R2P_CLOUD"))
    if _is_cloud:
        ai_options = ["None", "Hugging Face (Cloud)"]
        ai_default = 1
    else:
        ai_options = ["None", "Ollama (Local)", "Hugging Face (Cloud)"]
        ai_default = 0
    ai_engine = st.radio("Provider", ai_options, index=ai_default, label_visibility="collapsed")
    
    use_ollama = False
    use_hf = False
    hf_token = ""
    ollama_model = "llama3.2"
    ollama_url = "http://localhost:11434"

    if ai_engine == "Ollama (Local)":
        use_ollama = True
        ollama_url = st.text_input("Ollama URL", value="http://localhost:11434")
        ollama_status_data = OllamaStatus.get_status(ollama_url)
        if ollama_status_data["running"]:
            st.success(f"✅ Connected — {ollama_status_data['model_count']} model(s)")
            if ollama_status_data["models"]:
                ollama_model = st.selectbox("Model", ollama_status_data["models"])
            else:
                st.warning("No models — run: `ollama pull llama3.2`")
        else:
            st.error("❌ Not running — start: `ollama serve`")
            ollama_url = "http://localhost:11434"
    elif ai_engine == "Hugging Face (Cloud)":
        use_hf = True
        st.info("Uses Mistral-7B-Instruct via the free Serverless Inference API")
        hf_token = st.text_input("HF API Token (Optional)", type="password", placeholder="hf_xxxx")

    st.divider()
    st.markdown("### 🔑 GitHub Token")
    st.caption("Optional — raises rate limit to 5000/hr")
    github_token = st.text_input("Token", type="password",
                                  placeholder="ghp_xxxx (optional)",
                                  label_visibility="collapsed")

    st.divider()
    st.markdown("### 💡 Quick Examples")
    examples = {
        "FastAPI": "https://github.com/tiangolo/fastapi",
        "Streamlit": "https://github.com/streamlit/streamlit",
        "LangChain": "https://github.com/langchain-ai/langchain",
        "Flask": "https://github.com/pallets/flask",
        "scikit-learn": "https://github.com/scikit-learn/scikit-learn",
    }
    for label, url in examples.items():
        if st.button(label, use_container_width=True):
            st.session_state["prefill_url"] = url
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Input row — Smart input: URL or Username browse
# ─────────────────────────────────────────────────────────────────────────────

default_url = st.session_state.pop("prefill_url", "")
input_mode = st.radio(
    "Input mode",
    ["🔗 Enter Repo URL / owner/repo", "👤 Browse User Repos"],
    horizontal=True,
    label_visibility="collapsed",
)

repo_url = ""
analyze_btn = False

if input_mode == "🔗 Enter Repo URL / owner/repo":
    col_url, col_btn = st.columns([5, 1])
    with col_url:
        repo_url = st.text_input("GitHub URL", value=default_url,
                                  placeholder="https://github.com/owner/repo  or  owner/repo",
                                  label_visibility="collapsed")
    with col_btn:
        analyze_btn = st.button("⚡ Analyze", type="primary", use_container_width=True)
else:
    col_user, col_fetch = st.columns([4, 1])
    with col_user:
        gh_username = st.text_input("GitHub Username", placeholder="e.g. torvalds",
                                     label_visibility="collapsed")
    with col_fetch:
        fetch_repos_btn = st.button("🔍 Fetch Repos", use_container_width=True)

    if fetch_repos_btn and gh_username:
        with st.spinner("Fetching repositories..."):
            _fetcher = RepoFetcher(github_token=github_token or None)
            user_repos = _fetcher.fetch_user_repos(gh_username.strip())
            if user_repos:
                st.session_state["_browse_repos"] = user_repos
                st.session_state["_browse_user"] = gh_username.strip()
            else:
                st.warning(f"No public repos found for **{gh_username}**. Check the username.")

    if "_browse_repos" in st.session_state:
        user_repos = st.session_state["_browse_repos"]
        browse_user = st.session_state["_browse_user"]
        repo_options = [f"{r['name']}  ⭐{r['stars']}  ({r['language'] or '—'})" for r in user_repos]
        selected_idx = st.selectbox(
            f"Repositories for **{browse_user}** ({len(user_repos)} repos)",
            range(len(repo_options)),
            format_func=lambda i: repo_options[i],
        )
        if selected_idx is not None:
            repo_url = f"https://github.com/{user_repos[selected_idx]['full_name']}"
        analyze_btn = st.button("⚡ Analyze Selected Repo", type="primary", use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# Run pipeline
# ─────────────────────────────────────────────────────────────────────────────

if analyze_btn:
    if not repo_url.strip():
        st.warning("Please enter a GitHub repository URL")
    else:
        user_constraints = {
            "ram_gb": ram_gb, "os": os_choice, "has_gpu": has_gpu,
            "python_version": python_version, "use_ollama": use_ollama,
            "use_hf": use_hf, "hf_token": hf_token,
            "ollama_model": ollama_model, "ollama_url": ollama_url,
        }

        prog_bar = st.progress(0)
        prog_text = st.empty()

        def on_progress(msg, pct):
            prog_bar.progress(pct)
            prog_text.markdown(
                f"<span style='color:#8b949e;font-family:JetBrains Mono,monospace;font-size:0.82rem'>{msg}</span>",
                unsafe_allow_html=True)
            time.sleep(0.03)

        pipeline = Repo2ProductPipeline(
            output_dir="./output",
            github_token=github_token or None,
            progress_callback=on_progress,
        )

        with st.spinner(""):
            result = pipeline.run(repo_url, user_constraints)

        prog_bar.empty()
        prog_text.empty()

        if result.get("errors"):
            for e in result["errors"]:
                st.error(f"❌ **{e.get('stage','Error')}:** {e.get('error','')}")
        else:
            st.session_state["result"] = result
            st.session_state["constraints"] = user_constraints
            st.session_state["chat_history"] = []
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Results
# ─────────────────────────────────────────────────────────────────────────────

if "result" not in st.session_state:
    # Landing state — premium empty state with theme-adaptive cards
    st.markdown("""
    <div style="text-align:center; padding:4rem 1rem;">
        <div style="font-size:4rem; margin-bottom:0.5rem; animation: r2p-float 3s ease-in-out infinite;">🔬</div>
        <div style="font-size:1.4rem; color:var(--r2p-text); font-weight:700; margin-top:1rem; letter-spacing:-0.3px;">
            Paste a GitHub URL to begin
        </div>
        <div style="font-size:0.92rem; color:var(--r2p-text-secondary); margin-top:0.5rem; max-width:520px; margin-left:auto; margin-right:auto; line-height:1.5">
            Repo2Product AI will analyze the repository, detect dependencies, estimate resources,
            and generate a complete runnable setup — optimized for your hardware.
        </div>
        <div style="display:flex; justify-content:center; gap:1.2rem; margin-top:2.5rem; flex-wrap:wrap">
            <div class="r2p-feature-card">
                <div style="font-size:1.6rem">📦</div>
                <div style="color:var(--r2p-accent); font-size:0.8rem; font-weight:600; margin-top:0.4rem">Dependency<br>Analysis</div>
            </div>
            <div class="r2p-feature-card">
                <div style="font-size:1.6rem">⚡</div>
                <div style="color:var(--r2p-green); font-size:0.8rem; font-weight:600; margin-top:0.4rem">CPU<br>Optimization</div>
            </div>
            <div class="r2p-feature-card">
                <div style="font-size:1.6rem">🐳</div>
                <div style="color:var(--r2p-purple); font-size:0.8rem; font-weight:600; margin-top:0.4rem">Docker<br>Compose</div>
            </div>
            <div class="r2p-feature-card">
                <div style="font-size:1.6rem">🚀</div>
                <div style="color:var(--r2p-orange); font-size:0.8rem; font-weight:600; margin-top:0.4rem">One-Click<br>Setup</div>
            </div>
        </div>
        <div style="color:var(--r2p-text-muted); font-size:0.78rem; margin-top:2.5rem;">
            Supports Python · Node.js · Full-Stack · Go · Rust · Java
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

result = st.session_state["result"]
user_constraints = st.session_state.get("constraints", {})
summary = result.get("summary", {})
stages = result.get("stages", {})
fetch = stages.get("fetch", {})
structure = stages.get("structure", {})
meta = fetch.get("metadata", {})
adaptation = stages.get("adaptation", {})
dep_analysis = stages.get("dependencies", {})
dep_summary = dep_analysis.get("summary", {})
resources = stages.get("resources", {})
plan = stages.get("plan", {})
predictions = stages.get("predictions", {})
artifacts = stages.get("artifacts", {})
artifact_files = artifacts.get("files", {})


# ── Elapsed time banner ────────────────────────────────────────────────────
elapsed = result.get("elapsed_seconds", 0)
st.success(f"✅ Analysis complete in **{elapsed}s** — {summary.get('repo_name', '')}")


# ── Score strip ───────────────────────────────────────────────────────────────
score = summary.get("compatibility_score", 0)
c1, c2, c3, c4, c5, c6 = st.columns(6)

with c1:
    sc = score_color(score)
    st.markdown(f'<div class="score-card"><div class="score-number" style="color:{sc}">{score}</div>'
                f'<div class="score-label">Compatibility</div></div>', unsafe_allow_html=True)
with c2:
    risk = summary.get("risk_level","LOW")
    rc = risk_cls(risk)
    st.markdown(f'<div class="score-card"><div style="padding-top:0.4rem">'
                f'<span class="r2p-badge {rc}">{risk} RISK</span></div>'
                f'<div class="score-label">{summary.get("critical_issues",0)} critical</div></div>',
                unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="score-card"><div class="score-number">{summary.get("total_deps",0)}</div>'
                f'<div class="score-label">Dependencies</div></div>', unsafe_allow_html=True)
with c4:
    rec = summary.get("ram_recommended_gb", 0)
    st.markdown(f'<div class="score-card"><div class="score-number" style="font-size:1.4rem">{rec} GB</div>'
                f'<div class="score-label">RAM Needed</div></div>', unsafe_allow_html=True)
with c5:
    dsk = summary.get("disk_gb", 0)
    st.markdown(f'<div class="score-card"><div class="score-number" style="font-size:1.4rem">{dsk} GB</div>'
                f'<div class="score-label">Disk Space</div></div>', unsafe_allow_html=True)
with c6:
    total_changes = summary.get("packages_replaced",0) + summary.get("packages_removed",0)
    st.markdown(f'<div class="score-card"><div class="score-number">{total_changes}</div>'
                f'<div class="score-label">Adaptations</div></div>', unsafe_allow_html=True)

st.markdown("")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_ov, tab_deps, tab_res, tab_adapt, tab_plan, tab_issues, tab_dl, tab_readme_ai, tab_chat = st.tabs([
    "📊 Overview", "📦 Dependencies", "💾 Resources",
    "🔄 Adaptations", "📋 Setup Plan", "⚠️ Issues", "📥 Downloads", "📝 README AI", "💬 Chat AI"
])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1 — OVERVIEW
# ═══════════════════════════════════════════════════════════════════════════
with tab_ov:
    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.markdown(f"## {summary.get('repo_name','')}")
        st.markdown(f"*{meta.get('description','No description')}*")

        fws = summary.get("frameworks", [])
        if fws:
            chips = " ".join(f'<span class="fw-chip">{fw}</span>' for fw in fws)
            st.markdown(chips, unsafe_allow_html=True)
        st.markdown("")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("⭐ Stars", f"{meta.get('stars',0):,}")
        m2.metric("🍴 Forks", f"{meta.get('forks',0):,}")
        m3.metric("📄 Files", f"{structure.get('file_count',0):,}")
        m4.metric("📝 License", meta.get("license","?"))

        st.markdown("")
        flags = [("🧪 Tests", structure.get("has_tests",False)),
                 ("🐳 Docker", structure.get("has_docker",False)),
                 ("🔁 CI/CD", structure.get("has_ci",False)),
                 ("📚 Docs",  structure.get("has_docs",False))]
        fc = st.columns(4)
        for col, (lbl, val) in zip(fc, flags):
            clr = "#3fb950" if val else "#484f58"
            col.markdown(f"<div style='color:{clr};font-size:0.85rem'>{lbl}</div>", unsafe_allow_html=True)

        langs = structure.get("languages", {})
        if langs:
            st.markdown("")
            st.markdown('<div class="section-header">LANGUAGE BREAKDOWN</div>', unsafe_allow_html=True)
            total = sum(langs.values()) or 1
            for lang, cnt in sorted(langs.items(), key=lambda x:-x[1])[:6]:
                pct = cnt/total*100
                st.progress(pct/100, text=f"{lang}: {pct:.0f}% ({cnt} files)")

    with col_r:
        entries = structure.get("entry_points", [])
        if entries:
            st.markdown('<div class="section-header">ENTRY POINTS</div>', unsafe_allow_html=True)
            for ep in entries:
                st.code(ep["path"], language="bash")

        sc2 = score_color(score)
        st.markdown('<div class="section-header">COMPATIBILITY</div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem">
            <div style="font-size:2.2rem;font-weight:700;color:{sc2};font-family:'JetBrains Mono',monospace">{score}/100</div>
            <div style="color:#8b949e;font-size:0.82rem;margin-top:0.2rem">{adaptation.get("compatibility_label","")}</div>
            <div style="margin-top:0.6rem;font-size:0.8rem">
                <span style="color:#3fb950">✓ {adaptation.get("summary",{}).get("packages_replaced",0)} replaced</span> &nbsp;
                <span style="color:#f85149">✗ {adaptation.get("summary",{}).get("packages_removed",0)} removed</span>
            </div>
        </div>""", unsafe_allow_html=True)

        ai_exp = stages.get("ai_explanation", {})
        if ai_exp.get("repo_explanation"):
            st.markdown('<div class="section-header">🤖 AI EXPLANATION</div>', unsafe_allow_html=True)
            st.info(ai_exp["repo_explanation"])
            st.caption(f"Model: {ai_exp.get('model_used','')}")

        st.markdown('<div class="section-header">PROJECT TREE</div>', unsafe_allow_html=True)
        parser = RepoStructureParser(
            local_path=fetch.get("local_path"),
            file_list=fetch.get("file_list", []),
        )
        tree = parser.get_tree_string()
        if tree:
            st.markdown(f'<div class="tree-view">{tree[:3000]}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2 — DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════
with tab_deps:
    python_deps = dep_analysis.get("python", {}).get("all", [])
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Python Packages", dep_summary.get("total_python_deps", 0))
    c2.metric("Heavy Packages", len(dep_summary.get("heavy_deps", [])))
    c3.metric("GPU-Required", len(dep_summary.get("gpu_required", [])))

    col_l, col_r = st.columns(2)
    with col_l:
        st.markdown('<div class="section-header">ALL DEPENDENCIES</div>', unsafe_allow_html=True)
        weight_order = {"heavy":0,"medium":1,"light":2,"unknown":3}
        for dep in sorted(python_deps, key=lambda x: weight_order.get(x.get("weight","unknown"),3)):
            weight = dep.get("weight","unknown")
            wclr = {"heavy":"#f85149","medium":"#d29922","light":"#3fb950"}.get(weight,"#8b949e")
            tags = ""
            if dep.get("gpu_required"):   tags += '<span class="dep-tag tag-gpu">GPU</span>'
            if dep.get("gpu_optional"):   tags += '<span class="dep-tag tag-gpu">GPU-OPT</span>'
            if dep.get("requires_api_key"): tags += '<span class="dep-tag tag-api">API-KEY</span>'
            if dep.get("local_llm"):      tags += '<span class="dep-tag tag-local">LOCAL-LLM</span>'
            if weight == "heavy":         tags += '<span class="dep-tag tag-heavy">HEAVY</span>'
            ram = dep.get("ram_mb",0)
            ram_s = f" ({fmt_size(ram)})" if ram else ""
            ver = dep.get("version","")
            st.markdown(
                f'<div style="padding:4px 0;border-bottom:1px solid #21262d;font-size:0.82rem">'
                f'<span style="color:{wclr};font-family:JetBrains Mono,monospace">◆</span> '
                f'<span style="color:#e6edf3;font-family:JetBrains Mono,monospace">{dep["name"]}</span>'
                f'<span style="color:#484f58">{" "+ver if ver and ver!="any" else ""}{ram_s}</span> {tags}</div>',
                unsafe_allow_html=True)

    with col_r:
        heavy = dep_summary.get("heavy_deps", [])
        if heavy:
            st.markdown('<div class="section-header">⚠️ HEAVY PACKAGES</div>', unsafe_allow_html=True)
            for pkg in heavy:
                d = next((x for x in python_deps if x["name"]==pkg), {})
                st.markdown(f'<div class="issue-warning"><div class="issue-title">🔴 {pkg} ({fmt_size(d.get("ram_mb",0))})</div>'
                            f'<div class="issue-fix">{d.get("note","High resource usage")}</div></div>',
                            unsafe_allow_html=True)

        api_deps = dep_summary.get("api_key_required", [])
        if api_deps:
            st.markdown('<div class="section-header">🔑 API KEY REQUIRED</div>', unsafe_allow_html=True)
            for pkg in api_deps:
                d = next((x for x in python_deps if x["name"]==pkg), {})
                alts = d.get("alternatives", [])
                st.markdown(f'<div class="issue-warning"><div class="issue-title">🔑 {pkg}</div>'
                            f'<div class="issue-fix">Alternatives: {", ".join(alts) or "Ollama (local)"}</div></div>',
                            unsafe_allow_html=True)

        node_deps = dep_analysis.get("node", {})
        if node_deps.get("dependencies"):
            st.markdown('<div class="section-header">NODE.JS DEPENDENCIES</div>', unsafe_allow_html=True)
            for dep in node_deps["dependencies"][:12]:
                st.markdown(f'<div style="font-size:0.78rem;font-family:JetBrains Mono,monospace;color:#8b949e;padding:2px 0">'
                            f'📦 {dep["name"]} <span style="color:#484f58">{dep["version"]}</span></div>',
                            unsafe_allow_html=True)

        docker_info = dep_analysis.get("docker", {})
        if docker_info.get("base_image"):
            st.markdown('<div class="section-header">🐳 DOCKER</div>', unsafe_allow_html=True)
            st.code(f"FROM {docker_info['base_image']}", language="dockerfile")
            if docker_info.get("exposed_ports"):
                st.caption(f"Ports: {', '.join(docker_info['exposed_ports'])}")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3 — RESOURCES
# ═══════════════════════════════════════════════════════════════════════════
with tab_res:
    ram_info  = resources.get("ram", {})
    disk_info = resources.get("disk", {})
    gpu_info  = resources.get("gpu", {})
    cpu_info  = resources.get("cpu", {})
    usr_ram   = user_constraints.get("ram_gb", 8)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### 🧠 RAM")
        rec_gb = ram_info.get("recommended_gb", 0)
        clr = "#3fb950" if rec_gb<=usr_ram*0.6 else "#d29922" if rec_gb<=usr_ram*0.85 else "#f85149"
        st.markdown(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem;margin:0.5rem 0">'
                    f'<div style="font-size:1.8rem;font-weight:700;color:{clr};font-family:JetBrains Mono,monospace">{rec_gb} GB</div>'
                    f'<div style="color:#8b949e;font-size:0.78rem">Recommended RAM</div>'
                    f'<div style="color:#484f58;font-size:0.75rem;margin-top:0.5rem">'
                    f'Min: {ram_info.get("minimum_gb",0)}GB &nbsp;|&nbsp; Peak: {ram_info.get("peak_mb",0)//1024:.1f}GB<br>'
                    f'Your system: <span style="color:#58a6ff">{usr_ram}GB</span></div></div>',
                    unsafe_allow_html=True)
        fill = min(rec_gb/usr_ram, 1.0) if usr_ram else 0
        st.progress(fill, text=f"{fill*100:.0f}% of your {usr_ram}GB RAM")

    with c2:
        st.markdown("#### 💿 Disk")
        disk_gb = disk_info.get("install_gb", 0)
        dclr = "#3fb950" if disk_gb<10 else "#d29922" if disk_gb<20 else "#f85149"
        st.markdown(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem;margin:0.5rem 0">'
                    f'<div style="font-size:1.8rem;font-weight:700;color:{dclr};font-family:JetBrains Mono,monospace">{disk_gb} GB</div>'
                    f'<div style="color:#8b949e;font-size:0.78rem">Install Footprint</div>'
                    f'<div style="color:#484f58;font-size:0.75rem;margin-top:0.5rem">'
                    f'Deps: {fmt_size(disk_info.get("install_mb",0))}<br>'
                    f'Available: <span style="color:#58a6ff">40 GB</span></div></div>',
                    unsafe_allow_html=True)
        st.progress(min(disk_gb/40,1.0), text=f"{disk_gb}GB of 40GB disk")

    with c3:
        st.markdown("#### 🖥️ CPU")
        st.markdown(f'<div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem;margin:0.5rem 0">'
                    f'<div style="font-size:1.8rem;font-weight:700;color:#58a6ff;font-family:JetBrains Mono,monospace">{cpu_info.get("cores_minimum",1)}</div>'
                    f'<div style="color:#8b949e;font-size:0.78rem">Min CPU Cores</div>'
                    f'<div style="color:#484f58;font-size:0.75rem;margin-top:0.5rem">{"GPU-enabled" if user_constraints.get("has_gpu", False) else "CPU-only"} • {user_constraints.get("os", "linux").capitalize()}</div></div>',
                    unsafe_allow_html=True)
        for note in cpu_info.get("notes", []):
            st.caption(f"• {note}")

    st.markdown('<div class="section-header">GPU STATUS</div>', unsafe_allow_html=True)
    if gpu_info.get("required"):
        st.error(f"🚨 GPU Required by: {', '.join(gpu_info.get('required_packages', []))}")
        st.warning("See **Adaptations** tab for CPU fallbacks")
    elif gpu_info.get("optional"):
        st.warning(f"⚡ GPU-accelerated (optional): {', '.join(gpu_info.get('optional_packages', []))} — will run on CPU but slower")
    else:
        st.success("✅ No GPU required — runs natively on CPU")

    warnings = resources.get("warnings", [])
    if warnings:
        st.markdown('<div class="section-header">RESOURCE WARNINGS</div>', unsafe_allow_html=True)
        for w in warnings:
            lvl = w.get("level","info")
            if lvl=="critical": st.error(f"🚨 {w['message']}")
            elif lvl=="warning": st.warning(f"⚠️ {w['message']}")
            else: st.info(f"ℹ️ {w['message']}")

    ai_exp = stages.get("ai_explanation", {})
    if ai_exp.get("cpu_optimizations"):
        st.markdown('<div class="section-header">🤖 AI CPU TIPS</div>', unsafe_allow_html=True)
        st.info(ai_exp["cpu_optimizations"])


# ═══════════════════════════════════════════════════════════════════════════
# TAB 4 — ADAPTATIONS
# ═══════════════════════════════════════════════════════════════════════════
with tab_adapt:
    replacements = adaptation.get("package_replacements", [])
    removed      = adaptation.get("removed_packages", [])
    gpu_patches  = adaptation.get("gpu_patches", [])
    env_changes  = adaptation.get("environment_changes", [])
    dis_features = adaptation.get("disabled_features", [])

    if not replacements and not removed and not gpu_patches:
        st.success("✅ No adaptations needed — this project runs natively on your CPU system!")
    else:
        col_l, col_r = st.columns(2)
        with col_l:
            if replacements:
                st.markdown('<div class="section-header">📦 PACKAGE REPLACEMENTS</div>', unsafe_allow_html=True)
                for rep in replacements:
                    ic = f'<br><span style="color:#58a6ff;font-size:0.72rem">$ pip install {rep.get("install_cmd", rep.get("replacement",""))}</span>' if rep.get("install_cmd") else ""
                    cc = f'<br><span style="color:#8b949e;font-size:0.72rem">Code: {rep.get("code_change","")}</span>' if rep.get("code_change") else ""
                    st.markdown(
                        f'<div class="adapt-replace">'
                        f'<span style="color:#f85149;font-family:JetBrains Mono,monospace">{rep["original"]}</span>'
                        f'<span style="color:#484f58"> → </span>'
                        f'<span style="color:#3fb950;font-family:JetBrains Mono,monospace">{rep["replacement"]}</span>'
                        f'<br><span style="color:#8b949e;font-size:0.72rem">{rep.get("note",rep.get("reason",""))}</span>'
                        f'{ic}{cc}</div>', unsafe_allow_html=True)

            if removed:
                st.markdown('<div class="section-header">❌ REMOVED (GPU-only)</div>', unsafe_allow_html=True)
                for rem in removed:
                    st.markdown(
                        f'<div class="adapt-remove">'
                        f'<span style="color:#f85149;font-family:JetBrains Mono,monospace;text-decoration:line-through">{rem["package"]}</span>'
                        f'<br><span style="color:#8b949e;font-size:0.72rem">Reason: {rem.get("reason","GPU-only")}</span>'
                        f'<br><span style="color:#d29922;font-size:0.72rem">Impact: {rem.get("impact","Feature disabled")}</span>'
                        f'</div>', unsafe_allow_html=True)

        with col_r:
            if gpu_patches:
                st.markdown('<div class="section-header">🔧 GPU → CPU CODE PATCHES</div>', unsafe_allow_html=True)
                st.caption("Auto-apply these regex patches to source files")
                for patch in gpu_patches[:8]:
                    st.markdown(f"**{patch.get('description','')}**")
                    bc, ac = st.columns(2)
                    with bc:
                        st.code(patch.get("pattern",""), language="python")
                    with ac:
                        st.code(patch.get("replacement",""), language="python")

            if dis_features:
                st.markdown('<div class="section-header">🚫 DISABLED FEATURES</div>', unsafe_allow_html=True)
                for feat in dis_features:
                    st.markdown(
                        f'<div class="issue-warning">'
                        f'<div class="issue-title">🚫 {feat["feature"]}</div>'
                        f'<div class="issue-fix">Reason: {feat["reason"]}</div>'
                        f'<div class="issue-fix">Workaround: {feat.get("workaround","Remove usage")}</div>'
                        f'</div>', unsafe_allow_html=True)

            if env_changes:
                st.markdown('<div class="section-header">🌍 ENV CHANGES</div>', unsafe_allow_html=True)
                for ch in env_changes:
                    st.markdown(f"• **{ch.get('type','')}**: {ch.get('action','')}")
                    if ch.get("code_change"):
                        st.code(ch["code_change"], language="python")

    st.markdown('<div class="section-header">📄 ADAPTED REQUIREMENTS.TXT</div>', unsafe_allow_html=True)
    adp_reqs = adaptation.get("adapted_requirements","# No Python dependencies")
    st.code(adp_reqs, language="bash")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 5 — SETUP PLAN
# ═══════════════════════════════════════════════════════════════════════════
with tab_plan:
    run_cmds = plan.get("run_commands", [])
    if run_cmds:
        st.markdown('<div class="section-header">▶️ RUN COMMANDS</div>', unsafe_allow_html=True)
        cols = st.columns(min(len(run_cmds), 3))
        for i, (col, run) in enumerate(zip(cols, run_cmds[:3])):
            with col:
                st.markdown(f"**{run['label']}**")
                st.code(run["command"], language="bash")
                if run.get("note"):
                    st.caption(run["note"])

    st.markdown('<div class="section-header">PREREQUISITES</div>', unsafe_allow_html=True)
    prereqs = plan.get("prerequisites", [])
    for p in prereqs:
        st.markdown(f"• {p}")

    setup_steps = plan.get("setup_steps", [])
    if setup_steps:
        st.markdown('<div class="section-header">STEP-BY-STEP SETUP</div>', unsafe_allow_html=True)
        for i, step in enumerate(setup_steps, 1):
            with st.expander(f"Step {i}: {step['title']}", expanded=(i <= 3)):
                st.markdown(step.get("description",""))
                if step.get("commands"):
                    st.code("\n".join(step["commands"]), language="bash")
                for note in step.get("notes", []):
                    st.warning(f"⚠️ {note}")

    env_setup = plan.get("environment_setup", {})
    if env_setup.get("variables"):
        st.markdown('<div class="section-header">🔐 ENVIRONMENT VARIABLES</div>', unsafe_allow_html=True)
        env_lines = "\n".join(f"{k}={v}" for k,v in env_setup["variables"].items())
        st.code(env_lines, language="bash")
        for note in env_setup.get("notes", []):
            st.caption(f"• {note}")

    tips = plan.get("optimization_tips", [])
    if tips:
        st.markdown('<div class="section-header">⚡ PERFORMANCE TIPS</div>', unsafe_allow_html=True)
        for tip in tips:
            st.markdown(f"• {tip}")

    # Docker Compose preview
    docker_compose = artifact_files.get("docker-compose.yml", "") if artifacts else ""
    if docker_compose:
        st.markdown('<div class="section-header">🐳 DOCKER COMPOSE</div>', unsafe_allow_html=True)
        st.markdown("""
        <div style="background:rgba(22,27,34,0.6); backdrop-filter:blur(10px); border:1px solid rgba(48,54,61,0.6); border-radius:10px; padding:1rem; margin-bottom:0.5rem">
            <div style="color:#d2a8ff; font-weight:600; font-size:0.9rem">🐳 Docker Compose generated</div>
            <div style="color:#8b949e; font-size:0.78rem; margin-top:0.3rem">Run with: <code>docker compose up --build</code></div>
        </div>
        """, unsafe_allow_html=True)
        st.code(docker_compose, language="yaml")

    # Full plan as markdown
    full_plan_text = plan.get("full_plan_text", "")
    if full_plan_text:
        with st.expander("📄 View Full Plan (Markdown)"):
            st.markdown(full_plan_text)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 6 — ISSUES & PREDICTIONS
# ═══════════════════════════════════════════════════════════════════════════
with tab_issues:
    can_proceed = predictions.get("can_proceed", True)
    overall_risk = predictions.get("overall_risk", "LOW")
    pred_summary = predictions.get("summary", {})

    rc = risk_cls(overall_risk)
    col_a, col_b, col_c, col_d = st.columns(4)
    col_a.markdown(f'<div class="score-card"><span class="r2p-badge {rc}">{overall_risk}</span><div class="score-label">Overall Risk</div></div>', unsafe_allow_html=True)
    col_b.metric("🔴 Critical", pred_summary.get("critical", 0))
    col_c.metric("🟡 Warnings", pred_summary.get("warning", 0))
    col_d.metric("🔵 Info", pred_summary.get("info", 0))
    st.markdown("")

    if not can_proceed:
        st.error("🚨 **Critical issues found — fix these before running the project**")
    else:
        st.success("✅ No blocking issues — project should run with the adaptations applied")

    criticals = predictions.get("criticals", [])
    warnings  = predictions.get("warnings", [])
    infos     = predictions.get("infos", [])

    if criticals:
        st.markdown('<div class="section-header">🔴 CRITICAL ISSUES</div>', unsafe_allow_html=True)
        for p in criticals:
            fix_html = f'<div class="issue-fix">Fix: {p["fix"]}</div>' if p.get("fix") else ""
            auto = ' <span style="color:#3fb950;font-size:0.7rem">[auto-fixable]</span>' if p.get("auto_fixable") else ""
            st.markdown(
                f'<div class="issue-critical">'
                f'<div class="issue-title">🔴 [{p["category"]}] {p["message"]}{auto}</div>'
                f'{fix_html}</div>', unsafe_allow_html=True)

    if warnings:
        st.markdown('<div class="section-header">🟡 WARNINGS</div>', unsafe_allow_html=True)
        for p in warnings:
            fix_html = f'<div class="issue-fix">Fix: {p["fix"]}</div>' if p.get("fix") else ""
            st.markdown(
                f'<div class="issue-warning">'
                f'<div class="issue-title">⚠️ [{p["category"]}] {p["message"]}</div>'
                f'{fix_html}</div>', unsafe_allow_html=True)

    if infos:
        st.markdown('<div class="section-header">🔵 INFO</div>', unsafe_allow_html=True)
        for p in infos:
            fix_html = f'<div class="issue-fix">{p["fix"]}</div>' if p.get("fix") else ""
            st.markdown(
                f'<div class="issue-info">'
                f'<div class="issue-title">ℹ️ [{p["category"]}] {p["message"]}</div>'
                f'{fix_html}</div>', unsafe_allow_html=True)

    checklist = predictions.get("pre_run_checklist", [])
    if checklist:
        st.markdown('<div class="section-header">✅ PRE-RUN CHECKLIST</div>', unsafe_allow_html=True)
        for item in checklist:
            req_badge = "🔴" if item.get("required") else "⚪"
            st.markdown(
                f'<div class="checklist-item">'
                f'<span>{req_badge}</span>'
                f'<span style="color:#e6edf3">{item["item"]}</span>'
                f'</div>', unsafe_allow_html=True)

    # Flagged dep issues
    flagged = dep_summary.get("flagged_issues", [])
    if flagged:
        st.markdown('<div class="section-header">📦 DEPENDENCY FLAGS</div>', unsafe_allow_html=True)
        for iss in flagged:
            sev = iss.get("severity","info")
            cls = {"error":"issue-critical","warning":"issue-warning","info":"issue-info"}.get(sev,"issue-info")
            fix_html = f'<div class="issue-fix">Fix: {iss["fix"]}</div>' if iss.get("fix") else ""
            st.markdown(
                f'<div class="{cls}">'
                f'<div class="issue-title">{iss["package"]}: {iss["issue"]}</div>'
                f'{fix_html}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# TAB 7 — DOWNLOADS
# ═══════════════════════════════════════════════════════════════════════════
with tab_dl:
    zip_path = artifacts.get("zip_path", "")
    artifact_files = artifacts.get("files", {})
    output_dir_path = artifacts.get("output_dir", "")

    if zip_path and Path(zip_path).exists():
        with open(zip_path, "rb") as f:
            zip_bytes = f.read()

        st.markdown("### 📦 Complete Setup Package")
        st.markdown("Download everything you need to run this project on your system:")
        col_a, col_b = st.columns([2,3])
        with col_a:
            st.download_button(
                label="⬇️ Download Setup Package (.zip)",
                data=zip_bytes,
                file_name=Path(zip_path).name,
                mime="application/zip",
                use_container_width=True,
            )
        with col_b:
            st.markdown("""
            **Includes:**
            - `setup.sh` / `setup.bat` — one-click setup
            - `run.sh` / `run.bat` — launch scripts
            - `requirements_adapted.txt` — CPU-optimized deps
            - `.env.template` — environment config template
            - `docker-compose.yml` — containerized setup
            - `verify.py` — installation verifier
            - `README_ADAPTED.md` — full setup guide
            """)

    # Docker Compose standalone download
    docker_compose_content = artifact_files.get("docker-compose.yml", "")
    if docker_compose_content:
        st.markdown('<div class="section-header">🐳 DOCKER COMPOSE</div>', unsafe_allow_html=True)
        dc1, dc2 = st.columns([2, 3])
        with dc1:
            st.download_button(
                label="🐳 Download docker-compose.yml",
                data=docker_compose_content,
                file_name="docker-compose.yml",
                mime="text/yaml",
                use_container_width=True,
            )
        with dc2:
            st.markdown("""
            **Docker Quick Start:**
            ```bash
            docker compose up --build
            ```
            No Python/Node install needed — everything runs in containers.
            """)

    st.markdown('<div class="section-header">INDIVIDUAL FILES</div>', unsafe_allow_html=True)

    FILE_ICONS = {
        "setup.sh": "🐧", "setup.bat": "🪟", "run.sh": "▶️", "run.bat": "▶️",
        ".env.template": "🔐", "requirements_adapted.txt": "📦",
        "README_ADAPTED.md": "📖", "verify.py": "✅",
        "docker-compose.yml": "🐳", "Dockerfile": "🐳",
    }
    FILE_LANGS = {
        "setup.sh": "bash", "setup.bat": "batch", "run.sh": "bash", "run.bat": "batch",
        ".env.template": "bash", "requirements_adapted.txt": "text",
        "README_ADAPTED.md": "markdown", "verify.py": "python",
        "docker-compose.yml": "yaml", "Dockerfile": "dockerfile",
    }

    for fname, content in artifact_files.items():
        if fname.startswith("_"):
            continue
        icon = FILE_ICONS.get(fname, "📄")
        lang = FILE_LANGS.get(fname, "text")
        with st.expander(f"{icon} {fname}"):
            st.code(content[:4000] + ("\n\n... (truncated)" if len(content)>4000 else ""), language=lang)
            st.download_button(
                f"Download {fname}",
                data=content,
                file_name=fname,
                mime="text/plain",
                key=f"dl_{fname}",
            )

    st.divider()
    st.markdown("### 🚀 Quick Start (copy-paste)")
    repo_name = summary.get("repo_name","").split("/")[-1] or "project"
    run_cmd_first = plan.get("run_commands", [{}])[0].get("command", f"python main.py") if plan.get("run_commands") else "python main.py"
    st.code(f"""# 1. Download and extract the zip, then:
bash setup.sh

# OR manually:
git clone --depth=1 {fetch.get("url","")}
cd {repo_name}
python3 -m venv venv && source venv/bin/activate
pip install -r requirements_adapted.txt
cp .env.template .env  # Edit with your values
{run_cmd_first}""", language="bash")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 8 — README AI OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════
with tab_readme_ai:
    st.markdown('<div class="section-header">📝 AI README OPTIMIZER</div>', unsafe_allow_html=True)
    st.markdown("Improve any repository's README with AI — powered by your selected AI engine.")

    _is_cloud = bool(os.environ.get("SPACE_ID") or os.environ.get("R2P_CLOUD"))
    _ai_use_hf = user_constraints.get("use_hf", False) or _is_cloud
    _ai_use_ollama = user_constraints.get("use_ollama", False)
    _ai_hf_token = user_constraints.get("hf_token", "")
    _ai_ollama_model = user_constraints.get("ollama_model", "llama3.2")
    _ai_ollama_url = user_constraints.get("ollama_url", "http://localhost:11434")

    # Get README from key_files
    readme_content = ""
    key_files = fetch.get("key_files", {})
    for fname in ["README.md", "README.rst", "README.txt", "readme.md"]:
        if fname in key_files:
            readme_content = key_files[fname]
            break

    if readme_content:
        with st.expander("📄 Current README (click to expand)", expanded=False):
            st.markdown(readme_content[:5000])

        if st.button("⚡ Optimize README with AI", type="primary", use_container_width=True):
            st.markdown("---")
            st.markdown("### ✨ Improved README")
            improved_container = st.empty()
            full_text = ""
            for chunk in improve_readme_stream(
                readme_content,
                use_hf=_ai_use_hf,
                hf_token=_ai_hf_token,
                use_ollama=_ai_use_ollama,
                ollama_model=_ai_ollama_model,
                ollama_url=_ai_ollama_url,
            ):
                full_text += chunk
                improved_container.markdown(full_text + "▌")
            improved_container.markdown(full_text)

            if full_text and not full_text.startswith("Error") and not full_text.startswith("⚠️"):
                st.session_state["_optimized_readme"] = full_text

        if "_optimized_readme" in st.session_state:
            st.download_button(
                "📥 Download Improved README",
                st.session_state["_optimized_readme"],
                file_name="README_IMPROVED.md",
                mime="text/markdown",
                use_container_width=True,
            )
    else:
        st.info("No README found in this repository. The README optimizer works on repos that have an existing README file.")


# ═══════════════════════════════════════════════════════════════════════════
# TAB 9 — CHAT AI
# ═══════════════════════════════════════════════════════════════════════════
with tab_chat:
    st.markdown('<div class="section-header">💬 CHAT AI</div>', unsafe_allow_html=True)
    st.markdown(f"Ask an AI assistant about the **{summary.get('repo_name', 'project')}** repository's architecture and setup.")

    _is_cloud = bool(os.environ.get("SPACE_ID") or os.environ.get("R2P_CLOUD"))
    _ai_use_hf = user_constraints.get("use_hf", False) or _is_cloud
    _ai_use_ollama = user_constraints.get("use_ollama", False)
    _ai_hf_token = user_constraints.get("hf_token", "")
    _ai_ollama_model = user_constraints.get("ollama_model", "llama3.2")
    _ai_ollama_url = user_constraints.get("ollama_url", "http://localhost:11434")

    context_data = f"""
    Repo Name: {summary.get('repo_name')}
    Description: {summary.get('description')}
    Frameworks: {', '.join(summary.get('frameworks', [])) or 'None detected'}
    Heavy Dependencies: {', '.join(summary.get('heavy_deps', []))}
    GPU Required: {summary.get('gpu_required_flag')}
    Compatibility Score: {summary.get('compatibility_score')}/100 ({summary.get('compatibility_label')})
    Risk Level: {summary.get('risk_level')}
    Setup Run Command: {plan.get('run_commands', [{{}}])[0].get('command', 'python main.py') if plan.get('run_commands') else 'None'}
    """

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
        
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Ask about this repository architecture or setup..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            full_answer = ""
            for chunk in chat_stream(
                user_query=prompt,
                context=context_data,
                use_hf=_ai_use_hf,
                hf_token=_ai_hf_token,
                use_ollama=_ai_use_ollama,
                ollama_model=_ai_ollama_model,
                ollama_url=_ai_ollama_url,
            ):
                full_answer += chunk
                response_placeholder.markdown(full_answer + "▌")
            response_placeholder.markdown(full_answer)
            
        st.session_state.chat_history.append({"role": "assistant", "content": full_answer})
