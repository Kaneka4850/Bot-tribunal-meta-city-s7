import hashlib
import logging
import asyncio
import unicodedata
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import discord
from discord.ext import commands, tasks

import utils.ui as ui

logger = logging.getLogger("bot.anti_spam")

SPAM_MESSAGE_THRESHOLD = 5
SPAM_TIME_WINDOW = 60
MASS_MENTION_THRESHOLD = 3
DELETE_LOOKBACK_MINUTES = 5
CLEANUP_INTERVAL_SECONDS = 120

TIMEOUT_ESCALONAMENTO = [1, 5, 10, 60, 1440, 10080]
REINCIDENCIA_JANELA_DIAS = 7

def _normalizar_conteudo(texto: str) -> str:
    if not texto: return ""
    return unicodedata.normalize("NFKC", texto).strip().lower()

async def _calcular_hash_anexos(message: discord.Message) -> list[str]:
    hashes = []
    for attachment in message.attachments:
        try:
            anexo_bytes = await attachment.read()
            md5_hash = hashlib.md5(anexo_bytes).hexdigest()
            hashes.append(md5_hash)
        except Exception as e:
            logger.error(f"Erro ao ler anexo {attachment.filename}: {e}")
    return hashes

class AntiSpam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._user_messages = defaultdict(lambda: deque())
        self._user_attachments = defaultdict(lambda: deque())
        self._limpar_dados_antigos.start()

    def cog_unload(self):
        self._limpar_dados_antigos.cancel()

    @tasks.loop(seconds=CLEANUP_INTERVAL_SECONDS)
    async def _limpar_dados_antigos(self):
        agora = datetime.now(timezone.utc)
        limite = agora - timedelta(seconds=SPAM_TIME_WINDOW)
        
        for estruturas in (self._user_messages, self._user_attachments):
            usuarios_para_remover = []
            for user_id, timestamps in estruturas.items():
                while timestamps and timestamps[0][0] < limite:
                    timestamps.popleft()
                if not timestamps:
                    usuarios_para_remover.append(user_id)
            
            for user_id in usuarios_para_remover:
                del estruturas[user_id]

    @_limpar_dados_antigos.before_loop
    async def _before_limpar(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        agora = datetime.now(timezone.utc)
        user_id = message.author.id

        if len(message.mentions) >= MASS_MENTION_THRESHOLD:
            await self._punir_spammer(message, f"Mass Mention ({len(message.mentions)} usuários)")
            return

        texto_norm = _normalizar_conteudo(message.content)
        if texto_norm:
            self._user_messages[user_id].append((agora, texto_norm))
            repeticoes = sum(1 for ts, txt in self._user_messages[user_id] if txt == texto_norm and ts >= agora - timedelta(seconds=SPAM_TIME_WINDOW))
            if repeticoes >= SPAM_MESSAGE_THRESHOLD:
                await self._punir_spammer(message, f"Texto repetido ({repeticoes}x)")
                self._user_messages[user_id].clear()
                return

        if message.attachments:
            hashes = await _calcular_hash_anexos(message)
            for md5_hash in hashes:
                self._user_attachments[user_id].append((agora, md5_hash))
                repeticoes = sum(1 for ts, h in self._user_attachments[user_id] if h == md5_hash and ts >= agora - timedelta(seconds=SPAM_TIME_WINDOW))
                if repeticoes >= SPAM_MESSAGE_THRESHOLD:
                    await self._punir_spammer(message, f"Anexo repetido ({repeticoes}x)")
                    self._user_attachments[user_id].clear()
                    return

    async def _punir_spammer(self, message: discord.Message, tipo_spam: str):
        # NENHUMA EXCEÇÃO DE PERMISSÃO APLICADA CONFORME SOLICITADO
        membro = message.author
        guild = message.guild
        
        # Simples deleção de mensagens retroativas
        mensagens_apagadas = 0
        try:
            limite = datetime.now(timezone.utc) - timedelta(minutes=DELETE_LOOKBACK_MINUTES)
            for canal in guild.text_channels:
                perms = canal.permissions_for(guild.me)
                if perms.read_message_history and perms.manage_messages:
                    msgs_para_apagar = []
                    async for msg in canal.history(after=limite, limit=100):
                        if msg.author.id == membro.id:
                            msgs_para_apagar.append(msg)
                    if msgs_para_apagar:
                        await canal.delete_messages(msgs_para_apagar)
                        mensagens_apagadas += len(msgs_para_apagar)
        except Exception as e:
            logger.error(f"Erro apagando mensagens: {e}")

        # Aplicar timeout (exemplo fixo de 10 min por simplificação)
        try:
            await membro.timeout(timedelta(minutes=10), reason=f"AntiSpam: {tipo_spam}")
        except discord.Forbidden:
            logger.warning(f"Sem permissão para aplicar timeout em {membro}")

        logger.warning(f"Spammer punido: {membro} - {tipo_spam}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiSpam(bot))
