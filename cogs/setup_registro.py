"""
setup_registro.py — Registro de membros do Supremo Tribunal de Meta City.

Fluxo (mesmo do cadastro.py da Polícia Civil, adaptado ao tribunal):
  1. /setup_registro → painel com 2 botões: "Registro de Advogados" e "Registro de Seguranças"
  2. O botão define o tipo (o usuário não escolhe digitando → sem erro de fluxo)
  3. Modal: Nome e Sobrenome, Passaporte, Telefone
  4. Embed pendente no canal de aprovação (ID do usuário no rodapé = view stateless/persistente)
  5. Recrutador/Admin clica em Aceitar → cargos do tipo + nick "Passaporte • Nome" + log
     ou Recusar → registro removido + DM ao usuário
"""

import asyncio
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import utils.ui as ui
from config import settings
from services.membro_service import (
    adicionar_registro,
    aprovar_registro,
    blacklist_ativa,
    buscar_registro_por_discord_id,
    listar_registros_aprovados,
    passaporte_em_uso,
    remover_registro,
)
from utils.logger import log_event_async
from utils.permissao import eh_staff, is_admin, pode_recrutar
from utils.rate_limit import LIMITE_REGISTRO, LIMITE_STAFF

logger = logging.getLogger("bot.setup_registro")

RE_ID_FOOTER = re.compile(r"ID do Usuário:\s*(\d+)")
RE_TELEFONE = re.compile(r"\d{3}(-\d{3})?")
RE_PASSAPORTE = re.compile(r"\d{1,10}")

# Tipos de registro → metadados
TIPOS = {
    "advogado": {
        "label": "Advogado",
        "titulo": "Solicitação de Entrada - Advocacia",
        "cargos": lambda: settings.CARGOS_ADVOGADO,
    },
    "seguranca": {
        "label": "Segurança",
        "titulo": "Solicitação de Entrada - Segurança",
        "cargos": lambda: settings.CARGOS_SEGURANCA,
    },
}


# 🔹 Função para enviar logs e embeds
async def enviar_log(guild: discord.Guild, embed: discord.Embed):
    canal = guild.get_channel(settings.CANAL_LOGS_REGISTRO_ID)
    if canal:
        await canal.send(embed=embed)


