import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from config.settings import BASE_DIR
from database.models import Base

logger = logging.getLogger("bot.database")

DB_PATH = BASE_DIR / "stmc.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _migrar_colunas():
    """
    Migração leve: adiciona colunas novas em tabelas já existentes
    (create_all não altera tabelas antigas). Não apaga nenhum dado.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for tabela in Base.metadata.sorted_tables:
            if not insp.has_table(tabela.name):
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela.name)}
            for coluna in tabela.columns:
                if coluna.name in existentes:
                    continue
                tipo = coluna.type.compile(dialect=engine.dialect)
                # Nomes vêm dos modelos (código), nunca de input do usuário.
                conn.execute(text(f'ALTER TABLE "{tabela.name}" ADD COLUMN "{coluna.name}" {tipo}'))
                logger.info(f"🛠️ Coluna adicionada: {tabela.name}.{coluna.name}")


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrar_colunas()
    logger.info(f"🗄️ Banco de dados pronto: {DB_PATH.name}")


def get_session():
    return SessionLocal()
