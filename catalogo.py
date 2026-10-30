"""Catálogo de produtos, preços e regras fixas da loja."""

from decimal import Decimal

ALGODAO = "algodao"
MACA = "maca"

ESTEIRA_ALUGUEL = Decimal("20.00")
SINAL_MINIMO = Decimal("20.00")
QUANTIDADE_MAXIMA = 999

COLORIDO = "colorido"

CORES_ALGODAO = {
    "azul": {"nome": "Azul", "hex": "#8EC5E8"},
    "verde": {"nome": "Verde", "hex": "#A8D5A2"},
    "rosa": {"nome": "Rosa", "hex": "#F4B6C8"},
    "amarelo": {"nome": "Amarelo", "hex": "#F6E08A"},
    "laranja": {"nome": "Laranja", "hex": "#F5B97F"},
    "lilas": {"nome": "Lilás", "hex": "#D3C0E8"},
    "roxo": {"nome": "Roxo", "hex": "#A98BCB"},
    "branco": {"nome": "Branco", "hex": "#FFFFFF"},
    "colorido": {"nome": "Colorido", "hex": None},
}

PRODUTOS = {
    ALGODAO: {
        "nome": "Algodão doce",
        "descricao": "Nuvem de açúcar feita na hora, no palito ou no pote, em nove cores.",
        "opcoes": {
            "palito": {
                "nome": "Palito",
                "tipo": "Palito",
                "preco": Decimal("3.00"),
                "detalhe": "Saco 17x35 cm",
            },
            "pote200": {
                "nome": "Pote 200ml",
                "tipo": "Pote",
                "preco": Decimal("4.50"),
                "detalhe": "Pote com tampa",
            },
            "pote300": {
                "nome": "Pote 300ml",
                "tipo": "Pote",
                "preco": Decimal("6.50"),
                "detalhe": "Pote com tampa",
            },
        },
        "cores": CORES_ALGODAO,
    },
    MACA: {
        "nome": "Maçã do amor",
        "descricao": "Maçã fresquinha com calda vermelha crocante, do jeitinho clássico.",
        "opcoes": {
            "pequena": {"nome": "Pequena", "preco": Decimal("3.80"), "detalhe": "Ideal para lembrancinha"},
            "grande": {"nome": "Grande", "preco": Decimal("5.50"), "detalhe": "Para quem ama de verdade"},
        },
        "cores": {},
    },
}


# --- Salgados -----------------------------------------------------------------
# Encomenda: pedido para festas/eventos. Pick-up: retirada no balcão, só o que está na estufa.

ENCOMENDA = "encomenda"
PICKUP = "pickup"
MODOS = {ENCOMENDA: "Encomenda", PICKUP: "Pick-up"}

CATEGORIAS = {"assado": "Assados", "frito": "Fritos"}

SABORES = {
    "frango": "Frango",
    "queijo_presunto": "Queijo c/ presunto",
    "calabresa": "Calabresa",
    "carne": "Carne",
    "queijo_minas": "Queijo minas",
}
_CINCO_SABORES = list(SABORES)

TAMANHOS_SALGADO = {
    "grande": {"nome": "Grande", "precos": {PICKUP: Decimal("7.00"), ENCOMENDA: Decimal("4.00")},
               "promocao": Decimal("5.50")},  # só no balcão/pick-up, no horário de horario.py
    "pequeno": {"nome": "Pequeno", "precos": {PICKUP: Decimal("2.50"), ENCOMENDA: Decimal("2.50")}},
}
_OS_DOIS = ["grande", "pequeno"]
_SO_GRANDE = ["grande"]

SALGADOS = {
    "joelho": {"nome": "Joelho", "categoria": "assado", "sabores": ["frango", "queijo_presunto"], "tamanhos": _OS_DOIS},
    "pastel_forno": {"nome": "Pastel de forno", "categoria": "assado", "sabores": _CINCO_SABORES, "tamanhos": _OS_DOIS},
    "empada": {"nome": "Empada", "categoria": "assado", "sabores": _CINCO_SABORES, "tamanhos": _OS_DOIS},
    "empadao": {"nome": "Empadão", "categoria": "assado", "sabores": _CINCO_SABORES, "tamanhos": _SO_GRANDE,
                "preco_fixo": Decimal("11.00")},  # igual na encomenda e no balcão, sem promoção
    "hamburguer_forno": {"nome": "Hambúrguer de forno", "categoria": "assado", "sabores": [], "tamanhos": _SO_GRANDE},
    "hamburguer": {"nome": "Hambúrguer", "categoria": "assado", "sabores": [], "tamanhos": _SO_GRANDE, "so_balcao": True,
                   "sem_promocao": True},
    "cachorro_forno": {"nome": "Cachorro quente de forno", "categoria": "assado", "sabores": [], "tamanhos": _OS_DOIS},
    "esfirra": {"nome": "Esfirra de carne", "categoria": "assado", "sabores": [], "tamanhos": _SO_GRANDE},
    "coxinha": {"nome": "Coxinha", "categoria": "frito", "sabores": [], "tamanhos": _OS_DOIS},
    "salsicha": {"nome": "Salsicha", "categoria": "frito", "sabores": [], "tamanhos": _OS_DOIS},
    "bolinho_carne": {"nome": "Bolinho de carne", "categoria": "frito", "sabores": [], "tamanhos": _OS_DOIS},
    "enroladinho": {"nome": "Enroladinho de queijo c/ presunto", "categoria": "frito", "sabores": [], "tamanhos": _OS_DOIS},
}


def preco_salgado(salgado_id: str, tamanho: str, modo: str, promocao: bool = False) -> Decimal:
    if "preco_fixo" in SALGADOS[salgado_id]:
        return SALGADOS[salgado_id]["preco_fixo"]
    dados = TAMANHOS_SALGADO[tamanho]
    if promocao and modo == PICKUP and "promocao" in dados and not SALGADOS[salgado_id].get("sem_promocao"):
        return dados["promocao"]
    return dados["precos"][modo]


def variacoes_salgados():
    """Todas as combinações (salgado, tamanho, sabor) que podem estar na estufa. Sem sabor = ""."""
    for salgado_id, salgado in SALGADOS.items():
        for tamanho in salgado["tamanhos"]:
            for sabor in salgado["sabores"] or [""]:
                yield salgado_id, tamanho, sabor


def nome_cores(cor: str) -> str:
    """Nome de uma cor ou mescla guardada como "azul+verde": "Azul e Verde"."""
    nomes = [CORES_ALGODAO[chave]["nome"] for chave in cor.split("+")]
    return " e ".join(filter(None, [", ".join(nomes[:-1]), nomes[-1]]))


def brl(valor: Decimal) -> str:
    """Formata um valor no padrão brasileiro: R$ 1.234,56."""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"
