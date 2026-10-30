"""Vitrine de salgados e doces: encomendas e pick-up, com pedido finalizado pelo WhatsApp."""

import hmac
import os
import secrets
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

from catalogo import (
    CATEGORIAS,
    ENCOMENDA,
    ESTEIRA_ALUGUEL,
    MODOS,
    PICKUP,
    PRODUTOS,
    SABORES,
    SALGADOS,
    SINAL_MINIMO,
    TAMANHOS_SALGADO,
    brl,
    nome_cores,
    preco_salgado,
)
from estufa import EstoqueInsuficiente, Estufa
from horario import RESUMO_HORARIO, aceita_pickup, agora_loja, promocao_ativa, situacao
from pedido import (
    ItemInvalido,
    PedidoInvalido,
    adicionar_item,
    conferir_estoque,
    chave_item,
    montar_mensagem,
    nome_salgado,
    normalizar_item,
    normalizar_quantidade,
    resumo_carrinho,
    validar_pedido,
)

NOME_LOJA = os.environ.get("NOME_LOJA", "Tia Lúcia: Salgados e Doces")
WHATSAPP_NUMERO = os.environ.get("WHATSAPP_NUMERO", "5521985209765")
CONTATO = {
    "telefone": "(21) 2440-4237",
    "telefone_link": "+552124404237",
    "celular": "(21) 98520-9765",
    "celular_link": "+5521985209765",
    "instagram": "algodaodoce_tia_lucia",
    "endereco": "Avenida dos Mananciais, 1020 - Taquara",
    "mapa": "https://www.google.com/maps/search/?api=1&query=Avenida+dos+Mananciais%2C+1020+-+Taquara%2C+Rio+de+Janeiro",
}
PASTA_DADOS = Path(os.environ.get("PASTA_DADOS", Path(__file__).parent / "dados"))

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
estufa = Estufa(PASTA_DADOS / "loja.db")


def senha_painel() -> str:
    """PAINEL_SENHA, ou uma senha gerada uma vez e guardada em dados/senha_painel.txt."""
    if os.environ.get("PAINEL_SENHA"):
        return os.environ["PAINEL_SENHA"]
    arquivo = PASTA_DADOS / "senha_painel.txt"
    if not arquivo.exists():
        arquivo.write_text(secrets.token_urlsafe(9), encoding="utf-8")
    return arquivo.read_text(encoding="utf-8").strip()


# --- Carrinho -----------------------------------------------------------------


def _carrinho() -> list[dict]:
    return [dict(item) for item in session.get("carrinho", [])]


def _modo() -> str:
    return session.get("modo", ENCOMENDA)


def _salvar(carrinho: list[dict], modo: str | None = None) -> None:
    session["carrinho"] = carrinho
    session["modo"] = (modo or _modo()) if carrinho else ENCOMENDA


def _valor(numero: Decimal) -> dict:
    return {"valor": float(numero), "texto": brl(numero)}


def _erro(mensagem: str, status: int = 400, **extra):
    return jsonify({"erro": mensagem, **extra}), status


def _carrinho_json(carrinho: list[dict], modo: str) -> dict:
    resumo = resumo_carrinho(carrinho, modo, promocao_ativa(agora_loja()))
    estoque = estufa.quantidades() if modo == PICKUP else {}
    itens = []
    for linha in resumo["linhas"]:
        if linha["produto"] in SALGADOS:
            salgado = SALGADOS[linha["produto"]]
            nome, opcao = salgado["nome"], TAMANHOS_SALGADO[linha["opcao"]]["nome"]
            variacao, categoria = SABORES.get(linha["sabor"]), salgado["categoria"]
        else:
            produto = PRODUTOS[linha["produto"]]
            nome, opcao = produto["nome"], produto["opcoes"][linha["opcao"]]["nome"]
            variacao = nome_cores(linha["cor"]) if linha["cor"] else None
            categoria = "doce"
        itens.append({
            "indice": linha["indice"],
            "produto": linha["produto"],
            "categoria": categoria,
            "nome": nome,
            "opcao": opcao,
            "variacao": variacao,
            "cor_id": linha["cor"],
            "quantidade": linha["quantidade"],
            "maximo": estoque.get(chave_item(linha), 0) if modo == PICKUP else 999,
            "preco_unitario": _valor(linha["preco_unitario"]),
            "subtotal": _valor(linha["subtotal"]),
        })
    return {
        "modo": modo,
        "itens": itens,
        "quantidade_total": resumo["quantidade_total"],
        "subtotal": _valor(resumo["subtotal"]),
        "tem_algodao": resumo["tem_algodao"],
    }


