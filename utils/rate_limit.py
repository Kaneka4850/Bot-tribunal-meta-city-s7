"""
rate_limit.py — Rate limit em memória para interações (botões, selects, modais).

Slash commands usam o cooldown nativo (app_commands.checks.cooldown).
Componentes persistentes não têm cooldown nativo, então usamos este limitador.
"""

import time
from collections import defaultdict, deque


class RateLimiter:
    """Permite `limite` ações por usuário dentro de `janela` segundos."""

    def __init__(self, limite: int, janela: float):
        self.limite = limite
        self.janela = janela
        self._hits: dict[int, deque] = defaultdict(deque)

    def verificar(self, user_id: int) -> float:
        """
        Registra a tentativa. Retorna 0 se permitido, ou os segundos
        restantes até a próxima tentativa liberada.
        """
        agora = time.monotonic()
        fila = self._hits[user_id]
        while fila and agora - fila[0] > self.janela:
            fila.popleft()

        if len(fila) >= self.limite:
            return round(self.janela - (agora - fila[0]), 1)

        fila.append(agora)
        return 0.0

    def limpar(self):
        """Remove usuários sem registros recentes (evita crescer a memória)."""
        agora = time.monotonic()
        for uid in [u for u, f in self._hits.items() if not f or agora - f[-1] > self.janela]:
            del self._hits[uid]


# Limitadores compartilhados
LIMITE_TICKET = RateLimiter(limite=2, janela=60)      # abrir ticket
LIMITE_REGISTRO = RateLimiter(limite=2, janela=60)    # enviar registro
LIMITE_STAFF = RateLimiter(limite=10, janela=30)      # ações de staff (botões/modais)
