"""Estoque da estufa e reservas de pick-up, guardados em SQLite."""

import json
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from catalogo import variacoes_salgados


class EstoqueInsuficiente(Exception):
    pass


class Estufa:
    def __init__(self, caminho: str | Path):
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._conexao() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS estoque (
                    salgado TEXT NOT NULL,
                    tamanho TEXT NOT NULL,
                    sabor TEXT NOT NULL DEFAULT '',
                    quantidade INTEGER NOT NULL DEFAULT 0 CHECK (quantidade >= 0),
                    PRIMARY KEY (salgado, tamanho, sabor)
                );
                CREATE TABLE IF NOT EXISTS reservas (
                    codigo TEXT PRIMARY KEY,
                    criada_em TEXT NOT NULL,
                    retirada_em TEXT NOT NULL,
                    cliente TEXT NOT NULL,
                    telefone TEXT NOT NULL,
                    pagamento TEXT NOT NULL,
                    total TEXT NOT NULL,
                    itens TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pendente'
                );
            """)

    @contextmanager
    def _conexao(self):
        con = sqlite3.connect(self.caminho, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def _transacao(self):
        """BEGIN IMMEDIATE trava a escrita, então duas reservas nunca levam a mesma unidade."""
        with self._conexao() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
            except BaseException:
                con.execute("ROLLBACK")
                raise
            con.execute("COMMIT")

    # --- Estoque --------------------------------------------------------------

    def quantidades(self) -> dict[tuple[str, str, str], int]:
        """Quantidade de cada (salgado, tamanho, sabor) do catálogo; o que não foi lançado vale 0."""
        with self._conexao() as con:
            salvas = {(r["salgado"], r["tamanho"], r["sabor"]): r["quantidade"]
                      for r in con.execute("SELECT * FROM estoque")}
        return {chave: salvas.get(chave, 0) for chave in variacoes_salgados()}

    def definir(self, quantidades: dict[tuple[str, str, str], int]) -> None:
        validas = set(variacoes_salgados())
        with self._transacao() as con:
            for chave, quantidade in quantidades.items():
                if chave in validas:
                    con.execute(
                        "INSERT INTO estoque (salgado, tamanho, sabor, quantidade) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (salgado, tamanho, sabor) DO UPDATE SET quantidade = excluded.quantidade",
                        (*chave, max(0, int(quantidade))),
                    )

    # --- Reservas -------------------------------------------------------------

    def reservar(self, itens: list[dict], *, cliente: str, telefone: str, retirada_em: datetime,
                 pagamento: str, total: str) -> str:
        """Tira os itens da estufa e registra a reserva. Devolve o código para o cliente."""
        with self._transacao() as con:
            faltando = []
            for item in itens:
                cursor = con.execute(
                    "UPDATE estoque SET quantidade = quantidade - ? "
                    "WHERE salgado = ? AND tamanho = ? AND sabor = ? AND quantidade >= ?",
                    (item["quantidade"], item["produto"], item["opcao"], item["sabor"], item["quantidade"]),
                )
                if cursor.rowcount == 0:
                    faltando.append(item)
            if faltando:
                raise EstoqueInsuficiente(faltando)

            while True:
                codigo = secrets.token_hex(2).upper()
                if not con.execute("SELECT 1 FROM reservas WHERE codigo = ?", (codigo,)).fetchone():
                    break
            con.execute(
                "INSERT INTO reservas (codigo, criada_em, retirada_em, cliente, telefone, pagamento, total, itens) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (codigo, datetime.now().isoformat(timespec="seconds"), retirada_em.isoformat(timespec="minutes"),
                 cliente, telefone, pagamento, total, json.dumps(itens, ensure_ascii=False)),
            )
        return codigo

    def reservas(self, status: str = "pendente") -> list[dict]:
        with self._conexao() as con:
            linhas = con.execute("SELECT * FROM reservas WHERE status = ? ORDER BY retirada_em", (status,)).fetchall()
        return [{**dict(linha), "itens": json.loads(linha["itens"]),
                 "retirada_em": datetime.fromisoformat(linha["retirada_em"])} for linha in linhas]

    def concluir(self, codigo: str) -> bool:
        with self._transacao() as con:
            cursor = con.execute(
                "UPDATE reservas SET status = 'retirada' WHERE codigo = ? AND status = 'pendente'", (codigo,))
        return cursor.rowcount == 1

    def cancelar(self, codigo: str) -> bool:
        """Cancela a reserva e devolve as unidades para a estufa."""
        with self._transacao() as con:
            linha = con.execute(
                "SELECT itens FROM reservas WHERE codigo = ? AND status = 'pendente'", (codigo,)).fetchone()
            if linha is None:
                return False
            for item in json.loads(linha["itens"]):
                con.execute(
                    "INSERT INTO estoque (salgado, tamanho, sabor, quantidade) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (salgado, tamanho, sabor) DO UPDATE SET quantidade = quantidade + excluded.quantidade",
                    (item["produto"], item["opcao"], item["sabor"], item["quantidade"]),
                )
            con.execute("UPDATE reservas SET status = 'cancelada' WHERE codigo = ?", (codigo,))
        return True
