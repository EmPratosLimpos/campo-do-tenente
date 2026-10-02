#!/usr/bin/env python3
"""Regra so dados mudaram, usada pelo workflow semanal.

Recebe a lista de arquivos alterados e responde se todos sao dados.
Permite: dentro de dados/ apenas .json, .sha256, .csv e .txt, mais
CHANGELOG.md e config_cidade.json na raiz.
A lista e de extensoes permitidas, nao de extensoes proibidas: qualquer
arquivo de dados/ fora dessa lista reprova, mesmo com extensao nova.
Nenhum gerador grava em tela/, por isso tela/ reprova.

A regra aceita exatamente o que o workflow leva no commit:
git add -- dados config_cidade.json CHANGELOG.md.

Uso: python scripts/so_dados_mudaram.py <arquivo...> <arquivo...>
Saida 0 quando so dados mudaram. Saida 1 caso contrario.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXATOS_PERMITIDOS = frozenset({"config_cidade.json", "CHANGELOG.md"})
PREFIXOS_PERMITIDOS = ("dados/",)
EXTENSOES_PERMITIDAS_DADOS = frozenset({".json", ".sha256", ".csv", ".txt"})


def normalizar(caminho: str) -> str:
    texto = str(caminho or "").strip().replace("\\", "/")
    while texto.startswith("./"):
        texto = texto[2:]
    return texto


def e_dado(normalizado: str) -> bool:
    if not normalizado:
        return True
    if normalizado in EXATOS_PERMITIDOS:
        return True
    for prefixo in PREFIXOS_PERMITIDOS:
        if normalizado == prefixo.rstrip("/") or normalizado.startswith(prefixo):
            return True
    return False


def extensao_permitida(normalizado: str) -> bool:
    """Dentro de dados/ so passam as extensoes da lista permitida."""
    return Path(normalizado).suffix.lower() in EXTENSOES_PERMITIDAS_DADOS


def arquivos_fora_do_permitido(arquivos: list[str]) -> list[str]:
    fora = []
    for item in arquivos or []:
        normal = normalizar(item)
        if not normal:
            continue
        if not e_dado(normal):
            fora.append(normal)
            continue
        if normal in EXATOS_PERMITIDOS:
            continue
        if not extensao_permitida(normal):
            fora.append(normal)
    vistos = set()
    saida = []
    for item in fora:
        if item not in vistos:
            vistos.add(item)
            saida.append(item)
    return sorted(saida)


def so_dados_mudaram(arquivos: list[str]) -> bool:
    limpos = [normalizar(item) for item in arquivos or []]
    limpos = [item for item in limpos if item]
    if not limpos:
        return True
    return not arquivos_fora_do_permitido(limpos)


def arquivos_de_git_status(porcelana: str) -> list[str]:
    saida = []
    for linha in (porcelana or "").splitlines():
        linha = linha.rstrip("\n")
        if len(linha) < 4:
            continue
        resto = linha[3:].strip()
        if " -> " in resto:
            resto = resto.split(" -> ", 1)[1].strip()
        nome = resto.strip().strip('"')
        if nome:
            saida.append(nome)
    return saida


def planejar_publicacao(arquivos: list[str]) -> dict:
    """Decide o proximo passo do workflow a partir dos arquivos alterados.

    Devolve um dicionario com decisao e fora:
    sem_mudanca quando a lista fica vazia,
    publicar quando so dados mudaram,
    bloquear quando algum codigo mudou junto.
    O workflow publica so com publicar e abre uma so issue com bloquear.
    """
    limpos = [normalizar(item) for item in arquivos or []]
    limpos = [item for item in limpos if item]
    if not limpos:
        return {"decisao": "sem_mudanca", "fora": [], "total": 0}
    fora = arquivos_fora_do_permitido(limpos)
    if not fora:
        return {"decisao": "publicar", "fora": [], "total": len(limpos)}
    return {"decisao": "bloquear", "fora": fora, "total": len(limpos)}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 1 and Path(args[0]).is_file():
        try:
            texto = Path(args[0]).read_text(encoding="utf-8")
            if "\n" in texto or " " not in texto.strip():
                args = [item for item in texto.split() if item.strip()]
        except OSError:
            pass
    plano = planejar_publicacao(args)
    if plano["decisao"] == "sem_mudanca":
        print("Sem mudanca.")
        return 0
    if plano["decisao"] == "publicar":
        print("So dados mudaram.")
        return 0
    print("Arquivo fora do permitido so para dados:")
    for item in plano["fora"]:
        print(f"  {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
