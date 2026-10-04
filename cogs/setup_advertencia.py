"""
setup_advertencia.py — Sistema de advertências do STMC.

Mesmo fluxo do advertencia.py da Polícia Civil:
  /setup_advertencia → embed persistente com botão → modal (ID, tipo, duração, motivo)
  → remove ADV anterior e aplica a nova → embed em penalidades + log detalhado + DM.
Extra: a advertência fica registrada no banco (SQLAlchemy).
"""

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import utils.ui as ui
from config import settings
from services.membro_service import adicionar_advertencia, contar_advertencias
from utils.logger import log_event_async
from utils.permissao import eh_staff, pode_advertir
from utils.rate_limit import LIMITE_STAFF

logger = logging.getLogger("bot.advertencia")


# ──────────────────────────────────────────────
#  MODAL — preenchido pelo aplicador
# ──────────────────────────────────────────────
class AdvertenciaModal(discord.ui.Modal, title="Aplicar Advertência"):

    id_membro = discord.ui.TextInput(
        label="ID Discord do membro",
        placeholder="Ex: 123456789012345678",
        required=True,
        min_length=17,
        max_length=20,
    )

    tipo_adv = discord.ui.TextInput(
        label="Tipo de advertência",
        placeholder="ADV1, ADV2 ou ADV3",
        required=True,
        max_length=4,
    )

    duracao = discord.ui.TextInput(
        label="Duração em dias (vazio = permanente)",
        placeholder="Ex: 30",
        required=False,
        max_length=5,
    )

    motivo = discord.ui.TextInput(
        label="Motivo",
        placeholder="Descreva o motivo da advertência...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    def __init__(self, cog: "Advertencias"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        aplicador = interaction.user
        guild = interaction.guild

        # ── Verifica permissão ──────────────────
        if not pode_advertir(aplicador):
            return await interaction.followup.send(embed=ui.build_error_embed("Você não tem permissão para aplicar advertências."), ephemeral=True)

        # ── Valida ID do membro ─────────────────
        membro_id_str = self.id_membro.value.strip()
        if not membro_id_str.isdigit():
            return await interaction.followup.send(embed=ui.build_warn_embed("ID inválido. Digite apenas números."), ephemeral=True)

        membro = guild.get_member(int(membro_id_str))
        if not membro:
            try:
                membro = await guild.fetch_member(int(membro_id_str))
            except discord.NotFound:
                return await interaction.followup.send(embed=ui.build_warn_embed("Membro não encontrado neste servidor."), ephemeral=True)

        if membro.id == aplicador.id:
            return await interaction.followup.send(embed=ui.build_warn_embed("Você não pode advertir a si mesmo."), ephemeral=True)

        # ── Valida tipo ─────────────────────────
        tipo = self.tipo_adv.value.strip().upper().replace(" ", "")
        cargos_validos = {k: v for k, v in settings.CARGOS_ADVERTENCIA.items() if v}
        if tipo not in cargos_validos:
            tipos_validos = ", ".join(cargos_validos.keys()) or "nenhum configurado"
            return await interaction.followup.send(embed=ui.build_warn_embed(f"Tipo inválido. Use: `{tipos_validos}`"), ephemeral=True)

        # ── Valida duração ──────────────────────
        duracao_str = self.duracao.value.strip()
        if duracao_str:
            if not duracao_str.isdigit() or int(duracao_str) <= 0:
                return await interaction.followup.send(embed=ui.build_warn_embed("Duração inválida. Digite um número inteiro positivo ou deixe em branco."), ephemeral=True)
            duracao_dias = int(duracao_str)
        else:
            duracao_dias = None  # permanente

        motivo_texto = ui.sanitizar(self.motivo.value, 500)
        duracao_label = f"{duracao_dias} dias" if duracao_dias else "Permanente"

        # ── Valida hierarquia ───────────────────
        cargo_id = cargos_validos[tipo]
        cargo = guild.get_role(cargo_id)

        if not cargo:
            return await interaction.followup.send(embed=ui.build_error_embed("Cargo de advertência não encontrado. Verifique o ID no `.env`."), ephemeral=True)

        if cargo.position >= guild.me.top_role.position:
            return await interaction.followup.send(embed=ui.build_error_embed("Esse cargo está acima do meu na hierarquia. Não consigo aplicá-lo."), ephemeral=True)

        if membro.top_role.position >= guild.me.top_role.position:
            return await interaction.followup.send(embed=ui.build_error_embed("Esse membro tem um cargo acima ou igual ao meu. Não posso modificá-lo."), ephemeral=True)

        if guild.owner_id != aplicador.id and membro.top_role.position >= aplicador.top_role.position:
            return await interaction.followup.send(embed=ui.build_error_embed("Você não pode advertir um membro com cargo igual ou superior ao seu."), ephemeral=True)

        # ── Remove cargos de advertência anteriores e aplica o novo ────
        cargos_adv_ids = set(cargos_validos.values())
        cargos_para_remover = [r for r in membro.roles if r.id in cargos_adv_ids and r.id != cargo_id]
        try:
            if cargos_para_remover:
                await membro.remove_roles(*cargos_para_remover, reason=f"Substituído por [{tipo}]")
            await membro.add_roles(cargo, reason=f"[{tipo}] {motivo_texto[:400]}")
        except discord.Forbidden:
            return await interaction.followup.send(embed=ui.build_error_embed("Não consegui alterar os cargos do membro. Verifique minhas permissões."), ephemeral=True)

        # ── Persistência ────────────────────────
        await asyncio.to_thread(adicionar_advertencia, membro.id, tipo, duracao_dias, motivo_texto, aplicador.id)
        total = await asyncio.to_thread(contar_advertencias, membro.id)
        await log_event_async(str(aplicador), f"Advertência {tipo}", f"{membro} ({membro.id})", extra=motivo_texto)

        agora = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M")

        # ── Embed de penalidades (limpo) ────────
        embed_penalidades = ui.build_embed(
            title="Advertência Aplicada",
            description=f"<@{membro.id}> recebeu uma advertência do tipo **{tipo}**.",
            color=ui.UI_COLOR_WARNING,
        )
        embed_penalidades.add_field(name="Motivo", value=motivo_texto, inline=False)
        embed_penalidades.add_field(name="Duração", value=duracao_label, inline=True)
        embed_penalidades.add_field(name="Aplicador", value=aplicador.mention, inline=True)
        embed_penalidades.set_footer(
            text=f"{ui.FOOTER_TEXT} • Ação realizada em {agora}",
            icon_url=aplicador.display_avatar.url,
        )

        # ── Embed de log (detalhado) ────────────
        embed_log = ui.build_embed(
            title="Log de Advertência",
            description="Registro de nova advertência.",
            color=ui.UI_COLOR_ERROR,
        )
        embed_log.timestamp = datetime.now(timezone.utc)
        embed_log.add_field(name="Membro advertido", value=f"{membro.mention}\n`{membro.id}`", inline=True)
        embed_log.add_field(name="Tipo", value=tipo, inline=True)
        embed_log.add_field(name="Duração", value=duracao_label, inline=True)
        embed_log.add_field(name="Motivo", value=motivo_texto, inline=False)
        embed_log.add_field(name="Aplicador", value=f"{aplicador.mention}\n`{aplicador.id}`", inline=True)
        embed_log.add_field(name="Data/Hora", value=agora, inline=True)
        embed_log.add_field(name="Total de advertências", value=str(total), inline=True)
        embed_log.set_thumbnail(url=membro.display_avatar.url)
        embed_log.set_footer(text=f"{ui.FOOTER_TEXT} • Servidor: {guild.name}")

        # ── DM ao membro ────────────────────────
        try:
            embed_dm = ui.build_embed(
                title="Aviso de Advertência",
                description=f"Você foi advertido no **{settings.BOT_NOME}**.",
                color=ui.UI_COLOR_WARNING,
            )
            embed_dm.add_field(name="Tipo", value=tipo, inline=True)
            embed_dm.add_field(name="Duração", value=duracao_label, inline=True)
            embed_dm.add_field(name="Aplicador", value=aplicador.display_name, inline=True)
            embed_dm.add_field(name="Motivo", value=motivo_texto, inline=False)
            await membro.send(embed=embed_dm)
        except discord.Forbidden:
            pass  # DM fechada — intencional

        # ── Envia no canal de penalidades ───────
        canal_penalidades = self.cog.bot.get_channel(settings.CANAL_PENALIDADES_ID)
        if canal_penalidades:
            await canal_penalidades.send(content=f"<@{membro.id}>", embed=embed_penalidades)
        else:
            await interaction.followup.send(embed=ui.build_error_embed("Canal de penalidades não encontrado (`CANAL_PENALIDADES_ID`)."), ephemeral=True)

        # ── Envia no canal de log ───────────────
        canal_log = self.cog.bot.get_channel(settings.CANAL_LOGS_ADV_ID)
        if canal_log:
            await canal_log.send(embed=embed_log)

        # ── Confirmação ephemeral ───────────────
        await interaction.followup.send(
            embed=ui.build_success_embed(f"Advertência **{tipo}** aplicada a <@{membro.id}>."),
            ephemeral=True,
        )


# ──────────────────────────────────────────────
#  VIEW PERSISTENTE — botão no embed
# ──────────────────────────────────────────────
class AdvertenciaView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)  # persistente — sobrevive a restart

    @discord.ui.button(
        label="Aplicar advertência",
        style=discord.ButtonStyle.danger,
        custom_id="stmc_adv_abrir_modal",  # ID fixo obrigatório para views persistentes
    )
    async def abrir_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.cogs.get("Advertencias")
        if not cog:
            return await interaction.response.send_message(embed=ui.build_error_embed("Cog não carregada."), ephemeral=True)

        # Verifica permissão antes de abrir o modal
        if not pode_advertir(interaction.user):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você não tem permissão para usar isso."), ephemeral=True)

        espera = LIMITE_STAFF.verificar(interaction.user.id)
        if espera:
            return await interaction.response.send_message(embed=ui.build_warn_embed(f"Aguarde **{espera}s** e tente novamente."), ephemeral=True)

        await interaction.response.send_modal(AdvertenciaModal(cog))


