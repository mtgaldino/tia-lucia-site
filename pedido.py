"""Regras do carrinho e montagem do pedido enviado pelo WhatsApp."""

import re
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from catalogo import (
    ALGODAO,
    COLORIDO,
    ENCOMENDA,
    ESTEIRA_ALUGUEL,
    PICKUP,
    PRODUTOS,
    QUANTIDADE_MAXIMA,
    SABORES,
    SALGADOS,
    SINAL_MINIMO,
    TAMANHOS_SALGADO,
    brl,
    nome_cores,
    preco_salgado,
)
from horario import FUNCIONAMENTO, aceita_pickup, dentro_do_horario, erro_horario_retirada, hora_texto, promocao_ativa

PAGAMENTOS = {"pix": "PIX", "cartao": "Cartão", "dinheiro": "Dinheiro"}
MOMENTOS_PAGAMENTO = {"antecipado": "Antecipado", "retirada": "Na retirada"}
ENTREGAS = {"caixa": "Caixa", "esteira": "Esteira"}


class ItemInvalido(ValueError):
    pass


class PedidoInvalido(ValueError):
    def __init__(self, erros: dict[str, str]):
        super().__init__("Pedido inválido")
        self.erros = erros


# --- Carrinho -----------------------------------------------------------------


def normalizar_quantidade(valor) -> int:
    try:
        quantidade = int(valor)
    except (TypeError, ValueError):
        raise ItemInvalido("Quantidade inválida.")
    if not 1 <= quantidade <= QUANTIDADE_MAXIMA:
        raise ItemInvalido(f"A quantidade deve ser entre 1 e {QUANTIDADE_MAXIMA}.")
    return quantidade


def _normalizar_cores(valor, cores: dict) -> str:
    """Devolve a mescla na ordem do catálogo ("azul+verde"); todas as cores viram "colorido"."""
    escolhidas = valor.split("+") if isinstance(valor, str) else valor
    if not isinstance(escolhidas, list) or not escolhidas or not all(c in cores for c in map(str, escolhidas)):
        raise ItemInvalido("Escolha pelo menos uma cor.")
    separadas = [chave for chave in cores if chave != COLORIDO]
    if COLORIDO in escolhidas or set(escolhidas) == set(separadas):
        return COLORIDO
    return "+".join(chave for chave in separadas if chave in escolhidas)


def _normalizar_salgado(dados: dict, modo: str) -> dict:
    salgado = SALGADOS[dados["produto"]]
    if modo == ENCOMENDA and salgado.get("so_balcao"):
        raise ItemInvalido(f"{salgado['nome']} é vendido só no balcão ou no pick-up.")
    tamanho = dados.get("opcao")
    if tamanho not in salgado["tamanhos"]:
        raise ItemInvalido("Escolha um tamanho válido.")
    sabor = dados.get("sabor") or ""
    if salgado["sabores"]:
        if sabor not in salgado["sabores"]:
            raise ItemInvalido("Escolha um sabor.")
    else:
        sabor = ""
    return {"produto": dados["produto"], "opcao": tamanho, "cor": None, "sabor": sabor,
            "quantidade": normalizar_quantidade(dados.get("quantidade"))}


def normalizar_item(dados: dict, modo: str = ENCOMENDA) -> dict:
    """Valida um item vindo do site e devolve a versão guardada no carrinho."""
    if dados.get("produto") in SALGADOS:
        return _normalizar_salgado(dados, modo)

    produto = PRODUTOS.get(dados.get("produto"))
    if produto is None:
        raise ItemInvalido("Produto não encontrado.")
    if modo == PICKUP:
        raise ItemInvalido("No pick-up só temos os salgados da estufa.")

    opcao = dados.get("opcao")
    if opcao not in produto["opcoes"]:
        raise ItemInvalido("Escolha uma opção válida.")

    cor = _normalizar_cores(dados.get("cor"), produto["cores"]) if produto["cores"] else None

    return {
        "produto": dados["produto"],
        "opcao": opcao,
        "cor": cor,
        "sabor": "",
        "quantidade": normalizar_quantidade(dados.get("quantidade")),
    }


