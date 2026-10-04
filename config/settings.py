"""
settings.py — Configuração centralizada do STMC.

Todos os IDs são lidos do arquivo .env. O parser é tolerante a:
  - comentários inline  (ex: ADMIN_ROLE_ID=123 # cargo admin)
  - listas por vírgula  (ex: CARGO_ESTAGIARIO_ID=111, 222)
  - valores vazios      (retorna 0 / lista vazia — o recurso fica desativado)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _raw(*nomes: str) -> str:
    """Retorna o primeiro valor não-vazio entre os nomes informados, sem comentários."""
    for nome in nomes:
        valor = os.getenv(nome)
        if valor:
            return valor.split("#", 1)[0].strip()
    return ""


def get_int(*nomes: str) -> int:
    valor = _raw(*nomes)
    return int(valor) if valor.isdigit() else 0


def get_int_list(*nomes: str) -> list[int]:
    valor = _raw(*nomes)
    return [int(p.strip()) for p in valor.split(",") if p.strip().isdigit()]


# ──────────────────────────────────────────────
# Geral
# ──────────────────────────────────────────────
BOT_NOME = "Supremo Tribunal de Meta City"
BOT_SIGLA = "STMC"
LOGO_PATH = BASE_DIR / "image.png"

# ──────────────────────────────────────────────
# Cargos de staff
# ──────────────────────────────────────────────
ADMIN_ROLE_ID = get_int("ADMIN_ROLE_ID")
RECRUTADOR_ROLE_ID = get_int("RECRUTADOR_ROLE_ID")
# Cargo extra com permissão de advertir/exonerar (opcional — Admin sempre pode)
PERM_ADVERTENCIA_ROLE_ID = get_int("PERM_ADVERTENCIA_ROLE_ID")

# ──────────────────────────────────────────────
# Tickets
# ──────────────────────────────────────────────
LOG_CHANNEL_ID = get_int("LOG_CHANNEL_ID")
TICKET_CATEGORIES = {
    "troca_nome": get_int("TICKET_CATEGORY_NOME_ID"),
    "certidoes":  get_int("TICKET_CATEGORY_CERTIDAO_ID"),
    "patentes":   get_int("TICKET_CATEGORY_PATENTE_ID"),
    "cnpj":       get_int("TICKET_CATEGORY_CNPJ_ID"),
    "porte_arma": get_int("TICKET_CATEGORY_PORTE_ID"),
    "processo":   get_int("TICKET_CATEGORY_PROCESSO_ID"),
}

# ──────────────────────────────────────────────
# Registro
# ──────────────────────────────────────────────
CARGOS_ADVOGADO = get_int_list("CARGO_ESTAGIARIO_ID")
CARGOS_SEGURANCA = get_int_list("CARGO_SEGURANÇA_ID", "CARGO_SEGURANCA_ID")
CANAL_APROVACAO_REGISTRO_ID = get_int("CANAL_APROVACAO_REGISTRO_ID")
CANAL_LOGS_REGISTRO_ID = get_int("CANAL_LOGS_REGISTRO_ID")

# ──────────────────────────────────────────────
# Advertências
# ──────────────────────────────────────────────
CARGOS_ADVERTENCIA = {
    "ADV1": get_int("ADV_1_ID"),
    "ADV2": get_int("ADV_2_ID"),
    "ADV3": get_int("ADV_3_ID"),
}
CANAL_PENALIDADES_ID = get_int("CANAL_PENALIDADES_ID")
CANAL_LOGS_ADV_ID = get_int("CANAL_LOGS_ADV_ID")

# ──────────────────────────────────────────────
# Exoneração
# ──────────────────────────────────────────────
CARGO_EXONERADO_ID = get_int("CARGO_EXONERADO_ID")
CANAL_EXONERACAO_ID = get_int("CANAL_EXONERACAO_ID")
CANAL_BLACKLIST_ID = get_int("CANAL_BLACKLIST_ID")
