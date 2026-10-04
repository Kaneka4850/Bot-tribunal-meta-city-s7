import os
import sys
import signal
import logging
import faulthandler
import traceback
import asyncio
import threading
import platform

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv

faulthandler.enable()

load_dotenv()

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
root_logger.addHandler(console_handler)

try:
    file_handler = logging.FileHandler("bot.log", encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    root_logger.addHandler(file_handler)
except Exception as e:
    logging.warning(f"Não foi possível criar arquivo de log: {e}")

logger = logging.getLogger("bot.main")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

class STMCBot(commands.Bot):
    async def setup_hook(self):
        await load_cogs()

        for guild_id_str in (os.getenv("GUILD_IDS", "")).split(","):
            guild_id_str = guild_id_str.strip()
            if guild_id_str.isdigit():
                guild_obj = discord.Object(id=int(guild_id_str))
                self.tree.clear_commands(guild=guild_obj)
                await self.tree.sync(guild=guild_obj)
                logger.info(f"🧹 Comandos removidos do servidor ID: {guild_id_str}")

        try:
            synced = await self.tree.sync()
            logger.info(f"✅ {len(synced)} slash commands sincronizados globalmente.")
        except Exception as e:
            logger.error(f"❌ Erro ao sincronizar comandos globalmente: {e}")

        if not self.monitor_recursos.is_running():
            self.monitor_recursos.start()
        logger.info("📊 Monitor de recursos iniciado (intervalo: 30s).")

        loop = asyncio.get_running_loop()
        loop.set_exception_handler(self._asyncio_exception_handler)

    async def on_ready(self):
        logger.info(f"🤖 Bot online como: {self.user}")
        logger.info(f"📊 Servidores conectados: {[g.name for g in self.guilds]}")
        logger.info(f"📊 Latência do Gateway: {self.latency * 1000:.1f}ms")

    async def close(self):
        logger.warning("⚠️ bot.close() foi chamado — o bot está sendo encerrado.")
        if self.monitor_recursos.is_running():
            self.monitor_recursos.cancel()
        await super().close()

    @staticmethod
    def _asyncio_exception_handler(loop, context):
        exception = context.get("exception")
        message = context.get("message", "Nenhuma mensagem")
        logger.error("🚨 EXCEÇÃO NÃO TRATADA NO ASYNCIO")
        logger.error(f"   Mensagem: {message}")
        if exception:
            logger.error(f"   Exceção: {type(exception).__name__}: {exception}")

    @tasks.loop(seconds=30)
    async def monitor_recursos(self):
        try:
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
        except ImportError:
            mem_mb = -1
            
        try:
            num_tasks = len(asyncio.all_tasks())
        except RuntimeError:
            num_tasks = -1

        num_threads = threading.active_count()
        latency_ms = self.latency * 1000

        logger.info(
            f"📊 MONITOR | "
            f"Memória: {mem_mb:.1f}MB | "
            f"Tasks asyncio: {num_tasks} | "
            f"Threads: {num_threads} | "
            f"Latência Gateway: {latency_ms:.1f}ms | "
            f"Guilds: {len(self.guilds)} | "
            f"PID: {os.getpid()} | "
            f"OS: {platform.system()}"
        )

        if mem_mb > 250:
            logger.warning(f"⚠️ ALERTA DE MEMÓRIA: {mem_mb:.1f}MB")

    @monitor_recursos.before_loop
    async def before_monitor(self):
        await self.wait_until_ready()

bot = STMCBot(command_prefix="!", intents=intents)

COGS = [
    "cogs.setup_tickets",
    "cogs.setup_registro",
    "cogs.anti_spam",
    "cogs.setup_advertencia",
    "cogs.setup_demissao"
]

@bot.tree.command(name="comandos", description="Lista todos os comandos disponíveis")
async def comandos(interaction: discord.Interaction):
    embed = discord.Embed()
    embed.title = "📝 Lista de Comandos Disponíveis"
    embed.description = "Esses são os comandos do bot do STMC. Eles funcionam usando `/` (slash commands)."
    embed.color = discord.Color.blue()
    embed.add_field(name="/setup_tickets",           value="(Apenas Administradores) Cria o painel de tickets.", inline=False)
    embed.add_field(name="/setup_registro",          value="(Apenas Administradores) Cria o painel de registro de Advogados e Seguranças.", inline=False)
    embed.add_field(name="/setup_advertencia",       value="(Apenas Administradores) Cria o painel de advertências.", inline=False)
    embed.add_field(name="/setup_demissao",          value="(Apenas Administradores) Cria o painel de exoneração e blacklist.", inline=False)
    embed.add_field(name="/comandos",                value="Lista todos os comandos disponíveis.", inline=False)
    embed.set_footer(text="Supremo Tribunal de Meta City (STMC)")
    
    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        
    await interaction.response.send_message(embed=embed)

async def load_cogs():
    for cog in COGS:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {cog}: {e}", exc_info=True)

def _handle_signal(signum, frame):
    sig_name = signal.Signals(signum).name
    logger.critical(f"🚨 SINAL RECEBIDO: {sig_name} (signum={signum})")
    for handler in logging.root.handlers:
        handler.flush()
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)

if __name__ == "__main__":
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, _handle_signal)

    def global_exception_handler(exc_type, exc_value, exc_tb):
        logger.critical("🚨 EXCEÇÃO GLOBAL NÃO TRATADA:")
        logger.critical("".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        for handler in logging.root.handlers:
            handler.flush()
    sys.excepthook = global_exception_handler

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise ValueError("Token não encontrado no .env")

    from database.connection import init_db
    init_db()

    bot.run(token, log_handler=None)
