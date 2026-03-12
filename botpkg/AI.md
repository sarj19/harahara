# AI & NLP Module

harahara's AI subsystem is fully optional — zero overhead when disabled, auto-detected when installed.

## Architecture

```text
User message (no / prefix)
        │
        ▼
  ┌─────────────┐
  │  NLP Brain   │  brain.py
  │  (3 stages)  │
  └──────┬──────┘
         │
  Stage 1: Fuzzy Match
  Match text against command names + descriptions.
  High confidence → suggest instantly (no AI call).
         │
  Stage 2: AI Backend
  _call_ai() dispatcher with auto-detection:
         │
         ├── Ollama available? → _call_ollama()  (local, free)
         ├── Gemini available? → _call_gemini()   (cloud)
         └── Neither?         → error message
         │
  Stage 3: Multi-Step Plans
  Multiple /commands → show plan with [▶ Run All]
```

## Files

| File | Purpose |
|---|---|
| `brain.py` | NLP pipeline: fuzzy matching, AI dispatch, response parsing, conversation memory, multi-step plans |
| `ollama.py` | Self-contained Ollama integration (subprocess only, zero pip deps) |

Gemini CLI is called via subprocess in `brain.py` — no dedicated module needed.

## AI Backends

### Auto-Detection

Default behavior (`BOT_AI_BACKEND=auto`): on first NLP call, the bot probes for available backends and caches the result.

**Priority:** Ollama (if installed + running) → Gemini CLI (if found in PATH) → error

Override by setting `BOT_AI_BACKEND=ollama` or `BOT_AI_BACKEND=gemini` in `.env`.

### Ollama (Local, Free)

```bash
brew install ollama
ollama serve                    # Start the server
ollama pull llama3.2:1b         # Pull a model (~650 MB)
```

Or use `/ollamasetup` from Telegram for an interactive wizard with model picker.

**Recommended small models:**

| Model | Size | Best For |
|---|---|---|
| `qwen2.5:0.5b` | ~400 MB | Ultra-light, basic tasks |
| `llama3.2:1b` | ~650 MB | **Recommended** — good balance |
| `gemma3:1b` | ~815 MB | Google's compact model |
| `deepseek-r1:1.5b` | ~1 GB | Reasoning-focused |
| `llama3.2:3b` | ~2 GB | Better quality, more RAM |

**Module API** (`botpkg/ollama.py`):

```python
from botpkg.ollama import is_available, is_running, list_models, pull_model, generate

if is_available() and is_running():
    response = generate("What is 2+2?", model="llama3.2:1b")
```

All functions use `subprocess.run` — no pip dependencies required.

### Gemini CLI (Cloud)

```bash
npm install -g @google/generative-ai-cli
```

Called via subprocess with `--yolo --output-format text` flags. The system prompt includes all available commands and conversation history.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BOT_NLP_ENABLED` | `false` | Enable NLP mode (plain text → AI pipeline) |
| `BOT_AI_BACKEND` | `auto` | Backend: `auto`, `gemini`, or `ollama` |
| `BOT_OLLAMA_MODEL` | `llama3.2:1b` | Ollama model to use |
| `BOT_NLP_CONTEXT_SIZE` | `20` | Conversation memory size (messages) |
| `BOT_PERSIST_CONVERSATIONS` | `false` | Persist NLP history across restarts |

## Commands

| Command | Description |
|---|---|
| `/ai <question>` | Direct AI query (aliases: `/ask`, `/llm`, `/ollama`) |
| `/ollamasetup` | Interactive setup wizard for Ollama |
| `/brain` | NLP memory status |
| `/brain clear` | Reset conversation history |

## Conversation Memory

Each chat maintains a sliding window of recent messages (default: 20). This context is included in AI prompts so the model can reference earlier conversation.

Memory persists across bot restarts when `BOT_PERSIST_CONVERSATIONS=true` (stored in `personal/conversations.json`).

## Fallback Chain

```
BOT_AI_BACKEND=ollama:
  Ollama → (fails) → Gemini → (fails) → error

BOT_AI_BACKEND=gemini:
  Gemini → (fails) → error

BOT_AI_BACKEND=auto:
  detect() → use winner → (fails) → error
```

## Testing

All AI tests are in `tests/test_ollama.py` and `tests/test_brain.py`.

Tests mock subprocess — no actual AI backend needed:

```bash
python3 -m unittest tests.test_ollama tests.test_brain -v
```
