"""
models.py — Modelos SQLAlchemy do STMC.

Todas as consultas passam pelo ORM (parâmetros vinculados / bind params),
o que impede SQL Injection: nenhum input do usuário é concatenado em SQL.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class RegistroTribunal(Base):
    __tablename__ = "registros"

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_id = Column(BigInteger, unique=True, nullable=False, index=True)
    usuario = Column(String(64), nullable=False, default="")
    nome = Column(String(64), nullable=False)
    passaporte = Column(String(32), nullable=False)
    telefone = Column(String(16), nullable=False, default="")
    cargo = Column(String(32), nullable=False)          # "advogado" | "seguranca"
    aprovado = Column(Boolean, default=False)
    aprovado_por = Column(BigInteger, nullable=True)
    criado_em = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<RegistroTribunal(nome='{self.nome}', passaporte='{self.passaporte}', cargo='{self.cargo}')>"


class Advertencia(Base):
    __tablename__ = "advertencias"

    id = Column(Integer, primary_key=True, autoincrement=True)
    membro_id = Column(BigInteger, nullable=False, index=True)
    tipo = Column(String(8), nullable=False)
    duracao_dias = Column(Integer, nullable=True)       # None = permanente
    motivo = Column(String(500), nullable=False)
    aplicador_id = Column(BigInteger, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)


class Blacklist(Base):
    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    discord_id = Column(BigInteger, nullable=False, index=True)
    motivo = Column(String(500), nullable=False)
    expira_em = Column(DateTime, nullable=True)         # None = permanente
    aplicador_id = Column(BigInteger, nullable=False)
    criado_em = Column(DateTime, default=datetime.utcnow)


class EventoLog(Base):
    __tablename__ = "eventos_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    autor = Column(String(100))
    acao = Column(String(100))
    alvo = Column(String(200))
    extra = Column(String(1000))
    timestamp = Column(DateTime, default=datetime.utcnow)
