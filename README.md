# harahara 🐟

**Your Mac, from anywhere.**

A text-based remote desktop.\
A glorified SSH you actually enjoy using.\
A tunnel to your machine that fits in your pocket.\
Your remote control.\
Your file server.\
Your note taker.\
Your reminder.\
Your status checker.\
Your clipboard, your cron, your macro runner.\
All through Telegram. Zero AI tokens burned.

> **What is harahara?** The [Hara hara](https://en.wikipedia.org/wiki/Hara_hara) is a small catfish (up to 13 cm)
> native to the rivers of Nepal, Bangladesh, India, and Myanmar. Known locally as
> *Kutakanti* (कुटा कानटी) and nicknamed the "moth catfish" for its broad pectoral
> fins, it's a quiet, bottom-dwelling fish that minds its own business — much like
> this bot, which sits quietly on your Mac until you need it. 🐟

## Security

harahara's security is **as strong as Telegram's** — because Telegram is the only way to access the bot.

- **Single-user lockdown**: Only one authorized Telegram user ID can interact with the bot. All other messages are silently rejected and logged.
- **No open ports**: The bot does not expose any HTTP server, API, or network listener. It connects outbound to Telegram's servers via long-polling — nothing to port-scan, nothing to brute-force.
- **No stored credentials exposed**: Tokens live in `.env` (gitignored), never committed to source.
- **Dangerous command confirmation**: Commands like `/restart`, `/shutdown`, and `/trash` require explicit `yes` confirmation before execution.
- **Unauthorized access logging**: Every rejected message is logged to `logs/latest_unauthorized_id.txt`.

In short: if someone can't compromise your Telegram account, they can't touch your Mac.

## Why?

Projects like [ClawdBot](https://github.com/openclaw/clawdbot) and MoltBot are impressive, but they burn a lot of AI tokens on every interaction. I didn't need full conversational AI capabilities — just a fast, scriptable remote control that I could operate from Telegram chat, plus extras like screenshots, keyboard control, timers, and clipboard history.

So I built harahara. **It burns zero AI tokens** unless you explicitly invoke AI. Everything is command-driven — you type `/screenshot`, not "hey can you take a screenshot please".

If you want natural language, you can:

- **Enable NLP mode** during setup — plain text routes through a 3-stage AI pipeline
- **Use local AI** — Ollama integration auto-detects and uses your local LLM (free, private, offline)
- **Use cloud AI** — Gemini CLI for cloud intelligence
- **Use any AI CLI** by adding it as a YAML command

But if your message starts with `/`, it goes straight to the command handler. No AI. No tokens. No cost.

## Who Is It For?

- **Developers** who leave a Mac running at home or the office and need to run commands, grab files, or check logs remotely
- **Self-hosters** running Pi-hole, Plex, or Docker who want a single mobile dashboard to manage everything
- **Remote workers** who travel and need quick access to their home Mac without VPN or TeamViewer
- **macOS power users** who automate with shell scripts, launchd, and cron — and want to trigger and monitor from their phone
- **Anyone who wants a personal assistant bot** — reminders, notes, clipboard history, focus timers, daily briefings — all in Telegram, no AI cost

## Features

- 📸 **Screenshots & Webcam** — capture and send, with multi-shot intervals
- ⌨️ **Keyboard & App Control** — send keystrokes, open/quit apps, type text
- 🖥 **System Info** — uptime, CPU, memory, disk, battery, processes
- 🔊 **Volume & Audio** — get/set volume, mute/unmute, text-to-speech
- ⏰ **Reminders & Timers** — timed reminders, visual countdown timer, Pomodoro mode
- 🔒 **Security** — single authorized user, inline confirmation buttons for dangerous commands
- 🔴 **Live Output Streaming** — real-time command output via message edits
- 📸 **Screenshot Diff** — visual change detection between screenshots
- 🗺 **Network Context** — public IP, WiFi, geolocation in one command
- 📋 **Clipboard History** — background monitor with search and retrieval
- 💓 **Smart Heartbeat** — edit-on-consecutive pulses, configurable interval
- ⏱ **Inline Timeouts** — override command timeouts on the fly (`-t 30m`)
- 🤖 **Local AI (Ollama)** — free, private, offline AI — auto-detected, zero config
- 🧠 **Optional NLP Mode** — 3-stage AI pipeline with fuzzy matching, tool routing, and multi-step plans
- ↕️ **Smart Output** — truncates long output, sends full as document
- ⭐ **Favorites Bar** — persistent keyboard with your most-used commands (`/fav`)
- 🪄 **Interactive UI** — conversational prompts, paginated logs, typo recovery, and undo actions
- 📎 **macOS Shortcuts** — list and run Shortcuts.app shortcuts from Telegram
- ⏰ **Schedule Manager** — add/remove/list scheduled tasks without editing YAML

## Quick Start

```bash
git clone https://github.com/sarj19/harahara.git
cd harahara
./setup.sh
```

The interactive setup script will:

1. Install Python dependencies (`pyTelegramBotAPI`, `pyyaml`)
2. Walk you through creating a Telegram bot via @BotFather
3. Prompt for your bot token & user ID → saves to `.env`
4. Set up personal commands file with a sample `/cal` command
5. Detect optional tools (imagesnap for webcam, Gemini CLI, Ollama)
6. Optionally install a launchd auto-start service

Then send `/setup` in Telegram to grant macOS permissions one at a time.

### Manual Setup

```bash
pip3 install pyTelegramBotAPI pyyaml
cp .env.example .env                          # Edit with your credentials
cp personal/bot_commands.yaml.example personal/bot_commands.yaml
python3 telegram_listener.py
```

## Configuration

All settings come from environment variables or a `.env` file:

| Variable | Required | Description |
| -------- | -------- | ----------- |
| `TELEGRAM_BOT_TOKEN` | ✅ | Bot token from @BotFather |
| `TELEGRAM_AUTHORIZED_USER_ID` | ✅ | Your numeric Telegram user ID |
| `BOT_HEARTBEAT_INTERVAL` | | Heartbeat interval in minutes, 0 to disable (default: `15`) |
| `BOT_AI_BACKEND` | | AI backend: `auto`, `gemini`, or `ollama` (default: `auto`) |
| `BOT_OLLAMA_MODEL` | | Ollama model name (default: `llama3.2:1b`) |
| `BOT_NLP_ENABLED` | | Enable NLP mode for plain text (default: `false`) |
| `BOT_NLP_CONTEXT_SIZE` | | Conversation memory size (default: `20` messages) |
| `BOT_GREETING` | | Custom startup greeting (default: time-based) |
| `BOT_STATUS_TAGLINE` | | Tagline shown in `/status` |
| `BOT_VOICE` | | macOS voice for `/say` (run `/voices` to list) |
| `BOT_DIGEST_TIME` | | Daily digest time in 24h format, empty = disabled |
| `BOT_KEYBOARD_COMMANDS` | | Comma-separated commands for `/keyboard` |
| `BOT_DOWNLOADS_DIR` | | Where incoming files are saved (default: `~/Downloads/harahara`) |
| `BOT_NOTES_BACKEND` | | Notes backend: `local`, `apple`, or `google` (default: `local`) |

See [`.env.example`](.env.example) for the full list with all optional path overrides.

## Commands

### Special Commands (Python handlers)

| Command | Description |
| ------- | ----------- |
| `/help` | Grouped command list |
| `/status` | Bot status: uptime, heartbeat config, tagline |
| `/settings` | Interactive wizard to configure bot settings (`.env`) |
| `/screenshot [count]` (`/ss`) | Screenshot(s), 1 min apart. `/screenshot stop` to cancel |
| `/webcam [count]` | Webcam photo(s), 1 min apart |
| `/key <keys>` (`/k`) | Keystrokes: `/key cmd l`, `/key enter`, `/key alt shift 3` |
| `/type <text>` | Type text via AppleScript |
| `/url <url>` | Open URL in browser |
| `/say <text>` | Speak text aloud (uses `BOT_VOICE` if set) |
| `/voices` (`/v`) | List available macOS voices |
| `/keyboard` (`/kb`) | Show quick reply keyboard with frequent commands |
| `/logs [n]` | Show last N bot log lines |
| `/kill <name>` | Kill process by name |
| `/open <app>` / `/quit <app>` | Open or quit an app |
| `/remind <dur> <msg>` (`/r`) | Reminder: `/remind 5m call back` |
| `/restartbot` | Restart the bot process |
| `/download <path>` (`/dl`) | Send a file from Mac to Telegram |
| `/upload [path]` (`/ul`) | Save next incoming file to path |
| `/notifications [n]` (`/notifs`) | Show recent macOS notifications |
| `/note <sub> <text>` (`/n`) | Notes: save, list, search, delete |
| `/record <dur>` (`/rec`) | Record screen video (max 5 min) |
| `/audio <dur>` (`/mic`) | Record audio from mic (max 5 min) |
| `/macro <name>` | Run a multi-step macro |
| `/macros` | List available macros |
| `/brain` | NLP brain status, `/brain clear` to reset memory |
| `/calendar` (`/cal`, `/today`) | Calendar: today, tomorrow, week, add events |
| `/mail` (`/email`, `/gmail`) | Email: inbox, search, read, send |
| `/googlesetup` | Set up Google Calendar & Gmail API |
| `/last [n]` (`/l`, `/history`) | Show last N commands with timestamps and exit codes |
| `/diff` (`/compare`, `/changed`) | Screenshot comparison with visual change detection |
| `/timer <dur> [label]` (`/countdown`) | Visual countdown timer with progress bar |
| `/pomodoro` (`/pomo`) | 25m work → 5m break Pomodoro cycle |
| `/where` (`/network`, `/ip`, `/wifi`) | Network context: public IP, WiFi, geo, signal |
| `/snippet` (`/clip`, `/clipboard`) | Clipboard history: list, retrieve, search, clear |
| `/build` (`/new`, `/create`) | Interactive wizard to create commands, schedules, or macros |
| `/start` (`/tour`, `/welcome`) | Interactive onboarding tour with tappable examples |
| `/menu` (`/categories`) | Quick-access category keyboards |
| `/focus` (`/dnd`, `/deepwork`) | Focus mode: countdown timer + Do Not Disturb |
| `/pin` (`/bookmark`) | Pin a message by replying or inline: `/pin remember this` |
| `/pins` (`/saved`) | List or clear pinned messages |
| `/streak` (`/stats`) | Usage streak, best streak, total active days |
| `/shortcut` (`/shortcuts`) | List or run macOS Shortcuts: `/shortcut <name>` |
| `/schedule` (`/sched`) | Manage schedules: `/schedule add <name> <interval> <cmd>` |
| `/ai <question>` (`/ask`, `/llm`) | Direct AI query (uses auto-detected backend) |
| `/ollamasetup` | Set up local AI with Ollama |
| `/setup` | macOS permissions walkthrough & tips |

### YAML Commands

**Shared** (`bot_commands.yaml`) — checked into git, ships with common macOS commands.

**Personal** (`personal/bot_commands.yaml`) — gitignored, for your private scripts and overrides. Auto-reloads on change (**no restart needed**).

```yaml
weather:
  cmd: "curl -s 'wttr.in/?format=3'"
  desc: "Show weather"
  aliases: [w, wttr]
```

## AI Integration

harahara supports **local AI (Ollama)** and **cloud AI (Gemini)** with automatic backend detection. Install one and it just works — zero config.

```bash
# Option A: Local AI (free, private, offline)
brew install ollama && ollama serve && ollama pull llama3.2:1b

# Option B: Cloud AI
npm install -g @google/generative-ai-cli
```

Enable NLP mode with `BOT_NLP_ENABLED=true` in `.env`, or use `/ai <question>` for direct queries anytime.

→ See [botpkg/AI.md](botpkg/AI.md) for full architecture, model recommendations, fallback chains, and configuration.

## Personalization

### Scheduled Commands

Manage via `/schedule` or edit `personal/schedules.yaml`:

```text
/schedule                                    → list all schedules
/schedule add battery 2h pmset -g batt       → add a schedule
/schedule remove battery                     → remove a schedule
```

### macOS Shortcuts

```text
/shortcut                    → list available shortcuts
/shortcut My Shortcut Name   → run a shortcut
```

### Multi-Step Macros

```yaml
# personal/macros.yaml
morning:
  desc: "Morning check"
  steps:
    - cmd: "pmset -g batt | grep -Eo '\\d+%'"
      desc: "Battery"
    - cmd: "/screenshot"
      desc: "Screen"
```

Run with `/macro morning`. List with `/macros`.

### Build Wizard

Create commands, schedules, and macros interactively from Telegram:

```text
/build                              → interactive wizard
/build mycommand curl wttr.in       → quick one-liner creation
```

### Interactive UI & Error Recovery

- **Typo Recovery:** Suggests closest command match with tappable `[ ▶ Run ]` button.
- **Conversational Parsing:** Commands ask for missing arguments instead of showing errors.
- **Paginated Output:** Long text split into interactive pages with navigation.
- **Undo Actions:** Inline `[ ↩️ Relaunch ]` and `[ ↩️ Undo ]` lifelines.
- **Interactive Settings:** `/settings` wizard to configure without editing files.

### Calendar & Email

```text
/calendar              → Today's events
/calendar add Meeting tomorrow 3pm with John
/mail                  → Last 5 inbox messages
/mail search from:rabi → Search Gmail
```

Setup: Run `/googlesetup` for full Google API access, or add your Google account in macOS System Settings.

### File Transfer

- **`/download ~/path/to/file`** — send any file from Mac to Telegram
- **`/upload [dir]`** — set where the next incoming file is saved
- **Send a file directly** — saved to `~/Downloads/harahara/`

### Other Customizations

- **Custom voice**: `BOT_VOICE=Samantha` in `.env`
- **Daily digest**: `BOT_DIGEST_TIME=21:00` for nightly activity summary
- **Quick keyboard**: `/keyboard` for tap-friendly command bar
- **Custom greetings**: `BOT_GREETING` and `BOT_STATUS_TAGLINE` in `.env`
- **Aliases**: Built-in (`/ss` → `/screenshot`) and custom via YAML `aliases:`

## macOS Permissions

Run `/setup` in Telegram to grant permissions one at a time — it opens the exact settings pane for each.

| Permission | Required For | Grant To |
| ---------- | ------------ | -------- |
| Screen Recording | `/screenshot`, `/record` | Terminal.app / your terminal |
| Accessibility | `/key`, `/type` | Terminal.app / your terminal |
| Camera | `/webcam` | imagesnap |
| Microphone | `/audio` | sox or ffmpeg |
| Full Disk Access | `/notifications` | Terminal.app (for notification DB) |

## Auto-Start (launchd)

```bash
cp com.harahara.bot.plist.example ~/Library/LaunchAgents/com.harahara.bot.plist
# Edit paths in the plist, then:
launchctl load ~/Library/LaunchAgents/com.harahara.bot.plist
```

## Testing

258 tests covering all handlers, NLP brain, Ollama integration, build wizard, usability, and personalization.

→ See [tests/README.md](tests/README.md) for running tests, per-file coverage, and writing new tests.

## Logs

| File | Content |
|---|---|
| `logs/harahara_bot.log` | Main bot log — commands, NLP, heartbeats |
| `logs/harahara_bot_err.log` | Stderr from launchd |
| `logs/latest_unauthorized_id.txt` | Unauthorized access attempts |

View remotely with `/logs [n]` from Telegram.

## License

MIT
