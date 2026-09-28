#!/usr/bin/env python3
"""Gera tela/modelo.html (estrutura sem dados de exemplo) a partir da referencia Campo Largo."""

from __future__ import annotations

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
REF = RAIZ / "referencia-campo-largo" / "index.html"
SAIDA = RAIZ / "tela" / "modelo.html"

sys.path.insert(0, str(RAIZ / "scripts"))
from montar_tela_d1b import remover_bloco_votacao_html  # noqa: E402


def neutralizar_dados_exemplo(html: str) -> str:
    """Remove numeros e links de sessao/materia de exemplo do HTML estático."""
    html = re.sub(
        r"<p>Dados oficiais coletados em <strong>[^<]+</strong>\.</p>",
        '<p>Dados oficiais coletados em <strong id="data-coleta-impressao"></strong>.</p>',
        html,
        count=1,
    )
    html = re.sub(
        r'<a class="secao-sub" href="[^"]*"[^>]*>[^<]+</a>',
        '<a class="secao-sub" id="link-titulo-ultima-sessao" href="#" hidden></a>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<a class="card-meta" id="link-meta-data-votacoes-sessao" href="#")[^>]*>[\s\S]*?<svg',
        r'\1><span id="texto-meta-data-votacoes-sessao"></span><svg',
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="card-app" id="card-votacoes-sessao"[\s\S]*?<a class="card-meta" )href="[^"]*"',
        r'\1id="link-meta-data-votacoes-sessao" href="#"',
        html,
        count=1,
    )
    html = re.sub(
        r'(<a class="card-meta" id="link-meta-data-votacoes-sessao" href="#")[^>]*>[\s\S]*?<svg',
        r'\1><span id="texto-meta-data-votacoes-sessao"></span><svg',
        html,
        count=1,
    )
    html = re.sub(
        r'<span class="metrica-numero">[^<]*</span>',
        '<span class="metrica-numero"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'<span class="det-valor det-valor-unanimidade">[\s\S]*?</span>',
        '<span class="det-valor det-valor-unanimidade"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'<span class="det-valor det-valor-maioria">[\s\S]*?</span>',
        '<span class="det-valor det-valor-maioria"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'aria-label="[^"]*matérias votadas[^"]*"',
        'aria-label="Matérias votadas na sessão"',
        html,
        count=1,
    )
    html = re.sub(
        r'<span class="anel-porcento">[^<]*</span>',
        '<span class="anel-porcento"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="card-app" id="card-presenca-sessao"[\s\S]*?<a class="card-meta" )href="[^"]*"',
        r'\1id="link-meta-presenca-sessao" href="#"',
        html,
        count=1,
    )
    html = re.sub(
        r'(<a class="card-meta" id="link-meta-presenca-sessao" href="#")[^>]*>[\s\S]*?<svg',
        r'\1><span id="texto-meta-presenca-sessao"></span><svg',
        html,
        count=1,
    )
    pres = re.search(
        r'<div class="card-app" id="card-presenca-sessao"[\s\S]*?</div>\s*</div>',
        html,
    )
    if pres:
        bloco = pres.group(0)
        bloco = re.sub(
            r'(<span class="capsula-valor">)\s*[^<]*\s*(</span>)',
            r"\1\2",
            bloco,
        )
        html = html[: pres.start()] + bloco + html[pres.end() :]
    html = re.sub(
        r'<footer class="rodape-coleta"[^>]*>[\s\S]*?</footer>',
        '<footer class="rodape-coleta" aria-label="Informações sobre a coleta de dados"></footer>',
        html,
    )
    html = re.sub(
        r'<h2 class="sessao-titulo">[^<]+</h2>',
        '<h2 class="sessao-titulo" id="titulo-periodo-mes"></h2>',
        html,
        count=1,
    )
    html = re.sub(
        r'<p class="sessao-meta">[^<]+</p>',
        '<p class="sessao-meta" id="meta-periodo-mes"></p>',
        html,
        count=1,
    )
    html = re.sub(
        r'<div class="barra-tema-cam barra-temas" id="tipos-mes-barras">[\s\S]*?</div>\s*</section>',
        '<div class="barra-tema-cam barra-temas" id="tipos-mes-barras"></div></section>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="painel-camara-interno" id="painel-periodo-todo"[\s\S]*?<h2 class="sessao-titulo">)[^<]+',
        r'\1<span id="titulo-periodo-todo"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="painel-camara-interno" id="painel-periodo-todo"[\s\S]*?<p class="sessao-meta">)[^<]+',
        r'\1<span id="meta-periodo-todo"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="painel-camara-interno" id="painel-periodo-todo"[\s\S]*?<p class="legenda">)Projetos de Lei[^<]+',
        r'\1<span id="legenda-tipos-todo"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<div class="painel-camara-interno" id="painel-periodo-todo"[\s\S]*?<div class="barra-tema-cam barra-temas">)[\s\S]*?(</div>\s*</section>\s*<section class="secao" aria-labelledby="tit-resultado-todo">)',
        r'\1<div id="barra-tipos-todo"></div>\2',
        html,
        count=1,
    )
    html = re.sub(
        r'(<section class="secao" aria-labelledby="tit-resultado-todo">[\s\S]*?<p class="legenda">)Resultado dos[^<]+',
        r'\1<span id="legenda-resultado-todo"></span>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<section class="secao" aria-labelledby="tit-resultado-todo">[\s\S]*?<div class="barra-status-trilho")[^>]*>[\s\S]*?</div>',
        r'\1 id="barra-resultado-todo" role="img"></div>',
        html,
        count=1,
    )
    html = re.sub(
        r'(<section class="secao" aria-labelledby="tit-resultado-todo">[\s\S]*?<div class="status-cartoes">)[\s\S]*?(</div>\s*<p class="nota-rodape">)',
        r'\1<div id="cartoes-resultado-todo"></div>\2',
        html,
        count=1,
    )
    html = re.sub(
        r'<p class="nota-rodape">[^<]+</p>',
        '<p class="nota-rodape" id="nota-resultado-todo"></p>',
        html,
        count=1,
    )
    html = re.sub(
        r'var DATA_ULTIMA_SESSAO = "[^"]+";',
        'var DATA_ULTIMA_SESSAO = "";',
        html,
        count=1,
    )
    html = re.sub(r"var SESSAO_VOTACAO_ID = \d+;", "var SESSAO_VOTACAO_ID = null;", html, count=1)
    return html


def main() -> int:
    if not REF.is_file():
        print(f"Referencia ausente: {REF}", file=sys.stderr)
        return 1
    html = REF.read_text(encoding="utf-8")
    html = remover_bloco_votacao_html(html)
    linhas = html.split("\n")
    html = "\n".join(
        ln for ln in linhas if "turnstile" not in ln.lower() and "btn-votar" not in ln.lower()
    )
    if "<script>" in html:
        cabeca, script = html.split("<script>", 1)
        cabeca = neutralizar_dados_exemplo(cabeca)
        html = cabeca + "<script>" + script
    else:
        html = neutralizar_dados_exemplo(html)
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(html, encoding="utf-8")
    print(f"Gerado {SAIDA} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
