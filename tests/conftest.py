import os
import tempfile

# O app abre o banco ao ser importado; os testes usam uma pasta temporária.
os.environ["PASTA_DADOS"] = tempfile.mkdtemp(prefix="loja-testes-")
os.environ["PAINEL_SENHA"] = "senha-de-teste"


import pytest


@pytest.fixture(autouse=True)
def relogio_da_loja(monkeypatch):
    """Por padrão, os testes rodam numa sexta às 10h, com a loja aberta e sem promoção."""
    from datetime import datetime

    import app as modulo_app

    monkeypatch.setattr(modulo_app, "agora_loja", lambda: datetime(2026, 10, 30, 10, 0))
