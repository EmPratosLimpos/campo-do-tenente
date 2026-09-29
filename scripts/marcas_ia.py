#!/usr/bin/env python3
"""Deteccao de marcas de ferramentas de IA em mensagens de commit."""

from __future__ import annotations

import pathlib
import re
import subprocess

# Nomes ou fragmentos de e-mail associados a ferramentas de IA (case insensitive).
_MARCAS_COAUTOR = re.compile(
    r"(?i)"
    r"(cursor|cursoragent|claude|anthropic|commandcode|gemini|antigravity|"
    r"copilot|opencode|aider|grok)"
)

_RE_COAUTHOR = re.compile(r"^\s*co-authored-by:\s*(.+)$", re.IGNORECASE)
# Prefixo opcional sem letras ASCII (emoji, espacos, simbolos) antes de "Generated with".
_RE_GENERATED = re.compile(r"^[^a-zA-Z]*generated with\b", re.IGNORECASE)
_RE_CLAUDE_SESSION = re.compile(r"^\s*claude-session:\s*", re.IGNORECASE)


def linha_e_marca_ia(linha: str) -> bool:
    """Retorna True se a linha inteira for uma marca de IA a remover ou reprovar."""
    if _RE_GENERATED.search(linha):
        return True
    if _RE_CLAUDE_SESSION.search(linha):
        return True
    m = _RE_COAUTHOR.match(linha)
    if m and _MARCAS_COAUTOR.search(m.group(1)):
        return True
    return False


def sanitizar_mensagem_commit(mensagem: str) -> str:
    """Remove marcas de IA e linhas em branco finais (espelha o hook commit-msg)."""
    linhas = mensagem.splitlines()
    filtradas = [ln for ln in linhas if not linha_e_marca_ia(ln)]
    while filtradas and filtradas[-1].strip() == "":
        filtradas.pop()
    if not filtradas:
        return ""
    return "\n".join(filtradas) + "\n"


def mensagem_tem_marca_ia(mensagem: str) -> bool:
    """True se alguma linha da mensagem for marca de IA."""
    return any(linha_e_marca_ia(ln) for ln in mensagem.splitlines())


def ler_marco_marcas_ia(raiz: pathlib.Path) -> str | None:
    arq = raiz / ".marcas-ia-desde"
    if not arq.is_file():
        return None
    linha = arq.read_text(encoding="utf-8").strip().splitlines()
    if not linha:
        return None
    return linha[0].strip()


def verificar_commits_marcas_ia(
    raiz: pathlib.Path,
) -> tuple[list[str], list[str]]:
    """
    Verifica mensagens de commit apos o marco em .marcas-ia-desde.

    Retorna (erros, avisos). Erros vazios e aviso presente = historico indisponivel.
    """
    erros: list[str] = []
    avisos: list[str] = []
    marco = ler_marco_marcas_ia(raiz)
    if not marco:
        avisos.append(
            "Arquivo .marcas-ia-desde ausente ou vazio: verificacao de marcas de IA ignorada."
        )
        return erros, avisos

    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{marco}^{{commit}}"],
        cwd=raiz,
        capture_output=True,
        text=True,
    )
    if verify.returncode != 0:
        avisos.append(
            f"Marco {marco} indisponivel (clone raso ou historico incompleto): "
            "verificacao de marcas de IA ignorada."
        )
        return erros, avisos

    log = subprocess.run(
        ["git", "log", f"{marco}..HEAD", "--format=%H%x00%B%x00"],
        cwd=raiz,
        capture_output=True,
        text=True,
    )
    if log.returncode != 0:
        avisos.append(
            "Nao foi possivel ler o historico de commits: verificacao de marcas de IA ignorada."
        )
        return erros, avisos

    partes = [p for p in log.stdout.split("\x00") if p != ""]
    for i in range(0, len(partes), 2):
        h = partes[i].strip()
        if len(h) != 40:
            continue
        corpo = partes[i + 1] if i + 1 < len(partes) else ""
        if mensagem_tem_marca_ia(corpo):
            erros.append(
                f"VIOLACAO: commit {h[:12]} contem marca de ferramenta de IA na mensagem."
            )

    return erros, avisos
