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
    read -p "Overwrite with new values? (y/N): " OVERWRITE_ENV
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
    read -p "Enter your bot token: " BOT_TOKEN
    while [[ -z "$BOT_TOKEN" ]] || [[ ! "$BOT_TOKEN" == *":"* ]]; do
        error "Token must contain a colon (e.g. 123456:ABC-DEF...)"
        read -p "Enter your bot token: " BOT_TOKEN
    done

    echo ""
    echo "📱 Get your USER ID:"
    echo "   1. Open Telegram and search for @userinfobot"
    echo "   2. Send /start — it replies with your numeric ID"
    echo ""
    read -p "Enter your Telegram user ID: " USER_ID
    while [[ -z "$USER_ID" ]] || ! [[ "$USER_ID" =~ ^[0-9]+$ ]]; do
        error "User ID must be a number"
        read -p "Enter your Telegram user ID: " USER_ID
    done

    echo ""
    echo -e "${BOLD}Heartbeat Notification:${NC}"
    echo "   The bot can periodically send its emoji to your Telegram"
    echo "   to let you know it is still running and connected."
    echo "   (Set to 0 to disable message notifications.)"
    echo ""
    read -p "Heartbeat interval in hours [1]: " HEARTBEAT_INTERVAL
    HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-1}
    while ! [[ "$HEARTBEAT_INTERVAL" =~ ^[0-9]+$ ]]; do
        error "Heartbeat interval must be a number (0 to disable)"
        read -p "Heartbeat interval in hours [1]: " HEARTBEAT_INTERVAL
        HEARTBEAT_INTERVAL=${HEARTBEAT_INTERVAL:-1}
    done

    echo ""
    echo -e "${BOLD}Natural Language Processing (NLP):${NC}"
    echo "   When enabled, plain text messages (without a / prefix) are"
    echo "   forwarded to the Gemini CLI for AI-powered responses."
    echo "   Commands starting with / are always handled directly — no AI tokens burned."
    echo "   (Requires Gemini CLI to be installed.)"
    echo ""
    read -p "Enable NLP mode? (y/N): " ENABLE_NLP
    if [[ "$ENABLE_NLP" =~ ^[Yy]$ ]]; then
        NLP_ENABLED="true"

        echo ""
        echo -e "  ${BOLD}Persist conversations?${NC}"
        echo "   If enabled, NLP conversation history survives bot restarts."
        echo "   If disabled (default), conversations reset on each restart."
        read -p "Persist NLP conversations across restarts? (y/N): " PERSIST_CONV
        if [[ "$PERSIST_CONV" =~ ^[Yy]$ ]]; then
            PERSIST_CONVERSATIONS="true"
        else
            PERSIST_CONVERSATIONS="false"
        fi
    else
        NLP_ENABLED="false"
        PERSIST_CONVERSATIONS="false"
    fi

    echo ""
    echo -e "${BOLD}Bot Identity:${NC}"
    echo "   Give your bot a name and emoji. These appear in heartbeats,"
    echo "   startup messages, /help, and /status."
    echo ""
    read -p "Bot name [harahara]: " CUSTOM_NAME
    CUSTOM_NAME=${CUSTOM_NAME:-harahara}
    read -p "Bot emoji [🐟]: " CUSTOM_EMOJI
    CUSTOM_EMOJI=${CUSTOM_EMOJI:-🐟}
    cat > "$SCRIPT_DIR/.env" << EOF
# Auto-generated by setup.sh — $(date)
TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_AUTHORIZED_USER_ID=$USER_ID
BOT_HEARTBEAT_INTERVAL=$HEARTBEAT_INTERVAL
BOT_NLP_ENABLED=$NLP_ENABLED
BOT_PERSIST_CONVERSATIONS=$PERSIST_CONVERSATIONS
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
    read -p "Add /cal command? (Y/n): " ADD_CAL
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
    read -p "Install imagesnap via Homebrew? (Y/n): " INSTALL_IMAGESNAP
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
    read -p "Install sox via Homebrew? (Y/n): " INSTALL_SOX
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
header "Step 5: Google Calendar & Gmail (Optional)"
# ──────────────────────────────────────────────────────────