def _responder_carrinho(status: int = 200):
    return jsonify(_carrinho_json(_carrinho(), _modo())), status


@app.get("/")
def index():
    return render_template(
        "index.html",
        loja=NOME_LOJA,
        contato=CONTATO,
        horario=RESUMO_HORARIO,
        situacao=situacao(agora_loja()),
        preco_salgado=preco_salgado,
        produtos=PRODUTOS,
        salgados=SALGADOS,
        categorias=CATEGORIAS,
        tamanhos=TAMANHOS_SALGADO,
        sabores=SABORES,
        encomenda=ENCOMENDA,
        pickup=PICKUP,
        brl=brl,
        esteira=brl(ESTEIRA_ALUGUEL),
        sinal=brl(SINAL_MINIMO),
        config={
            "esteira": float(ESTEIRA_ALUGUEL),
            "sinalMinimo": float(SINAL_MINIMO),
            "situacao": situacao(agora_loja()),
        },
    )


@app.get("/api/loja")
def ver_loja():
    """Consultado de tempos em tempos para o site mudar sozinho quando a promoção começa ou termina."""
    return jsonify(situacao(agora_loja()))


@app.get("/api/estufa")
def ver_estufa():
    """Salgados disponíveis agora para pick-up, com preço de balcão."""
    itens = []
    promocao = promocao_ativa(agora_loja())
    for (salgado_id, tamanho, sabor), quantidade in estufa.quantidades().items():
        if quantidade > 0:
            salgado = SALGADOS[salgado_id]
            itens.append({
                "produto": salgado_id,
                "nome": salgado["nome"],
                "categoria": salgado["categoria"],
                "opcao": tamanho,
                "tamanho": TAMANHOS_SALGADO[tamanho]["nome"],
                "sabor": sabor,
                "sabor_nome": SABORES.get(sabor),
                "preco": _valor(preco_salgado(salgado_id, tamanho, PICKUP, promocao)),
                "preco_normal": _valor(preco_salgado(salgado_id, tamanho, PICKUP)),
                "disponivel": quantidade,
            })
    return jsonify({"itens": itens})


@app.get("/api/carrinho")
def ver_carrinho():
    return _responder_carrinho()


@app.post("/api/carrinho")
def adicionar():
    dados = request.get_json(silent=True) or {}
    modo = dados.get("modo", ENCOMENDA)
    if modo not in MODOS:
        return _erro("Tipo de pedido inválido.")
    carrinho = _carrinho()
    if carrinho and _modo() != modo:
        return _erro(f"Seu carrinho já tem um pedido de {MODOS[_modo()].lower()}. "
                     f"Para fazer um pedido de {MODOS[modo].lower()}, esvazie o carrinho.", 409, conflito=True)
    if modo == PICKUP and not aceita_pickup(agora_loja()):
        return _erro(situacao(agora_loja())["mensagem"], 409)
    try:
        carrinho = adicionar_item(carrinho, normalizar_item(dados, modo))
    except ItemInvalido as erro:
        return _erro(str(erro))
    if modo == PICKUP and (problemas := conferir_estoque(carrinho, estufa.quantidades())):
        return _erro(problemas[0], 409)
    _salvar(carrinho, modo)
    return _responder_carrinho(201)


@app.patch("/api/carrinho/<int:indice>")
def alterar_quantidade(indice: int):
    carrinho = _carrinho()
    if not 0 <= indice < len(carrinho):
        return _erro("Item não encontrado.", 404)
    try:
        carrinho[indice]["quantidade"] = normalizar_quantidade((request.get_json(silent=True) or {}).get("quantidade"))
    except ItemInvalido as erro:
        return _erro(str(erro))
    if _modo() == PICKUP and (problemas := conferir_estoque([carrinho[indice]], estufa.quantidades())):
        return _erro(problemas[0], 409)
    _salvar(carrinho)
    return _responder_carrinho()


@app.delete("/api/carrinho/<int:indice>")
def remover(indice: int):
    carrinho = _carrinho()
    if not 0 <= indice < len(carrinho):
        return _erro("Item não encontrado.", 404)
    carrinho.pop(indice)
    _salvar(carrinho)
    return _responder_carrinho()


@app.delete("/api/carrinho")
def esvaziar():
    _salvar([])
    return _responder_carrinho()


# --- Pedido -------------------------------------------------------------------


def _validar():
    modo = _modo()
    estoque = estufa.quantidades() if modo == PICKUP else None
    return validar_pedido(request.get_json(silent=True) or {}, _carrinho(), agora_loja(), modo, estoque)


