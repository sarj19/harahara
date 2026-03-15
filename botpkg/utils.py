"""Utility functions: YAML loading, file sending, screenshots, duration parsing, aliases."""
import os
import re
import subprocess

import yaml

from botpkg import bot, logger
from settings import YAML_PATH, PERSONAL_YAML_PATH

# ─── YAML Command Cache ───
_commands_cache = {}
_commands_mtime = (0, 0)  # (shared_mtime, personal_mtime)
commands_sections = []  # [(section_name, [cmd_names])] — used by /help
_aliases_cache = {}  # alias → canonical command name (from YAML aliases: field)
_cmd_to_section = {}  # command_name → section_name (for themed responses)
followups_map = {}  # command_name → [(label, command)] — from YAML followups key


def _parse_sections(raw_lines, commands_dict):
    """Parse section headers from YAML comment lines."""
    sections = []
    current_section = "Other"
    current_cmds = []
    for line in raw_lines:
        stripped = line.strip()
        m = re.match(r'^#\s*─+\s*(.+?)\s*─+\s*$', stripped)
        if m:
            if current_cmds:
                sections.append((current_section, current_cmds))
            current_section = m.group(1)
            current_cmds = []
        elif stripped and not stripped.startswith('#') and ':' in stripped:
            cmd_name = stripped.split(':')[0].strip().lower()
            if cmd_name in commands_dict:
                current_cmds.append(cmd_name)
    if current_cmds:
        sections.append((current_section, current_cmds))
    return sections


def _build_cmd_to_section(sections):
    """Build a mapping from command name to section name."""
    mapping = {}
    for section_name, cmd_names in sections:
        for cmd in cmd_names:
            mapping[cmd] = section_name
    return mapping


def _build_aliases(commands_dict):
    """Build alias → canonical name mapping from YAML aliases: fields."""
    aliases = {}
    for cmd_name, entry in commands_dict.items():
        if isinstance(entry, dict) and "aliases" in entry:
            for alias in entry["aliases"]:
                aliases[alias.strip().lower()] = cmd_name
    return aliases


def load_commands():
    """Load commands from bot_commands.yaml + personal_bot_commands.yaml (if exists).
    Personal commands merge into (and can override) shared commands.
    Returns dict of {name: {"cmd": str, "desc": str, ...}}.
    Also populates commands_sections for grouped /help output.
    """
    global _commands_cache, _commands_mtime, commands_sections
    global _aliases_cache, _cmd_to_section
    try:
        shared_mtime = os.path.getmtime(YAML_PATH) if os.path.exists(YAML_PATH) else 0
        personal_mtime = os.path.getmtime(PERSONAL_YAML_PATH) if os.path.exists(PERSONAL_YAML_PATH) else 0

        if (shared_mtime, personal_mtime) == _commands_mtime and _commands_cache:
            return _commands_cache

        # Load shared commands
        all_commands = {}
        all_raw_lines = []
        if os.path.exists(YAML_PATH):
            with open(YAML_PATH, "r") as f:
                raw_lines = f.readlines()
                f.seek(0)
                commands = yaml.safe_load(f) or {}
            all_commands.update({k.strip().lower(): v for k, v in commands.items()})
            all_raw_lines.extend(raw_lines)

        # Load personal commands (merge/override)
        if os.path.exists(PERSONAL_YAML_PATH):
            with open(PERSONAL_YAML_PATH, "r") as f:
                raw_lines = f.readlines()
                f.seek(0)
                personal = yaml.safe_load(f) or {}
            all_commands.update({k.strip().lower(): v for k, v in personal.items()})
            all_raw_lines.extend(raw_lines)

        _commands_cache = all_commands
        _commands_mtime = (shared_mtime, personal_mtime)
        commands_sections = _parse_sections(all_raw_lines, all_commands)
        _cmd_to_section = _build_cmd_to_section(commands_sections)
        _aliases_cache = _build_aliases(all_commands)

        # Extract _special section → populate SPECIAL_COMMANDS and aliases
        special_data = all_commands.pop("_special", None)
        if special_data and isinstance(special_data, dict):
            from botpkg.config import load_special_from_yaml
            load_special_from_yaml(special_data)
            # Merge special command followups into followups_map
            for name, entry in special_data.items():
                if isinstance(entry, dict) and "followups" in entry:
                    fups = entry["followups"]
                    if isinstance(fups, list):
                        followups_map[name] = [
                            (f.get("label", f.get("cmd", "")), f.get("cmd", ""))
                            for f in fups if isinstance(f, dict)
                        ]

        # Build follow-up buttons map from YAML commands
        for name, entry in all_commands.items():
            if isinstance(entry, dict) and "followups" in entry:
                fups = entry["followups"]
                if isinstance(fups, list):
                    followups_map[name] = [
                        (f.get("label", f.get("cmd", "")), f.get("cmd", ""))
                        for f in fups if isinstance(f, dict)
                    ]

        # Update cache (without _special)
        _commands_cache = all_commands

        return _commands_cache
    except Exception as e:
        logger.error(f"Error loading commands: {e}")
        return _commands_cache if _commands_cache else {}


