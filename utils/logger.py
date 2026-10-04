import asyncio
import logging

from services.membro_service import registrar_evento

logger = logging.getLogger("bot.logger")


def log_console(author, action, target=None, extra=None):
    logger.info(f"Ação: {action} | Autor: {author} | Alvo: {target} | Extra: {extra}")


async def log_event_async(author, action, target=None, extra=None):
    """Log no console + banco (SQLAlchemy) sem bloquear o event loop."""
    log_console(author, action, target, extra)
    try:
        await asyncio.to_thread(registrar_evento, author, action, target, extra)
    except Exception as e:
        logger.error(f"Erro ao logar evento async: {e}", exc_info=True)
