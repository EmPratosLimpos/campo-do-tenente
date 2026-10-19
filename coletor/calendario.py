"""Data das sessoes no fuso da cidade, sem dependencia interna.

America/Sao_Paulo. O Brasil nao tem mais horario de verao desde 2019,
por isso o deslocamento fixo de -3 horas. Fica nomeado aqui porque o
config_cidade.json ainda nao tem campo de fuso.

Quem coleta e quem deriva compartilham este modulo: os dois precisam
tratar igual a sessao ordinaria que ainda nao aconteceu.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

FUSO_CIDADE = timezone(timedelta(hours=-3), "America/Sao_Paulo")


def hoje_na_cidade() -> date:
    """Data de hoje no fuso da cidade. Separada para o teste injetar a data."""
    return datetime.now(FUSO_CIDADE).date()


def data_da_sessao(sessao: dict) -> date | None:
    """Data de inicio da sessao, ou None quando ausente ou invalida.

    O SAPL entrega data_inicio como AAAA-MM-DD. Data invalida segue o
    caminho de erro de sempre, nunca e tratada como futura.
    """
    valor = sessao.get("data_inicio")
    if not isinstance(valor, str) or len(valor) < 10:
        return None
    try:
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def sessao_ja_aconteceu(sessao: dict, hoje: date) -> bool:
    """True quando a sessao e de hoje ou de antes. Data invalida conta como ja.

    Sessao futura fica fora do alvo e da derivacao desta execucao. Data
    invalida nao pode sumir em silencio: segue o caminho de erro de
    sempre, por isso nao e tratada como futura.
    """
    quando = data_da_sessao(sessao)
    return quando is None or quando <= hoje
