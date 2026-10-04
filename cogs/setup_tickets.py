"""
setup_tickets.py — Central de Atendimento do STMC (baseado no corregedoria.py da Polícia Civil).

Funcionalidades:
  - Setup persistente com Select de categorias (6 tipos + resetar)
  - Cada tipo abre o ticket na sua própria categoria (IDs no .env)
  - Modal obrigatório: Nome, Passaporte, Solicitação, Anexos (opcional)
  - Controle de duplicidade (1 ticket aberto por usuário)
  - Botões: Solicitar Atendimento, Assumir, Pokar Membro, Remover Membro, Encerrar
  - Transcript HTML (chat_exporter) no canal de logs e na DM de todos os envolvidos
  - Log estruturado em canal dedicado
"""

import datetime
import io
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import utils.ui as ui
from config import settings
from utils.logger import log_event_async
from utils.permissao import eh_staff
from utils.rate_limit import LIMITE_STAFF, LIMITE_TICKET

logger = logging.getLogger("bot.setup_tickets")

# ─────────────────────────────────────────────
# Tipos de ticket: value → (label, descrição, emoji)
# ─────────────────────────────────────────────
TIPOS_TICKET = {
    "troca_nome": ("Troca de nome",            "Solicitar alteração de nome civil"),
    "certidoes":  ("Solicitação de Certidões", "Certidões e documentos oficiais"),
    "patentes":   ("Solicitação de Patentes",  "Registro e solicitação de patentes"),
    "cnpj":       ("CNPJ - Contratos",         "Abertura de CNPJ e registro de contratos"),
    "porte_arma": ("Porte de Arma de fogo",    "Solicitação de porte de arma"),
    "processo":   ("Processo em geral",        "Ações e processos judiciais"),
}

RE_CRIADOR = re.compile(r"ticket:(\d+)")
RE_ASSUMIDO = re.compile(r"assumido:(\d+)")


# ─────────────────────────────────────────────
# HELPERS de tópico (persistência sem banco)
# ─────────────────────────────────────────────
def criador_id_do_canal(canal: discord.TextChannel) -> int | None:
    m = RE_CRIADOR.search(canal.topic or "")
    return int(m.group(1)) if m else None


def assumido_id_do_canal(canal: discord.TextChannel) -> int | None:
    m = RE_ASSUMIDO.search(canal.topic or "")
    return int(m.group(1)) if m else None


def tipo_do_canal(canal: discord.TextChannel) -> str:
    m = re.search(r"Tipo:\s*([^|]+)", canal.topic or "")
    return m.group(1).strip() if m else "Desconhecido"


async def buscar_membro(guild: discord.Guild, user_id: int | None) -> discord.Member | None:
    if not user_id:
        return None
    membro = guild.get_member(user_id)
    if membro:
        return membro
    try:
        return await guild.fetch_member(user_id)
    except (discord.NotFound, discord.HTTPException):
        return None


async def checar_staff(interaction: discord.Interaction) -> bool:
    if not eh_staff(interaction.user):
        await interaction.response.send_message(embed=ui.build_error_embed("Apenas a equipe do tribunal pode usar esta função."), ephemeral=True)
        return False
    espera = LIMITE_STAFF.verificar(interaction.user.id)
    if espera:
        await interaction.response.send_message(embed=ui.build_warn_embed(f"Calma! Tente novamente em **{espera}s**."), ephemeral=True)
        return False
    return True


# ─────────────────────────────────────────────
# HELPER: Geração de log
# ─────────────────────────────────────────────
async def gerar_log(bot, autor, acao: str, membro=None, moderador=None, extras: dict | None = None, canal=None):
    """Envia um embed de log no canal configurado."""
    await log_event_async(str(autor), acao, str(membro) if membro else None, extra=str(extras) if extras else None)

    canal_logs = bot.get_channel(settings.LOG_CHANNEL_ID)
    if not canal_logs:
        return

    hora = discord.utils.format_dt(datetime.datetime.now(), style="F")
    descricao = f"**Autor:** {autor.mention}\n**Alvo:** {membro.mention}" if membro else f"**Autor:** {autor.mention}"
    if canal:
        descricao += f"\n**Ticket:** `{canal.name}`"

    embed = ui.build_embed(title=f"Log de {acao}", description=descricao, color=ui.UI_COLOR_MAIN)
    if moderador:
        embed.add_field(name="Moderador", value=moderador, inline=True)
    embed.add_field(name="Horário", value=hora, inline=True)
    if extras:
        for k, v in extras.items():
            if v:
                v = str(v)[:1000]
                embed.add_field(name=f"{k}", value=f"```\n{v}\n```" if len(v) > 20 else v, inline=False)
    embed.set_footer(text=f"{ui.FOOTER_TEXT} • ID do Usuário: {autor.id}", icon_url=autor.display_avatar.url)
    await canal_logs.send(embed=embed)