# ──────────────────────────────────────────────
#  COG PRINCIPAL
# ──────────────────────────────────────────────
class Advertencias(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Registra a view persistente no bot ao carregar a cog."""
        self.bot.add_view(AdvertenciaView())

    @app_commands.command(name="setup_advertencia", description="Painel de advertências")
    @app_commands.checks.cooldown(1, 10)
    async def setup_advertencia(self, interaction: discord.Interaction):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você não tem permissão para usar esse comando."), ephemeral=True)

        tipos = ", ".join(k for k, v in settings.CARGOS_ADVERTENCIA.items() if v) or "—"
        embed = ui.build_embed(
            title="Sistema de Advertências - STMC",
            description=(
                "Clique no botão abaixo para abrir o formulário de advertência.\n\n"
                "Preencha os campos corretamente:\n"
                "• **ID Discord** do membro a ser advertido\n"
                f"• **Tipo:** {tipos}\n"
                "• **Duração** em dias (opcional — permanente se vazio)\n"
                "• **Motivo** da advertência"
            ),
        )
        embed.set_footer(text=f"{ui.FOOTER_TEXT} • Apenas membros autorizados podem aplicar advertências.")
        arquivo = ui.aplicar_logo(embed, interaction.guild)
        kwargs = {"file": arquivo} if arquivo else {}

        await interaction.channel.send(embed=embed, view=AdvertenciaView(), **kwargs)
        await interaction.response.send_message(embed=ui.build_success_embed("Painel de advertência configurado."), ephemeral=True)


# ──────────────────────────────────────────────
#  SETUP
# ──────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(Advertencias(bot))
