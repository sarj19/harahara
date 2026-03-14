"""AI command handlers: /ai and /ollamasetup."""
import threading

from botpkg import bot, logger


# ═══════════════════════════════════════════════════════════════════
# Ollama Setup — interactive Ollama installation wizard
# ═══════════════════════════════════════════════════════════════════

def handle_ollamasetup(message, chat_id, text):
    """Handle /ollamasetup — detect, configure, and test Ollama."""
    # Lazy import — zero overhead if never called
    from botpkg.ollama import is_available, is_running, list_models, RECOMMENDED_MODELS

    if not is_available():
        bot.send_message(
            chat_id,
            "🤖 *Ollama Setup*\n\n"
            "Ollama is not installed.\n\n"
            "*Install with:*\n"
            "```\nbrew install ollama\n```\n\n"
            "Then run `/ollamasetup` again.",
            parse_mode="Markdown",
        )
        return

    if not is_running():
        bot.send_message(
            chat_id,
            "🤖 *Ollama Setup*\n\n"
            "Ollama is installed but the server isn't running.\n\n"
            "*Start with:*\n"
            "```\nollama serve\n```\n\n"
            "Then run `/ollamasetup` again.",
            parse_mode="Markdown",
        )
        return

    args = text.split(" ", 1)[1].strip() if " " in text else ""

    # If user specified a model to pull
    if args and args.lower() not in ("status", "list", "models"):
        _ollama_pull_model(message, chat_id, args.strip())
        return

    # Show status and model picker
    installed = list_models()
    installed_names = [m.split(":")[0] if ":" in m else m for m in installed]

    lines = ["🤖 *Ollama Setup*\n"]

    if installed:
        lines.append(f"✅ Server running with {len(installed)} model(s):\n")
        for m in installed[:10]:
            lines.append(f"  `{m}`")
        lines.append("")

    lines.append("*Available small models:*\n")
    import telebot
    markup = telebot.types.InlineKeyboardMarkup(row_width=1)
    for model in RECOMMENDED_MODELS:
        name = model["name"]
        base_name = name.split(":")[0]
        already = "✅ " if any(base_name in m for m in installed_names) else ""
        markup.add(telebot.types.InlineKeyboardButton(
            f"{already}{name} ({model['size']}) — {model['desc']}",
            callback_data=f"runcmd:/ollamasetup {name}",
        ))

    try:
        from settings import BOT_AI_BACKEND, BOT_OLLAMA_MODEL
        lines.append(f"\n⚙️ Current backend: `{BOT_AI_BACKEND}`")
        if BOT_AI_BACKEND == "ollama":
            lines.append(f"🧠 Model: `{BOT_OLLAMA_MODEL}`")
    except (ImportError, AttributeError):
        lines.append("\n⚙️ Current backend: `gemini` (default)")

    lines.append("\n_Tap a model to pull it, or:_")
    lines.append("`/ollamasetup <model>` to pull manually")
    lines.append("\nSet `BOT_AI_BACKEND=ollama` in `.env` to switch.")

    bot.send_message(chat_id, "\n".join(lines), parse_mode="Markdown", reply_markup=markup)


def _ollama_pull_model(message, chat_id, model_name):
    """Pull an Ollama model in the background."""
    from botpkg.ollama import pull_model, generate

    bot.reply_to(message, f"🤖 Pulling `{model_name}`... this may take a few minutes.", parse_mode="Markdown")

    def do_pull():
        success, output = pull_model(model_name)
        if success:
            bot.send_message(
                chat_id,
                f"✅ Model `{model_name}` ready!\n\n"
                "Testing with a quick prompt...",
                parse_mode="Markdown",
            )
            # Quick test
            test_response = generate("Say hello in one sentence.", model=model_name, timeout=30)
            if test_response:
                bot.send_message(
                    chat_id,
                    f"🧠 Test response:\n_{test_response[:200]}_\n\n"
                    f"To use Ollama as your AI backend, add to `.env`:\n"
                    f"```\nBOT_AI_BACKEND=ollama\nBOT_OLLAMA_MODEL={model_name}\n```",
                    parse_mode="Markdown",
                )
            else:
                bot.send_message(
                    chat_id,
                    f"✅ Model `{model_name}` pulled but test failed.\n"
                    "Make sure `ollama serve` is running.",
                    parse_mode="Markdown",
                )
        else:
            bot.send_message(chat_id, f"❌ Pull failed:\n```\n{output[:500]}\n```", parse_mode="Markdown")

    threading.Thread(target=do_pull, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════
# AI — direct AI query (uses configured backend)
# ═══════════════════════════════════════════════════════════════════

def handle_ai(message, chat_id, text):
    """Handle /ai <question> — direct AI query."""
    args = text.split(" ", 1)[1].strip() if " " in text else ""
    if not args:
        try:
            from settings import BOT_AI_BACKEND
        except (ImportError, AttributeError):
            BOT_AI_BACKEND = "gemini"
        bot.reply_to(
            message,
            f"🤖 *AI Query* (backend: `{BOT_AI_BACKEND}`)\n\n"
            "Usage: `/ai <question>`\n"
            "Example: `/ai summarize what I did today`\n\n"
            "💡 Change backend with `BOT_AI_BACKEND` in `.env`\n"
            "💡 Run `/ollamasetup` for free local AI",
            parse_mode="Markdown",
        )
        return

    status_msg = bot.reply_to(message, "🧠 Thinking...")

    def do_query():
        from botpkg.brain import _call_ai
        from botpkg.memory import add_to_history

        add_to_history(chat_id, "user", args)
        result = _call_ai(args, chat_id)

        if result is None:
            bot.send_message(
                chat_id,
                "❌ No AI backend available.\n\n"
                "• Gemini: `npm install -g @google/generative-ai-cli`\n"
                "• Ollama: `/ollamasetup`",
                parse_mode="Markdown",
            )
            return

        response, backend = result
        if response is None:
            bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text="❌ AI query failed. Check that your backend is running.")
            return

        add_to_history(chat_id, "assistant", response[:500])

        if len(response) > 4000:
            response = response[:4000] + "\n...[truncated]"

        footer = f"\n\n_via {backend}_" if backend else ""
        bot.edit_message_text(chat_id=chat_id, message_id=status_msg.message_id, text=f"{response}{footer}", parse_mode="Markdown")

    threading.Thread(target=do_query, daemon=True).start()