# ─────────────────────────────────────────────
# HELPER: Gerar transcript HTML e distribuir
# ─────────────────────────────────────────────
async def gerar_e_enviar_transcript(bot, canal: discord.TextChannel, envolvidos: list[discord.Member], fechado_por, motivo: str, veredito: str):
    """Gera o transcript e envia no canal de logs + DM de cada envolvido."""
    try:
        import chat_exporter
    except ImportError:
        logger.warning("`chat_exporter` não está instalado.")
        canal_logs = bot.get_channel(settings.LOG_CHANNEL_ID)
        if canal_logs:
            await canal_logs.send("⚠️ `chat_exporter` não está instalado. Instale com `pip install chat-exporter`.")
        return

    try:
        # LIMITE: exporta no máximo 500 mensagens para evitar picos de memória
        transcript = await chat_exporter.export(canal, limit=500, tz_info="America/Sao_Paulo", bot=bot)
        if not transcript:
            logger.warning(f"Transcript vazio para canal {canal.name}")
            return
        dados = transcript.encode()
        nome_arquivo = f"transcript-{canal.name}.html"

        def novo_arquivo():
            return discord.File(io.BytesIO(dados), filename=nome_arquivo)

        embed_t = ui.build_embed(
            title="Transcript do Atendimento",
            description=f"O ticket **{canal.name}** foi encerrado.\nO histórico completo das mensagens está anexado abaixo.",
            color=ui.UI_COLOR_MAIN,
        )
        embed_t.add_field(name="Categoria", value=f"`{tipo_do_canal(canal)}`", inline=True)
        embed_t.add_field(name="Encerrado por", value=fechado_por.mention, inline=True)
        embed_t.add_field(name="Veredito", value=veredito or "—", inline=True)
        embed_t.add_field(name="Motivo", value=motivo or "—", inline=False)
        embed_t.set_footer(text=f"{ui.FOOTER_TEXT} • Central de Atendimento")

        # DM para todos os envolvidos
        falhas = []
        for membro in envolvidos:
            try:
                await membro.send(embed=embed_t, file=novo_arquivo())
            except (discord.Forbidden, discord.HTTPException):
                falhas.append(membro.mention)

        # Canal de logs (sempre)
        canal_logs = bot.get_channel(settings.LOG_CHANNEL_ID)
        if canal_logs:
            embed_log = embed_t.copy()
            embed_log.add_field(name="Envolvidos", value=", ".join(m.mention for m in envolvidos) or "—", inline=False)
            if falhas:
                embed_log.add_field(name="DM fechada", value=", ".join(falhas), inline=False)
            await canal_logs.send(embed=embed_log, file=novo_arquivo())

        del transcript, dados
    except Exception as e:
        logger.error(f"Erro ao gerar transcript para {canal.name}: {e}", exc_info=True)


