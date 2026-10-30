from datetime import datetime
from decimal import Decimal

import pytest

import app as modulo_app
from app import app, estufa
from catalogo import ENCOMENDA, PICKUP, preco_salgado
from horario import aceita_pickup, promocao_ativa, situacao
from pedido import PedidoInvalido, montar_mensagem, normalizar_item, validar_pedido

SEXTA = (2026, 10, 30)
SABADO = (2026, 10, 31)
DOMINGO = (2026, 11, 1)
CLIENTE = {"nome": "Ana", "telefone": "21985209765"}


@pytest.mark.parametrize("dia, hora, minuto, esperado", [
    (SEXTA, 15, 59, False), (SEXTA, 16, 0, True), (SEXTA, 18, 29, True), (SEXTA, 18, 30, False),
    (SABADO, 14, 59, False), (SABADO, 15, 0, True), (SABADO, 17, 0, False), (DOMINGO, 16, 0, False),
])
def test_horario_da_promocao(dia, hora, minuto, esperado):
    assert promocao_ativa(datetime(*dia, hora, minuto)) is esperado


def test_precos_e_promocao():
    assert preco_salgado("coxinha", "grande", PICKUP, promocao=True) == Decimal("5.50")
    assert preco_salgado("coxinha", "grande", ENCOMENDA, promocao=True) == Decimal("4.00")  # não vale na encomenda
    assert preco_salgado("coxinha", "pequeno", PICKUP, promocao=True) == Decimal("2.50")
    assert preco_salgado("hamburguer", "grande", PICKUP, promocao=True) == Decimal("7.00")
    assert preco_salgado("hamburguer_forno", "grande", PICKUP, promocao=True) == Decimal("5.50")
    for modo in (PICKUP, ENCOMENDA):
        assert preco_salgado("empadao", "grande", modo, promocao=True) == Decimal("11.00")


def test_faixa_conforme_o_horario():
    assert situacao(datetime(*SEXTA, 10, 0))["tipo"] == "aberta"
    assert situacao(datetime(*SEXTA, 16, 30))["tipo"] == "promocao"
    assert "Abrimos hoje às 8:30" in situacao(datetime(*SEXTA, 7, 40))["mensagem"]
    assert "Abrimos amanhã às 8:30" in situacao(datetime(*SEXTA, 19, 0))["mensagem"]
    assert "Abrimos segunda às 8:30" in situacao(datetime(*SABADO, 17, 30))["mensagem"]
    assert "Abrimos amanhã às 8:30" in situacao(datetime(*DOMINGO, 10, 0))["mensagem"]
    assert aceita_pickup(datetime(*SEXTA, 7, 40))  # reserva a caminho do trabalho
    assert not aceita_pickup(datetime(*DOMINGO, 10, 0))


def test_pedido_pickup_em_promocao():
    item = normalizar_item({"produto": "coxinha", "opcao": "grande", "quantidade": 2}, PICKUP)
    pedido = validar_pedido({**CLIENTE, "horario_retirada": "16:40", "momento_pagamento": "antecipado"},
                            [item], datetime(*SEXTA, 16, 10), PICKUP, {("coxinha", "grande", ""): 2})
    assert pedido.total == Decimal("11.00")
    assert "Promoção aplicada" in montar_mensagem(pedido, "Loja")


@pytest.mark.parametrize("hora", ["08:00", "18:31"])
def test_retirada_pickup_fora_do_horario(hora):
    item = normalizar_item({"produto": "coxinha", "opcao": "grande", "quantidade": 1}, PICKUP)
    with pytest.raises(PedidoInvalido) as erro:
        validar_pedido({**CLIENTE, "horario_retirada": hora, "momento_pagamento": "antecipado"},
                       [item], datetime(*SEXTA, 7, 40), PICKUP, {("coxinha", "grande", ""): 1})
    assert "horario_retirada" in erro.value.erros


@pytest.mark.parametrize("data, hora", [("2026-11-08", "10:00"), ("2026-11-07", "17:30"), ("2026-11-06", "08:00")])
def test_encomenda_so_retira_com_loja_aberta(data, hora):
    item = normalizar_item({"produto": "maca", "opcao": "grande", "quantidade": 10})
    with pytest.raises(PedidoInvalido) as erro:
        validar_pedido({**CLIENTE, "data": data, "horario": hora, "pagamento": "pix", "sinal": "20"},
                       [item], datetime(*SEXTA, 10, 0))
    assert "data" in erro.value.erros


def test_api_muda_sozinha_e_bloqueia_fechado(monkeypatch):
    estufa.definir({("coxinha", "grande", ""): 3})
    cliente = app.test_client()
    item = {"modo": PICKUP, "produto": "coxinha", "opcao": "grande", "quantidade": 1}

    monkeypatch.setattr(modulo_app, "agora_loja", lambda: datetime(*SEXTA, 16, 0))
    assert cliente.get("/api/loja").get_json()["promocao"] is True
    assert cliente.get("/api/estufa").get_json()["itens"][0]["preco"]["texto"] == "R$ 5,50"
    assert cliente.post("/api/carrinho", json=item).get_json()["subtotal"]["texto"] == "R$ 5,50"
    assert "Promoção no ar" in cliente.get("/").get_data(as_text=True)

    cliente.delete("/api/carrinho")
    monkeypatch.setattr(modulo_app, "agora_loja", lambda: datetime(*DOMINGO, 10, 0))
    assert cliente.post("/api/carrinho", json=item).status_code == 409
    estufa.definir({("coxinha", "grande", ""): 0})
