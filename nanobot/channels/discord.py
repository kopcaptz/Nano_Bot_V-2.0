"""Discord channel implementation using discord.py with slash commands and rich UI."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.config.schema import DiscordConfig

if TYPE_CHECKING:
    pass

try:
    import discord
    from discord import app_commands

    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None
    app_commands = None

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # 20MB
EMBED_DESC_MAX = 4096
EMBED_TITLE_MAX = 256
CONFIRM_PREFIX = "cfm:"
ERR_PREFIX = "err:"
CONFIRM_TIMEOUT_SEC = 300  # 5 minutes
PENDING_INTERACTION_TIMEOUT = 15 * 60  # 15 min for deferred followup


def _clean_response(text: str) -> str:
    """Remove internal tool-call XML tags from model output."""
    text = re.sub(r"<function_calls>.*?</function_calls>", "", text, flags=re.DOTALL)
    text = re.sub(r"<invoke.*?>.*?</invoke>", "", text, flags=re.DOTALL)
    text = re.sub(r"<parameter.*?>.*?</parameter>", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate(text: str, max_len: int, suffix: str = "...") -> str:
    """Truncate text to max length."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


class NanobotDiscordClient(discord.Client if DISCORD_AVAILABLE else object):  # type: ignore[misc]
    """Discord client with slash commands, holds reference to DiscordChannel."""

    def __init__(self, channel: "DiscordChannel", intents: Any):
        if DISCORD_AVAILABLE:
            super().__init__(intents=intents)
            self.tree = app_commands.CommandTree(self)
        else:
            super().__init__()
            self.tree = None
        self._channel = channel

    async def setup_hook(self) -> None:
        """Sync commands globally (can take up to 1h) or per-guild for instant sync."""
        try:
            guild_id = getattr(self._channel.config, "guild_id", None)
            if guild_id:
                guild_obj = discord.Object(id=int(guild_id))
                self.tree.copy_global_to(guild=guild_obj)
                await self.tree.sync(guild=guild_obj)
                logger.info(f"Discord slash commands synced to guild {guild_id} (instant)")
            else:
                await self.tree.sync()
                logger.info("Discord slash commands synced globally (may take up to 1h to propagate)")
        except Exception as e:
            logger.warning(f"Discord command sync failed: {e}")

    async def on_ready(self) -> None:
        """Log when bot is ready."""
        if self.user:
            logger.info(f"Discord bot logged in as {self.user} ({self.user.id})")


