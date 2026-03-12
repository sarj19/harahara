"""Status card image generator using Pillow.

Generates a dark-themed PNG dashboard showing battery, CPU, memory, disk,
uptime, streak, and top commands.
"""
import io
import os
import re
import subprocess
import time

from PIL import Image, ImageDraw, ImageFont


# ─── Theme ───
BG_COLOR = (24, 24, 32)
CARD_COLOR = (34, 34, 48)
ACCENT = (88, 166, 255)
GREEN = (72, 199, 142)
YELLOW = (255, 193, 7)
RED = (255, 82, 82)
TEXT = (230, 230, 240)
DIM = (140, 140, 160)
BAR_BG = (50, 50, 65)

WIDTH = 600
PADDING = 24
CARD_PAD = 16
CARD_RADIUS = 12
ROW_HEIGHT = 36


def _get_font(size=16):
    """Get a font, falling back to default."""
    paths = [
        "/System/Library/Fonts/SFCompact.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_bar(draw, x, y, width, percent, color, height=14):
    """Draw a progress bar."""
    draw.rounded_rectangle([x, y, x + width, y + height], radius=4, fill=BAR_BG)
    filled = max(2, int(width * percent / 100))
    draw.rounded_rectangle([x, y, x + filled, y + height], radius=4, fill=color)


def _get_battery():
    """Get battery percent and charging status."""
    try:
        result = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split("\n"):
            if "%" in line:
                match = re.search(r"(\d+)%", line)
                if match:
                    pct = int(match.group(1))
                    charging = "charging" in line.lower()
                    return pct, charging
    except Exception:
        pass
    return None, False


def _get_cpu_mem():
    """Get CPU and memory usage."""
    cpu, mem = 0, 0
    try:
        result = subprocess.run(
            ["ps", "-A", "-o", "%cpu,%mem"], capture_output=True, text=True, timeout=5
        )
        lines = result.stdout.strip().split("\n")[1:]  # Skip header
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                cpu += float(parts[0])
                mem += float(parts[1])
        cpu = min(cpu, 100)  # Can exceed 100 on multi-core
        mem = min(mem, 100)
    except Exception:
        pass
    return int(cpu), int(mem)


def _get_disk():
    """Get disk usage percent."""
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            fields = lines[1].split()
            if len(fields) >= 5:
                return int(fields[4].rstrip("%")), fields[2], fields[1]
    except Exception:
        pass
    return 0, "?", "?"


def generate_status_card(bot_name, bot_emoji, uptime_secs, commands_run,
                         screenshots, top_cmds, streak_data, tagline=""):
    """Generate a status card PNG and return bytes."""
    font = _get_font(16)
    font_sm = _get_font(13)
    font_lg = _get_font(22)
    font_title = _get_font(28)

    # Gather system data
    batt_pct, charging = _get_battery()
    cpu_pct, mem_pct = _get_cpu_mem()
    disk_pct, disk_used, disk_total = _get_disk()

    hours = uptime_secs // 3600
    mins = (uptime_secs % 3600) // 60

    # Calculate image height
    rows = 7  # title, uptime, battery, cpu, mem, disk, stats
    if streak_data.get("current", 0) > 0:
        rows += 1
    if top_cmds:
        rows += 1
    height = PADDING * 2 + CARD_PAD * 2 + ROW_HEIGHT * rows + 60

    # Create image
    img = Image.new("RGB", (WIDTH, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    y = PADDING

    # ─── Title ───
    title = f"{bot_emoji}  {bot_name}"
    draw.text((PADDING, y), title, fill=TEXT, font=font_title)
    y += 40

    if tagline:
        draw.text((PADDING, y), tagline, fill=DIM, font=font_sm)
        y += 20

    # ─── Card background ───
    card_top = y
    card_bottom = height - PADDING
    draw.rounded_rectangle(
        [PADDING - 4, card_top, WIDTH - PADDING + 4, card_bottom],
        radius=CARD_RADIUS, fill=CARD_COLOR
    )
    y += CARD_PAD

    # ─── Uptime ───
    draw.text((PADDING + CARD_PAD, y), "⏱  Uptime", fill=DIM, font=font_sm)
    draw.text((WIDTH - PADDING - CARD_PAD - 120, y), f"{hours}h {mins}m", fill=TEXT, font=font)
    y += ROW_HEIGHT

    # ─── Battery ───
    if batt_pct is not None:
        batt_color = GREEN if batt_pct > 40 else (YELLOW if batt_pct > 15 else RED)
        label = f"🔋  Battery {'⚡' if charging else ''}"
        draw.text((PADDING + CARD_PAD, y), label, fill=DIM, font=font_sm)
        bar_x = PADDING + CARD_PAD + 180
        _draw_bar(draw, bar_x, y + 2, 200, batt_pct, batt_color)
        draw.text((bar_x + 208, y), f"{batt_pct}%", fill=TEXT, font=font_sm)
        y += ROW_HEIGHT

    # ─── CPU ───
    cpu_color = GREEN if cpu_pct < 50 else (YELLOW if cpu_pct < 80 else RED)
    draw.text((PADDING + CARD_PAD, y), "🧮  CPU", fill=DIM, font=font_sm)
    bar_x = PADDING + CARD_PAD + 180
    _draw_bar(draw, bar_x, y + 2, 200, min(cpu_pct, 100), cpu_color)
    draw.text((bar_x + 208, y), f"{cpu_pct}%", fill=TEXT, font=font_sm)
    y += ROW_HEIGHT

    # ─── Memory ───
    mem_color = GREEN if mem_pct < 60 else (YELLOW if mem_pct < 85 else RED)
    draw.text((PADDING + CARD_PAD, y), "💾  Memory", fill=DIM, font=font_sm)
    _draw_bar(draw, bar_x, y + 2, 200, mem_pct, mem_color)
    draw.text((bar_x + 208, y), f"{mem_pct}%", fill=TEXT, font=font_sm)
    y += ROW_HEIGHT

    # ─── Disk ───
    disk_color = GREEN if disk_pct < 70 else (YELLOW if disk_pct < 90 else RED)
    draw.text((PADDING + CARD_PAD, y), "📀  Disk", fill=DIM, font=font_sm)
    _draw_bar(draw, bar_x, y + 2, 200, disk_pct, disk_color)
    draw.text((bar_x + 208, y), f"{disk_pct}%", fill=TEXT, font=font_sm)
    y += ROW_HEIGHT + 8

    # ─── Divider ───
    draw.line([(PADDING + CARD_PAD, y), (WIDTH - PADDING - CARD_PAD, y)], fill=BAR_BG, width=1)
    y += 12

    # ─── Stats row ───
    draw.text((PADDING + CARD_PAD, y), f"📊 Commands: {commands_run}", fill=TEXT, font=font)
    draw.text((WIDTH // 2, y), f"📸 Screenshots: {screenshots}", fill=TEXT, font=font)
    y += ROW_HEIGHT

    # ─── Streak ───
    current_streak = streak_data.get("current", 0)
    if current_streak > 0:
        flame = "🔥" * min(current_streak, 7)
        draw.text((PADDING + CARD_PAD, y), f"{flame}  {current_streak} day streak", fill=YELLOW, font=font)
        y += ROW_HEIGHT

    # ─── Top commands ───
    if top_cmds:
        top_str = "  ".join(f"/{c} ×{n}" for c, n in top_cmds[:4])
        draw.text((PADDING + CARD_PAD, y), f"🏆  {top_str}", fill=ACCENT, font=font_sm)
        y += ROW_HEIGHT

    # Export to bytes
    buf = io.BytesIO()
    img.save(buf, format="PNG", quality=95)
    buf.seek(0)
    return buf