def resolve_alias(name):
    """Resolve a command alias to its canonical name.

    Checks YAML aliases first, then special command aliases from config.
    Returns the canonical name, or the original name if not an alias.
    """
    from botpkg.config import SPECIAL_COMMAND_ALIASES
    name = name.lower()
    # YAML aliases (populated during load_commands)
    if name in _aliases_cache:
        return _aliases_cache[name]
    # Special command aliases (hardcoded in config)
    if name in SPECIAL_COMMAND_ALIASES:
        return SPECIAL_COMMAND_ALIASES[name]
    return name


def get_aliases_for(name):
    """Get all aliases that map to a given command name."""
    from botpkg.config import SPECIAL_COMMAND_ALIASES
    name = name.lower()
    aliases = []
    for alias, target in _aliases_cache.items():
        if target == name:
            aliases.append(alias)
    for alias, target in SPECIAL_COMMAND_ALIASES.items():
        if target == name:
            aliases.append(alias)
    return sorted(aliases)


def get_cmd_section(name):
    """Get the section name for a command (for themed emoji lookup)."""
    return _cmd_to_section.get(name.lower(), "")


def send_file_smart(chat_id, file_path, caption=None, delete_message_id=None, reply_to_message_id=None):
    """Send as photo if < 10MB, else as document."""
    try:
        if delete_message_id: 
            try: bot.delete_message(chat_id, delete_message_id) 
            except: pass
        if not os.path.exists(file_path):
            return False
        file_size = os.path.getsize(file_path)
        if file_size < 10 * 1024 * 1024:
            with open(file_path, "rb") as f:
                bot.send_photo(chat_id, f, caption=caption, reply_to_message_id=reply_to_message_id)
        else:
            with open(file_path, "rb") as f:
                bot.send_document(chat_id, f, caption=caption, reply_to_message_id=reply_to_message_id)
        return True
    except Exception as e:
        logger.error(f"Error sending file {file_path}: {e}")
        return False


def take_and_send_screenshot(chat_id, delete_message_id=None, reply_to_message_id=None):
    """Wake display, capture a screenshot, and send it."""

    if delete_message_id:
        try: bot.delete_message(chat_id, delete_message_id)
        except: pass

    screenshot_path = "/tmp/harahara_bot_screenshot.jpg"
    try:
        subprocess.run(["caffeinate", "-u", "-t", "2"], capture_output=True)
        if os.path.exists(screenshot_path):
            os.remove(screenshot_path)
        subprocess.run(
            ["screencapture", "-x", "-t", "jpg", screenshot_path],
            check=True, capture_output=True, text=True,
        )
        if os.path.exists(screenshot_path):
            success = send_file_smart(chat_id, screenshot_path, reply_to_message_id=reply_to_message_id)
            os.remove(screenshot_path)
            if success:
                activity_stats["screenshots_taken"] += 1
            return success
    except subprocess.CalledProcessError as e:
        err_out = e.stderr.strip() if e.stderr else str(e)
        error_msg = f"❌ Screenshot failed: {err_out}"
        if "could not create image from display" in err_out or "error (1)" in err_out:
            error_msg += "\n\n💡 *Tip:* Grant 'Screen Recording' permission in System Settings > Privacy & Security."
        bot.send_message(chat_id, error_msg, parse_mode="Markdown")
        logger.error(f"Screenshot follow-up failed: {err_out}")
    except Exception as e:
        logger.error(f"Screenshot follow-up failed: {e}")
    return False


def parse_duration(s):
    """Parse a duration string like '5m', '2h', '90s', '90' into seconds.
    Returns (seconds, human_label) or (None, None) on failure.
    """
    s = s.strip().lower()
    m = re.match(r'^(\d+)\s*(s|sec|secs|m|min|mins|h|hr|hrs|hour|hours)?$', s)
    if not m:
        return None, None
    val = int(m.group(1))
    unit = m.group(2) or 's'
    if unit.startswith('h'):
        seconds = val * 3600
        label = f"{val} hour{'s' if val != 1 else ''}"
    elif unit.startswith('m'):
        seconds = val * 60
        label = f"{val} minute{'s' if val != 1 else ''}"
    else:
        seconds = val
        label = f"{val} second{'s' if val != 1 else ''}"
    return seconds, label


def get_cmd_name(text):
    """Extract command name from message text."""
    return text.split("@")[0].split(" ")[0].lower()
