#!/usr/bin/env python3
"""Regra so dados mudaram, usada pelo workflow semanal.

Recebe a lista de arquivos alterados e responde se todos sao dados.
Permite: tudo em dados/, CHANGELOG.md, config_cidade.json e JSON da tela.
Qualquer codigo (.py, .html, .js, .css, .yml, outro .md) reprova.

Uso: python scripts/so_dados_mudaram.py <arquivo...> <arquivo...>
Saida 0 quando so dados mudaram. Saida 1 caso contrario.
"""

from __future__ import annotations

import sys
from pathlib import Path

EXATOS_PERMITIDOS = frozenset({"config_cidade.json", "CHANGELOG.md"})
PREFIXOS_PERMITIDOS = ("dados/", "tela/")
SUFFIXOS_CODIGO = (".py", ".html", ".js", ".css", ".yml", ".yaml", ".md")


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
            if normalizado.startswith("tela/"):
                return normalizado.lower().endswith(".json")
            return True
    return False


def arquivos_fora_do_permitido(arquivos: list[str]) -> list[str]:
    fora = []
    for item in arquivos or []:
        normal = normalizar(item)
        if not normal:
            continue
        if not e_dado(normal):
            fora.append(normal)
            continue
        base = normal.lower()
        if normal in EXATOS_PERMITIDOS:
            continue
        for sufixo in SUFFIXOS_CODIGO:
            if base.endswith(sufixo):
                fora.append(normal)
                break
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


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 1 and Path(args[0]).is_file():
        try:
            texto = Path(args[0]).read_text(encoding="utf-8")
            if "\n" in texto or " " not in texto.strip():
                args = [item for item in texto.split() if item.strip()]
        except OSError:
            pass
    fora = arquivos_fora_do_permitido(args)
    if not fora:
        print("So dados mudaram.")
        return 0
    print("Codigo fora de dados:")
    for item in fora:
        print(f"  {item}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
