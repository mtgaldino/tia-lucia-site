from datetime import datetime
from decimal import Decimal

import pytest

from app import app
from pedido import (
    ItemInvalido,
    PedidoInvalido,
    adicionar_item,
    montar_mensagem,
    normalizar_item,
    validar_pedido,
)

AGORA = datetime(2026, 10, 29, 12, 0)
CLIENTE = {
    "nome": "Maria Silva",
    "telefone": "(11) 98765-4321",
    "data": "2026-11-05",
    "horario": "15:30",
    "pagamento": "pix",
}


def item(produto, opcao, quantidade, cor=None):
    return normalizar_item({"produto": produto, "opcao": opcao, "cor": cor, "quantidade": quantidade})


def test_algodao_exige_cor_valida():
    with pytest.raises(ItemInvalido):
        item("algodao", "palito", 1)
    with pytest.raises(ItemInvalido):
        item("algodao", "palito", 1, cor="preto")


def test_maca_ignora_cor():
    assert item("maca", "grande", 2, cor="rosa")["cor"] is None


def test_itens_iguais_somam_quantidade():
    carrinho = adicionar_item([], item("maca", "pequena", 2))
    carrinho = adicionar_item(carrinho, item("maca", "pequena", 3))
    assert len(carrinho) == 1 and carrinho[0]["quantidade"] == 5


def test_pedido_com_esteira_soma_aluguel():
    carrinho = [item("algodao", "pote200", 10, cor="rosa"), item("maca", "grande", 4)]
    pedido = validar_pedido({**CLIENTE, "modo_entrega": "esteira", "sinal": "30,00"}, carrinho, AGORA)
    assert pedido.resumo["subtotal"] == Decimal("67.00")  # 10 x 4,50 + 4 x 5,50
    assert pedido.total == Decimal("87.00")
    assert pedido.restante == Decimal("57.00")

    mensagem = montar_mensagem(pedido, "Loja")
    assert "*Nome do cliente:* Maria Silva" in mensagem
    assert "*Telefone/Celular:* (11) 98765-4321" in mensagem
    assert "Tipo: Pote 200ml | Cor: Rosa" in mensagem
    assert "*Quantidade:* 14 unidade(s)" in mensagem
    assert "*Preço total + esteira:* R$ 87,00" in mensagem
    assert "*Data + horário da retirada no local:* 05/11/2026 às 15:30" in mensagem
    assert "*Método de pagamento:* PIX" in mensagem
    assert "*Valor do sinal:* R$ 30,00" in mensagem


def test_palito_mostra_tamanho_do_saco():
    pedido = validar_pedido({**CLIENTE, "modo_entrega": "caixa", "sinal": "20"},
                            [item("algodao", "palito", 10, cor="colorido")], AGORA)
    mensagem = montar_mensagem(pedido, "Loja")
    assert "Tipo: Palito (Saco 17x35 cm) | Cor: Colorido" in mensagem
    assert "*Modo de retirada:* Caixa" in mensagem


def test_sinal_minimo_de_20_reais():
    carrinho = [item("maca", "grande", 10)]
    with pytest.raises(PedidoInvalido) as erro:
        validar_pedido({**CLIENTE, "sinal": "19.99"}, carrinho, AGORA)
    assert "sinal" in erro.value.erros


def test_pedido_menor_que_20_tem_sinal_igual_ao_total():
    pedido = validar_pedido({**CLIENTE, "sinal": "3.80"}, [item("maca", "pequena", 1)], AGORA)
    assert pedido.sinal == Decimal("3.80") and pedido.restante == 0


def test_sem_algodao_nao_pede_modo_de_entrega():
    pedido = validar_pedido({**CLIENTE, "sinal": "20"}, [item("maca", "grande", 10)], AGORA)
    assert pedido.modo_entrega is None
    assert "Modo de retirada" not in montar_mensagem(pedido, "Loja")


def test_campos_obrigatorios_e_data_passada():
    carrinho = [item("algodao", "pote300", 5, cor="azul")]
    with pytest.raises(PedidoInvalido) as erro:
        validar_pedido({"data": "2026-10-28", "horario": "10:00"}, carrinho, AGORA)
    assert set(erro.value.erros) >= {"nome", "telefone", "data", "pagamento", "modo_entrega"}


def test_fluxo_pela_api():
    cliente = app.test_client()
    resposta = cliente.post("/api/carrinho", json={"produto": "algodao", "opcao": "pote300",
                                                   "cor": "lilas", "quantidade": 3})
    assert resposta.status_code == 201
    assert resposta.get_json()["subtotal"]["texto"] == "R$ 19,50"

    pedido = {**CLIENTE, "data": "2099-01-01", "modo_entrega": "caixa", "sinal": "19.50"}
    resposta = cliente.post("/api/pedido", json=pedido)
    assert resposta.status_code == 200, resposta.get_json()
    assert "Cor: Lilás" in resposta.get_json()["mensagem"]

    dados = cliente.post("/api/pedido/enviar", json=pedido).get_json()
    assert dados["whatsapp"].startswith("https://wa.me/")
    assert "Lil%C3%A1s" in dados["whatsapp"]
    assert dados["codigo"] is None  # encomenda não reserva nada
    assert cliente.get("/api/carrinho").get_json()["itens"] == []


def test_algodao_mescla_cores():
    mescla = item("algodao", "palito", 1, cor=["amarelo", "azul", "verde"])
    assert mescla["cor"] == "azul+verde+amarelo"  # ordem do catálogo, para somar pedidos iguais
    dados = {**CLIENTE, "modo_entrega": "caixa", "sinal": "3"}
    assert "Cores: Azul, Verde e Amarelo" in montar_mensagem(validar_pedido(dados, [mescla], AGORA), "Loja")
    dupla = item("algodao", "palito", 1, cor=["rosa", "verde"])
    assert "Cores: Verde e Rosa" in montar_mensagem(validar_pedido(dados, [dupla], AGORA), "Loja")


def test_todas_as_cores_viram_colorido():
    todas = ["azul", "verde", "rosa", "amarelo", "laranja", "lilas", "roxo", "branco"]
    assert item("algodao", "palito", 1, cor=todas)["cor"] == "colorido"
    assert item("algodao", "palito", 1, cor=["rosa", "colorido"])["cor"] == "colorido"


@pytest.mark.parametrize("cor", [[], ["preto"], ["azul", "preto"], [1], {"a": 1}])
def test_cores_invalidas(cor):
    with pytest.raises(ItemInvalido):
        item("algodao", "palito", 1, cor=cor)


@pytest.mark.parametrize("sinal", ["", "abc", "19.99", "0"])
def test_sinal_invalido_nao_finaliza(sinal):
    cliente = app.test_client()
    cliente.post("/api/carrinho", json={"produto": "maca", "opcao": "grande", "quantidade": 10})
    pedido = {**CLIENTE, "data": "2099-01-01", "sinal": sinal}
    for rota in ("/api/pedido", "/api/pedido/enviar"):
        resposta = cliente.post(rota, json=pedido)
        assert resposta.status_code == 400 and "sinal" in resposta.get_json()["erros"]
    assert cliente.get("/api/carrinho").get_json()["itens"]  # nada foi finalizado