echo "  Connect Google Calendar and Gmail for /calendar and /mail commands."
echo "  This requires a Google Cloud project with Calendar + Gmail APIs enabled."
echo ""
read -p "Set up Google integration? (y/N): " SETUP_GOOGLE
if [[ "$SETUP_GOOGLE" =~ ^[Yy]$ ]]; then
    info "Installing Google API packages..."
    pip3 install --quiet google-api-python-client google-auth-httplib2 google-auth-oauthlib 2>/dev/null || \
        pip3 install google-api-python-client google-auth-httplib2 google-auth-oauthlib
    success "Google API packages installed"
    echo ""
    echo "  📋 Steps to get Google credentials:"
    echo "     1. Go to https://console.cloud.google.com"
    echo "     2. Create a project (or select one)"
    echo "     3. Enable 'Google Calendar API' and 'Gmail API'"
    echo "        (APIs & Services → Library → search and enable both)"
    echo "     4. Create OAuth2 credentials:"
    echo "        APIs & Services → Credentials → Create → OAuth Client ID → Desktop App"
    echo "     5. Download the JSON and save it as:"
    echo "        personal/google_credentials.json"
    echo ""
    read -p "Press Enter when google_credentials.json is saved (or 's' to skip)... " GOOGLE_SKIP
    if [[ "$GOOGLE_SKIP" != "s" && -f "$SCRIPT_DIR/personal/google_credentials.json" ]]; then
        info "Running Google auth flow (a browser will open)..."
        cd "$SCRIPT_DIR" && python3 -c "from botpkg.google_auth import run_auth_flow; run_auth_flow()"
        if [ $? -eq 0 ]; then
            success "Google authentication complete!"
        else
            warn "Auth flow failed. You can try later with /googlesetup"
        fi
    elif [[ "$GOOGLE_SKIP" == "s" ]]; then
        info "Skipped. You can set up Google later with /googlesetup"
    else
        warn "Credentials file not found at personal/google_credentials.json"
        warn "You can set this up later with /googlesetup"
    fi
else
    info "Skipped. You can set up Google later with /googlesetup"
fi

# ──────────────────────────────────────────────────────────
header "Step 6: macOS Permissions"
# ──────────────────────────────────────────────────────────

echo -e "${BOLD}The bot needs specific macOS permissions to work fully.${NC}"
echo "You'll need to grant these in System Settings > Privacy & Security."
echo ""
echo "  📸 ${BOLD}Screen Recording${NC} — required for /screenshot, /record"
echo "     Grant to: Terminal.app (or your terminal emulator)"
echo ""
echo "  ⌨️  ${BOLD}Accessibility${NC} — required for /key, /type"
echo "     Grant to: Terminal.app (or your terminal emulator)"
echo ""
echo "  📷 ${BOLD}Camera${NC} — required for /webcam"
echo "     Grant to: imagesnap (if installed)"
echo ""
echo "  🎙 ${BOLD}Microphone${NC} — required for /audio"
echo "     Grant to: Terminal.app (or your terminal emulator)"
echo ""
echo "  💾 ${BOLD}Full Disk Access${NC} — required for /notifications"
echo "     Grant to: Terminal.app (or your terminal emulator)"
echo ""

read -p "Open System Settings > Privacy & Security now? (Y/n): " OPEN_SETTINGS
if [[ ! "$OPEN_SETTINGS" =~ ^[Nn]$ ]]; then
    open "x-apple.systempreferences:com.apple.preference.security?Privacy"
    info "Opened Privacy & Security settings."
    echo "  Please grant the permissions listed above, then come back."
    read -p "Press Enter when done..."
fi

# ──────────────────────────────────────────────────────────
header "Step 6: Auto-Start (launchd)"
# ──────────────────────────────────────────────────────────

PLIST_NAME="com.harahara.bot"
PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

echo -e "${BOLD}Set up the bot to start automatically on login?${NC}"
read -p "Install launchd service? (Y/n): " INSTALL_LAUNCHD
if [[ ! "$INSTALL_LAUNCHD" =~ ^[Nn]$ ]]; then
    read -p "Service name [$PLIST_NAME]: " CUSTOM_SERVICE
    PLIST_NAME="${CUSTOM_SERVICE:-$PLIST_NAME}"
    PLIST_DEST="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"

    if [ -f "$PLIST_DEST" ]; then
        warn "Plist already exists at $PLIST_DEST"
        read -p "Overwrite? (y/N): " OVERWRITE_PLIST
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
    info "You can run the bot manually anytime:"
    echo "    cd $SCRIPT_DIR && python3 telegram_listener.py"
fi

# ──────────────────────────────────────────────────────────
header "Step 7: Verify"
# ──────────────────────────────────────────────────────────

echo "Running import check..."
if cd "$SCRIPT_DIR" && python3 -c "from botpkg import bot; import botpkg.handlers; print('OK')" 2>/dev/null; then
    success "All imports verified."
else
    error "Import check failed. Check the error above."
    exit 1
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
echo -e "${BOLD}🚀 Quick start:${NC}"
echo "   Open Telegram, send /help to your bot!"
echo ""
echo -e "${BOLD}🔨 Build custom commands, schedules & macros:${NC}"
echo "   /build                → interactive wizard (choose command, schedule, or macro)"
echo "   /build mycommand curl wttr.in  → quick one-liner command creation"
echo ""
echo "   Or edit YAML files directly:"
echo "     personal/bot_commands.yaml → custom commands (live-reloaded)"
echo "     personal/schedules.yaml    → scheduled/cron-like tasks"
echo "     personal/macros.yaml       → multi-step command sequences"
echo ""
echo -e "${BOLD}📝 Quick notes:${NC}"
echo "   /note save Remember to deploy"
echo "   /note list   —   /note search deploy   —   /note delete 1"
echo ""
echo -e "${BOLD}🧪 Run tests:${NC}"
echo "   TELEGRAM_BOT_TOKEN='123456:FAKE' TELEGRAM_AUTHORIZED_USER_ID='12345' \\"
echo "     python3 -m unittest discover -s tests -v"
echo ""