# ──────────────────────────────────────────────
# 🟢 View Persistente de Aprovação
# ──────────────────────────────────────────────
class AprovacaoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # Timeout=None a torna persistente

    async def verificar_permissao(self, interaction: discord.Interaction) -> bool:
        if not pode_recrutar(interaction.user):
            await interaction.response.send_message(embed=ui.build_error_embed("Sem permissão para interagir com este registro."), ephemeral=True)
            return False
        espera = LIMITE_STAFF.verificar(interaction.user.id)
        if espera:
            await interaction.response.send_message(embed=ui.build_warn_embed(f"Aguarde **{espera}s** e tente novamente."), ephemeral=True)
            return False
        return True

    @staticmethod
    def extrair_id_usuario(interaction: discord.Interaction) -> int | None:
        # Extrai o ID do usuário do rodapé (footer) do embed
        if not interaction.message.embeds:
            return None
        match = RE_ID_FOOTER.search(interaction.message.embeds[0].footer.text or "")
        return int(match.group(1)) if match else None

    @discord.ui.button(label="Aceitar", style=discord.ButtonStyle.green, custom_id="stmc_btn_aprovar_registro")
    async def aprovar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.verificar_permissao(interaction):
            return

        user_id = self.extrair_id_usuario(interaction)
        if not user_id:
            return await interaction.response.send_message(embed=ui.build_error_embed("Não foi possível identificar o usuário deste registro."), ephemeral=True)

        registro = await asyncio.to_thread(buscar_registro_por_discord_id, user_id)
        if not registro:
            return await interaction.response.send_message(embed=ui.build_error_embed("Registro não encontrado no banco de dados. Talvez já tenha sido processado."), ephemeral=True)
        if registro["aprovado"]:
            return await interaction.response.send_message(embed=ui.build_warn_embed("Este registro já foi aprovado."), ephemeral=True)

        guild = interaction.guild
        aprovador = interaction.user
        tipo = TIPOS.get(registro["cargo"], TIPOS["advogado"])
        cargos = [r for r in (guild.get_role(cid) for cid in tipo["cargos"]()) if r]

        if not cargos:
            return await interaction.response.send_message(embed=ui.build_error_embed(f"Nenhum cargo de **{tipo['label']}** configurado/encontrado. Verifique o `.env`."), ephemeral=True)

        # ── Hierarquia: o recrutador não pode entregar cargos acima/igual ao dele ──
        if not is_admin(aprovador) and guild.owner_id != aprovador.id:
            acima = [r for r in cargos if r.position >= aprovador.top_role.position]
            if acima:
                nomes = ", ".join(r.mention for r in acima)
                return await interaction.response.send_message(embed=ui.build_error_embed(f"Você não pode atribuir cargos iguais ou acima do seu: {nomes}"), ephemeral=True)

        # ── Hierarquia do bot ──
        if any(r.position >= guild.me.top_role.position for r in cargos):
            return await interaction.response.send_message(embed=ui.build_error_embed("Algum cargo do registro está acima do meu na hierarquia. Não consigo aplicá-lo."), ephemeral=True)

        await interaction.response.defer()

        await asyncio.to_thread(aprovar_registro, user_id, aprovador.id)
        await log_event_async(str(aprovador), "Aprovou registro", registro["usuario"], extra=tipo["label"])

        membro = guild.get_member(user_id)
        if membro:
            try:
                await membro.add_roles(*cargos, reason=f"Registro aprovado por {aprovador}")
            except discord.Forbidden:
                logger.warning(f"Sem permissão para adicionar cargos em {membro}")
            # ✨ Nickname com estética "Passaporte • Nome"
            novo_nick = f"{registro['passaporte']} • {registro['nome']}"[:32]
            try:
                await membro.edit(nick=novo_nick)
            except discord.Forbidden:
                logger.warning("Permissão insuficiente para mudar o apelido.")
            except discord.HTTPException as e:
                logger.warning(f"Erro ao editar apelido: {e}")

            try:
                await membro.send(embed=ui.build_success_embed(
                    f"Seu registro como **{tipo['label']}** no **{settings.BOT_NOME}** foi aprovado por {aprovador.mention}.",
                    title="Registro Aprovado",
                ))
            except discord.Forbidden:
                pass

        # Atualiza a mensagem original para remover os botões
        embed_atualizado = interaction.message.embeds[0]
        embed_atualizado.color = ui.UI_COLOR_SUCCESS
        await interaction.message.edit(
            content=f"Registro aprovado por {aprovador.mention}.",
            embed=embed_atualizado,
            view=None,
        )
        await interaction.channel.send(f"O membro <@{user_id}> foi aprovado como **{tipo['label']}** por {aprovador.mention}.")

        # 📝 Envia embed de aprovação para logs
        embed_log = ui.build_embed(
            title="Registro Aprovado",
            description=(
                f"Usuário: {registro['usuario']}\n"
                f"Discord ID: {user_id}\n"
                f"Nome: {registro['nome']}\n"
                f"Passaporte: {registro['passaporte']}\n"
                f"Telefone: {registro['telefone']}\n"
                f"Função: {tipo['label']}\n"
                f"Aprovado por: {aprovador.mention}"
            ),
            color=ui.UI_COLOR_SUCCESS,
        )
        await enviar_log(guild, embed_log)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.red, custom_id="stmc_btn_recusar_registro")
    async def recusar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.verificar_permissao(interaction):
            return

        user_id = self.extrair_id_usuario(interaction)
        if not user_id:
            return await interaction.response.send_message(embed=ui.build_error_embed("Não foi possível identificar o usuário deste registro."), ephemeral=True)

        registro = await asyncio.to_thread(buscar_registro_por_discord_id, user_id)
        if registro:
            if registro["aprovado"]:
                return await interaction.response.send_message(embed=ui.build_warn_embed("Este registro já foi aprovado. Use o painel de exoneração."), ephemeral=True)
            await asyncio.to_thread(remover_registro, user_id)
            await log_event_async(str(interaction.user), "Recusou registro", registro["usuario"])

        embed_atualizado = interaction.message.embeds[0]
        embed_atualizado.color = ui.UI_COLOR_ERROR
        await interaction.response.edit_message(
            content=f"Registro recusado por {interaction.user.mention}.",
            embed=embed_atualizado,
            view=None,
        )

        membro = interaction.guild.get_member(user_id)
        if membro:
            try:
                await membro.send(embed=ui.build_error_embed(
                    f"Seu registro no **{settings.BOT_NOME}** foi reprovado por {interaction.user.name}.",
                    title="Registro Reprovado",
                ))
            except discord.Forbidden:
                pass  # Ignora se a DM do usuário estiver fechada

        embed_log = ui.build_embed(
            title="Registro Recusado",
            description=f"<@{user_id}>\nDiscord ID: {user_id}\nRecusado por: {interaction.user.mention}",
            color=ui.UI_COLOR_ERROR,
        )
        await enviar_log(interaction.guild, embed_log)


