"""
utils/package_imports.py — Repo2Product AI
Single source of truth for mapping PyPI distribution names to their import names.

Used by the generated `verify.py`, the planner's verification commands, and anywhere
else that needs to turn a requirements-file entry into something importable. Keeping
one map avoids the naive `name.replace("-", "_")` heuristic reporting false failures
for packages whose import name differs from their distribution name.
"""

from typing import Dict

# Distribution name (lowercased) → import name
PACKAGE_IMPORT_MAP: Dict[str, str] = {
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "opencv-contrib-python": "cv2",
    "pillow": "PIL",
    "pillow-simd": "PIL",
    "beautifulsoup4": "bs4",
    "scikit-learn": "sklearn",
    "scikit-image": "skimage",
    "pyyaml": "yaml",
    "python-dotenv": "dotenv",
    "python-dateutil": "dateutil",
    "python-multipart": "multipart",
    "msgpack-python": "msgpack",
    "attrs": "attr",
    "faiss-cpu": "faiss",
    "faiss-gpu": "faiss",
    "psycopg2-binary": "psycopg2",
    "mysqlclient": "MySQLdb",
    "pymysql": "pymysql",
    "google-generativeai": "google.generativeai",
    "google-cloud-storage": "google.cloud.storage",
    "protobuf": "google.protobuf",
    "grpcio": "grpc",
    "sentence-transformers": "sentence_transformers",
    "huggingface-hub": "huggingface_hub",
    "huggingface_hub": "huggingface_hub",
    "llama-index": "llama_index",
    "langchain-community": "langchain_community",
    "langchain-core": "langchain_core",
    "langchain-openai": "langchain_openai",
    "pytorch-lightning": "pytorch_lightning",
    "torch-audio": "torchaudio",
    "tensorflow-cpu": "tensorflow",
    "tensorflow-gpu": "tensorflow",
    "tf-nightly": "tensorflow",
    "typing-extensions": "typing_extensions",
    "pytest-cov": "pytest_cov",
    "python-jose": "jose",
    "pycryptodome": "Crypto",
    "pymupdf": "fitz",
    "pdfminer.six": "pdfminer",
    "docx": "docx",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "ruamel.yaml": "ruamel.yaml",
    "azure-storage-blob": "azure.storage.blob",
    "nvidia-ml-py": "pynvml",
    "nvidia-ml-py3": "pynvml",
    "discord.py": "discord",
    "python-telegram-bot": "telegram",
    "pytz": "pytz",
    "setuptools": "setuptools",
    "wheel": "wheel",
}


def to_import_name(package_name: str) -> str:
    """
    Best-effort mapping from a distribution name to an import name.

    Looks the package up in PACKAGE_IMPORT_MAP first; falls back to the usual
    `-`/`.` normalisation for the (majority) case where they coincide.
    """
    if not package_name:
        return ""

    # Strip any extras or environment markers that survived parsing: pkg[extra]
    clean = package_name.strip().split("[")[0].strip()
    key = clean.lower()

    if key in PACKAGE_IMPORT_MAP:
        return PACKAGE_IMPORT_MAP[key]

    # Default: hyphens are not legal in identifiers; keep only the first
    # dotted segment so namespace packages still import cleanly.
    return clean.replace("-", "_").split(".")[0]
