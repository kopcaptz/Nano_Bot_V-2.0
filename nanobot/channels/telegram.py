"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import TYPE_CHECKING

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from nanobot.bus.events import OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import TelegramConfig

if TYPE_CHECKING:
    from nanobot.session.manager import SessionManager


def _markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown to Telegram-safe HTML.
    """
    if not text:
        return ""

    # 0. Rich formatting: emoji status, progress bars (before code block extraction)
    text = re.sub(r":ok:", "✅", text)
    text = re.sub(r":fail:", "❌", text)
    text = re.sub(r":pending:", "⏳", text)
    text = re.sub(r":error:", "❌", text)
    text = re.sub(r":running:", "🔄", text)
    # [progress:80] -> ████████░░ 80%
    def _progress_bar(m: re.Match) -> str:
        pct = int(m.group(1))
        pct = max(0, min(100, pct))
        filled = int(10 * pct / 100)
        bar = "█" * filled + "░" * (10 - filled)
        return f"{bar} {pct}%"
    text = re.sub(r"\[progress:(\d+)\]", _progress_bar, text)

    # 1. Extract and protect code blocks (preserve content from other processing)
    code_blocks: list[str] = []
    def save_code_block(m: re.Match) -> str:
        code_blocks.append(m.group(1))
        return f"\x00CB{len(code_blocks) - 1}\x00"
    
    text = re.sub(r'```[\w]*\n?([\s\S]*?)```', save_code_block, text)
    
    # 2. Extract and protect inline code
    inline_codes: list[str] = []
    def save_inline_code(m: re.Match) -> str:
        inline_codes.append(m.group(1))
        return f"\x00IC{len(inline_codes) - 1}\x00"
    
    text = re.sub(r'`([^`]+)`', save_inline_code, text)
    
    # 3. Headers # Title -> just the title text
    text = re.sub(r'^#{1,6}\s+(.+)$', r'\1', text, flags=re.MULTILINE)
    
    # 4. Blockquotes > text -> just the text (before HTML escaping)
    text = re.sub(r'^>\s*(.*)$', r'\1', text, flags=re.MULTILINE)
    
    # 5. Escape HTML special characters
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    
    # 6. Links [text](url) - must be before bold/italic to handle nested cases
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    
    # 7. Bold **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)
    
    # 8. Italic _text_ (avoid matching inside words like some_var_name)
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])', r'<i>\1</i>', text)
    
    # 9. Strikethrough ~~text~~
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
    
    # 10. Bullet lists - item -> • item
    text = re.sub(r'^[-*]\s+', '• ', text, flags=re.MULTILINE)

    # 10b. Markdown tables -> HTML table
    table_pattern = r'(\|[^\n]+\|\n)((?:\|[-:\s|]+\|\n)?(?:\|[^\n]+\|\n?)*)'
    def _table_replacer(m: re.Match) -> str:
        header_line = m.group(1)
        body = m.group(2)
        cells = [c.strip() for c in header_line.split("|") if c.strip()]
        if not cells:
            return m.group(0)
        header = "<tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr>"
        rows = []
        for line in body.strip().split("\n"):
            if re.match(r'^\|[-:\s|]+\|', line):
                continue
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if cells:
                row = "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
                rows.append(row)
        return f"<table border=\"1\">{header}{''.join(rows)}</table>"
    text = re.sub(table_pattern, _table_replacer, text)

    # 11. Restore inline code with HTML tags
    for i, code in enumerate(inline_codes):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00IC{i}\x00", f"<code>{escaped}</code>")
    
    # 12. Restore code blocks with HTML tags
    for i, code in enumerate(code_blocks):
        # Escape HTML in code content
        escaped = code.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00CB{i}\x00", f"<pre><code>{escaped}</code></pre>")
    
    return text


class TelegramChannel(BaseChannel):
    """
    Telegram channel using long polling.
    
    Simple and reliable - no webhook/public IP needed.
    """
    
    name = "telegram"
    
    # Commands registered with Telegram's command menu
    BOT_COMMANDS = [
        BotCommand("start", "Start the bot"),
        BotCommand("reset", "Reset conversation history"),
        BotCommand("help", "Show available commands"),
    ]
    MAX_MESSAGE_LENGTH = 4000
    MENU_STATE_KEY = "menu_state"
    MENU_STACK_KEY = "menu_stack"
    MENU_PENDING_COMMAND_KEY = "pending_command"
    MENU_MESSAGE_ID_KEY = "menu_message_id"

    MENU_STATE_MAIN = "main"
    MENU_STATE_COMMANDS = "commands"
    MENU_STATE_REFLECTION = "commands_reflection"
    MENU_STATE_MEMORY = "commands_memory"
    MENU_STATE_TOOLS = "commands_tools"
    MENU_STATE_FILES = "files"
    MENU_STATE_GIT = "git"
    MENU_STATE_SKILLS = "skills"
    MENU_STATE_CONFIRM = "command_confirm"

    CMD_MENU_MAIN = "cmd_menu_main"
    CMD_MENU_COMMANDS = "cmd_menu_commands"
    CMD_MENU_REFLECTION = "cmd_menu_reflection"
    CMD_MENU_MEMORY = "cmd_menu_memory"
    CMD_MENU_TOOLS = "cmd_menu_tools"
    CMD_MENU_FILES = "quick:files"
    CMD_MENU_GIT = "quick:git"
    CMD_MENU_SKILLS = "quick:skills"
    CMD_SELECT_PREFIX = "cmd_select:"
    CMD_EXEC_PREFIX = "cmd_exec:"
    CMD_BACK = "cmd_back"
    CMD_CANCEL = "cmd_cancel"

    # Confirmation callback prefix (cfm:yes:id, cfm:no:id, cfm:later:id)
    CONFIRM_PREFIX = "cfm:"
    CONFIRM_TIMEOUT_SEC = 300  # 5 minutes
    # Error retry callback prefix (err:retry:id, err:cancel:id)
    ERR_PREFIX = "err:"

    COMMANDS = {
        MENU_STATE_REFLECTION: [
            ("reflect_session", "/reflect session", "🔍 Рефлексия (сессия)"),
            ("reflect_error", "/reflect error", "🧩 Рефлексия (ошибка)"),
            ("confidence", "/confidence", "📊 Уверенность (/confidence)"),
            ("premortem", "/pre-mortem", "🛡 Pre-mortem (/pre-mortem)"),
        ],
        MENU_STATE_MEMORY: [
            ("remember", "/remember", "💾 Запомнить (/remember)"),
            ("recall", "/recall", "🧠 Вспомнить (/recall)"),
            ("crystallize", "/crystallize", "💎 Кристаллизация (/crystallize)"),
        ],
        MENU_STATE_TOOLS: [
            ("weather", "/weather", "🌤 Погода (/weather)"),
            ("vision", "/vision", "👁 Vision (скриншот)"),
            ("cron_list", "/cron list", "⏰ Cron list (/cron list)"),
        ],
        MENU_STATE_FILES: [
            ("list_files", "покажи файлы в текущей директории", "📋 Список"),
            ("read_file", "прочитай файл", "👁️ Просмотр"),
            ("edit_file", "отредактируй файл", "✏️ Редактировать"),
            ("send_file", "отправь файл", "📤 Отправить"),
            ("delete_file", "удали файл", "🗑️ Удалить"),
        ],
        MENU_STATE_GIT: [
            ("git_status", "git status", "📊 Status"),
            ("git_commit", "git commit", "📝 Commit"),
            ("git_branch", "git branch", "🌿 Branch"),
            ("git_pr", "создай pull request", "🔀 PR"),
            ("git_tag", "git tag", "🏷️ Tag"),
        ],
        MENU_STATE_SKILLS: [
            ("skill_search", "найди навыки", "🎯 Поиск"),
            ("skill_create", "создай навык", "➕ Создать"),
            ("skill_list", "список навыков", "📋 Список"),
            ("skill_settings", "настройки навыков", "⚙️ Настройки"),
        ],
    }

    COMMANDS_WITH_ARGS = {"/remember", "/recall", "/weather"}
    
    def __init__(
        self,
        config: TelegramConfig,
        bus: MessageBus,
        groq_api_key: str = "",
        session_manager: SessionManager | None = None,
    ):
        super().__init__(config, bus)
        self.config: TelegramConfig = config
        self.groq_api_key = groq_api_key
        self.session_manager = session_manager
        self._app: Application | None = None
        self._chat_ids: dict[str, int] = {}  # Map sender_id to chat_id for replies
        self._typing_tasks: dict[str, asyncio.Task] = {}  # chat_id -> typing loop task
        self._last_message_id: dict[str, int] = {}  # chat_id -> last sent message_id (for progress edits)
        self._pending_retry: dict[str, dict] = {}  # action_id -> {retry_content, chat_id, created_at}

    def _split_message(self, text: str, max_length: int = 4000) -> list[str]:
        """Split long text into Telegram-safe chunks on natural boundaries."""
        if len(text) <= max_length:
            return [text]

        parts: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_length:
                parts.append(remaining)
                break

            chunk = remaining[:max_length]
            split_at = chunk.rfind("\n") + 1
            if split_at == 0:
                split_at = chunk.rfind(" ") + 1
            if split_at == 0:
                split_at = max_length

            parts.append(remaining[:split_at])
            remaining = remaining[split_at:]

        return parts

    def _clean_response(self, text: str) -> str:
        """Remove internal tool-call XML tags from model output."""
        text = re.sub(r"<function_calls>.*?</function_calls>", "", text, flags=re.DOTALL)
        text = re.sub(r"<invoke.*?>.*?</invoke>", "", text, flags=re.DOTALL)
        text = re.sub(r"<parameter.*?>.*?</parameter>", "", text, flags=re.DOTALL)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
    
    async def start(self) -> None:
        """Start the Telegram bot with long polling."""
        if not self.config.token:
            logger.error("Telegram bot token not configured")
            return
        
        self._running = True
        
        # Build the application
        builder = Application.builder().token(self.config.token)
        if self.config.proxy:
            builder = builder.proxy(self.config.proxy).get_updates_proxy(self.config.proxy)
        self._app = builder.build()
        
        # Add command handlers
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("reset", self._on_reset))
        self._app.add_handler(CommandHandler("help", self._on_help))
        self._app.add_handler(CallbackQueryHandler(self._on_callback_query))
        
        # Add message handler for text, photos, voice, documents
        self._app.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO | filters.Document.ALL) 
                & ~filters.COMMAND, 
                self._on_message
            )
        )
        
        logger.info("Starting Telegram bot (polling mode)...")
        
        # Initialize and start polling
        await self._app.initialize()
        await self._app.start()
        
        # Get bot info and register command menu
        bot_info = await self._app.bot.get_me()
        logger.info(f"Telegram bot @{bot_info.username} connected")
        
        try:
            await self._app.bot.set_my_commands(self.BOT_COMMANDS)
            logger.debug("Telegram bot commands registered")
        except Exception as e:
            logger.warning(f"Failed to register bot commands: {e}")
        
        # Start polling (this runs until stopped)
        await self._app.updater.start_polling(
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True  # Ignore old messages on startup
        )
        
        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)
    
    async def stop(self) -> None:
        """Stop the Telegram bot."""
        self._running = False
        
        # Cancel all typing indicators
        for chat_id in list(self._typing_tasks):
            self._stop_typing(chat_id)
        
        if self._app:
            logger.info("Stopping Telegram bot...")
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
    
    async def send(self, msg: OutboundMessage) -> bool:
        """Send a message through Telegram."""
        if not self._app:
            logger.warning("Telegram bot not running")
            return False

        self._stop_typing(msg.chat_id)

        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error(f"Invalid chat_id: {msg.chat_id}")
            return False

        meta = msg.metadata or {}
        reply_markup = None
        if action_id := meta.get("confirmation_action_id"):
            reply_markup = self.create_confirmation_keyboard(action_id)
        elif suggested := meta.get("suggested_actions"):
            rows = []
            for item in (suggested[:4] if isinstance(suggested, list) else []):
                if isinstance(item, dict):
                    lbl, cb = item.get("label", ""), item.get("callback", "")
                else:
                    lbl, cb = (item[0], item[1]) if len(item) >= 2 else ("", "")
                if lbl and cb:
                    rows.append([InlineKeyboardButton(lbl, callback_data=cb)])
            if rows:
                reply_markup = InlineKeyboardMarkup(rows)
        elif error_action_id := meta.get("error_action_id"):
            reply_markup = self.create_retry_keyboard(error_action_id)
            retry_payload = meta.get("retry_payload", "")
            self._pending_retry[error_action_id] = {
                "retry_content": retry_payload,
                "chat_id": str(chat_id),
                "created_at": datetime.now().isoformat(),
            }

        cleaned_text = self._clean_response(msg.content)
        if meta.get("show_progress_bar") and "progress" in meta:
            pct = int(meta.get("progress", 0))
            pct = max(0, min(100, pct))
            filled = int(10 * pct / 100)
            bar = "█" * filled + "░" * (10 - filled)
            cleaned_text = f"{cleaned_text}\n\n{bar} {pct}%"

        edit_msg_id = meta.get("edit_message_id")
        if meta.get("edit_last_message") and not edit_msg_id:
            edit_msg_id = self._last_message_id.get(str(chat_id))

        if edit_msg_id:
            try:
                html_content = _markdown_to_telegram_html(cleaned_text)
                await self._app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(edit_msg_id),
                    text=html_content,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
            except Exception as e:
                logger.warning(f"Edit message failed, sending new: {e}")
                edit_msg_id = None

        if not edit_msg_id:
            parts = self._split_message(cleaned_text, self.MAX_MESSAGE_LENGTH)
            for i, part in enumerate(parts):
                is_last = i == len(parts) - 1
                kbd = reply_markup if (is_last and reply_markup) else None
                try:
                    html_content = _markdown_to_telegram_html(part)
                    sent = await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=html_content,
                        parse_mode="HTML",
                        reply_markup=kbd,
                    )
                    self._last_message_id[str(chat_id)] = sent.message_id
                except Exception as e:
                    logger.warning(f"HTML parse failed, falling back to plain text: {e}")
                    try:
                        sent = await self._app.bot.send_message(
                            chat_id=chat_id,
                            text=part,
                            reply_markup=kbd,
                        )
                        self._last_message_id[str(chat_id)] = sent.message_id
                    except Exception as e2:
                        logger.error(f"Error sending Telegram message: {e2}")
                        return False
                if i < len(parts) - 1:
                    await asyncio.sleep(0.5)

        return True
    
    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if not update.message or not update.effective_user:
            return

        user = update.effective_user
        self._set_menu_state(context, self.MENU_STATE_MAIN, reset_stack=True)

        ux_level = getattr(self.config, "ux_level", "advanced")
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm nanobot.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands.",
            reply_markup=self._build_main_keyboard(),
            parse_mode="HTML",
        )

        # Quick reply keyboard (persistent) for standard/advanced
        if ux_level != "minimal":
            quick_kbd = self._build_quick_reply_keyboard()
            if quick_kbd:
                await update.message.reply_text(
                    "Быстрые действия:",
                    reply_markup=quick_kbd,
                )

    def _set_menu_state(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        state: str,
        *,
        push_previous: bool = False,
        reset_stack: bool = False,
    ) -> None:
        """Persist user menu state in context.user_data."""
        if reset_stack:
            context.user_data[self.MENU_STACK_KEY] = []

        if push_previous:
            prev_state = context.user_data.get(self.MENU_STATE_KEY)
            if prev_state:
                stack = context.user_data.setdefault(self.MENU_STACK_KEY, [])
                stack.append(prev_state)

        context.user_data[self.MENU_STATE_KEY] = state

    def _pop_previous_menu_state(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Return previous state from stack or fallback to main."""
        stack = context.user_data.get(self.MENU_STACK_KEY, [])
        if stack:
            prev_state = stack.pop()
            context.user_data[self.MENU_STATE_KEY] = prev_state
            return prev_state
        context.user_data[self.MENU_STATE_KEY] = self.MENU_STATE_MAIN
        return self.MENU_STATE_MAIN

    def _build_main_keyboard(self) -> InlineKeyboardMarkup:
        """Build main inline menu."""
        ux_level = getattr(self.config, "ux_level", "advanced")
        rows = [
            [
                InlineKeyboardButton("🚀 Старт", callback_data=self.CMD_MENU_MAIN),
                InlineKeyboardButton("📋 Команды", callback_data=self.CMD_MENU_COMMANDS),
                InlineKeyboardButton("❓ Помощь", callback_data="help"),
            ]
        ]
        if ux_level != "minimal":
            rows.append([
                InlineKeyboardButton("📁 Файлы", callback_data=self.CMD_MENU_FILES),
                InlineKeyboardButton("🔧 Git", callback_data=self.CMD_MENU_GIT),
                InlineKeyboardButton("🤖 Навыки", callback_data=self.CMD_MENU_SKILLS),
            ])
        return InlineKeyboardMarkup(rows)

    def _build_commands_keyboard(self) -> InlineKeyboardMarkup:
        """Build top-level commands category menu."""
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔍 Рефлексия", callback_data=self.CMD_MENU_REFLECTION)],
                [InlineKeyboardButton("🧠 Память", callback_data=self.CMD_MENU_MEMORY)],
                [InlineKeyboardButton("🛠 Инструменты", callback_data=self.CMD_MENU_TOOLS)],
                [
                    InlineKeyboardButton("📁 Файлы", callback_data=self.CMD_MENU_FILES),
                    InlineKeyboardButton("🔧 Git", callback_data=self.CMD_MENU_GIT),
                    InlineKeyboardButton("🤖 Навыки", callback_data=self.CMD_MENU_SKILLS),
                ],
                [InlineKeyboardButton("⬅️ Назад", callback_data=self.CMD_BACK)],
            ]
        )

    def _build_category_keyboard(self, category_state: str) -> InlineKeyboardMarkup:
        """Build command list keyboard for a category."""
        command_rows = []
        for command_id, _, label in self.COMMANDS.get(category_state, []):
            command_rows.append(
                [InlineKeyboardButton(label, callback_data=f"{self.CMD_SELECT_PREFIX}{command_id}")]
            )
        command_rows.append([InlineKeyboardButton("⬅️ Назад", callback_data=self.CMD_BACK)])
        return InlineKeyboardMarkup(command_rows)

    def _build_confirm_keyboard(self, command: str) -> InlineKeyboardMarkup:
        """Build command confirmation keyboard."""
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("▶️ Выполнить", callback_data=f"{self.CMD_EXEC_PREFIX}{command}")],
                [
                    InlineKeyboardButton("⬅️ Назад", callback_data=self.CMD_BACK),
                    InlineKeyboardButton("❌ Отмена", callback_data=self.CMD_CANCEL),
                ],
            ]
        )

    def create_confirmation_keyboard(self, action_id: str, show_info: bool = True) -> InlineKeyboardMarkup:
        """Build inline confirmation keyboard: [✅ Да] [❌ Нет] [⏸️ Позже] [ℹ️ Подробнее]."""
        row1 = [
            InlineKeyboardButton("✅ Да", callback_data=f"{self.CONFIRM_PREFIX}yes:{action_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"{self.CONFIRM_PREFIX}no:{action_id}"),
            InlineKeyboardButton("⏸️ Позже", callback_data=f"{self.CONFIRM_PREFIX}later:{action_id}"),
        ]
        if show_info:
            row1.append(InlineKeyboardButton("ℹ️ Подробнее", callback_data=f"{self.CONFIRM_PREFIX}info:{action_id}"))
        return InlineKeyboardMarkup([row1])

    def create_retry_keyboard(self, action_id: str) -> InlineKeyboardMarkup:
        """Build error retry keyboard: [🔄 Повторить] [❌ Отмена]."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Повторить", callback_data=f"{self.ERR_PREFIX}retry:{action_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data=f"{self.ERR_PREFIX}cancel:{action_id}"),
            ]
        ])

    # Quick reply button label -> content to send to agent
    QUICK_REPLIES: list[tuple[str, str]] = [
        ("📁 Файлы", "покажи файлы в текущей директории"),
        ("🔧 Git", "git status"),
        ("🤖 Навыки", "список навыков"),
        ("📊 Статус", "статус проекта"),
        ("⚙️ Настройки", "помощь"),
    ]

    def _resolve_quick_reply(self, content: str) -> str:
        """If content matches a quick reply button, return mapped content; else return original."""
        for label, mapped in self.QUICK_REPLIES:
            if content.strip() == label:
                logger.info("telegram_quick_reply: label=%s -> content=%s", label, mapped)
                return mapped
        return content

    def _build_quick_reply_keyboard(self) -> ReplyKeyboardMarkup | None:
        """Build persistent quick reply keyboard. None if ux_level is minimal."""
        if getattr(self.config, "ux_level", "advanced") == "minimal":
            return None
        keyboard = [[KeyboardButton(label)] for label, _ in self.QUICK_REPLIES]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)

    def _build_command_hint(self, command: str) -> str:
        """Return hint for commands that require arguments."""
        if command.startswith("/remember"):
            return "Введите текст после команды: /remember [текст]"
        if command.startswith("/recall"):
            return "Введите запрос после команды: /recall [запрос]"
        if command.startswith("/weather"):
            return "Введите город после команды: /weather [город]"
        return ""

    def _resolve_command(self, command_id: str) -> str | None:
        """Resolve command id from button callback to executable command."""
        for commands in self.COMMANDS.values():
            for candidate_id, command, _ in commands:
                if candidate_id == command_id:
                    return command
        return None

    BREADCRUMB_LABELS: dict[str, str] = {
        "main": "Главная",
        "commands": "Команды",
        "commands_reflection": "Рефлексия",
        "commands_memory": "Память",
        "commands_tools": "Инструменты",
        "files": "Файлы",
        "git": "Git",
        "skills": "Навыки",
    }

    def _get_breadcrumb(self, context: ContextTypes.DEFAULT_TYPE) -> str:
        """Build breadcrumb string: Главная > Git > Status."""
        stack = context.user_data.get(self.MENU_STACK_KEY, [])
        current = context.user_data.get(self.MENU_STATE_KEY, self.MENU_STATE_MAIN)
        parts = stack + [current]
        labels = [self.BREADCRUMB_LABELS.get(p, p) for p in parts]
        return " > ".join(labels) if labels else "Главная"

    def _render_menu_screen(self, state: str, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
        """Build menu text and keyboard by FSM state."""
        ux_level = getattr(self.config, "ux_level", "advanced")
        breadcrumb = f"{self._get_breadcrumb(context)}\n\n" if ux_level == "advanced" else ""

        if state == self.MENU_STATE_MAIN:
            return (
                breadcrumb + "Главное меню:\nВыберите действие.",
                self._build_main_keyboard(),
            )
        if state == self.MENU_STATE_COMMANDS:
            return (
                breadcrumb + "📋 <b>Команды</b>\nВыберите категорию:",
                self._build_commands_keyboard(),
            )
        if state == self.MENU_STATE_REFLECTION:
            return (
                breadcrumb + "🔍 <b>Рефлексия</b>\nВыберите команду:",
                self._build_category_keyboard(self.MENU_STATE_REFLECTION),
            )
        if state == self.MENU_STATE_MEMORY:
            return (
                breadcrumb + "🧠 <b>Память</b>\nВыберите команду:",
                self._build_category_keyboard(self.MENU_STATE_MEMORY),
            )
        if state == self.MENU_STATE_TOOLS:
            return (
                breadcrumb + "🛠 <b>Инструменты</b>\nВыберите команду:",
                self._build_category_keyboard(self.MENU_STATE_TOOLS),
            )
        if state == self.MENU_STATE_FILES:
            return (
                breadcrumb + "📁 <b>Файлы</b>\nВыберите действие:",
                self._build_category_keyboard(self.MENU_STATE_FILES),
            )
        if state == self.MENU_STATE_GIT:
            return (
                breadcrumb + "🔧 <b>Git</b>\nВыберите действие:",
                self._build_category_keyboard(self.MENU_STATE_GIT),
            )
        if state == self.MENU_STATE_SKILLS:
            return (
                breadcrumb + "🤖 <b>Навыки</b>\nВыберите действие:",
                self._build_category_keyboard(self.MENU_STATE_SKILLS),
            )

        pending_command = context.user_data.get(self.MENU_PENDING_COMMAND_KEY)
        if pending_command:
            hint = self._build_command_hint(pending_command)
            text = f"Выбрана: {pending_command}"
            if hint:
                text += f"\n\n{hint}"
            return text, self._build_confirm_keyboard(pending_command)

        return "Главное меню:\nВыберите действие.", self._build_main_keyboard()

    async def _on_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline menu callbacks with FSM state tracking."""
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return

        await query.answer()
        context.user_data[self.MENU_MESSAGE_ID_KEY] = query.message.message_id if query.message else None
        callback_data = query.data
        user = update.effective_user
        chat_id = str(query.message.chat_id) if query.message else ""
        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"

        # --- Confirmation callbacks (cfm:yes|no|later|info:action_id) ---
        if callback_data.startswith(self.CONFIRM_PREFIX):
            parts = callback_data[len(self.CONFIRM_PREFIX):].split(":", 1)
            if len(parts) != 2:
                logger.warning("telegram_callback: invalid cfm format data=%s", callback_data)
                return
            action, action_id = parts[0], parts[1]
            logger.info(
                "telegram_callback: action=%s action_id=%s chat_id=%s user_id=%s",
                action, action_id, chat_id, user.id,
            )

            session_key = f"{self.name}:{chat_id}"
            session = self.session_manager.get_or_create(session_key) if self.session_manager else None
            if not session or not session.pending_confirmation:
                await query.edit_message_text(
                    "⏱ Истекло время подтверждения. Повторите запрос.",
                    reply_markup=None,
                )
                logger.warning("telegram_callback: no pending confirmation for action_id=%s", action_id)
                return

            pending = session.pending_confirmation
            if pending.get("action_id") != action_id:
                await query.edit_message_text(
                    "⏱ Истекло время подтверждения. Повторите запрос.",
                    reply_markup=None,
                )
                logger.warning("telegram_callback: action_id mismatch for session")
                return

            created_at = pending.get("created_at")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                    elapsed = (now - dt).total_seconds()
                    if elapsed > self.CONFIRM_TIMEOUT_SEC:
                        session.pending_confirmation = None
                        if self.session_manager:
                            self.session_manager.save(session)
                        await query.edit_message_text(
                            "⏱ Истекло время подтверждения (5 мин). Повторите запрос.",
                            reply_markup=None,
                        )
                        logger.warning("telegram_callback: confirmation timeout action_id=%s", action_id)
                        return
                except (ValueError, TypeError):
                    pass

            if action == "info":
                # Show full args, keep buttons
                tool_name = pending.get("tool_name", "")
                tool_args = pending.get("tool_args", {})
                args_str = json.dumps(tool_args, ensure_ascii=False, indent=2)
                detail_text = (
                    f"⚠️ <b>Подробности</b>\n\n"
                    f"Tool: <code>{tool_name}</code>\n\n"
                    f"<pre>{args_str[:3500]}</pre>"
                )
                await query.edit_message_text(
                    detail_text,
                    reply_markup=self.create_confirmation_keyboard(action_id),
                    parse_mode="HTML",
                )
                return

            # yes, no, later — remove buttons and forward to agent
            await query.edit_message_text(
                query.message.text if query.message else "Обрабатываю...",
                reply_markup=None,
                parse_mode="HTML",
            )

            self._chat_ids[sender_id] = int(chat_id)
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=action,
                metadata={
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "is_group": query.message.chat.type != "private" if query.message else False,
                    "from_callback": True,
                },
            )
            return

        # --- Error retry callbacks (err:retry:id, err:cancel:id) ---
        if callback_data.startswith(self.ERR_PREFIX):
            parts = callback_data[len(self.ERR_PREFIX):].split(":", 1)
            if len(parts) != 2:
                logger.warning("telegram_callback: invalid err format data=%s", callback_data)
                return
            action, action_id = parts[0], parts[1]
            logger.info(
                "telegram_callback: err action=%s action_id=%s chat_id=%s user_id=%s",
                action, action_id, chat_id, user.id,
            )

            await query.edit_message_text(
                "Обрабатываю..." if action == "retry" else "Отменено.",
                reply_markup=None,
                parse_mode="HTML",
            )

            pending = self._pending_retry.pop(action_id, None)
            if action == "retry" and pending:
                if str(query.message.chat_id) == pending.get("chat_id"):
                    retry_content = pending.get("retry_content", "")
                    created_at = pending.get("created_at", "")
                    if created_at:
                        try:
                            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                            now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
                            if (now - dt).total_seconds() > self.CONFIRM_TIMEOUT_SEC:
                                await query.edit_message_text("Истекло время. Повторите запрос.")
                                return
                        except (ValueError, TypeError):
                            pass
                    self._chat_ids[sender_id] = int(chat_id)
                    await self._handle_message(
                        sender_id=sender_id,
                        chat_id=chat_id,
                        content=retry_content,
                        metadata={
                            "user_id": user.id,
                            "username": user.username,
                            "first_name": user.first_name,
                            "is_group": query.message.chat.type != "private" if query.message else False,
                            "from_retry": True,
                        },
                    )
                else:
                    await query.edit_message_text("Истекло время или действие не найдено.")
            return

        if callback_data == self.CMD_MENU_MAIN:
            logger.info("telegram_callback: menu main user_id=%s chat_id=%s", user.id, chat_id)
            self._set_menu_state(context, self.MENU_STATE_MAIN, push_previous=True)
            text, markup = self._render_menu_screen(self.MENU_STATE_MAIN, context)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            return

        if callback_data == self.CMD_MENU_COMMANDS:
            self._set_menu_state(context, self.MENU_STATE_COMMANDS, push_previous=True)
            logger.info(
                f"heartbeat: user opened commands menu (user_id={user.id}, chat_id={query.message.chat_id if query.message else 'unknown'})"
            )
            text, markup = self._render_menu_screen(self.MENU_STATE_COMMANDS, context)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            return

        if callback_data in {
            self.CMD_MENU_REFLECTION,
            self.CMD_MENU_MEMORY,
            self.CMD_MENU_TOOLS,
            self.CMD_MENU_FILES,
            self.CMD_MENU_GIT,
            self.CMD_MENU_SKILLS,
        }:
            state_map = {
                self.CMD_MENU_REFLECTION: self.MENU_STATE_REFLECTION,
                self.CMD_MENU_MEMORY: self.MENU_STATE_MEMORY,
                self.CMD_MENU_TOOLS: self.MENU_STATE_TOOLS,
                self.CMD_MENU_FILES: self.MENU_STATE_FILES,
                self.CMD_MENU_GIT: self.MENU_STATE_GIT,
                self.CMD_MENU_SKILLS: self.MENU_STATE_SKILLS,
            }
            next_state = state_map[callback_data]
            self._set_menu_state(context, next_state, push_previous=True)
            text, markup = self._render_menu_screen(next_state, context)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            return

        if callback_data == self.CMD_BACK:
            logger.info("telegram_callback: menu back user_id=%s chat_id=%s", user.id, chat_id)
            prev_state = self._pop_previous_menu_state(context)
            text, markup = self._render_menu_screen(prev_state, context)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            return

        if callback_data == self.CMD_CANCEL:
            logger.info("telegram_callback: menu cancel user_id=%s chat_id=%s", user.id, chat_id)
            context.user_data.pop(self.MENU_PENDING_COMMAND_KEY, None)
            self._set_menu_state(context, self.MENU_STATE_MAIN, reset_stack=True)
            text, markup = self._render_menu_screen(self.MENU_STATE_MAIN, context)
            await query.edit_message_text("Действие отменено.", reply_markup=markup, parse_mode="HTML")
            return

        if callback_data == "help":
            self._set_menu_state(context, self.MENU_STATE_MAIN, push_previous=True)
            await query.edit_message_text(
                "🐈 <b>nanobot commands</b>\n\n"
                "/start — Start the bot\n"
                "/reset — Reset conversation history\n"
                "/help — Show this help message\n\n"
                "Нажмите «📋 Команды», чтобы открыть меню категорий.",
                parse_mode="HTML",
                reply_markup=self._build_main_keyboard(),
            )
            return

        if callback_data.startswith(self.CMD_SELECT_PREFIX):
            command_id = callback_data[len(self.CMD_SELECT_PREFIX):]
            command = self._resolve_command(command_id)
            if not command:
                await query.edit_message_text(
                    "Не удалось определить команду. Попробуйте снова.",
                    reply_markup=self._build_commands_keyboard(),
                )
                return

            context.user_data[self.MENU_PENDING_COMMAND_KEY] = command
            self._set_menu_state(context, self.MENU_STATE_CONFIRM, push_previous=True)
            text, markup = self._render_menu_screen(self.MENU_STATE_CONFIRM, context)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            return

        if callback_data.startswith(self.CMD_EXEC_PREFIX):
            selected_command = callback_data[len(self.CMD_EXEC_PREFIX):].strip()
            base_command = selected_command.split()[0] if selected_command else ""
            if not selected_command:
                await query.edit_message_text(
                    "Команда не выбрана. Вернитесь в меню.",
                    reply_markup=self._build_commands_keyboard(),
                )
                return

            if base_command in self.COMMANDS_WITH_ARGS and selected_command == base_command:
                hint = self._build_command_hint(base_command)
                self._set_menu_state(context, self.MENU_STATE_COMMANDS)
                await query.edit_message_text(
                    f"Выбрана: {base_command}\n{hint}",
                    reply_markup=self._build_commands_keyboard(),
                    parse_mode="HTML",
                )
                return

            logger.info(
                f"heartbeat: user executed {selected_command} (user_id={user.id}, chat_id={query.message.chat_id if query.message else 'unknown'})"
            )
            await query.edit_message_text(
                f"Выбрана: {selected_command}\n▶️ Выполняю команду...",
                reply_markup=self._build_main_keyboard(),
            )

            chat_id = str(query.message.chat_id) if query.message else str(update.effective_chat.id)
            sender_id = str(user.id)
            if user.username:
                sender_id = f"{sender_id}|{user.username}"

            self._chat_ids[sender_id] = int(chat_id)
            self._start_typing(chat_id)
            context.user_data.pop(self.MENU_PENDING_COMMAND_KEY, None)
            self._set_menu_state(context, self.MENU_STATE_MAIN, reset_stack=True)

            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=selected_command,
                metadata={
                    "user_id": user.id,
                    "username": user.username,
                    "first_name": user.first_name,
                    "is_group": query.message.chat.type != "private" if query.message else False,
                    "from_menu": True,
                },
            )
            return
    
    async def _on_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /reset command — clear conversation history."""
        if not update.message or not update.effective_user:
            return
        
        chat_id = str(update.message.chat_id)
        session_key = f"{self.name}:{chat_id}"
        
        if self.session_manager is None:
            logger.warning("/reset called but session_manager is not available")
            await update.message.reply_text("⚠️ Session management is not available.")
            return
        
        session = self.session_manager.get_or_create(session_key)
        msg_count = len(session.messages)
        session.clear()
        self.session_manager.save(session)
        
        logger.info(f"Session reset for {session_key} (cleared {msg_count} messages)")
        await update.message.reply_text("🔄 Conversation history cleared. Let's start fresh!")
    
    async def _on_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command — show available commands."""
        if not update.message:
            return
        
        help_text = (
            "🐈 <b>nanobot commands</b>\n\n"
            "/start — Start the bot\n"
            "/reset — Reset conversation history\n"
            "/help — Show this help message\n\n"
            "Just send me a text message to chat!"
        )
        await update.message.reply_text(help_text, parse_mode="HTML")
    
    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle incoming messages (text, photos, voice, documents)."""
        if not update.message or not update.effective_user:
            return
        
        message = update.message
        user = update.effective_user
        chat_id = message.chat_id
        
        # Use stable numeric ID, but keep username for allowlist compatibility
        sender_id = str(user.id)
        if user.username:
            sender_id = f"{sender_id}|{user.username}"
        
        # Store chat_id for replies
        self._chat_ids[sender_id] = chat_id
        
        # Build content from text and/or media
        content_parts = []
        media_paths = []
        
        # Text content
        if message.text:
            content_parts.append(message.text)
        if message.caption:
            content_parts.append(message.caption)
        
        # Handle media files
        media_file = None
        media_type = None
        
        if message.photo:
            media_file = message.photo[-1]  # Largest photo
            media_type = "image"
        elif message.voice:
            media_file = message.voice
            media_type = "voice"
        elif message.audio:
            media_file = message.audio
            media_type = "audio"
        elif message.document:
            media_file = message.document
            media_type = "file"
        
        # Download media if present
        if media_file and self._app:
            try:
                file = await self._app.bot.get_file(media_file.file_id)
                ext = self._get_extension(media_type, getattr(media_file, 'mime_type', None))
                
                # Save to workspace/media/
                from pathlib import Path
                media_dir = Path.home() / ".nanobot" / "media"
                media_dir.mkdir(parents=True, exist_ok=True)
                
                file_path = media_dir / f"{media_file.file_id[:16]}{ext}"
                await file.download_to_drive(str(file_path))
                
                media_paths.append(str(file_path))
                
                # Handle voice transcription
                if media_type == "voice" or media_type == "audio":
                    from nanobot.providers.transcription import GroqTranscriptionProvider
                    transcriber = GroqTranscriptionProvider(api_key=self.groq_api_key)
                    transcription = await transcriber.transcribe(file_path)
                    if transcription:
                        logger.info(f"Transcribed {media_type}: {transcription[:50]}...")
                        content_parts.append(f"[transcription: {transcription}]")
                    else:
                        content_parts.append(f"[{media_type}: {file_path}]")
                else:
                    content_parts.append(f"[{media_type}: {file_path}]")
                    
                logger.debug(f"Downloaded {media_type} to {file_path}")
            except Exception as e:
                logger.error(f"Failed to download media: {e}")
                content_parts.append(f"[{media_type}: download failed]")
        
        content = "\n".join(content_parts) if content_parts else "[empty message]"
        content = self._resolve_quick_reply(content)

        logger.debug(f"Telegram message from {sender_id}: {content[:50]}...")
        
        str_chat_id = str(chat_id)
        
        # Start typing indicator before processing
        self._start_typing(str_chat_id)
        
        # Forward to the message bus
        await self._handle_message(
            sender_id=sender_id,
            chat_id=str_chat_id,
            content=content,
            media=media_paths,
            metadata={
                "message_id": message.message_id,
                "user_id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "is_group": message.chat.type != "private"
            }
        )
    
    def _start_typing(self, chat_id: str) -> None:
        """Start sending 'typing...' indicator for a chat."""
        # Cancel any existing typing task for this chat
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(self._typing_loop(chat_id))
    
    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()
    
    async def _typing_loop(self, chat_id: str) -> None:
        """Repeatedly send 'typing' action until cancelled."""
        try:
            while self._app:
                await self._app.bot.send_chat_action(chat_id=int(chat_id), action="typing")
                await asyncio.sleep(4)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Typing indicator stopped for {chat_id}: {e}")
    
    def _get_extension(self, media_type: str, mime_type: str | None) -> str:
        """Get file extension based on media type."""
        if mime_type:
            ext_map = {
                "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
                "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
            }
            if mime_type in ext_map:
                return ext_map[mime_type]
        
        type_map = {"image": ".jpg", "voice": ".ogg", "audio": ".mp3", "file": ""}
        return type_map.get(media_type, "")
