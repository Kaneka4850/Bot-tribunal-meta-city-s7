"""
setup_demissao.py — Exoneração de membros do STMC.

Mesmo fluxo do demitir.py da Polícia Civil:
  /setup_demissao → embed persistente → modal (ID, motivo, blacklist)
  → confirmação ephemeral (Confirmar / Cancelar)
  → remove cargos (+ cargo de exonerado, se configurado), apaga registro do banco,
    reseta nick, publica no canal de exonerações e, se permanente, no canal de blacklist.
Extra: a blacklist fica salva no banco e bloqueia novos registros enquanto vigente.
"""

import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

import utils.ui as ui
from config import settings
from services.membro_service import adicionar_blacklist, buscar_registro_por_discord_id, remover_registro
from utils.logger import log_event_async
from utils.permissao import eh_staff, pode_advertir
from utils.rate_limit import LIMITE_STAFF

logger = logging.getLogger("bot.demissao")

TIPO_LABEL = {"advogado": "Advogado", "seguranca": "Segurança"}


# ──────────────────────────────────────────────
#  VIEW DE CONFIRMAÇÃO — Confirmar / Cancelar
# ──────────────────────────────────────────────
class ConfirmarDemissaoView(discord.ui.View):
    """View ephemeral com botões de Confirmar / Cancelar a exoneração."""

    def __init__(self, cog: "Demissao", membro: discord.Member, registro: dict, motivo: str,
                 blacklist_dias: int | None, blacklist_ativa: bool, blacklist_label: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.membro = membro
        self.registro = registro
        self.motivo = motivo
        self.blacklist_dias = blacklist_dias      # None + ativa = permanente
        self.blacklist_ativa = blacklist_ativa
        self.blacklist_label = blacklist_label    # "Nenhuma", "X dias", "Permanente"
        self.executado = False

    @discord.ui.button(label="Confirmar exoneração", style=discord.ButtonStyle.danger)
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.executado:
            return await interaction.response.send_message(embed=ui.build_warn_embed("Esta exoneração já foi processada."), ephemeral=True)
        self.executado = True
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        aplicador = interaction.user
        membro = self.membro
        agora = datetime.now(timezone.utc).strftime("%d/%m/%Y às %H:%M")

        # ── 1. Remove todos os cargos e aplica o cargo de exonerado (se houver) ──
        cargo_exonerado = guild.get_role(settings.CARGO_EXONERADO_ID) if settings.CARGO_EXONERADO_ID else None
        try:
            cargos_para_remover = [r for r in membro.roles if r != guild.default_role and r.is_assignable()]
            if cargos_para_remover:
                await membro.remove_roles(*cargos_para_remover, reason=f"Exoneração por {aplicador}")
            if cargo_exonerado:
                await membro.add_roles(cargo_exonerado, reason=f"Exoneração por {aplicador}")
            try:
                await membro.edit(nick=None, reason="Exoneração")
            except discord.HTTPException:
                pass
        except discord.Forbidden:
            await interaction.followup.send(
                embed=ui.build_error_embed("Não foi possível modificar os cargos do membro. Verifique as permissões do bot."),
                ephemeral=True,
            )
            self.stop()
            return

        # ── 2. Remove registro do banco e grava blacklist ──
        await asyncio.to_thread(remover_registro, membro.id)
        if self.blacklist_ativa:
            await asyncio.to_thread(adicionar_blacklist, membro.id, self.motivo, self.blacklist_dias, aplicador.id)
        await log_event_async(str(aplicador), "Exoneração", self.registro["usuario"], extra=f"{self.motivo} | Blacklist: {self.blacklist_label}")

        # ── 3. Embed de exoneração (canal de exoneração — SEMPRE) ──
        embed_exoneracao = ui.build_embed(
            title="Exoneração Realizada",
            description=f"<@{membro.id}> foi exonerado do {settings.BOT_NOME}.",
            color=ui.UI_COLOR_ERROR,
        )
        embed_exoneracao.add_field(name="Membro exonerado", value=f"{membro.mention}\n`{membro.id}`", inline=True)
        embed_exoneracao.add_field(name="Nome", value=f"`{self.registro['nome']}`", inline=True)
        embed_exoneracao.add_field(name="Passaporte", value=f"`{self.registro['passaporte']}`", inline=True)
        embed_exoneracao.add_field(name="Função", value=TIPO_LABEL.get(self.registro["cargo"], self.registro["cargo"]), inline=True)
        embed_exoneracao.add_field(name="Motivo", value=self.motivo, inline=False)
        embed_exoneracao.add_field(name="Blacklist", value=self.blacklist_label, inline=True)
        embed_exoneracao.add_field(name="Exonerado por", value=f"{aplicador.mention}\n`{aplicador.id}`", inline=True)
        embed_exoneracao.add_field(name="Data/Hora", value=agora, inline=True)
        embed_exoneracao.set_thumbnail(url=membro.display_avatar.url)
        embed_exoneracao.set_footer(text=f"{ui.FOOTER_TEXT} • Ação realizada em {agora}", icon_url=aplicador.display_avatar.url)

        canal_exoneracao = self.cog.bot.get_channel(settings.CANAL_EXONERACAO_ID)
        if canal_exoneracao:
            await canal_exoneracao.send(content=f"<@{membro.id}>", embed=embed_exoneracao)
        else:
            logger.warning("Canal de exoneração não encontrado (ID: %s)", settings.CANAL_EXONERACAO_ID)

        # ── 4. Embed de blacklist permanente (canal de blacklist — SÓ SE permanente) ──
        if self.blacklist_ativa and self.blacklist_dias is None:
            embed_blacklist = ui.build_embed(
                title="Blacklist Permanente",
                description=f"<@{membro.id}> recebeu blacklist **permanente** do {settings.BOT_SIGLA}.",
                color=ui.UI_COLOR_ERROR,
            )
            embed_blacklist.add_field(name="Membro", value=f"{membro.mention}\n`{membro.id}`", inline=True)
            embed_blacklist.add_field(name="Nome", value=f"`{self.registro['nome']}`", inline=True)
            embed_blacklist.add_field(name="Passaporte", value=f"`{self.registro['passaporte']}`", inline=True)
            embed_blacklist.add_field(name="Motivo", value=self.motivo, inline=False)
            embed_blacklist.add_field(name="Aplicado por", value=f"{aplicador.mention}\n`{aplicador.id}`", inline=True)
            embed_blacklist.add_field(name="Data/Hora", value=agora, inline=True)
            embed_blacklist.set_thumbnail(url=membro.display_avatar.url)
            embed_blacklist.set_footer(text=f"{ui.FOOTER_TEXT} • Blacklist permanente")

            canal_blacklist = self.cog.bot.get_channel(settings.CANAL_BLACKLIST_ID)
            if canal_blacklist:
                await canal_blacklist.send(content=f"<@{membro.id}>", embed=embed_blacklist)
            else:
                logger.warning("Canal de blacklist não encontrado (ID: %s)", settings.CANAL_BLACKLIST_ID)

        # ── 5. DM ao membro ──
        try:
            await membro.send(embed=ui.build_error_embed(
                f"Você foi exonerado do **{settings.BOT_NOME}**.\n**Motivo:** {self.motivo}\n**Blacklist:** {self.blacklist_label}",
                title="Aviso de Exoneração",
            ))
        except discord.Forbidden:
            pass

        # ── 6. Confirmação ephemeral ──
        await interaction.followup.send(embed=ui.build_success_embed(f"<@{membro.id}> foi exonerado."), ephemeral=True)
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=ui.build_warn_embed("Operação cancelada. Nenhuma exoneração foi realizada."), ephemeral=True)
        self.stop()


