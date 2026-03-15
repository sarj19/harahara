#!/bin/bash
# ──────────────────────────────────────────────────────────
# setup.sh — Interactive setup for macOS Telegram Bot
# ──────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m' # No Color

header() { echo -e "\n${BLUE}${BOLD}═══ $1 ═══${NC}\n"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

echo -e "${BOLD}"
cat << 'FISH'

                                       .&(*
                                    ,/(%@%@%.
                                  .,#%#&/&&(&*
                                *.&/&#%*%*&%&#(
                        **@#&(,&&&%#(//%,%%(#&%*
               **##*%/(&#%/(%%////#%%(&%###%      ,,,                  ,&@%(#
        /&#,**% (,/**%,/(###*#((/...//#&#%%((%.&&(&*#(          .(%.,*( (&.
    .(,,.%.%%/###/,.#&,(%&%%#**##,,*.###(*#...*%%%/#*(##%%&(#&&&,**(&/(#&#
     %,% /*/(,,#(%#(&##*,&&&%%##/((#%(%#,#//#/&%%&&(((%%#%%%&%%&  / *#&@&
    . .       ..  %/*##%&&/,&@%%%&#%&&&&&/&%&&&&#&(*,        ,*.#@,(%.(#&
                       ( .%&%,     %%@/      (%&&/ ,&%              , &@&%#
                             *&%     %&(.        ,%%&#
                                                    &

FISH
echo -e "  ${BLUE}harahara${NC}${BOLD} — macOS Remote Control Bot"
echo -e "  Named after the Hara hara, a small catfish from Nepal 🐟${NC}"
echo ""

# ──────────────────────────────────────────────────────────
header "Step 1: Python Dependencies"
# ──────────────────────────────────────────────────────────

info "Checking Python 3..."
if ! command -v python3 &>/dev/null; then
    error "Python 3 is not installed. Please install it first:"
    echo "  brew install python3"
    exit 1
fi
success "Python 3 found: $(python3 --version)"

info "Installing required packages..."
pip3 install --quiet pyTelegramBotAPI pyyaml 2>/dev/null || pip3 install pyTelegramBotAPI pyyaml
success "Python packages installed (pyTelegramBotAPI, pyyaml)"

# ──────────────────────────────────────────────────────────
header "Step 2: Telegram Bot Setup"
# ──────────────────────────────────────────────────────────

if [ -f "$SCRIPT_DIR/.env" ]; then
    warn ".env file already exists."
    read -rp "Overwrite with new values? (y/N): " OVERWRITE_ENV
    if [[ ! "$OVERWRITE_ENV" =~ ^[Yy]$ ]]; then
        info "Keeping existing .env"
        source "$SCRIPT_DIR/.env" 2>/dev/null || true
    fi
fi

if [ ! -f "$SCRIPT_DIR/.env" ] || [[ "$OVERWRITE_ENV" =~ ^[Yy]$ ]]; then
    echo ""
    echo -e "${BOLD}To create a Telegram bot, you need a bot token and your user ID.${NC}"
    echo ""
    echo "📱 Get your BOT TOKEN:"
    echo "   1. Open Telegram and search for @BotFather"
    echo "   2. Send /newbot and follow the prompts"
    echo "   3. Copy the token (format: 123456:ABC-DEF...)"
    echo ""
    read -rp "Enter your bot token: " BOT_TOKEN
    while [[ -z "$BOT_TOKEN" ]] || [[ ! "$BOT_TOKEN" == *":"* ]]; do
        error "Token must contain a colon (e.g. 123456:ABC-DEF...)"
        read -rp "Enter your bot token: " BOT_TOKEN
    done

    echo ""
    echo "📱 Get your USER ID:"
    echo "   1. Open Telegram and search for @userinfobot"
    echo "   2. Send /start — it replies with your numeric ID"
    echo ""
    read -rp "Enter your Telegram user ID: " USER_ID
    while [[ -z "$USER_ID" ]] || ! [[ "$USER_ID" =~ ^[0-9]+$ ]]; do
        error "User ID must be a number"
        read -rp "Enter your Telegram user ID: " USER_ID
    done

    echo ""
    echo -e "${BOLD}Heartbeat Notification:${NC}"
    echo "   The bot can periodically send its emoji to your Telegram"
    echo "   to let you know it is still running and connected."
    echo "   (Set to 0 to disable message notifications.)"
    echo ""
    read -rp "Heartbeat interval in hours [1]: " HEARTBEAT_INTERVAL
    HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-1}
    while ! [[ "$HEARTBEAT_INTERVAL" =~ ^[0-9]+$ ]]; do
        error "Heartbeat interval must be a number (0 to disable)"
        read -rp "Heartbeat interval in hours [1]: " HEARTBEAT_INTERVAL
        HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-1}
    done

    echo ""
    echo -e "${BOLD}Natural Language Processing (NLP):${NC}"
    echo "   When enabled, plain text messages (without a / prefix) are"
    echo "   routed through an AI backend for intelligent responses."
    echo "   Commands starting with / are always handled directly."
    echo ""
    echo "   Choose your AI backend:"
    echo "     1) 🦙 Ollama  — local, free, private, offline"
    echo "     2) ✨ Gemini  — cloud AI via Gemini CLI"
    echo "     3) ❌ Disable — no NLP, commands only"
    echo ""
    read -rp "Choose [1/2/3, default: 3]: " NLP_CHOICE
    NLP_CHOICE=${NLP_CHOICE:-3}
    while [[ ! "$NLP_CHOICE" =~ ^[123]$ ]]; do
        error "Please enter 1, 2, or 3"
        read -rp "Choose [1/2/3, default: 3]: " NLP_CHOICE
        NLP_CHOICE=${NLP_CHOICE:-3}
    done

    if [[ "$NLP_CHOICE" == "1" ]]; then
        NLP_ENABLED="true"
        AI_BACKEND="ollama"
        if command -v ollama &>/dev/null; then
            success "Ollama found!"
        else
            warn "Ollama not installed yet."
            echo "  Install: brew install ollama && ollama serve && ollama pull llama3.2:1b"
        fi
        echo ""
        read -rp "Ollama model [llama3.2:1b]: " OLLAMA_MODEL
        OLLAMA_MODEL=${OLLAMA_MODEL:-llama3.2:1b}
    elif [[ "$NLP_CHOICE" == "2" ]]; then
        NLP_ENABLED="true"
        AI_BACKEND="gemini"
        if command -v gemini &>/dev/null; then
            success "Gemini CLI found!"
        else
            warn "Gemini CLI not installed yet."
            echo "  Install: npm install -g @google/generative-ai-cli"
        fi
        OLLAMA_MODEL=""
    else
        NLP_ENABLED="false"
        AI_BACKEND=""
        OLLAMA_MODEL=""
    fi

    PERSIST_CONVERSATIONS="false"
    if [[ "$NLP_ENABLED" == "true" ]]; then
        echo ""
        echo -e "  ${BOLD}Persist conversations?${NC}"
        echo "   If enabled, NLP conversation history survives bot restarts."
        echo "   If disabled (default), conversations reset on each restart."
        read -rp "Persist NLP conversations across restarts? (y/N): " PERSIST_CONV
        if [[ "$PERSIST_CONV" =~ ^[Yy]$ ]]; then
            PERSIST_CONVERSATIONS="true"
        fi
    fi

    echo ""
    echo -e "${BOLD}Bot Identity:${NC}"
    echo "   Give your bot a name and emoji. These appear in heartbeats,"
    echo "   startup messages, /help, and /status."
    echo ""
    read -rp "Bot name [harahara]: " CUSTOM_NAME
    CUSTOM_NAME=${CUSTOM_NAME:-harahara}
    read -rp "Bot emoji [🐟]: " CUSTOM_EMOJI
    CUSTOM_EMOJI=${CUSTOM_EMOJI:-🐟}
    cat > "$SCRIPT_DIR/.env" << EOF
# Auto-generated by setup.sh — $(date)
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_AUTHORIZED_USER_ID=$USER_ID
BOT_HEARTBEAT_INTERVAL=$HEARTBEAT_INTERVAL
BOT_NLP_ENABLED=$NLP_ENABLED
BOT_PERSIST_CONVERSATIONS=$PERSIST_CONVERSATIONS
BOT_AI_BACKEND=$AI_BACKEND
BOT_OLLAMA_MODEL=$OLLAMA_MODEL
BOT_NAME=$CUSTOM_NAME
BOT_EMOJI=$CUSTOM_EMOJI
EOF
    success "Created .env with your credentials"
fi

# ──────────────────────────────────────────────────────────
header "Step 3: Directories & Command Files"
# ──────────────────────────────────────────────────────────

# Create required directories
mkdir -p "$SCRIPT_DIR/logs" "$SCRIPT_DIR/personal"
success "Created logs/ and personal/ directories"

# Ensure shared bot_commands.yaml exists
if [ ! -f "$SCRIPT_DIR/bot_commands.yaml" ]; then
    error "bot_commands.yaml is missing! It should be included with the project."
    echo "  Try: git checkout bot_commands.yaml"
    exit 1
fi
success "Shared commands file found (bot_commands.yaml)"

# Create personal commands file
if [ ! -f "$SCRIPT_DIR/personal/bot_commands.yaml" ]; then
    cp "$SCRIPT_DIR/personal/bot_commands.yaml.example" "$SCRIPT_DIR/personal/bot_commands.yaml"
    info "Created personal/bot_commands.yaml from example."
    echo ""
    echo -e "${BOLD}Would you like to add a sample command?${NC}"
    echo "  This creates a /cal command that shows the calendar."
    read -rp "Add /cal command? (Y/n): " ADD_CAL
    if [[ ! "$ADD_CAL" =~ ^[Nn]$ ]]; then
        cat >> "$SCRIPT_DIR/personal/bot_commands.yaml" << 'EOF'

# ─── My Custom Commands ───
cal:
  cmd: "cal -h"
  desc: "Show calendar for current month"
EOF
        success "Added /cal command to personal/bot_commands.yaml"
    fi
    echo ""
    info "Add your own commands to personal/bot_commands.yaml anytime."
    info "Changes are picked up automatically — no restart needed."
else
    info "personal/bot_commands.yaml already exists, skipping."
fi

# ──────────────────────────────────────────────────────────
header "Step 4: Optional Tools"
# ──────────────────────────────────────────────────────────

echo "Checking for optional tools..."

# imagesnap (for /webcam)
if command -v imagesnap &>/dev/null; then
    success "imagesnap found (enables /webcam)"
else
    warn "imagesnap not found. /webcam will not work."
    read -rp "Install imagesnap via Homebrew? (Y/n): " INSTALL_IMAGESNAP
    if [[ ! "$INSTALL_IMAGESNAP" =~ ^[Nn]$ ]]; then
        if command -v brew &>/dev/null; then
            brew install imagesnap
            success "imagesnap installed"
        else
            error "Homebrew not found. Install manually: brew install imagesnap"
        fi
    fi
fi

# Gemini CLI
if command -v gemini &>/dev/null; then
    success "Gemini CLI found (enables /gemini)"
    GEMINI_PATH=$(which gemini)
    info "Path: $GEMINI_PATH"
else
    warn "Gemini CLI not found. /gemini will not work."
    echo "  Install: npm install -g @google/generative-ai-cli"
    echo "  Or: brew install gemini"
fi

# sox or ffmpeg (for /audio)
if command -v sox &>/dev/null; then
    success "sox found (enables /audio recording)"
elif command -v ffmpeg &>/dev/null; then
    success "ffmpeg found (enables /audio recording)"
else
    warn "Neither sox nor ffmpeg found. /audio will not work."
    read -rp "Install sox via Homebrew? (Y/n): " INSTALL_SOX
    if [[ ! "$INSTALL_SOX" =~ ^[Nn]$ ]]; then
        if command -v brew &>/dev/null; then
            brew install sox
            success "sox installed"
        else
            error "Homebrew not found. Install manually: brew install sox"
        fi
    fi
fi

# ──────────────────────────────────────────────────────────
header "Step 5: Auto-Start (launchd)"
# ──────────────────────────────────────────────────────────

PLIST_NAME="com.harahara.bot"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo -e "${BOLD}Set up the bot to start automatically on login?${NC}"
read -rp "Install launchd service? (Y/n): " INSTALL_LAUNCHD
if [[ ! "$INSTALL_LAUNCHD" =~ ^[Nn]$ ]]; then
    read -rp "Service name [$PLIST_NAME]: " CUSTOM_SERVICE
    PLIST_NAME="${CUSTOM_SERVICE:-$PLIST_NAME}"
    PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

    if [ -f "$PLIST_DEST" ]; then
        warn "Plist already exists at $PLIST_DEST"
        read -rp "Overwrite? (y/N): " OVERWRITE_PLIST
        if [[ ! "$OVERWRITE_PLIST" =~ ^[Yy]$ ]]; then
            info "Keeping existing plist."
            INSTALL_LAUNCHD="n"
        fi
    fi

    if [[ ! "$INSTALL_LAUNCHD" =~ ^[Nn]$ ]]; then
        # Update .env with the service name
        if ! grep -q "BOT_LAUNCHD_SERVICE" "$SCRIPT_DIR/.env" 2>/dev/null; then
            echo "BOT_LAUNCHD_SERVICE=$PLIST_NAME" >> "$SCRIPT_DIR/.env"
        fi

        # Generate plist from template
        sed \
            -e "s|__PROJECT_DIR__|$SCRIPT_DIR|g" \
            -e "s|__HOME_DIR__|$HOME|g" \
            -e "s|com.harahara.bot|$PLIST_NAME|g" \
            "$SCRIPT_DIR/com.harahara.bot.plist.example" > "$PLIST_DEST"

        launchctl load "$PLIST_DEST" 2>/dev/null || true
        success "Installed and loaded: $PLIST_DEST"
        info "Bot will auto-start on login and restart on crash."
    fi
else
    echo ""
    info "Starting the bot..."
    echo "    cd $SCRIPT_DIR && python3 telegram_listener.py"
    echo ""
    info "To start it again later:"
    echo "    cd $SCRIPT_DIR && python3 telegram_listener.py"
fi

echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║              Setup Complete! 🎉              ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo "📋 What was set up:"
echo "   ✅ Python dependencies installed"
echo "   ✅ Bot credentials configured in .env"
echo "   ✅ Personal commands file ready"
if [[ ! "$INSTALL_LAUNCHD" =~ ^[Nn]$ ]]; then
    echo "   ✅ Auto-start service installed"
fi
echo ""
echo -e "${BOLD}🚀 Next step:${NC}"
echo "   Send /setup in Telegram to grant macOS permissions."
echo "   You can always send /help for a full list of commands."
echo ""
