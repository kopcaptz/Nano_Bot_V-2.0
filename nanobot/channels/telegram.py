"""Telegram channel implementation using python-telegram-bot."""

from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from loguru import logger
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
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
    MENU_STATE_CONFIRM = "command_confirm"

    CMD_MENU_MAIN = "cmd_menu_main"
    CMD_MENU_COMMANDS = "cmd_menu_commands"
    CMD_MENU_REFLECTION = "cmd_menu_reflection"
    CMD_MENU_MEMORY = "cmd_menu_memory"
    CMD_MENU_TOOLS = "cmd_menu_tools"
    CMD_SELECT_PREFIX = "cmd_select:"
    CMD_EXEC_PREFIX = "cmd_exec:"
    CMD_BACK = "cmd_back"
    CMD_CANCEL = "cmd_cancel"

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
        
        # Stop typing indicator for this chat
        self._stop_typing(msg.chat_id)
        
        try:
            chat_id = int(msg.chat_id)
        except ValueError:
            logger.error(f"Invalid chat_id: {msg.chat_id}")
            return False

        cleaned_text = self._clean_response(msg.content)
        parts = self._split_message(cleaned_text, self.MAX_MESSAGE_LENGTH)

        for i, part in enumerate(parts):
            try:
                html_content = _markdown_to_telegram_html(part)
                await self._app.bot.send_message(
                    chat_id=chat_id,
                    text=html_content,
                    parse_mode="HTML",
                )
            except Exception as e:
                # Fallback to plain text if HTML parsing fails
                logger.warning(f"HTML parse failed, falling back to plain text: {e}")
                try:
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=part,
                    )
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
        await update.message.reply_text(
            f"👋 Hi {user.first_name}! I'm nanobot.\n\n"
            "Send me a message and I'll respond!\n"
            "Type /help to see available commands.",
            reply_markup=self._build_main_keyboard(),
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
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🚀 Старт", callback_data=self.CMD_MENU_MAIN),
                    InlineKeyboardButton("📋 Команды", callback_data=self.CMD_MENU_COMMANDS),
                    InlineKeyboardButton("❓ Помощь", callback_data="help"),
                ]
            ]
        )

    def _build_commands_keyboard(self) -> InlineKeyboardMarkup:
        """Build top-level commands category menu."""
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔍 Рефлексия", callback_data=self.CMD_MENU_REFLECTION)],
                [InlineKeyboardButton("🧠 Память", callback_data=self.CMD_MENU_MEMORY)],
                [InlineKeyboardButton("🛠 Инструменты", callback_data=self.CMD_MENU_TOOLS)],
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

    def _render_menu_screen(self, state: str, context: ContextTypes.DEFAULT_TYPE) -> tuple[str, InlineKeyboardMarkup]:
        """Build menu text and keyboard by FSM state."""
        if state == self.MENU_STATE_MAIN:
            return (
                "Главное меню:\nВыберите действие.",
                self._build_main_keyboard(),
            )
        if state == self.MENU_STATE_COMMANDS:
            return (
                "📋 <b>Команды</b>\nВыберите категорию:",
                self._build_commands_keyboard(),
            )
        if state == self.MENU_STATE_REFLECTION:
            return (
                "🔍 <b>Рефлексия</b>\nВыберите команду:",
                self._build_category_keyboard(self.MENU_STATE_REFLECTION),
            )
        if state == self.MENU_STATE_MEMORY:
            return (
                "🧠 <b>Память</b>\nВыберите команду:",
                self._build_category_keyboard(self.MENU_STATE_MEMORY),
            )
        if state == self.MENU_STATE_TOOLS:
            return (
                "🛠 <b>Инструменты</b>\nВыберите команду:",
                self._build_category_keyboard(self.MENU_STATE_TOOLS),
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

        if callback_data == self.CMD_MENU_MAIN:
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

        if callback_data in {self.CMD_MENU_REFLECTION, self.CMD_MENU_MEMORY, self.CMD_MENU_TOOLS}:
            state_map = {
                self.CMD_MENU_REFLECTION: self.MENU_STATE_REFLECTION,
                self.CMD_MENU_MEMORY: self.MENU_STATE_MEMORY,
                self.CMD_MENU_TOOLS: self.MENU_STATE_TOOLS,
            }
            next_state = state_map[callback_data]
            self._set_menu_state(context, next_state, push_previous=True)
            text, markup = self._render_menu_screen(next_state, context)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            return

        if callback_data == self.CMD_BACK:
            prev_state = self._pop_previous_menu_state(context)
            text, markup = self._render_menu_screen(prev_state, context)
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
            return

        if callback_data == self.CMD_CANCEL:
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
