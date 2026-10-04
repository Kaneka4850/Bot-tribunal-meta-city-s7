"""
permissao.py — Regras de permissão do STMC.

Regra geral (vale para TODOS os comandos/botões):
  ✔ Quem possui permissão de Administrador no servidor pode usar tudo.
  ✔ Caso contrário, precisa ter algum dos cargos declarados para aquela função.
"""

import discord

from config import settings


def is_admin(member: discord.abc.User) -> bool:
    perms = getattr(member, "guild_permissions", None)
    return bool(perms and perms.administrator)


def tem_algum_cargo(member: discord.abc.User, cargos_ids) -> bool:
    ids = {c for c in cargos_ids if c}
    return any(r.id in ids for r in getattr(member, "roles", []))


def pode(member: discord.abc.User, *cargos_ids: int) -> bool:
    """Administrador OU possui algum dos cargos informados."""
    return is_admin(member) or tem_algum_cargo(member, cargos_ids)


# ── Atalhos por função ─────────────────────────────────────
def eh_staff(member) -> bool:
    """Equipe do tribunal (atendimento de tickets, setups)."""
    return pode(member, settings.ADMIN_ROLE_ID)


def pode_recrutar(member) -> bool:
    return pode(member, settings.ADMIN_ROLE_ID, settings.RECRUTADOR_ROLE_ID)


def pode_advertir(member) -> bool:
    return pode(member, settings.ADMIN_ROLE_ID, settings.PERM_ADVERTENCIA_ROLE_ID)
