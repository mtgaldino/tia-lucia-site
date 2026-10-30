from datetime import datetime
from decimal import Decimal

import pytest

from app import app, estufa
from catalogo import ENCOMENDA, PICKUP
from estufa import EstoqueInsuficiente
from pedido import (
    ItemInvalido,
    PedidoInvalido,
    conferir_estoque,
    montar_mensagem,
    normalizar_item,
    resumo_carrinho,
    validar_pedido,
)

AGORA = datetime(2026, 10, 30, 7, 40)
CLIENTE = {"nome": "João", "telefone": "21985209765"}


def salgado(produto, tamanho, quantidade, sabor=None, modo=ENCOMENDA):
    return normalizar_item({"produto": produto, "opcao": tamanho, "sabor": sabor, "quantidade": quantidade}, modo)


@pytest.fixture(autouse=True)
def estufa_vazia():
    estufa.definir({chave: 0 for chave in estufa.quantidades()})


def test_preco_muda_entre_balcao_e_encomenda():
    carrinho = [salgado("coxinha", "grande", 2), salgado("empada", "pequeno", 2, sabor="frango")]
    assert resumo_carrinho(carrinho, PICKUP)["subtotal"] == Decimal("19.00")  # 2 x 7,00 + 2 x 2,50
    assert resumo_carrinho(carrinho, ENCOMENDA)["subtotal"] == Decimal("13.00")  # 2 x 4,00 + 2 x 2,50


def test_sabor_e_tamanho_validados():
    with pytest.raises(ItemInvalido):
        salgado("empada", "grande", 1)  # empada exige sabor
    with pytest.raises(ItemInvalido):
        salgado("empadao", "pequeno", 1, sabor="frango")  # empadão só grande
    with pytest.raises(ItemInvalido):
        salgado("joelho", "grande", 1, sabor="calabresa")  # joelho: frango ou queijo c/ presunto
    assert salgado("coxinha", "grande", 1, sabor="frango")["sabor"] == ""


def test_doces_nao_entram_no_pickup():
    with pytest.raises(ItemInvalido):
        normalizar_item({"produto": "maca", "opcao": "grande", "quantidade": 1}, PICKUP)


def test_conferir_estoque():
    carrinho = [salgado("coxinha", "grande", 3, modo=PICKUP)]
    assert conferir_estoque(carrinho, {("coxinha", "grande", ""): 3}) == []
    assert conferir_estoque(carrinho, {("coxinha", "grande", ""): 2}) == ["Coxinha grande: só restam 2 na estufa."]
    assert conferir_estoque(carrinho, {}) == ["Coxinha grande: acabou na estufa."]


def test_pedido_pickup_antecipado():
    carrinho = [salgado("pastel_forno", "grande", 2, sabor="carne", modo=PICKUP)]
    dados = {**CLIENTE, "horario_retirada": "08:40", "momento_pagamento": "antecipado"}
    pedido = validar_pedido(dados, carrinho, AGORA, PICKUP, {("pastel_forno", "grande", "carne"): 5})
    assert pedido.total == Decimal("14.00") and pedido.pagamento == "pix"

    mensagem = montar_mensagem(pedido, "Loja", codigo="A1B2")
    assert "*PEDIDO PICK-UP — Loja*" in mensagem
    assert "*Código da reserva:* A1B2" in mensagem
    assert "2x Pastel de forno grande | Sabor: Carne — R$ 7,00 cada = R$ 14,00" in mensagem
    assert "*Retirada:* hoje, 30/10/2026 às 08:40" in mensagem
    assert "*Pagamento:* Antecipado via PIX" in mensagem
    assert "sinal" not in mensagem.lower()


def test_pedido_pickup_regras():
    carrinho = [salgado("coxinha", "grande", 4, modo=PICKUP)]
    with pytest.raises(PedidoInvalido) as erro:
        validar_pedido({**CLIENTE, "horario_retirada": "07:00", "momento_pagamento": "retirada"},
                       carrinho, AGORA, PICKUP, {("coxinha", "grande", ""): 1})
    assert set(erro.value.erros) == {"horario_retirada", "pagamento", "carrinho"}

    pedido = validar_pedido({**CLIENTE, "horario_retirada": "08:30", "momento_pagamento": "retirada",
                             "pagamento": "dinheiro"}, carrinho, AGORA, PICKUP, {("coxinha", "grande", ""): 4})
    assert "*Pagamento:* Na retirada — Dinheiro" in montar_mensagem(pedido, "Loja")