def chave_item(item: dict) -> tuple[str, str, str]:
    """Identifica o item no carrinho e, para salgados, na estufa."""
    return item["produto"], item["opcao"], item.get("cor") or item.get("sabor") or ""


def adicionar_item(carrinho: list[dict], item: dict) -> list[dict]:
    """Soma a quantidade se o mesmo produto/opção/cor/sabor já estiver no carrinho."""
    for existente in carrinho:
        if chave_item(existente) == chave_item(item):
            existente["quantidade"] = min(existente["quantidade"] + item["quantidade"], QUANTIDADE_MAXIMA)
            return carrinho
    carrinho.append(item)
    return carrinho


def conferir_estoque(carrinho: list[dict], estoque: dict[tuple, int]) -> list[str]:
    """Problemas de quantidade no pick-up; lista vazia quando tudo cabe na estufa."""
    problemas = []
    for item in carrinho:
        disponivel = estoque.get(chave_item(item), 0)
        if item["quantidade"] > disponivel:
            nome = descrever_item(item)
            problemas.append(f"{nome}: só restam {disponivel} na estufa." if disponivel
                             else f"{nome}: acabou na estufa.")
    return problemas


def nome_salgado(produto: str, tamanho: str, sabor: str = "") -> str:
    texto = f"{SALGADOS[produto]['nome']} {TAMANHOS_SALGADO[tamanho]['nome'].lower()}"
    return f"{texto} | Sabor: {SABORES[sabor]}" if sabor else texto


def descrever_item(item: dict) -> str:
    if item["produto"] in SALGADOS:
        return nome_salgado(item["produto"], item["opcao"], item.get("sabor", ""))
    produto = PRODUTOS[item["produto"]]
    opcao = produto["opcoes"][item["opcao"]]
    if item["produto"] == ALGODAO:
        partes = [produto["nome"], f"Tipo: {opcao['nome']}"]
        if item["opcao"] == "palito":
            partes[-1] += f" ({opcao['detalhe']})"
        partes.append(f"{'Cores' if '+' in item['cor'] else 'Cor'}: {nome_cores(item['cor'])}")
        return " | ".join(partes)
    return f"{produto['nome']} {opcao['nome']}"


def preco_unitario(item: dict, modo: str = ENCOMENDA, promocao: bool = False) -> Decimal:
    if item["produto"] in SALGADOS:
        return preco_salgado(item["produto"], item["opcao"], modo, promocao)
    return PRODUTOS[item["produto"]]["opcoes"][item["opcao"]]["preco"]


def resumo_carrinho(carrinho: list[dict], modo: str = ENCOMENDA, promocao: bool = False) -> dict:
    linhas = []
    subtotal = Decimal("0")
    tem_promocao = False
    for indice, item in enumerate(carrinho):
        unitario = preco_unitario(item, modo, promocao)
        tem_promocao = tem_promocao or unitario < preco_unitario(item, modo)
        total_linha = unitario * item["quantidade"]
        subtotal += total_linha
        linhas.append({**item, "indice": indice, "descricao": descrever_item(item),
                       "preco_unitario": unitario, "subtotal": total_linha})
    return {
        "modo": modo,
        "tem_promocao": tem_promocao,
        "linhas": linhas,
        "quantidade_total": sum(item["quantidade"] for item in carrinho),
        "subtotal": subtotal,
        "tem_algodao": any(item["produto"] == ALGODAO for item in carrinho),
    }


def sinal_minimo(total: Decimal) -> Decimal:
    """Sinal mínimo de R$ 20,00 — ou o valor total, se o pedido for menor que isso."""
    return min(SINAL_MINIMO, total)


# --- Pedido -------------------------------------------------------------------


