"""Ollama integration — local AI via the ollama CLI.

This module is self-contained and uses only subprocess (no pip dependencies).
It is only imported when BOT_AI_BACKEND=ollama, ensuring zero overhead otherwise.

Usage:
    from botpkg.ollama import is_available, generate
    if is_available():
        response = generate("What is 2+2?")
"""
import os
import subprocess

from botpkg import logger

# ─── Recommended small models ───
RECOMMENDED_MODELS = [
    {"name": "qwen2.5:0.5b", "size": "~400 MB", "desc": "Ultra-light, basic tasks"},
    {"name": "llama3.2:1b", "size": "~650 MB", "desc": "Recommended — good balance"},
    {"name": "gemma3:1b", "size": "~815 MB", "desc": "Google's compact model"},
    {"name": "deepseek-r1:1.5b", "size": "~1 GB", "desc": "Reasoning-focused"},
    {"name": "llama3.2:3b", "size": "~2 GB", "desc": "Better quality, more RAM"},
]


def _find_ollama():
    """Find the ollama CLI binary."""
    for path in ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama"]:
        if os.path.exists(path):
            return path
    try:
        result = subprocess.run(["which", "ollama"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip() or None
    except Exception:
        return None


def is_available():
    """Check if the ollama CLI is installed."""
    return _find_ollama() is not None


def is_running():
    """Check if the ollama server is responding."""
    ollama = _find_ollama()
    if not ollama:
        return False
    try:
        result = subprocess.run(
            [ollama, "list"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def list_models():
    """Get list of installed model names."""
    ollama = _find_ollama()
    if not ollama:
        return []
    try:
        result = subprocess.run(
            [ollama, "list"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().split("\n")
        models = []
        for line in lines[1:]:  # Skip header
            parts = line.split()
            if parts:
                models.append(parts[0])
        return models
    except Exception:
        return []


def pull_model(name):
    """Pull a model. Returns (success, output)."""
    ollama = _find_ollama()
    if not ollama:
        return False, "Ollama not found."
    try:
        result = subprocess.run(
            [ollama, "pull", name],
            capture_output=True, text=True, timeout=600,  # Models can take a while
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Pull timed out (10 min limit)."
    except Exception as e:
        return False, str(e)


def generate(prompt, model=None, timeout=120):
    """Generate a response from a local model.

    Args:
        prompt: The full prompt (system + user)
        model: Model name override (defaults to BOT_OLLAMA_MODEL setting)
        timeout: Max seconds to wait

    Returns:
        Response text or None on failure.
    """
    ollama = _find_ollama()
    if not ollama:
        return None

    if model is None:
        try:
            from settings import BOT_OLLAMA_MODEL
            model = BOT_OLLAMA_MODEL
        except (ImportError, AttributeError):
            model = "llama3.2:1b"

    try:
        result = subprocess.run(
            [ollama, "run", model, "--nowordwrap", prompt],
            capture_output=True, text=True, timeout=timeout,
        )
        response = result.stdout.strip()
        if result.returncode != 0 and not response:
            stderr = result.stderr.strip()
            logger.error(f"Ollama error (exit {result.returncode}): {stderr}")
            return None
        return response
    except subprocess.TimeoutExpired:
        logger.error(f"Ollama timed out ({timeout}s)")
        return None
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return None