# ──────────────────────────────────────────────
#  MODAL — preenchido pelo aplicador
# ──────────────────────────────────────────────
class DemissaoModal(discord.ui.Modal, title="Exoneração de Membro"):

    id_membro = discord.ui.TextInput(
        label="ID Discord do membro",
        placeholder="Ex: 123456789012345678",
        required=True,
        min_length=17,
        max_length=20,
    )

    motivo = discord.ui.TextInput(
        label="Motivo da exoneração",
        placeholder="Descreva o motivo da exoneração...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    blacklist = discord.ui.TextInput(
        label="Blacklist (dias, 'permanente' ou vazio)",
        placeholder="Ex: 30, permanente ou deixe vazio",
        required=False,
        max_length=20,
    )

    def __init__(self, cog: "Demissao"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        aplicador = interaction.user
        guild = interaction.guild

        # ── Verifica permissão do aplicador ─────────
        if not pode_advertir(aplicador):
            return await interaction.followup.send(embed=ui.build_error_embed("Você não tem permissão para realizar exonerações."), ephemeral=True)

        # ── Valida ID do membro ─────────────────────
        membro_id_str = self.id_membro.value.strip()
        if not membro_id_str.isdigit():
            return await interaction.followup.send(embed=ui.build_warn_embed("ID inválido. Digite apenas números."), ephemeral=True)

        membro = guild.get_member(int(membro_id_str))
        if not membro:
            try:
                membro = await guild.fetch_member(int(membro_id_str))
            except discord.NotFound:
                return await interaction.followup.send(embed=ui.build_warn_embed("Membro não encontrado neste servidor."), ephemeral=True)

        # ── Verifica hierarquia ──
        if guild.owner_id != aplicador.id and membro.top_role.position >= aplicador.top_role.position:
            return await interaction.followup.send(embed=ui.build_error_embed("Você não pode exonerar um membro com cargo igual ou superior ao seu."), ephemeral=True)

        if membro.top_role.position >= guild.me.top_role.position:
            return await interaction.followup.send(embed=ui.build_error_embed("Esse membro tem um cargo acima ou igual ao meu. Não posso modificá-lo."), ephemeral=True)

        # ── Verifica registro no banco de dados ─────
        registro = await asyncio.to_thread(buscar_registro_por_discord_id, membro.id)
        if not registro:
            return await interaction.followup.send(embed=ui.build_error_embed(f"O membro <@{membro.id}> não possui registro no banco de dados."), ephemeral=True)

        # ── Valida campo de blacklist ────────────────
        blacklist_raw = self.blacklist.value.strip()
        blacklist_dias = None
        blacklist_ativa = False
        blacklist_label = "Nenhuma"

        if blacklist_raw:
            if blacklist_raw.lower() == "permanente":
                blacklist_ativa = True
                blacklist_label = "Permanente"
            elif blacklist_raw.isdigit() and int(blacklist_raw) > 0:
                blacklist_ativa = True
                blacklist_dias = int(blacklist_raw)
                blacklist_label = f"{blacklist_dias} dias"
            else:
                return await interaction.followup.send(
                    embed=ui.build_warn_embed(
                        "Valor de blacklist inválido.\n\n"
                        "Valores aceitos:\n"
                        "• **Número** de dias (ex: `30`)\n"
                        "• **Permanente** (escreva `permanente`)\n"
                        "• **Vazio** para nenhuma blacklist"
                    ),
                    ephemeral=True,
                )

        motivo_texto = ui.sanitizar(self.motivo.value, 500)

        # ── Monta embed de confirmação ───────────────
        embed_confirma = ui.build_embed(
            title="Confirmar Exoneração",
            description=(
                f"Você está prestes a exonerar <@{membro.id}> do {settings.BOT_SIGLA}.\n\n"
                f"**Nome:** `{registro['nome']}`\n"
                f"**Passaporte:** `{registro['passaporte']}`\n"
                f"**Função:** {TIPO_LABEL.get(registro['cargo'], registro['cargo'])}\n"
                f"**Motivo:** {motivo_texto}\n"
                f"**Blacklist:** {blacklist_label}\n\n"
                "**Esta ação é irreversível.** Deseja continuar?"
            ),
            color=ui.UI_COLOR_ERROR,
        )

        view = ConfirmarDemissaoView(
            cog=self.cog, membro=membro, registro=registro, motivo=motivo_texto,
            blacklist_dias=blacklist_dias, blacklist_ativa=blacklist_ativa, blacklist_label=blacklist_label,
        )
        await interaction.followup.send(embed=embed_confirma, view=view, ephemeral=True)


# ──────────────────────────────────────────────
#  VIEW PERSISTENTE — botão no embed
# ──────────────────────────────────────────────
class DemissaoView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)  # persistente — sobrevive a restart

    @discord.ui.button(
        label="Iniciar exoneração",
        style=discord.ButtonStyle.danger,
        custom_id="stmc_btn_iniciar_demissao",
    )
    async def abrir_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = interaction.client.cogs.get("Demissao")
        if not cog:
            return await interaction.response.send_message(embed=ui.build_error_embed("Cog não carregada."), ephemeral=True)

        if not pode_advertir(interaction.user):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você não tem permissão para usar isso."), ephemeral=True)

        espera = LIMITE_STAFF.verificar(interaction.user.id)
        if espera:
            return await interaction.response.send_message(embed=ui.build_warn_embed(f"Aguarde **{espera}s** e tente novamente."), ephemeral=True)

        await interaction.response.send_modal(DemissaoModal(cog))


