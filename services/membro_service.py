"""
membro_service.py — Camada de acesso a dados (mesmo papel do services/membro_service do molde).

Funções síncronas: chame-as com `await asyncio.to_thread(...)` para não bloquear o event loop.
Retornam dicts simples (sem objetos ORM "presos" à sessão).
"""

from datetime import datetime, timedelta

from sqlalchemy import or_, select

from database.connection import SessionLocal
from database.models import Advertencia, Blacklist, EventoLog, RegistroTribunal


def _registro_dict(r: RegistroTribunal) -> dict:
    return {
        "id": r.id,
        "discord_id": r.discord_id,
        "usuario": r.usuario,
        "nome": r.nome,
        "passaporte": r.passaporte,
        "telefone": r.telefone,
        "cargo": r.cargo,
        "aprovado": bool(r.aprovado),
    }


# ──────────────────────────────────────────────
# Registros
# ──────────────────────────────────────────────
def adicionar_registro(registro: dict):
    with SessionLocal() as session:
        membro = session.scalar(select(RegistroTribunal).where(RegistroTribunal.discord_id == registro["discord_id"]))
        if membro:
            membro.nome = registro["nome"]
            membro.passaporte = registro["passaporte"]
            membro.telefone = registro["telefone"]
            membro.usuario = registro["usuario"]
            membro.cargo = registro["cargo"]
            membro.aprovado = False
        else:
            session.add(RegistroTribunal(**registro, aprovado=False))
        session.commit()


def aprovar_registro(discord_id: int, aprovador_id: int):
    with SessionLocal() as session:
        membro = session.scalar(select(RegistroTribunal).where(RegistroTribunal.discord_id == discord_id))
        if membro:
            membro.aprovado = True
            membro.aprovado_por = aprovador_id
            session.commit()


def remover_registro(discord_id: int):
    with SessionLocal() as session:
        membro = session.scalar(select(RegistroTribunal).where(RegistroTribunal.discord_id == discord_id))
        if membro:
            session.delete(membro)
            session.commit()


def buscar_registro_por_discord_id(discord_id: int) -> dict | None:
    with SessionLocal() as session:
        membro = session.scalar(select(RegistroTribunal).where(RegistroTribunal.discord_id == discord_id))
        return _registro_dict(membro) if membro else None


def passaporte_em_uso(passaporte: str, ignorar_discord_id: int) -> bool:
    with SessionLocal() as session:
        return session.scalar(
            select(RegistroTribunal.id).where(
                RegistroTribunal.passaporte == passaporte,
                RegistroTribunal.discord_id != ignorar_discord_id,
            )
        ) is not None


def listar_registros_aprovados() -> list[dict]:
    with SessionLocal() as session:
        membros = session.scalars(
            select(RegistroTribunal).where(RegistroTribunal.aprovado.is_(True)).order_by(RegistroTribunal.cargo, RegistroTribunal.nome)
        ).all()
        return [_registro_dict(m) for m in membros]


# ──────────────────────────────────────────────
# Advertências
# ──────────────────────────────────────────────
def adicionar_advertencia(membro_id: int, tipo: str, duracao_dias: int | None, motivo: str, aplicador_id: int):
    with SessionLocal() as session:
        session.add(Advertencia(
            membro_id=membro_id, tipo=tipo, duracao_dias=duracao_dias,
            motivo=motivo, aplicador_id=aplicador_id,
        ))
        session.commit()


def contar_advertencias(membro_id: int) -> int:
    with SessionLocal() as session:
        return len(session.scalars(select(Advertencia.id).where(Advertencia.membro_id == membro_id)).all())


# ──────────────────────────────────────────────
# Blacklist
# ──────────────────────────────────────────────
def adicionar_blacklist(discord_id: int, motivo: str, dias: int | None, aplicador_id: int):
    expira = datetime.utcnow() + timedelta(days=dias) if dias else None
    with SessionLocal() as session:
        session.add(Blacklist(discord_id=discord_id, motivo=motivo, expira_em=expira, aplicador_id=aplicador_id))
        session.commit()


def blacklist_ativa(discord_id: int) -> dict | None:
    """Retorna a blacklist vigente (permanente ou não expirada), se houver."""
    agora = datetime.utcnow()
    with SessionLocal() as session:
        bl = session.scalar(
            select(Blacklist)
            .where(Blacklist.discord_id == discord_id, or_(Blacklist.expira_em.is_(None), Blacklist.expira_em > agora))
            .order_by(Blacklist.criado_em.desc())
        )
        if not bl:
            return None
        return {"motivo": bl.motivo, "expira_em": bl.expira_em}


# ──────────────────────────────────────────────
# Log de eventos
# ──────────────────────────────────────────────
def registrar_evento(autor: str, acao: str, alvo: str | None = None, extra: str | None = None):
    with SessionLocal() as session:
        session.add(EventoLog(
            autor=str(autor)[:100], acao=str(acao)[:100],
            alvo=str(alvo)[:200] if alvo else None,
            extra=str(extra)[:1000] if extra else None,
        ))
        session.commit()