@dataclass
class Pedido:
    modo: str
    nome: str
    telefone: str
    quando: datetime  # retirada no local
    pagamento: str
    momento_pagamento: str | None
    modo_entrega: str | None
    sinal: Decimal | None
    observacoes: str
    resumo: dict

    @property
    def valor_esteira(self) -> Decimal:
        return ESTEIRA_ALUGUEL if self.modo_entrega == "esteira" else Decimal("0")

    @property
    def total(self) -> Decimal:
        return self.resumo["subtotal"] + self.valor_esteira

    @property
    def restante(self) -> Decimal:
        return self.total - (self.sinal or 0)

    @property
    def descricao_pagamento(self) -> str:
        if self.momento_pagamento == "antecipado":
            return "Antecipado via PIX"
        if self.momento_pagamento == "retirada":
            return f"Na retirada — {PAGAMENTOS[self.pagamento]}"
        return PAGAMENTOS[self.pagamento]


def formatar_telefone(digitos: str) -> str:
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:]}"
    return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:]}"


def ler_valor(valor) -> Decimal | None:
    """Aceita 20, "20.5", "20,50" ou "R$ 1.020,50"."""
    texto = str(valor).replace("R$", "").strip()
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


def _validar_encomenda(dados: dict, resumo: dict, agora: datetime, erros: dict) -> dict:
    quando = None
    try:
        dia = date.fromisoformat(str(dados.get("data", "")))
        hora = time.fromisoformat(str(dados.get("horario", "")))
        quando = datetime.combine(dia, hora)
        if quando <= agora:
            erros["data"] = "Escolha uma data e horário futuros."
        elif erro := erro_horario_retirada(quando):
            erros["data"] = erro
    except ValueError:
        erros["data"] = "Informe a data e o horário da retirada."

    pagamento = dados.get("pagamento")
    if pagamento not in PAGAMENTOS:
        erros["pagamento"] = "Escolha a forma de pagamento."

    modo_entrega = None
    if resumo["tem_algodao"]:
        modo_entrega = dados.get("modo_entrega")
        if modo_entrega not in ENTREGAS:
            erros["modo_entrega"] = "Escolha caixa ou esteira."

    total = resumo["subtotal"] + (ESTEIRA_ALUGUEL if modo_entrega == "esteira" else 0)
    minimo = sinal_minimo(total)
    sinal = ler_valor(dados.get("sinal", ""))
    if sinal is None:
        erros["sinal"] = "Informe o valor do sinal."
    elif sinal < minimo:
        erros["sinal"] = f"O sinal deve ser de {brl(minimo)} ou mais. Digite um valor maior."
    elif sinal > total:
        erros["sinal"] = f"O sinal não pode passar do total ({brl(total)})."
    else:
        sinal = sinal.quantize(Decimal("0.01"))

    return {"quando": quando, "pagamento": pagamento, "momento_pagamento": None,
            "modo_entrega": modo_entrega, "sinal": sinal}


def _validar_pickup(dados: dict, agora: datetime, erros: dict) -> dict:
    quando = None
    try:
        quando = datetime.combine(agora.date(), time.fromisoformat(str(dados.get("horario_retirada", ""))))
        if not aceita_pickup(agora):
            erros["horario_retirada"] = "Estamos fechados agora. O pick-up volta quando a loja abrir."
        elif quando < agora.replace(second=0, microsecond=0):
            erros["horario_retirada"] = "Escolha um horário a partir de agora."
        elif not dentro_do_horario(quando):
            abre, fecha = FUNCIONAMENTO[agora.weekday()]
            erros["horario_retirada"] = f"Hoje, a retirada é das {hora_texto(abre)} às {hora_texto(fecha)}."
    except ValueError:
        erros["horario_retirada"] = "Informe o horário em que você vai retirar."

    momento = dados.get("momento_pagamento")
    pagamento = dados.get("pagamento")
    if momento == "antecipado":
        pagamento = "pix"
    elif momento == "retirada":
        if pagamento not in PAGAMENTOS:
            erros["pagamento"] = "Escolha a forma de pagamento na retirada."
    else:
        erros["momento_pagamento"] = "Escolha quando vai pagar."

    return {"quando": quando, "pagamento": pagamento, "momento_pagamento": momento,
            "modo_entrega": None, "sinal": None}