# ──────────────────────────────────────────────
#  COG PRINCIPAL
# ──────────────────────────────────────────────
class Demissao(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Registra a view persistente no bot ao carregar a cog."""
        self.bot.add_view(DemissaoView())

    @app_commands.command(name="setup_demissao", description="Painel de exoneração")
    @app_commands.checks.cooldown(1, 10)
    async def setup_demissao(self, interaction: discord.Interaction):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você não tem permissão para usar esse comando."), ephemeral=True)

        embed = ui.build_embed(
            title="Sistema de Exoneração - STMC",
            description=(
                "Clique no botão abaixo para abrir o formulário de exoneração.\n\n"
                "Preencha os campos corretamente:\n"
                "• **ID Discord** do membro a ser exonerado\n"
                "• **Motivo** da exoneração\n"
                "• **Blacklist** (número de dias, 'permanente' ou vazio)"
            ),
        )
        embed.set_footer(text=f"{ui.FOOTER_TEXT} • Apenas membros autorizados podem realizar exonerações.")
        arquivo = ui.aplicar_logo(embed, interaction.guild)
        kwargs = {"file": arquivo} if arquivo else {}

        await interaction.channel.send(embed=embed, view=DemissaoView(), **kwargs)
        await interaction.response.send_message(embed=ui.build_success_embed("Painel de exoneração configurado."), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Demissao(bot))
