"""Testes de sanidade da esteira de dados, rodados antes da publicacao.

Verifica que os arquivos consolidados em dados/tratados/ existem, sao
JSON/CSV validos e batem com os totais esperados de 2026. Nao valida o
conteudo linha a linha (isso e responsabilidade do gerador), apenas
detecta coleta quebrada, truncada ou vazia antes que ela va para main.

Uso:
    python coletor/testes_sanidade.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_TRATADOS = DIR_RAIZ / "dados" / "tratados"

ARQUIVO_JSON = DIR_TRATADOS / "atuacao_vereadores_2026.json"
ARQUIVO_CSV = DIR_TRATADOS / "atuacao_vereadores_2026.csv"
ARQUIVO_VEREADORES = DIR_TRATADOS / "vereadores.json"

N_SESSOES_ESPERADAS = 26
N_PLL_ESPERADOS = 100
N_VEREADORES_ESPERADOS = 15


class FalhaSanidade(Exception):
    pass


def checar(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise FalhaSanidade(mensagem)


def testar_json_atuacao() -> None:
    checar(ARQUIVO_JSON.exists(), f"Arquivo ausente: {ARQUIVO_JSON}")
    dados = json.loads(ARQUIVO_JSON.read_text(encoding="utf-8"))
    meta = dados.get("meta", {})
    checar(bool(meta), "atuacao_vereadores_2026.json sem bloco 'meta'")
    checar(
        int(meta.get("n_sessoes_ordinarias") or 0) >= N_SESSOES_ESPERADAS,
        f"n_sessoes_ordinarias={meta.get('n_sessoes_ordinarias')!r}, "
        f"esperado ao menos {N_SESSOES_ESPERADAS}",
    )
    checar(
        int(meta.get("n_pll_2026") or 0) >= N_PLL_ESPERADOS,
        f"n_pll_2026={meta.get('n_pll_2026')!r}, esperado ao menos {N_PLL_ESPERADOS}",
    )
    checar(
        meta.get("n_vereadores") == N_VEREADORES_ESPERADOS,
        f"n_vereadores={meta.get('n_vereadores')!r}, "
        f"esperado {N_VEREADORES_ESPERADOS}",
    )
    checar(
        int(meta.get("n_registros_votacao") or 0) > 0,
        "n_registros_votacao zerado ou ausente",
    )


def testar_csv_atuacao() -> None:
    checar(ARQUIVO_CSV.exists(), f"Arquivo ausente: {ARQUIVO_CSV}")
    with ARQUIVO_CSV.open(encoding="utf-8", newline="") as f:
        linhas = list(csv.reader(f))
    checar(len(linhas) > 1, "atuacao_vereadores_2026.csv sem linhas de dados")


def testar_vereadores() -> None:
    checar(ARQUIVO_VEREADORES.exists(), f"Arquivo ausente: {ARQUIVO_VEREADORES}")
    dados = json.loads(ARQUIVO_VEREADORES.read_text(encoding="utf-8"))
    vereadores = dados.get("vereadores") or dados.get("dados") or []
    if isinstance(vereadores, dict):
        vereadores = list(vereadores.values())
    checar(
        len(vereadores) == N_VEREADORES_ESPERADOS,
        f"vereadores.json tem {len(vereadores)} registros, "
        f"esperado {N_VEREADORES_ESPERADOS}",
    )


TESTES = [testar_json_atuacao, testar_csv_atuacao, testar_vereadores]


def main() -> int:
    falhas = []
    for teste in TESTES:
        try:
            teste()
        except FalhaSanidade as erro:
            falhas.append(f"{teste.__name__}: {erro}")
        except Exception as erro:  # dado malformado, arquivo corrompido, etc.
            falhas.append(f"{teste.__name__}: erro inesperado - {erro}")

    if falhas:
        print("FALHA nos testes de sanidade:", file=sys.stderr)
        for falha in falhas:
            print(f"  - {falha}", file=sys.stderr)
        return 1

    print(f"OK: {len(TESTES)} testes de sanidade passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
