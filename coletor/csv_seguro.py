"""Celula de CSV que planilha nao le como comando (SEG2 item F).

Uma planilha pode tentar executar uma celula de texto que comeca com
=, +, -, @, TAB ou CR. Aqui esse inicio vira texto: entra um apostrofo
antes. Numero, booleano e nulo passam sem mudanca, para nao alterar
nenhum valor contavel nem nenhuma soma.
"""

from __future__ import annotations

INICIOS_PERIGOSOS = ("=", "+", "-", "@", "\t", "\r")


def celula_csv(valor) -> object:
    """Devolve a celula pronta. Texto perigoso ganha apostrofo na frente."""
    if isinstance(valor, str) and valor[:1] in INICIOS_PERIGOSOS:
        return "'" + valor
    return valor


def linha_csv(linha: dict) -> dict:
    """Aplica celula_csv em todos os valores de um dicionario de linha."""
    return {chave: celula_csv(valor) for chave, valor in linha.items()}


def linhas_csv(linhas) -> list:
    return [linha_csv(linha) for linha in linhas]


class EscritorSeguro:
    """Envolve um csv.DictWriter e passa toda celula por celula_csv."""

    def __init__(self, escritor):
        self.escritor = escritor

    def writeheader(self):
        return self.escritor.writeheader()

    def writerow(self, linha):
        return self.escritor.writerow(linha_csv(linha))

    def writerows(self, linhas):
        for linha in linhas:
            self.writerow(linha)