def validar_pedido(dados: dict, carrinho: list[dict], agora: datetime, modo: str = ENCOMENDA,
                   estoque: dict[tuple, int] | None = None) -> Pedido:
    erros: dict[str, str] = {}
    if not carrinho:
        raise PedidoInvalido({"carrinho": "Seu carrinho está vazio."})
    resumo = resumo_carrinho(carrinho, modo, promocao_ativa(agora))

    nome = " ".join(str(dados.get("nome", "")).split())
    if len(nome) < 2:
        erros["nome"] = "Informe seu nome."

    telefone = re.sub(r"\D", "", str(dados.get("telefone", "")))
    if telefone.startswith("55") and len(telefone) in (12, 13):
        telefone = telefone[2:]
    if len(telefone) not in (10, 11):
        erros["telefone"] = "Informe um telefone com DDD."

    if modo == PICKUP:
        campos = _validar_pickup(dados, agora, erros)
        problemas = conferir_estoque(carrinho, estoque or {})
        if problemas:
            erros["carrinho"] = " ".join(problemas)
    else:
        campos = _validar_encomenda(dados, resumo, agora, erros)

    observacoes = str(dados.get("observacoes", "")).strip()[:500]

    if erros:
        raise PedidoInvalido(erros)

    return Pedido(modo=modo, nome=nome, telefone=formatar_telefone(telefone),
                  observacoes=observacoes, resumo=resumo, **campos)


def _linhas_itens(resumo: dict) -> list[str]:
    linhas = ["*Itens:*"]
    for linha in resumo["linhas"]:
        linhas.append(f"• {linha['quantidade']}x {linha['descricao']} — "
                      f"{brl(linha['preco_unitario'])} cada = {brl(linha['subtotal'])}")
    linhas += ["", f"*Quantidade:* {resumo['quantidade_total']} unidade(s)"]
    return linhas


def montar_mensagem(pedido: Pedido, loja: str, codigo: str | None = None) -> str:
    resumo = pedido.resumo
    if pedido.modo == PICKUP:
        linhas = [f"*PEDIDO PICK-UP — {loja}*"]
        if codigo:
            linhas.append(f"*Código da reserva:* {codigo}")
    else:
        linhas = [f"*NOVO PEDIDO — {loja}*"]
    linhas += [
        "",
        f"*Nome do cliente:* {pedido.nome}",
        f"*Telefone/Celular:* {pedido.telefone}",
        "",
        *_linhas_itens(resumo),
    ]

    if pedido.modo == PICKUP:
        linhas += [
            *(["*Promoção aplicada:* salgado grande a R$ 5,50"] if resumo["tem_promocao"] else []),
            f"*Preço total:* {brl(pedido.total)}",
            "",
            f"*Retirada:* hoje, {pedido.quando:%d/%m/%Y} às {pedido.quando:%H:%M}",
            f"*Pagamento:* {pedido.descricao_pagamento}",
        ]
        if pedido.momento_pagamento == "antecipado":
            linhas.append("Vou enviar o comprovante do PIX nesta conversa.")
    else:
        linhas.append(f"*Preço dos produtos:* {brl(resumo['subtotal'])}")
        if resumo["tem_algodao"]:
            if pedido.modo_entrega == "esteira":
                linhas.append(f"*Modo de retirada:* Esteira (aluguel de {brl(ESTEIRA_ALUGUEL)}, "
                              "devolvido após a devolução da esteira)")
                linhas.append(f"*Preço total + esteira:* {brl(pedido.total)}")
            else:
                linhas.append("*Modo de retirada:* Caixa")
                linhas.append(f"*Preço total:* {brl(pedido.total)}")
        else:
            linhas.append(f"*Preço total:* {brl(pedido.total)}")
        linhas += [
            "",
            f"*Data + horário da retirada no local:* {pedido.quando:%d/%m/%Y} às {pedido.quando:%H:%M}",
            f"*Método de pagamento:* {pedido.descricao_pagamento}",
            f"*Valor do sinal:* {brl(pedido.sinal)}",
            f"*Restante a pagar:* {brl(pedido.restante)}",
        ]

    if pedido.observacoes:
        linhas += ["", f"*Observações:* {pedido.observacoes}"]
    return "\n".join(linhas)

