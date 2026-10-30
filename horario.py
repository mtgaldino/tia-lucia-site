"""Horário de funcionamento e da promoção, sempre no fuso da loja."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from catalogo import TAMANHOS_SALGADO, PICKUP, brl

FUSO = ZoneInfo("America/Sao_Paulo")
SABADO = 5
DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# dia da semana (0 = segunda) -> (abre, fecha). Domingo não abre.
FUNCIONAMENTO = {
    **{dia: (time(8, 30), time(18, 30)) for dia in range(SABADO)},
    SABADO: (time(8, 30), time(17, 0)),
}
INICIO_PROMOCAO = {
    **{dia: time(16, 0) for dia in range(SABADO)},
    SABADO: time(15, 0),
}
RESUMO_HORARIO = "Segunda a sexta, das 8:30 às 18:30. Sábado, das 8:30 às 17h."


def agora_loja() -> datetime:
    """Hora local da loja (sem fuso), mesmo se o servidor estiver em outro país."""
    return datetime.now(FUSO).replace(tzinfo=None)


def hora_texto(hora: time) -> str:
    return f"{hora.hour}h" if hora.minute == 0 else f"{hora.hour}:{hora.minute:02d}"


def dentro_do_horario(momento: datetime) -> bool:
    horario = FUNCIONAMENTO.get(momento.weekday())
    return horario is not None and horario[0] <= momento.time() <= horario[1]


def promocao_ativa(momento: datetime) -> bool:
    inicio = INICIO_PROMOCAO.get(momento.weekday())
    return inicio is not None and inicio <= momento.time() < FUNCIONAMENTO[momento.weekday()][1]


def aceita_pickup(momento: datetime) -> bool:
    """Dá para reservar até o fechamento, inclusive antes de abrir (quem pede a caminho do trabalho)."""
    horario = FUNCIONAMENTO.get(momento.weekday())
    return horario is not None and momento.time() < horario[1]


def proxima_abertura(momento: datetime) -> str:
    horario = FUNCIONAMENTO.get(momento.weekday())
    if horario and momento.time() < horario[0]:
        return f"hoje às {hora_texto(horario[0])}"
    dia = momento + timedelta(days=1)
    while dia.weekday() not in FUNCIONAMENTO:
        dia += timedelta(days=1)
    nome = "amanhã" if dia.date() == (momento + timedelta(days=1)).date() else DIAS[dia.weekday()]
    return f"{nome} às {hora_texto(FUNCIONAMENTO[dia.weekday()][0])}"


def erro_horario_retirada(momento: datetime) -> str | None:
    """Encomenda também é retirada no local, então só vale com a loja aberta."""
    horario = FUNCIONAMENTO.get(momento.weekday())
    if horario is None:
        return "Não abrimos aos domingos. Escolha de segunda a sábado."
    if not dentro_do_horario(momento):
        return f"Nesse dia, a retirada é das {hora_texto(horario[0])} às {hora_texto(horario[1])}."
    return None


def situacao(momento: datetime) -> dict:
    """O que o site mostra agora: aberto ou fechado, promoção e limites do horário de retirada."""
    grande = TAMANHOS_SALGADO["grande"]
    normal, promocional = brl(grande["precos"][PICKUP]), brl(grande["promocao"])
    horario = FUNCIONAMENTO.get(momento.weekday())
    promocao = promocao_ativa(momento)
    aberta = dentro_do_horario(momento) and aceita_pickup(momento)

    if promocao:
        tipo = "promocao"
        mensagem = (f"Promoção no ar! Salgado grande de {normal} por {promocional} "
                    f"no balcão e no pick-up, até as {hora_texto(horario[1])}.")
    elif aberta:
        tipo = "aberta"
        mensagem = (f"Aberto até as {hora_texto(horario[1])}. Hoje, a partir das "
                    f"{hora_texto(INICIO_PROMOCAO[momento.weekday()])}, salgado grande por {promocional}.")
    else:
        tipo = "fechada"
        mensagem = f"Fechado agora. Abrimos {proxima_abertura(momento)}."

    limites = {}
    if aceita_pickup(momento):
        minimo = max(momento.time(), horario[0])
        padrao = min((datetime.combine(momento.date(), minimo) + timedelta(minutes=15)).time(), horario[1])
        limites = {"retirada_min": minimo.strftime("%H:%M"), "retirada_max": horario[1].strftime("%H:%M"),
                   "retirada_padrao": padrao.strftime("%H:%M")}

    return {"tipo": tipo, "mensagem": mensagem, "aberta": aberta, "promocao": promocao,
            "aceita_pickup": aceita_pickup(momento), **limites}