# ──────────────────────────────────────────────
# 📥 Modal de Registro
# ──────────────────────────────────────────────
class RegistroModal(discord.ui.Modal):
    nome = discord.ui.TextInput(label="Nome e Sobrenome", placeholder="Ex: João Silva", min_length=3, max_length=32)
    passaporte = discord.ui.TextInput(label="Passaporte", placeholder="Apenas números", max_length=10)
    telefone = discord.ui.TextInput(label="Telefone", placeholder="000-000", max_length=7)

    def __init__(self, tipo: str):
        self.tipo = tipo
        super().__init__(title=f"Registro de {TIPOS[tipo]['label']}")

    async def on_submit(self, interaction: discord.Interaction):
        meta = TIPOS[self.tipo]
        nome = discord.utils.escape_markdown(self.nome.value.strip())
        passaporte = self.passaporte.value.strip()
        telefone = self.telefone.value.strip()

        # ── Validações de formato ──
        if not RE_PASSAPORTE.fullmatch(passaporte):
            return await interaction.response.send_message(embed=ui.build_error_embed("Passaporte inválido! Use apenas números."), ephemeral=True)
        if not RE_TELEFONE.fullmatch(telefone):
            return await interaction.response.send_message(embed=ui.build_error_embed("Formato de telefone inválido. Use 000-000 ou 000."), ephemeral=True)

        canal_aprovacao = interaction.guild.get_channel(settings.CANAL_APROVACAO_REGISTRO_ID)
        if not canal_aprovacao:
            return await interaction.response.send_message(embed=ui.build_error_embed("Canal de aprovação não configurado. Avise a administração."), ephemeral=True)

        # ── Validações no banco ──
        bl = await asyncio.to_thread(blacklist_ativa, interaction.user.id)
        if bl:
            ate = "permanentemente" if not bl["expira_em"] else f"até {bl['expira_em'].strftime('%d/%m/%Y')}"
            return await interaction.response.send_message(embed=ui.build_error_embed(f"Você está na blacklist do tribunal {ate}.\n**Motivo:** {bl['motivo']}"), ephemeral=True)

        if await asyncio.to_thread(buscar_registro_por_discord_id, interaction.user.id):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você já tem um registro em andamento ou aprovado."), ephemeral=True)

        if await asyncio.to_thread(passaporte_em_uso, passaporte, interaction.user.id):
            return await interaction.response.send_message(embed=ui.build_error_embed("Este passaporte já está cadastrado por outro membro."), ephemeral=True)

        registro = {
            "nome": nome,
            "passaporte": passaporte,
            "telefone": telefone,
            "usuario": interaction.user.name,
            "discord_id": interaction.user.id,
            "cargo": self.tipo,
        }
        await asyncio.to_thread(adicionar_registro, registro)

        # Confirmação efêmera para o usuário
        await interaction.response.send_message(
            embed=ui.build_success_embed(f"{interaction.user.mention}, seus dados foram enviados para aprovação.", title="Registro enviado"),
            ephemeral=True,
        )

        # ✨ Embed de aprovação
        embed_pendente = ui.build_embed(
            title=f"{meta['titulo']}",
            description=f"**Novo membro solicitando entrada como {meta['label']} no {settings.BOT_SIGLA}**\n",
            color=ui.UI_COLOR_WARNING,
        )
        embed_pendente.add_field(name="Solicitante", value=f"{interaction.user.mention}\n`{interaction.user.name}`", inline=False)
        embed_pendente.add_field(name="Nome Cadastrado", value=f"`{nome}`", inline=True)
        embed_pendente.add_field(name="Passaporte", value=f"`{passaporte}`", inline=True)
        embed_pendente.add_field(name="Telefone", value=f"`{telefone}`", inline=True)
        embed_pendente.add_field(name="Função", value=f"**{meta['label']}**", inline=False)
        embed_pendente.set_thumbnail(url=interaction.user.display_avatar.url)

        # O truque de persistência: salvar o ID no rodapé para a AprovacaoView conseguir ler
        embed_pendente.set_footer(text=f"{ui.FOOTER_TEXT} • ID do Usuário: {interaction.user.id}")

        recrutador = interaction.guild.get_role(settings.RECRUTADOR_ROLE_ID)
        await canal_aprovacao.send(
            content=f"**Registro pendente:**\n{recrutador.mention if recrutador else ''} favor revisar.",
            embed=embed_pendente,
            view=AprovacaoView(),  # View sem argumentos (stateless)
            allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False),
        )