class DiscordChannel(BaseChannel):
    """Discord channel using discord.py with slash commands, embeds, and buttons."""

    name = "discord"

    def __init__(self, config: DiscordConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: DiscordConfig = config
        self._bot: NanobotDiscordClient | None = None
        self._bot_task: asyncio.Task | None = None
        self._typing_tasks: dict[str, asyncio.Task] = {}
        self._pending_interactions: dict[str, tuple[Any, float]] = {}
        self._pending_retry: dict[str, dict[str, Any]] = {}
        self._last_message_id: dict[str, int] = {}

    def _setup_bot(self) -> None:
        """Create client and register events and slash commands."""
        if not DISCORD_AVAILABLE:
            raise ImportError("discord.py is not installed. Run: pip install discord.py>=2.3.0")

        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        intents.guilds = True

        self._bot = NanobotDiscordClient(self, intents)
        tree = self._bot.tree

        @tree.command(name="ask", description="Ask the agent a question")
        @app_commands.describe(query="Your question for the agent")
        async def ask_cmd(interaction: discord.Interaction, query: str) -> None:
            await self._handle_slash_command(interaction, query, "ask")

        @tree.command(name="run", description="Run a command")
        @app_commands.describe(command="Command to execute (e.g. git status)")
        async def run_cmd(interaction: discord.Interaction, command: str) -> None:
            await self._handle_slash_command(interaction, command, "run")

        @tree.command(name="files", description="File management menu")
        async def files_cmd(interaction: discord.Interaction) -> None:
            await self._handle_slash_menu(interaction, "files", "📁 Файлы")

        @tree.command(name="git", description="Git operations menu")
        async def git_cmd(interaction: discord.Interaction) -> None:
            await self._handle_slash_menu(interaction, "git", "🔧 Git")

        @tree.command(name="skills", description="Skills management menu")
        async def skills_cmd(interaction: discord.Interaction) -> None:
            await self._handle_slash_menu(interaction, "skills", "🤖 Навыки")

        @self._bot.event
        async def on_message(message: discord.Message) -> None:
            if message.author.bot:
                return
            await self._handle_discord_message(message)

        @self._bot.event
        async def on_interaction(interaction: discord.Interaction) -> None:
            if interaction.type != discord.InteractionType.component:
                return
            if not interaction.data or "custom_id" not in interaction.data:
                return
            custom_id = interaction.data["custom_id"]
            await self._handle_button_callback(interaction, custom_id)

    async def _handle_slash_command(
        self,
        interaction: discord.Interaction,
        content: str,
        cmd_type: str,
    ) -> None:
        """Handle /ask and /run slash commands."""
        sender_id = str(interaction.user.id)
        if interaction.user.username:
            sender_id = f"{sender_id}|{interaction.user.username}"

        if not self.is_allowed(sender_id):
            await interaction.response.send_message(
                "Access denied. Add your ID to the allow list.",
                ephemeral=True,
            )
            return

        channel_id = str(interaction.channel_id) if interaction.channel_id else ""
        if not channel_id:
            await interaction.response.send_message("Could not determine channel.", ephemeral=True)
            return

        request_id = str(uuid.uuid4())
        await interaction.response.defer()

        self._pending_interactions[request_id] = (interaction, asyncio.get_event_loop().time())

        await self._handle_message(
            sender_id=sender_id,
            chat_id=channel_id,
            content=content,
            media=[],
            metadata={
                "message_id": "",
                "guild_id": str(interaction.guild_id) if interaction.guild_id else None,
                "reply_to": None,
                "request_id": request_id,
                "interaction_user_id": interaction.user.id,
                "from_slash": True,
                "slash_command": cmd_type,
            },
        )

    async def _handle_slash_menu(
        self,
        interaction: discord.Interaction,
        menu_type: str,
        title: str,
    ) -> None:
        """Handle /files, /git, /skills - show menu with buttons."""
        sender_id = str(interaction.user.id)
        if not self.is_allowed(sender_id):
            await interaction.response.send_message("Access denied.", ephemeral=True)
            return

        channel_id = str(interaction.channel_id) if interaction.channel_id else ""
        if not channel_id:
            await interaction.response.send_message("Could not determine channel.", ephemeral=True)
            return

        actions = self._get_menu_actions(menu_type)
        if not actions:
            await interaction.response.send_message(f"No actions for {menu_type}", ephemeral=True)
            return

        view = discord.ui.View(timeout=120)
        for label, content, action_id in actions:

            def make_callback(c: str, ch_id: str, sid: str):
                async def callback(btn_interaction: discord.Interaction) -> None:
                    await self._handle_menu_button(btn_interaction, c, ch_id, sid, menu_type)
                return callback

            btn = discord.ui.Button(
                label=label[:80],
                style=discord.ButtonStyle.primary,
                custom_id=f"menu:{menu_type}:{action_id}",
            )
            btn.callback = make_callback(content, channel_id, sender_id)
            view.add_item(btn)

        embed = discord.Embed(title=title, description="Choose an action:", color=0x5865F2)
        await interaction.response.send_message(embed=embed, view=view)

    async def _handle_menu_button(
        self,
        interaction: discord.Interaction,
        content: str,
        channel_id: str,
        sender_id: str,
        menu_type: str,
    ) -> None:
        """Handle menu button click - defer and forward to agent."""
        await interaction.response.defer()
        request_id = str(uuid.uuid4())
        self._pending_interactions[request_id] = (interaction, asyncio.get_event_loop().time())
        await self._handle_message(
            sender_id=sender_id,
            chat_id=channel_id,
            content=content,
            media=[],
            metadata={
                "request_id": request_id,
                "from_slash": True,
                "from_menu": menu_type,
            },
        )

    def _get_menu_actions(self, menu_type: str) -> list[tuple[str, str, str]]:
        """Return (label, content, action_id) for menu buttons."""
        if menu_type == "files":
            return [
                ("📋 List", "покажи файлы в текущей директории", "list"),
                ("👁 Read", "прочитай файл", "read"),
                ("✏️ Edit", "отредактируй файл", "edit"),
                ("📤 Send", "отправь файл", "send"),
                ("🗑 Delete", "удали файл", "delete"),
            ]
        if menu_type == "git":
            return [
                ("📊 Status", "git status", "status"),
                ("📝 Commit", "git commit", "commit"),
                ("🌿 Branch", "git branch", "branch"),
                ("⬆️ Push", "git push", "push"),
                ("🔀 PR", "создай pull request", "pr"),
            ]
        if menu_type == "skills":
            return [
                ("🎯 Search", "найди навыки", "search"),
                ("➕ Create", "создай навык", "create"),
                ("📋 List", "список навыков", "list"),
                ("⚙️ Settings", "настройки навыков", "settings"),
            ]
        return []

    async def _handle_button_callback(self, interaction: discord.Interaction, custom_id: str) -> None:
        """Handle button clicks: confirmation, retry, menu."""
        if custom_id.startswith(CONFIRM_PREFIX):
            parts = custom_id[len(CONFIRM_PREFIX) :].split(":", 1)
            if len(parts) != 2:
                await interaction.response.send_message("Invalid callback.", ephemeral=True)
                return
            action, action_id = parts[0], parts[1]
            await interaction.response.defer()
            chat_id = str(interaction.channel_id) if interaction.channel_id else ""
            sender_id = str(interaction.user.id)
            if interaction.user.username:
                sender_id = f"{sender_id}|{interaction.user.username}"
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=action,
                media=[],
                metadata={
                    "from_callback": True,
                    "confirmation_action_id": action_id,
                },
            )
            return

        if custom_id.startswith(ERR_PREFIX):
            parts = custom_id[len(ERR_PREFIX) :].split(":", 1)
            if len(parts) != 2:
                await interaction.response.send_message("Invalid callback.", ephemeral=True)
                return
            action, action_id = parts[0], parts[1]
            await interaction.response.defer()
            pending = self._pending_retry.pop(action_id, None)
            if action == "retry" and pending:
                chat_id = pending.get("chat_id", "")
                sender_id = str(interaction.user.id)
                if interaction.user.username:
                    sender_id = f"{sender_id}|{interaction.user.username}"
                retry_content = pending.get("retry_content", "")
                await self._handle_message(
                    sender_id=sender_id,
                    chat_id=chat_id,
                    content=retry_content,
                    media=[],
                    metadata={"from_retry": True},
                )
            elif action == "cancel":
                await interaction.followup.send("Cancelled.", ephemeral=True)
            return

        if custom_id.startswith("menu:"):
            return

        # Suggested action or other callback - forward to agent
        chat_id = str(interaction.channel_id) if interaction.channel_id else ""
        sender_id = str(interaction.user.id)
        if interaction.user.username:
            sender_id = f"{sender_id}|{interaction.user.username}"
        await interaction.response.defer()
        request_id = str(uuid.uuid4())
        self._pending_interactions[request_id] = (interaction, asyncio.get_event_loop().time())
        await self._handle_message(
            sender_id=sender_id,
            chat_id=chat_id,
            content=custom_id,
            media=[],
            metadata={"request_id": request_id, "from_callback": True},
        )

    async def _handle_discord_message(self, message: discord.Message) -> None:
        """Handle regular Discord messages."""
        sender_id = str(message.author.id)
        if message.author.username:
            sender_id = f"{sender_id}|{message.author.username}"

        if not self.is_allowed(sender_id):
            return

        channel_id = str(message.channel.id)
        content = message.content or ""

        content_parts = [content] if content else []
        media_paths: list[str] = []
        media_dir = Path.home() / ".nanobot" / "media"

        for attachment in message.attachments:
            if attachment.size and attachment.size > MAX_ATTACHMENT_BYTES:
                content_parts.append(f"[attachment: {attachment.filename} - too large]")
                continue
            try:
                media_dir.mkdir(parents=True, exist_ok=True)
                file_path = media_dir / f"{attachment.id}_{attachment.filename.replace('/', '_')}"
                await attachment.save(file_path)
                media_paths.append(str(file_path))
                content_parts.append(f"[attachment: {file_path}]")
            except Exception as e:
                logger.warning(f"Failed to download Discord attachment: {e}")
                content_parts.append(f"[attachment: {attachment.filename} - download failed]")

        reply_to = None
        if message.reference and message.reference.message_id:
            reply_to = str(message.reference.message_id)

        await self._start_typing(channel_id)

        await self._handle_message(
            sender_id=sender_id,
            chat_id=channel_id,
            content="\n".join(p for p in content_parts if p) or "[empty message]",
            media=media_paths,
            metadata={
                "message_id": str(message.id),
                "guild_id": str(message.guild.id) if message.guild else None,
                "reply_to": reply_to,
            },
        )

    async def start(self) -> None:
        """Start the Discord bot."""
        if not self.config.token:
            logger.error("Discord bot token not configured")
            return

        if not DISCORD_AVAILABLE:
            logger.error("discord.py not installed. Run: pip install discord.py>=2.3.0")
            return

        self._running = True
        self._setup_bot()

        try:
            await self._bot.start(self.config.token)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Discord bot error: {e}")
        finally:
            await self._cleanup()

    async def stop(self) -> None:
        """Stop the Discord channel."""
        self._running = False
        if self._bot:
            await self._bot.close()
        await self._cleanup()

    async def _cleanup(self) -> None:
        """Clean up resources."""
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()
        self._pending_interactions.clear()
        self._pending_retry.clear()
        self._bot = None

    async def send(self, msg: OutboundMessage) -> None:
        """Send a message through Discord (embed, buttons, or followup for slash)."""
        if not self._bot:
            logger.warning("Discord bot not initialized")
            return

        await self._stop_typing(msg.chat_id)

        meta = msg.metadata or {}
        request_id = meta.get("request_id")
        interaction = None
        if request_id:
            pending = self._pending_interactions.pop(request_id, None)
            if pending:
                interaction = pending[0]

        embed = self._build_embed(msg)
        view = self._build_view(msg)

        if meta.get("error_action_id"):
            self._pending_retry[meta["error_action_id"]] = {
                "retry_content": meta.get("retry_payload", msg.content),
                "chat_id": msg.chat_id,
                "created_at": datetime.now().isoformat(),
            }

        try:
            if interaction is not None:
                kwargs: dict[str, Any] = {"embed": embed}
                if view:
                    kwargs["view"] = view
                await interaction.followup.send(**kwargs)
            else:
                channel = self._bot.get_channel(int(msg.chat_id))
                if channel and hasattr(channel, "send"):
                    kwargs = {"embed": embed}
                    if view:
                        kwargs["view"] = view
                    sent = await channel.send(**kwargs)
                    self._last_message_id[msg.chat_id] = sent.id
                else:
                    logger.warning(f"Could not find Discord channel {msg.chat_id}")
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, "retry_after", 1.0)
                logger.warning(f"Discord rate limited, retrying in {retry_after}s")
                await asyncio.sleep(retry_after)
                await self.send(msg)
            else:
                logger.error(f"Discord send error: {e}")
        except Exception as e:
            logger.error(f"Error sending Discord message: {e}")

    def _build_embed(self, msg: OutboundMessage) -> discord.Embed:
        """Build a Discord embed from OutboundMessage."""
        cleaned = _clean_response(msg.content)
        meta = msg.metadata or {}

        if meta.get("show_progress_bar") and "progress" in meta:
            pct = int(meta.get("progress", 0))
            pct = max(0, min(100, pct))
            filled = int(10 * pct / 100)
            bar = "█" * filled + "░" * (10 - filled)
            cleaned = f"{cleaned}\n\n{bar} {pct}%"

        if len(cleaned) > EMBED_DESC_MAX:
            cleaned = _truncate(cleaned, EMBED_DESC_MAX)

        embed = discord.Embed(
            title="nanobot",
            description=cleaned or "(no content)",
            color=0x5865F2,
        )
        return embed

    def _build_view(self, msg: OutboundMessage) -> discord.ui.View | None:
        """Build Discord view with buttons from metadata."""
        meta = msg.metadata or {}
        view = discord.ui.View(timeout=CONFIRM_TIMEOUT_SEC)

        if action_id := meta.get("confirmation_action_id"):
            view.add_item(
                discord.ui.Button(
                    label="✅ Yes",
                    style=discord.ButtonStyle.success,
                    custom_id=f"{CONFIRM_PREFIX}yes:{action_id}",
                )
            )
            view.add_item(
                discord.ui.Button(
                    label="❌ No",
                    style=discord.ButtonStyle.danger,
                    custom_id=f"{CONFIRM_PREFIX}no:{action_id}",
                )
            )
            view.add_item(
                discord.ui.Button(
                    label="⏸ Later",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"{CONFIRM_PREFIX}later:{action_id}",
                )
            )
        elif action_id := meta.get("error_action_id"):
            view.add_item(
                discord.ui.Button(
                    label="🔄 Retry",
                    style=discord.ButtonStyle.primary,
                    custom_id=f"{ERR_PREFIX}retry:{action_id}",
                )
            )
            view.add_item(
                discord.ui.Button(
                    label="❌ Cancel",
                    style=discord.ButtonStyle.danger,
                    custom_id=f"{ERR_PREFIX}cancel:{action_id}",
                )
            )
        elif suggested := meta.get("suggested_actions"):
            for item in (suggested[:5] if isinstance(suggested, list) else []):
                if isinstance(item, dict):
                    lbl, cb = item.get("label", ""), item.get("callback", "")
                else:
                    lbl, cb = (item[0], item[1]) if len(item) >= 2 else ("", "")
                if lbl and cb:
                    view.add_item(
                        discord.ui.Button(
                            label=lbl[:80],
                            style=discord.ButtonStyle.secondary,
                            custom_id=cb[:100],
                        )
                    )
        else:
            return None

        return view if view.children else None

    async def _start_typing(self, channel_id: str) -> None:
        """Start typing indicator."""
        await self._stop_typing(channel_id)
        if not self._bot:
            return

        async def typing_loop() -> None:
            channel = self._bot.get_channel(int(channel_id)) if self._bot else None
            while self._running and channel and hasattr(channel, "typing"):
                try:
                    async with channel.typing():
                        await asyncio.sleep(5)
                except Exception:
                    pass

        self._typing_tasks[channel_id] = asyncio.create_task(typing_loop())

    async def _stop_typing(self, channel_id: str) -> None:
        """Stop typing indicator."""
        task = self._typing_tasks.pop(channel_id, None)
        if task:
            task.cancel()