# ─────────────────────────────────────────────
# MODAL: Encerramento de ticket
# ─────────────────────────────────────────────
class ModalFecharTicket(discord.ui.Modal, title="Encerramento de Ticket"):
    motivo = discord.ui.TextInput(
        label="Motivo do Encerramento",
        placeholder="Descreva brevemente o porquê do ticket estar sendo fechado...",
        style=discord.TextStyle.paragraph,
        max_length=500,
    )
    veredito = discord.ui.TextInput(
        label="Veredito Final",
        placeholder="Ex: Deferido / Indeferido / Resolvido",
        style=discord.TextStyle.short,
        max_length=50,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        canal = interaction.channel
        guild = interaction.guild
        motivo = ui.sanitizar(self.motivo.value, 500)
        veredito = ui.sanitizar(self.veredito.value, 50)

        try:
            # Envolvidos: criador + membros pokados (overwrites) + quem assumiu + quem fechou
            ids = {criador_id_do_canal(canal), assumido_id_do_canal(canal), interaction.user.id}
            ids |= {alvo.id for alvo in canal.overwrites if isinstance(alvo, discord.Member)}
            envolvidos = []
            for uid in ids:
                membro = await buscar_membro(guild, uid)
                if membro and not membro.bot:
                    envolvidos.append(membro)

            await gerar_e_enviar_transcript(self.bot, canal, envolvidos, interaction.user, motivo, veredito)
            await gerar_log(
                self.bot, interaction.user, "Encerramento de Ticket",
                moderador=interaction.user.name, canal=canal,
                extras={"Categoria": tipo_do_canal(canal), "Motivo": motivo, "Veredito": veredito},
            )
            await canal.delete(reason=f"Ticket encerrado por {interaction.user}")
        except Exception as e:
            logger.error(f"Erro ao encerrar ticket: {e}", exc_info=True)
            await interaction.followup.send(embed=ui.build_error_embed(f"Ocorreu um erro ao encerrar o ticket: `{e}`"), ephemeral=True)


# ─────────────────────────────────────────────
# MODAL: Pokar membro
# ─────────────────────────────────────────────
class PokeModal(discord.ui.Modal, title="Adicionar Membro"):
    membro_id = discord.ui.TextInput(
        label="ID do Usuário",
        placeholder="Cole o ID numérico do usuário (ex: 123456789012345678)",
        min_length=17,
        max_length=20,
    )

    def __init__(self, bot, channel):
        super().__init__()
        self.bot = bot
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        valor = self.membro_id.value.strip()
        if not valor.isdigit():
            return await interaction.response.send_message(embed=ui.build_error_embed("O ID fornecido é inválido. Insira apenas números."), ephemeral=True)

        membro = await buscar_membro(self.channel.guild, int(valor))
        if not membro:
            return await interaction.response.send_message(embed=ui.build_error_embed("Membro não encontrado no servidor."), ephemeral=True)

        await self.channel.set_permissions(membro, view_channel=True, send_messages=True, attach_files=True, read_message_history=True)

        embed_dm = ui.build_embed(
            title="Convocação em Atendimento",
            description=f"Você foi convocado pela equipe do tribunal em um ticket de atendimento.\n\nClique no botão abaixo para acessar o canal.",
            color=ui.UI_COLOR_MAIN,
        )
        view_link = discord.ui.View()
        view_link.add_item(discord.ui.Button(label="Acessar Ticket", url=self.channel.jump_url, style=discord.ButtonStyle.link))
        try:
            await membro.send(embed=embed_dm, view=view_link)
        except discord.Forbidden:
            pass

        await self.channel.send(embed=ui.build_embed(title="Membro Adicionado", description=f"{membro.mention} foi adicionado ao ticket por {interaction.user.mention}.", color=ui.UI_COLOR_INFO))
        await gerar_log(self.bot, interaction.user, "Convocação", membro=membro, moderador=interaction.user.name, canal=self.channel)
        await interaction.response.send_message(embed=ui.build_success_embed(f"O membro {membro.mention} foi adicionado ao ticket e notificado."), ephemeral=True)


# ─────────────────────────────────────────────
# MODAL: Remover membro pokado
# ─────────────────────────────────────────────
class RemoverMembroModal(discord.ui.Modal, title="Remover Membro do Ticket"):
    membro_id = discord.ui.TextInput(
        label="ID do Usuário a ser removido",
        placeholder="Cole o ID numérico do usuário (ex: 123456789012345678)",
        min_length=17,
        max_length=20,
    )

    def __init__(self, bot, channel):
        super().__init__()
        self.bot = bot
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        valor = self.membro_id.value.strip()
        if not valor.isdigit():
            return await interaction.response.send_message(embed=ui.build_error_embed("O ID fornecido é inválido. Insira apenas números."), ephemeral=True)

        uid = int(valor)
        if uid == criador_id_do_canal(self.channel):
            return await interaction.response.send_message(embed=ui.build_warn_embed("Não é possível remover o autor do ticket. Use Encerrar ticket."), ephemeral=True)

        membro = await buscar_membro(self.channel.guild, uid)
        if not membro or membro not in self.channel.overwrites:
            return await interaction.response.send_message(embed=ui.build_warn_embed("Este usuário não foi adicionado neste ticket."), ephemeral=True)

        await self.channel.set_permissions(membro, overwrite=None)
        await self.channel.send(embed=ui.build_embed(title="Membro Removido", description=f"{membro.mention} foi removido do ticket por {interaction.user.mention}.", color=ui.UI_COLOR_WARNING))
        await gerar_log(self.bot, interaction.user, "Remoção de Membro do Ticket", membro=membro, moderador=interaction.user.name, canal=self.channel)
        await interaction.response.send_message(embed=ui.build_success_embed(f"{membro.mention} foi removido do ticket."), ephemeral=True)


# ─────────────────────────────────────────────
# MODAL: Abertura de ticket
# ─────────────────────────────────────────────
class ModalAbrirTicket(discord.ui.Modal):
    nome = discord.ui.TextInput(label="Nome", placeholder="Nome e sobrenome do personagem", max_length=64)
    passaporte = discord.ui.TextInput(label="Passaporte", placeholder="Apenas números", max_length=10)
    solicitacao = discord.ui.TextInput(
        label="Descreva sua solicitação",
        placeholder="Forneça o máximo de detalhes possível para agilizar seu atendimento...",
        style=discord.TextStyle.paragraph,
        min_length=10,
        max_length=1500,
    )
    anexos = discord.ui.TextInput(
        label="Anexos (opcional)",
        placeholder="Links de imagens/documentos. Também pode enviar arquivos no ticket.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500,
    )

    def __init__(self, bot, chave: str):
        self.bot = bot
        self.chave = chave
        self.tipo, _ = TIPOS_TICKET[chave]
        super().__init__(title=f"Abertura: {self.tipo}"[:45])

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)

        guild = interaction.guild
        usuario = interaction.user
        passaporte = self.passaporte.value.strip()

        if not passaporte.isdigit():
            return await interaction.followup.send(embed=ui.build_error_embed("Passaporte inválido! Use apenas números."), ephemeral=True)

        categoria = guild.get_channel(settings.TICKET_CATEGORIES.get(self.chave, 0))
        if not isinstance(categoria, discord.CategoryChannel):
            return await interaction.followup.send(embed=ui.build_error_embed("A categoria deste atendimento não está configurada. Avise a administração."), ephemeral=True)

        # ── Duplicidade: 1 ticket aberto por usuário (em qualquer categoria) ──
        for canal in guild.text_channels:
            if criador_id_do_canal(canal) == usuario.id:
                return await interaction.followup.send(
                    embed=ui.build_warn_embed(f"Você já possui um ticket em aberto em {canal.mention}. Por favor, aguarde o encerramento antes de abrir um novo."),
                    ephemeral=True,
                )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            usuario: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_permissions=True, read_message_history=True),
        }
        role_staff = guild.get_role(settings.ADMIN_ROLE_ID)
        if role_staff:
            overwrites[role_staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_messages=True, attach_files=True, read_message_history=True)

        try:
            canal = await guild.create_text_channel(
                name=f"ticket-{usuario.name}",
                category=categoria,
                overwrites=overwrites,
                topic=f"ticket:{usuario.id} | Tipo: {self.tipo}",
                reason=f"Ticket aberto por {usuario}",
            )
        except discord.Forbidden:
            return await interaction.followup.send(embed=ui.build_error_embed("Não tenho permissão para criar canais nessa categoria."), ephemeral=True)

        embed_ticket = ui.build_embed(
            title="Central de Atendimento - STMC",
            description=(
                "A equipe do tribunal analisará a sua solicitação em breve.\n"
                "Enquanto isso, envie aqui quaisquer **documentos, provas ou anexos** adicionais."
            ),
            color=ui.UI_COLOR_MAIN,
        )
        embed_ticket.add_field(name="Solicitante", value=usuario.mention, inline=True)
        embed_ticket.add_field(name="Categoria", value=f"`{self.tipo}`", inline=True)
        embed_ticket.add_field(name="\u200b", value="\u200b", inline=True)
        embed_ticket.add_field(name="Nome", value=f"`{ui.sanitizar(self.nome.value, 64)}`", inline=True)
        embed_ticket.add_field(name="Passaporte", value=f"`{passaporte}`", inline=True)
        embed_ticket.add_field(name="\u200b", value="\u200b", inline=True)
        embed_ticket.add_field(name="Solicitação", value=f"```\n{ui.sanitizar(self.solicitacao.value, 1000)}\n```", inline=False)
        if self.anexos.value.strip():
            embed_ticket.add_field(name="Anexos", value=ui.sanitizar(self.anexos.value, 500), inline=False)
        embed_ticket.set_footer(text=f"{ui.FOOTER_TEXT} • Aberto em {datetime.datetime.now().strftime('%d/%m/%Y às %H:%M')}")
        arquivo = ui.aplicar_logo(embed_ticket, guild)
        kwargs = {"file": arquivo} if arquivo else {}

        await canal.send(
            content=f"{usuario.mention} | {role_staff.mention if role_staff else ''}",
            embed=embed_ticket,
            view=TicketView(self.bot),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True, everyone=False),
            **kwargs,
        )

        await gerar_log(self.bot, usuario, "Abertura de Ticket", canal=canal, extras={"Categoria": self.tipo, "Passaporte": passaporte})
        await interaction.followup.send(embed=ui.build_success_embed(f"Ticket criado. Acesse: {canal.mention}"), ephemeral=True)