# ──────────────────────────────────────────────
# 🟢 View Persistente de Início de Registro (2 botões)
# ──────────────────────────────────────────────
class RegistroView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @staticmethod
    async def _abrir(interaction: discord.Interaction, tipo: str):
        espera = LIMITE_REGISTRO.verificar(interaction.user.id)
        if espera:
            return await interaction.response.send_message(embed=ui.build_warn_embed(f"Aguarde **{espera}s** antes de tentar novamente."), ephemeral=True)
        await interaction.response.send_modal(RegistroModal(tipo))

    @discord.ui.button(label="Registro de Advogados", style=discord.ButtonStyle.primary, custom_id="stmc_btn_registro_advogado")
    async def advogado(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._abrir(interaction, "advogado")

    @discord.ui.button(label="Registro de Seguranças", style=discord.ButtonStyle.secondary, custom_id="stmc_btn_registro_seguranca")
    async def seguranca(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._abrir(interaction, "seguranca")


# ──────────────────────────────────────────────
# 🔧 Comandos principais
# ──────────────────────────────────────────────
class Cadastro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Inicializa as views persistentes quando o Cog carrega
    async def cog_load(self):
        self.bot.add_view(RegistroView())
        self.bot.add_view(AprovacaoView())

    @app_commands.command(name="setup_registro", description="Cria a mensagem permanente de Registro do tribunal")
    @app_commands.checks.cooldown(1, 10)
    async def setup_registro(self, interaction: discord.Interaction):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você não tem permissão para usar esse comando."), ephemeral=True)

        embed = ui.build_embed(
            title=f"Cadastro - {settings.BOT_NOME}",
            description=(
                "Escolha abaixo a função para a qual deseja se registrar.\n\n"
                "**Registro de Advogados** - ingresso na advocacia do tribunal.\n"
                "**Registro de Seguranças** - ingresso na segurança do tribunal.\n\n"
                "**OBSERVAÇÃO:** Preencha seus dados corretamente. Registros com informações "
                "falsas serão recusados. Em caso de erro, procure a administração.\n\n"
                "Atenciosamente, Presidência do STMC"
            ),
            color=ui.UI_COLOR_MAIN,
        )
        arquivo = ui.aplicar_logo(embed, interaction.guild)
        kwargs = {"file": arquivo} if arquivo else {}
        await interaction.channel.send(embed=embed, view=RegistroView(), **kwargs)
        await interaction.response.send_message(embed=ui.build_success_embed("Painel de registro configurado."), ephemeral=True)

    @app_commands.command(name="listar_registros", description="Lista todos os membros aprovados do tribunal")
    @app_commands.checks.cooldown(1, 15)
    async def listar_registros(self, interaction: discord.Interaction):
        if not pode_recrutar(interaction.user):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você não tem permissão para usar esse comando."), ephemeral=True)

        registros_aprovados = await asyncio.to_thread(listar_registros_aprovados)
        if not registros_aprovados:
            return await interaction.response.send_message(embed=ui.build_warn_embed("Nenhum registro aprovado encontrado."), ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        for i in range(0, len(registros_aprovados), 5):
            bloco = registros_aprovados[i:i + 5]
            embed = ui.build_embed(
                title=f"Membros do {settings.BOT_SIGLA}",
                description="Lista dos membros cadastrados no tribunal",
                color=ui.UI_COLOR_MAIN,
            )
            for idx, registro in enumerate(bloco, start=i + 1):
                meta = TIPOS.get(registro["cargo"], TIPOS["advogado"])
                embed.add_field(
                    name=f"{idx}. {registro['usuario']}",
                    value=(
                        f"**Nome:** {registro['nome']}\n**Passaporte:** {registro['passaporte']}\n"
                        f"**Telefone:** {registro['telefone']}\n**Função:** {meta['label']}"
                    ),
                    inline=False,
                )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Cadastro(bot))
