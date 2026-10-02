"""Testes de sanidade da esteira de dados, rodados antes da publicacao.

Verifica que os arquivos consolidados em dados/tratados/ existem, sao
JSON/CSV validos e batem com os pisos de cada ano definidos em
config_cidade.json (D-016): vereadores exato, sessoes ordinarias e projetos
de lei (PLEG e PLEX somados) como minimo.
Nao valida o conteudo linha a linha (isso e responsabilidade do gerador),
apenas detecta coleta quebrada, truncada ou vazia antes que ela va para main.

Uso:
    python coletor/testes_sanidade.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from config_cidade import (
    PisoNaoDefinido,
    anos_recorte,
    campos_pessoais,
    carregar_config,
    exigir_piso,
    pisos_sanidade,
)

DIR_RAIZ = Path(__file__).resolve().parent.parent
DIR_TRATADOS = DIR_RAIZ / "dados" / "tratados"
DIR_BRUTOS = DIR_RAIZ / "dados" / "brutos"
DIR_DADOS = DIR_RAIZ / "dados"
CONFIG = carregar_config()
ANOS = anos_recorte(CONFIG)
PISOS = {ano: pisos_sanidade(ano, CONFIG) for ano in ANOS}

# Pagina de terceiro nao entra no repositorio. Em dados/ so ha dado do SAPL
# e o texto puro que comprova o que o SAPL nao registra.
EXTENSOES_DE_PAGINA = frozenset({".html", ".htm", ".xhtml", ".svg"})


class FalhaSanidade(Exception):
    pass


def checar(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise FalhaSanidade(mensagem)


def arquivo_atuacao_json(ano: int) -> Path:
    return DIR_TRATADOS / f"atuacao_vereadores_{ano}.json"


def arquivo_atuacao_csv(ano: int) -> Path:
    return DIR_TRATADOS / f"atuacao_vereadores_{ano}.csv"


def arquivo_vereadores() -> Path:
    return DIR_TRATADOS / "vereadores.json"


def testar_json_atuacao(ano: int, n_sessoes: int, n_projetos: int, n_vereadores: int) -> None:
    caminho = arquivo_atuacao_json(ano)
    checar(caminho.exists(), f"Arquivo ausente: {caminho}")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    meta = dados.get("meta", {})
    checar(bool(meta), f"atuacao_vereadores_{ano}.json sem bloco 'meta'")
    checar(
        int(meta.get("n_sessoes_ordinarias") or 0) >= n_sessoes,
        f"{ano}: n_sessoes_ordinarias={meta.get('n_sessoes_ordinarias')!r}, "
        f"esperado ao menos {n_sessoes}",
    )
    chave_projetos = "n_projetos_lei_legislativo_e_executivo"
    n_projetos_meta = meta.get(chave_projetos)
    checar(
        int(n_projetos_meta or 0) >= n_projetos,
        f"{ano}: {chave_projetos}={n_projetos_meta!r}, esperado ao menos {n_projetos}",
    )
    checar(
        meta.get("n_vereadores") == n_vereadores,
        f"{ano}: n_vereadores={meta.get('n_vereadores')!r}, "
        f"esperado {n_vereadores}",
    )
    checar(
        int(meta.get("n_registros_votacao") or 0) > 0,
        f"{ano}: n_registros_votacao zerado ou ausente",
    )


def testar_csv_atuacao(ano: int) -> None:
    caminho = arquivo_atuacao_csv(ano)
    checar(caminho.exists(), f"Arquivo ausente: {caminho}")
    with caminho.open(encoding="utf-8", newline="") as f:
        linhas = list(csv.reader(f))
    checar(len(linhas) > 1, f"atuacao_vereadores_{ano}.csv sem linhas de dados")


def testar_vereadores(ano: int, n_vereadores: int) -> None:
    caminho = arquivo_vereadores()
    checar(caminho.exists(), f"Arquivo ausente: {caminho}")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    vereadores = dados.get("vereadores") or dados.get("dados") or []
    if isinstance(vereadores, dict):
        vereadores = list(vereadores.values())
    do_ano = [
        item for item in vereadores if ano in (item.get("anos_com_mandato") or [])
    ]
    checar(
        len(do_ano) == n_vereadores,
        f"vereadores.json tem {len(do_ano)} vereadores com mandato em {ano}, "
        f"esperado {n_vereadores}",
    )


def testar_arquivo_real(ano: int) -> None:
    caminho = arquivo_atuacao_json(ano)
    checar(caminho.exists(), f"Arquivo ausente: {caminho.name}")
    bruto = caminho.read_bytes()
    checar(b"\r" not in bruto, f"{caminho.name} nao esta em LF")
    dados = json.loads(bruto.decode("utf-8"))
    meta = dados.get("meta") or {}
    checar(
        isinstance(meta.get("dado_coletado_em"), str) and meta["dado_coletado_em"].strip(),
        f"{ano}: meta.dado_coletado_em ausente",
    )
    checar(
        "lacuna_sessoes_ordinarias" in meta,
        f"{ano}: meta sem lacuna_sessoes_ordinarias",
    )
    contagem_caminho = DIR_RAIZ / "dados" / "brutos" / f"contagem_votacoes_ordinarias_{ano}.json"
    if contagem_caminho.exists():
        contagem = json.loads(contagem_caminho.read_text(encoding="utf-8"))
        checar(
            meta.get("lacuna_sessoes_ordinarias") == contagem.get("lacuna_sessoes_ordinarias"),
            f"{ano}: lacuna do consolidado diferente da contagem",
        )
    def tem_chave_ip(obj) -> bool:
        if isinstance(obj, dict):
            if "ip" in obj:
                return True
            return any(tem_chave_ip(valor) for valor in obj.values())
        if isinstance(obj, list):
            return any(tem_chave_ip(valor) for valor in obj)
        return False

    checar(not tem_chave_ip(dados), f"{ano}: campo ip em dado tratado")


def pagina_versionada_em_dados() -> list[str]:
    """Arquivos de pagina dentro de dados/. Nenhum pode ser versionado."""
    achados = []
    for caminho in sorted(DIR_DADOS.rglob("*")):
        if not caminho.is_file():
            continue
        if caminho.suffix.lower() in EXTENSOES_DE_PAGINA:
            achados.append(caminho.relative_to(DIR_RAIZ).as_posix())
    return achados


def testar_sem_pagina_versionada_em_dados() -> None:
    achados = pagina_versionada_em_dados()
    checar(
        not achados,
        "dados/ nao pode ter pagina versionada (.html, .htm, .xhtml, .svg): "
        + ", ".join(achados),
    )


def arquivo_com_campo_pessoal() -> list[str]:
    """Arquivo de dados/ com campo pessoal do SAPL dentro de um JSON."""
    chaves = set(campos_pessoais(CONFIG))
    achados = []
    for caminho in sorted(DIR_DADOS.rglob("*.json")):
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if contem_chave(dados, chaves):
            achados.append(caminho.relative_to(DIR_RAIZ).as_posix())
    return achados


def contem_chave(valor, chaves: set) -> bool:
    if isinstance(valor, dict):
        if chaves & set(valor.keys()):
            return True
        return any(contem_chave(sub, chaves) for sub in valor.values())
    if isinstance(valor, list):
        return any(contem_chave(sub, chaves) for sub in valor)
    return False


def testar_sem_campo_pessoal_em_dados() -> None:
    achados = arquivo_com_campo_pessoal()
    nomes = ", ".join(campos_pessoais(CONFIG))
    checar(
        not achados,
        f"dados/ nao pode ter campo pessoal ({nomes}): " + ", ".join(achados),
    )


def main() -> int:
    try:
        pisos = {}
        for ano in ANOS:
            pisos[ano] = {
                chave: exigir_piso(chave, PISOS[ano][chave], ano)
                for chave in (
                    "sessoes_ordinarias",
                    "projetos_lei_legislativo_e_executivo",
                    "vereadores",
                )
            }
    except PisoNaoDefinido as erro:
        print(str(erro), file=sys.stderr)
        return 1

    falhas = []
    testes_globais = (
        ("testar_sem_pagina_versionada_em_dados", testar_sem_pagina_versionada_em_dados),
        ("testar_sem_campo_pessoal_em_dados", testar_sem_campo_pessoal_em_dados),
    )
    for nome, teste in testes_globais:
        try:
            teste()
        except FalhaSanidade as erro:
            falhas.append(f"{nome}: {erro}")
        except Exception as erro:
            falhas.append(f"{nome}: erro inesperado - {erro}")
    for ano in ANOS:
        piso = pisos[ano]
        for nome, teste in (
            (f"testar_vereadores_{ano}", lambda a=ano, p=piso: testar_vereadores(a, p["vereadores"])),
            (
                f"testar_json_atuacao_{ano}",
                lambda a=ano, p=piso: testar_json_atuacao(
                    a,
                    p["sessoes_ordinarias"],
                    p["projetos_lei_legislativo_e_executivo"],
                    p["vereadores"],
                ),
            ),
            (f"testar_csv_atuacao_{ano}", lambda a=ano: testar_csv_atuacao(a)),
            (f"testar_arquivo_real_{ano}", lambda a=ano: testar_arquivo_real(a)),
        ):
            try:
                teste()
            except FalhaSanidade as erro:
                falhas.append(f"{nome}: {erro}")
            except Exception as erro:
                falhas.append(f"{nome}: erro inesperado - {erro}")

    if falhas:
        print("FALHA nos testes de sanidade:", file=sys.stderr)
        for falha in falhas:
            print(f"  - {falha}", file=sys.stderr)
        return 1

    n_testes = 4 * len(ANOS) + len(testes_globais)
    print(f"OK: {n_testes} testes de sanidade passaram.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
