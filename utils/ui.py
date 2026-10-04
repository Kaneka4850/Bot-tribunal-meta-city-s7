import discord

from config import settings

# ==========================================
# Constantes de Cores e Estilos (Design System)
# ==========================================
UI_COLOR_MAIN = 0x2b2d31
UI_COLOR_GOLD = 0xF5C518
UI_COLOR_SUCCESS = discord.Color.brand_green()
UI_COLOR_ERROR = discord.Color.brand_red()
UI_COLOR_WARNING = discord.Color.gold()
UI_COLOR_INFO = discord.Color.blurple()

# ==========================================
# Emojis Padrões (Removidos para manter tom institucional)
# ==========================================
EMOJI_SUCCESS = ""
EMOJI_ERROR = ""
EMOJI_WARN = ""
EMOJI_INFO = ""
EMOJI_LOCK = ""
EMOJI_TICKET = ""

# ==========================================
# Configurações Globais
# ==========================================
FOOTER_TEXT = f"{settings.BOT_SIGLA} | {settings.BOT_NOME}"
LOGO_FILENAME = "logo_stmc.png"


def build_embed(title: str, description: str, color: int = UI_COLOR_MAIN) -> discord.Embed:
    """Cria um embed padrão do sistema com o rodapé e a cor configurados."""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=FOOTER_TEXT)
    return embed


def build_success_embed(message: str, title: str = "Sucesso") -> discord.Embed:
    return build_embed(title=title, description=message, color=UI_COLOR_SUCCESS)


def build_error_embed(message: str, title: str = "Erro") -> discord.Embed:
    return build_embed(title=title, description=message, color=UI_COLOR_ERROR)


def build_warn_embed(message: str, title: str = "Aviso") -> discord.Embed:
    return build_embed(title=title, description=message, color=UI_COLOR_WARNING)


def logo_file() -> discord.File | None:
    """Retorna a logo do tribunal como anexo (ou None se o arquivo não existir)."""
    if settings.LOGO_PATH.exists():
        return discord.File(settings.LOGO_PATH, filename=LOGO_FILENAME)
    return None


def aplicar_logo(embed: discord.Embed, guild: discord.Guild | None = None) -> discord.File | None:
    """
    Coloca a logo do STMC como thumbnail. Se a imagem não existir,
    usa o ícone do servidor. Retorna o File que deve ser enviado junto.
    """
    arquivo = logo_file()
    if arquivo:
        embed.set_thumbnail(url=f"attachment://{LOGO_FILENAME}")
    elif guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return arquivo


def sanitizar(texto: str, limite: int = 1000) -> str:
    """Remove quebras de bloco de código e limita o tamanho de textos do usuário."""
    return (texto or "").replace("```", "'''").strip()[:limite]