def test_encomenda_de_salgados_sem_minimo_com_sinal():
    carrinho = [salgado("coxinha", "pequeno", 1)]
    pedido = validar_pedido({**CLIENTE, "data": "2026-11-10", "horario": "14:00", "pagamento": "pix",
                             "sinal": "2.50"}, carrinho, AGORA)
    assert pedido.total == Decimal("2.50") and pedido.sinal == Decimal("2.50")


def test_reserva_desconta_e_cancelamento_devolve():
    estufa.definir({("coxinha", "grande", ""): 3})
    itens = [{"produto": "coxinha", "opcao": "grande", "sabor": "", "quantidade": 2, "descricao": "Coxinha grande"}]
    reserva = dict(cliente="A", telefone="(21) 9", retirada_em=AGORA, pagamento="PIX", total="R$ 14,00")

    codigo = estufa.reservar(itens, **reserva)
    assert estufa.quantidades()[("coxinha", "grande", "")] == 1
    with pytest.raises(EstoqueInsuficiente):
        estufa.reservar(itens, **reserva)
    assert estufa.quantidades()[("coxinha", "grande", "")] == 1  # a tentativa que falhou não mexe na estufa

    assert estufa.cancelar(codigo)
    assert estufa.quantidades()[("coxinha", "grande", "")] == 3
    assert not estufa.cancelar(codigo)
    assert estufa.reservas() == []


def test_fluxo_pickup_pela_api():
    estufa.definir({("empada", "grande", "frango"): 2})
    cliente = app.test_client()

    assert cliente.get("/api/estufa").get_json()["itens"][0]["preco"]["texto"] == "R$ 7,00"

    item = {"modo": PICKUP, "produto": "empada", "opcao": "grande", "sabor": "frango"}
    assert cliente.post("/api/carrinho", json={**item, "quantidade": 3}).status_code == 409  # só tem 2
    assert cliente.post("/api/carrinho", json={**item, "quantidade": 2}).status_code == 201

    doce = {"modo": ENCOMENDA, "produto": "maca", "opcao": "grande", "quantidade": 1}
    conflito = cliente.post("/api/carrinho", json=doce)
    assert conflito.status_code == 409 and conflito.get_json()["conflito"]

    dados = {**CLIENTE, "horario_retirada": "10:30", "momento_pagamento": "antecipado"}
    assert cliente.post("/api/pedido", json=dados).status_code == 200
    assert estufa.quantidades()[("empada", "grande", "frango")] == 2  # revisar não reserva

    enviado = cliente.post("/api/pedido/enviar", json=dados).get_json()
    assert enviado["codigo"] and f"C%C3%B3digo%20da%20reserva%3A%2A%20{enviado['codigo']}" in enviado["whatsapp"]
    assert estufa.quantidades()[("empada", "grande", "frango")] == 0
    assert cliente.get("/api/carrinho").get_json()["itens"] == []
    assert [r["codigo"] for r in estufa.reservas()] == [enviado["codigo"]]
    estufa.cancelar(enviado["codigo"])


def test_painel_exige_senha_e_salva_estufa():
    cliente = app.test_client()
    assert cliente.post("/painel/estufa", data={"q:coxinha:grande:": "9"}).status_code == 302
    assert estufa.quantidades()[("coxinha", "grande", "")] == 0

    assert cliente.post("/painel/entrar", data={"senha": "errada"}).status_code == 401
    cliente.post("/painel/entrar", data={"senha": "senha-de-teste"})
    cliente.post("/painel/estufa", data={"q:coxinha:grande:": "9", "q:joelho:pequeno:frango": "4",
                                         "q:empadao:pequeno:frango": "5"})
    quantidades = estufa.quantidades()
    assert quantidades[("coxinha", "grande", "")] == 9
    assert quantidades[("joelho", "pequeno", "frango")] == 4
    assert ("empadao", "pequeno", "frango") not in quantidades  # não existe empadão pequeno
    assert "Coxinha" in cliente.get("/painel").get_data(as_text=True)


def test_hamburguer_so_no_balcao_ou_pickup():
    with pytest.raises(ItemInvalido):
        salgado("hamburguer", "grande", 1)
    assert salgado("hamburguer", "grande", 1, modo=PICKUP)["produto"] == "hamburguer"
    assert salgado("hamburguer_forno", "grande", 1)["produto"] == "hamburguer_forno"
    pagina = app.test_client().get("/").get_data(as_text=True)
    assert 'data-produto="hamburguer"' not in pagina and 'data-produto="hamburguer_forno"' in pagina
    assert 'name="quantidade" value="0"' in pagina and 'value="25"' not in pagina