# ─────────────────────────────────────────────
# VIEW: Botões de controle do ticket (persistente)
# ─────────────────────────────────────────────
class TicketView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Solicitar atendimento", style=discord.ButtonStyle.success, custom_id="stmc_ticket_solicitar", row=0)
    async def solicitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != criador_id_do_canal(interaction.channel):
            return await interaction.response.send_message(embed=ui.build_error_embed("Apenas o autor do ticket pode solicitar atendimento."), ephemeral=True)

        espera = LIMITE_TICKET.verificar(interaction.user.id)
        if espera:
            return await interaction.response.send_message(embed=ui.build_warn_embed(f"A equipe já foi notificada. Aguarde **{espera}s** para notificar novamente."), ephemeral=True)

        await interaction.response.send_message(embed=ui.build_success_embed("Atendimento solicitado. A equipe foi notificada novamente."), ephemeral=True)
        role = interaction.guild.get_role(settings.ADMIN_ROLE_ID)
        assumido = assumido_id_do_canal(interaction.channel)
        alvo = f"<@{assumido}>" if assumido else (role.mention if role else "Equipe")
        await interaction.channel.send(f"{alvo}, o usuário {interaction.user.mention} está solicitando atenção no ticket.")
        await gerar_log(self.bot, interaction.user, "Solicitação de Atendimento (Ping)", canal=interaction.channel)

    @discord.ui.button(label="Assumir ticket", style=discord.ButtonStyle.primary, custom_id="stmc_ticket_assumir", row=0)
    async def assumir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await checar_staff(interaction):
            return

        canal = interaction.channel
        if assumido_id_do_canal(canal):
            return await interaction.response.send_message(embed=ui.build_warn_embed(f"Este ticket já foi assumido por <@{assumido_id_do_canal(canal)}>."), ephemeral=True)

        await interaction.response.defer(ephemeral=True, thinking=True)

        apelido = interaction.user.display_name.lower().replace(" ", "-")
        novo_nome = f"atendimento-{apelido}"[:100]
        novo_topico = f"{canal.topic} | assumido:{interaction.user.id}"[:1024]

        try:
            await canal.edit(name=novo_nome, topic=novo_topico)
        except discord.Forbidden:
            return await interaction.followup.send(embed=ui.build_error_embed("Sem permissão para editar o canal."), ephemeral=True)
        except discord.HTTPException:
            # Rate limit de renomear canal (2 por 10 min) — garante ao menos o tópico
            try:
                await canal.edit(topic=novo_topico)
            except discord.HTTPException:
                pass

        for item in self.children:
            if isinstance(item, discord.ui.Button) and item.custom_id == "stmc_ticket_assumir":
                item.label = f"Assumido por {interaction.user.display_name}"[:80]
                item.style = discord.ButtonStyle.secondary
                item.disabled = True
                break
        await interaction.message.edit(view=self)

        await canal.send(embed=ui.build_embed(title="Ticket Assumido", description=f"Este atendimento será conduzido por {interaction.user.mention}.", color=ui.UI_COLOR_INFO))
        await gerar_log(self.bot, interaction.user, "Ticket Assumido", canal=canal, extras={"Novo Nome do Canal": novo_nome})
        await interaction.followup.send(embed=ui.build_success_embed("Ticket assumido com sucesso."), ephemeral=True)

    @discord.ui.button(label="Convocar membro", style=discord.ButtonStyle.secondary, custom_id="stmc_ticket_poke", row=1)
    async def pokar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await checar_staff(interaction):
            return
        await interaction.response.send_modal(PokeModal(self.bot, interaction.channel))

    @discord.ui.button(label="Remover membro", style=discord.ButtonStyle.secondary, custom_id="stmc_ticket_remover", row=1)
    async def remover(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await checar_staff(interaction):
            return
        await interaction.response.send_modal(RemoverMembroModal(self.bot, interaction.channel))

    @discord.ui.button(label="Encerrar ticket", style=discord.ButtonStyle.danger, custom_id="stmc_ticket_fechar", row=1)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await checar_staff(interaction):
            return
        await interaction.response.send_modal(ModalFecharTicket(self.bot))


# ─────────────────────────────────────────────
# SELECT: Seleção de categoria do ticket (setup)
# ─────────────────────────────────────────────
class CategoriaSetupSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = [
            discord.SelectOption(label=label, description=desc, value=chave)
            for chave, (label, desc) in TIPOS_TICKET.items()
        ]
        options.append(discord.SelectOption(label="Resetar escolha", description="Limpar a seleção atual", value="resetar"))
        super().__init__(
            placeholder="Selecione o tipo de atendimento que deseja...",
            options=options,
            custom_id="stmc_setup_ticket_select",
        )

    async def callback(self, interaction: discord.Interaction):
        valor = self.values[0]
        if valor == "resetar":
            return await interaction.response.send_message(embed=ui.build_success_embed("Ação cancelada. O menu foi resetado para você."), ephemeral=True)

        espera = LIMITE_TICKET.verificar(interaction.user.id)
        if espera:
            return await interaction.response.send_message(embed=ui.build_warn_embed(f"Aguarde **{espera}s** antes de tentar abrir outro ticket."), ephemeral=True)

        await interaction.response.send_modal(ModalAbrirTicket(self.bot, valor))


class SetupView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.add_item(CategoriaSetupSelect(bot))


# ─────────────────────────────────────────────
# COG PRINCIPAL
# ─────────────────────────────────────────────
class SetupTicketsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(SetupView(self.bot))
        self.bot.add_view(TicketView(self.bot))

    @app_commands.command(name="setup_tickets", description="Painel de atendimento do tribunal")
    @app_commands.checks.cooldown(1, 10)
    async def setup_tickets(self, interaction: discord.Interaction):
        if not eh_staff(interaction.user):
            return await interaction.response.send_message(embed=ui.build_error_embed("Você não tem permissão para usar esse comando."), ephemeral=True)

        linhas = "\n".join(f"**{label}** — {desc}" for label, desc in TIPOS_TICKET.values())
        embed = ui.build_embed(
            title=f"Central de Atendimento — {settings.BOT_NOME}",
            description=(
                "Bem-vindo(a) à Central de Atendimento do tribunal.\n\n"
                "Para agilizar seu atendimento, selecione no menu abaixo a opção que melhor se encaixa na sua necessidade.\n\n"
                f"**Categorias Disponíveis:**\n{linhas}"
            ),
            color=ui.UI_COLOR_MAIN,
        )
        embed.set_footer(text=f"{ui.FOOTER_TEXT} • Selecione uma categoria para iniciar o atendimento")
        arquivo = ui.aplicar_logo(embed, interaction.guild)
        kwargs = {"file": arquivo} if arquivo else {}

        await interaction.channel.send(embed=embed, view=SetupView(self.bot), **kwargs)
        await interaction.response.send_message(embed=ui.build_success_embed("Painel de atendimento configurado."), ephemeral=True)


async def setup(bot):
    await bot.add_cog(SetupTicketsCog(bot))
