#!/usr/bin/env python3
"""Grava no index.html o bloco do cabecalho que depende da cidade.

O resto da tela le config_cidade.json no navegador. So o que precisa existir
antes do JavaScript fica aqui: titulo da pagina, descricao, etiquetas de
compartilhamento, endereco canonico e a politica de seguranca de conteudo
(CSP), que precisa do endereco do SAPL para liberar as fotos oficiais.

Uso:
  python scripts/gerar_cabecalho_index.py            grava o bloco
  python scripts/gerar_cabecalho_index.py --conferir sai com erro se o bloco estiver desatualizado
"""

from __future__ import annotations

import html
import json
import pathlib
import re
import sys
from urllib.parse import urlsplit

RAIZ = pathlib.Path(__file__).resolve().parent.parent
INDEX = RAIZ / "index.html"
CONFIG = RAIZ / "config_cidade.json"

INICIO = "<!-- inicio: bloco gerado por scripts/gerar_cabecalho_index.py a partir de config_cidade.json; nao edite a mao -->"
FIM = "<!-- fim: bloco gerado -->"


def origem_https(url: str) -> str:
    partes = urlsplit(str(url).strip())
    if partes.scheme != "https" or not partes.netloc:
        raise SystemExit(f"Endereco precisa ser https: {url!r}")
    return f"https://{partes.netloc}"


def montar_bloco(cfg: dict) -> str:
    cidade = cfg["cidade"]["nome"]
    uf = cfg["cidade"]["uf"]
    painel = cfg["painel"]
    projeto = painel["nome_projeto"]
    endereco = painel["endereco_publico"]
    sapl = origem_https(cfg["sapl"]["endereco_base"])
    anos = cfg["recorte"]["anos"]

    titulo = f"{projeto}: Câmara Municipal de {cidade} ({uf})"
    descricao = (
        f"O que a Câmara Municipal de {cidade} ({uf}) votou de {anos[0]} a {anos[-1]}, "
        "quem estava presente em cada sessão e como cada vereador votou, "
        "com link para o registro oficial no SAPL."
    )
    csp = "; ".join([
        "default-src 'self'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-src 'none'",
        "child-src 'none'",
        "worker-src 'none'",
        "manifest-src 'none'",
        "font-src 'none'",
        f"img-src 'self' {sapl}",
        "style-src 'self'",
        "script-src 'self'",
        "connect-src 'self'",
        "form-action 'none'",
        "upgrade-insecure-requests",
    ])
    e = lambda s: html.escape(str(s), quote=False).replace("\"", "&quot;")  # noqa: E731
    linhas = [
        INICIO,
        f'<meta http-equiv="Content-Security-Policy" content="{e(csp)}">',
        f"<title>{e(titulo)}</title>",
        f'<meta name="description" content="{e(descricao)}">',
        f'<link rel="canonical" href="{e(endereco)}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="pt_BR">',
        f'<meta property="og:site_name" content="{e(projeto)}">',
        f'<meta property="og:title" content="{e(titulo)}">',
        f'<meta property="og:description" content="{e(descricao)}">',
        f'<meta property="og:url" content="{e(endereco)}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{e(titulo)}">',
        f'<meta name="twitter:description" content="{e(descricao)}">',
        FIM,
    ]
    return "\n".join(linhas)


def aplicar(texto: str, bloco: str) -> str:
    padrao = re.compile(re.escape(INICIO) + r".*?" + re.escape(FIM), re.S)
    if not padrao.search(texto):
        raise SystemExit("Marcadores do bloco gerado nao encontrados no index.html.")
    return padrao.sub(lambda _m: bloco, texto, count=1)


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    atual = INDEX.read_text(encoding="utf-8")
    novo = aplicar(atual, montar_bloco(cfg))
    if "--conferir" in sys.argv:
        if novo != atual:
            print("index.html desatualizado. Rode python scripts/gerar_cabecalho_index.py")
            return 1
        print("OK: cabecalho do index.html confere com config_cidade.json.")
        return 0
    if novo != atual:
        INDEX.write_text(novo, encoding="utf-8", newline="\n")
        print("index.html atualizado.")
    else:
        print("index.html ja estava atualizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