@app.post("/api/pedido")
def revisar():
    """Valida e mostra a mensagem; nada é reservado ainda."""
    try:
        pedido = _validar()
    except PedidoInvalido as erro:
        return jsonify({"erros": erro.erros}), 400
    return jsonify({"modo": pedido.modo, "mensagem": montar_mensagem(pedido, NOME_LOJA)})


@app.post("/api/pedido/enviar")
def enviar():
    """Confirma o pedido: no pick-up reserva as unidades da estufa, depois esvazia o carrinho."""
    try:
        pedido = _validar()
    except PedidoInvalido as erro:
        return jsonify({"erros": erro.erros}), 400

    codigo = None
    if pedido.modo == PICKUP:
        itens = [{"produto": i["produto"], "opcao": i["opcao"], "sabor": i["sabor"], "quantidade": i["quantidade"],
                  "descricao": nome_salgado(i["produto"], i["opcao"], i["sabor"])} for i in _carrinho()]
        try:
            codigo = estufa.reservar(itens, cliente=pedido.nome, telefone=pedido.telefone,
                                     retirada_em=pedido.quando, pagamento=pedido.descricao_pagamento,
                                     total=brl(pedido.total))
        except EstoqueInsuficiente as erro:
            nomes = ", ".join(item["descricao"] for item in erro.args[0])
            return jsonify({"erros": {"carrinho": f"Acabou de esgotar na estufa: {nomes}. Ajuste o carrinho."}}), 409

    mensagem = montar_mensagem(pedido, NOME_LOJA, codigo)
    _salvar([])
    return jsonify({
        "modo": pedido.modo,
        "codigo": codigo,
        "mensagem": mensagem,
        "whatsapp": f"https://wa.me/{WHATSAPP_NUMERO}?text={quote(mensagem)}",
    })


# --- Painel da loja -----------------------------------------------------------


def _linhas_estufa() -> list[dict]:
    quantidades = estufa.quantidades()
    linhas = []
    for salgado_id, salgado in SALGADOS.items():
        for sabor in salgado["sabores"] or [""]:
            linhas.append({
                "nome": salgado["nome"],
                "sabor": SABORES.get(sabor),
                "categoria": salgado["categoria"],
                "celulas": {
                    tamanho: {"campo": f"q:{salgado_id}:{tamanho}:{sabor}",
                              "valor": quantidades[(salgado_id, tamanho, sabor)]}
                    for tamanho in salgado["tamanhos"]
                },
            })
    return linhas


@app.get("/painel")
def painel():
    if not session.get("painel"):
        return render_template("painel_login.html", loja=NOME_LOJA)
    return render_template("painel.html", loja=NOME_LOJA, linhas=_linhas_estufa(), categorias=CATEGORIAS,
                           tamanhos=TAMANHOS_SALGADO, reservas=estufa.reservas(), agora=agora_loja())


@app.post("/painel/entrar")
def painel_entrar():
    if hmac.compare_digest(request.form.get("senha", "").encode(), senha_painel().encode()):
        session["painel"] = True
        return redirect(url_for("painel"))
    return render_template("painel_login.html", loja=NOME_LOJA, erro="Senha incorreta."), 401


@app.post("/painel/sair")
def painel_sair():
    session.pop("painel", None)
    return redirect(url_for("painel"))


@app.post("/painel/estufa")
def painel_estufa():
    if not session.get("painel"):
        return redirect(url_for("painel"))
    quantidades = {}
    for campo, valor in request.form.items():
        partes = campo.split(":")
        if len(partes) == 4 and partes[0] == "q" and valor.strip().isdigit():
            quantidades[tuple(partes[1:])] = int(valor)
    if request.form.get("zerar"):
        quantidades = {chave: 0 for chave in estufa.quantidades()}
    estufa.definir(quantidades)
    flash("Estufa zerada." if request.form.get("zerar") else "Estufa atualizada.")
    return redirect(url_for("painel"))


@app.post("/painel/reservas/<codigo>/<acao>")
def painel_reserva(codigo: str, acao: str):
    if not session.get("painel"):
        return redirect(url_for("painel"))
    if acao == "retirada" and estufa.concluir(codigo):
        flash(f"Reserva {codigo} marcada como retirada.")
    elif acao == "cancelar" and estufa.cancelar(codigo):
        flash(f"Reserva {codigo} cancelada. As unidades voltaram para a estufa.")
    else:
        flash(f"A reserva {codigo} não está mais pendente.")
    return redirect(url_for("painel") + "#reservas")


if __name__ == "__main__":
    if not os.environ.get("PAINEL_SENHA"):
        print(f" * Senha do painel (/painel): {senha_painel()}  — defina PAINEL_SENHA para escolher a sua")
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
