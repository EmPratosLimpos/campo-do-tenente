#!/usr/bin/env python3
"""Gera prints locais da D2b em docs-previa/ (nao commitar) com verificacao de cada estado.

Para cada largura (390 e 1440) e tema (claro e escuro):
- aba Camara nos tres periodos (so o periodo escolhido visivel, sem rolagem lateral);
- aba Vereadores com Jorge Quege e Rafael Ventura (cabecalho, perfil e cartoes sem
  sobreposicao, legenda de presenca com numero e rotulo na mesma linha).

Antes de cada print o script confere no DOM a visibilidade real (getBoundingClientRect
e estilo computado) e grava o resultado em docs-previa/d2b-verificacao.json.
"""

from __future__ import annotations

import json
import pathlib
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parent.parent
OUT = RAIZ / "docs-previa"

PERIODOS = ("sessao", "mes", "todo")
VEREADORES = (("1", "jorge-quege"), ("5", "rafael-ventura"))
MARCADORES = {
    "sessao": "Presença dos vereadores",
    "mes": "Quantas votações por tipo?",
    "todo": "Qual foi o resultado das votações?",
}

JS_HELPERS = """
() => {
  window.__vis = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    let n = el;
    while (n && n !== document.body) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      n = n.parentElement;
    }
    return true;
  };
  return true;
}
"""

JS_ESTADO = """(periodo) => {
  const ids = { sessao: 'painel-periodo-sessao', mes: 'painel-periodo-mes', todo: 'painel-periodo-todo' };
  const out = { paineis: {}, marcadores: {}, scroll: {}, quebraLetra: [] };
  Object.keys(ids).forEach(function (p) {
    const el = document.getElementById(ids[p]);
    const cs = el ? getComputedStyle(el) : null;
    const r = el ? el.getBoundingClientRect() : { width: 0, height: 0 };
    out.paineis[p] = {
      visivel: window.__vis(el),
      display: cs ? cs.display : 'sem-elemento',
      area: el ? Math.round(r.width) + 'x' + Math.round(r.height) : '0x0'
    };
  });
  const texto = document.body.innerText;
  Object.keys(MARCADORES_JS).forEach(function (p) {
    out.marcadores[p] = texto.indexOf(MARCADORES_JS[p]) !== -1;
  });
  out.scroll = {
    sw: document.documentElement.scrollWidth,
    cw: document.documentElement.clientWidth
  };
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let el = walker.currentNode;
  while (el) {
    if (window.__vis(el) && !el.closest('.pular-conteudo')) {
      let direto = '';
      for (const n of el.childNodes) {
        if (n.nodeType === 3) direto += n.textContent;
      }
      const t = direto.replace(/\\s+/g, ' ').trim();
      if (t.length > 6) {
        const r = el.getBoundingClientRect();
        if (r.width < 60) {
          const cs = getComputedStyle(el);
          ctx.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
          const padH = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
          const disponivel = r.width - padH;
          let pior = { palavra: '', largura: 0 };
          t.split(' ').forEach(function (palavra) {
            const w = ctx.measureText(palavra).width;
            if (w > pior.largura) pior = { palavra: palavra, largura: Math.round(w) };
          });
          if (pior.largura > disponivel + 1) {
            out.quebraLetra.push({ texto: t.slice(0, 30), largura: Math.round(r.width), palavra: pior.palavra });
          }
        }
      }
    }
    el = walker.nextNode();
  }
  return out;
}"""

JS_VEREADORES = """() => {
  const seletores = ['.titulo-site', '.selo-sapl', '.subtitulo-site', '.titulo-vereadores',
    '.seletor-vereador', '.nav-vereador', '.perfil-cabecalho'];
  const els = [];
  seletores.forEach(function (s) {
    document.querySelectorAll(s).forEach(function (el) {
      if (window.__vis(el)) els.push({ sel: s, el: el, r: el.getBoundingClientRect() });
    });
  });
  const sobrepostos = [];
  for (let i = 0; i < els.length; i++) {
    for (let j = i + 1; j < els.length; j++) {
      if (els[i].el.contains(els[j].el) || els[j].el.contains(els[i].el)) continue;
      const a = els[i].r, b = els[j].r;
      const ix = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const iy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (ix > 2 && iy > 2) sobrepostos.push(els[i].sel + ' sobrepoe ' + els[j].sel);
    }
  }
  const legendaFora = [];
  document.querySelectorAll('.rosca-legenda').forEach(function (leg) {
    if (!window.__vis(leg)) return;
    const dts = leg.querySelectorAll('dt');
    const dds = leg.querySelectorAll('dd');
    dts.forEach(function (dt, i) {
      const dd = dds[i];
      if (!dd) return;
      const rt = dt.getBoundingClientRect();
      const rd = dd.getBoundingClientRect();
      if (Math.abs((rt.top + rt.bottom) / 2 - (rd.top + rd.bottom) / 2) > Math.max(rt.height, rd.height) / 2) {
        legendaFora.push(dt.textContent.trim());
      }
    });
  });
  const titulo = document.querySelector('.titulo-site').getBoundingClientRect();
  const seletor = document.querySelector('#sel-vereador').getBoundingClientRect();
  return {
    sobrepostos: sobrepostos,
    legendaFora: legendaFora,
    larguraTitulo: Math.round(titulo.width),
    larguraSeletor: Math.round(seletor.width),
    sw: document.documentElement.scrollWidth,
    cw: document.documentElement.clientWidth
  };
}"""

JS_DUAS_COLUNAS = """(selArea) => {
  const area = document.querySelector(selArea);
  if (!area || !window.__vis(area)) return false;
  const cards = Array.prototype.slice.call(area.querySelectorAll('.card-app, .secao'))
    .filter(function (el) { return window.__vis(el); });
  for (let i = 0; i < cards.length; i++) {
    for (let j = i + 1; j < cards.length; j++) {
      const a = cards[i].getBoundingClientRect();
      const b = cards[j].getBoundingClientRect();
      const overlapV = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      const separadoH = Math.max(a.left, b.left) - Math.min(a.right, b.right);
      if (overlapV > Math.min(a.height, b.height) * 0.5 && separadoH > 8) return true;
    }
  }
  return false;
}"""


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)


def _clicar_periodo(page, periodo: str) -> None:
    largura = page.viewport_size["width"]
    seletor = (
        f'#seletor-periodo-lateral button[data-periodo="{periodo}"]'
        if largura >= 900
        else f'#seletor-periodo-mobile button[data-periodo="{periodo}"]'
    )
    page.click(seletor)
    page.wait_for_timeout(500)


def _checar_camara(page, registro: dict, periodo: str) -> None:
    estado = page.evaluate(
        "(arg) => { const MARCADORES_JS = " + json.dumps(MARCADORES) + "; return (" + JS_ESTADO + ")(arg); }",
        periodo,
    )
    registro["paineis"] = estado["paineis"]
    registro["marcadores"] = estado["marcadores"]
    registro["scroll"] = estado["scroll"]
    registro["quebraLetra"] = estado["quebraLetra"]
    for p in PERIODOS:
        esperado = p == periodo
        assert estado["paineis"][p]["visivel"] is esperado, f"painel {p}: {estado['paineis'][p]}"
        assert estado["marcadores"][p] is esperado, f"marcador de {p} fora do periodo {periodo}"
    assert estado["scroll"]["sw"] <= estado["scroll"]["cw"] + 1, f"scroll horizontal: {estado['scroll']}"
    assert estado["quebraLetra"] == [], f"quebra letra a letra: {estado['quebraLetra']}"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    servidor = ThreadingHTTPServer(("127.0.0.1", 8798), _Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.35)
    base = "http://127.0.0.1:8798/index.html"
    verificacao: dict = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for tema in ("claro", "escuro"):
            for largura in (390, 1440):
                page = browser.new_page(viewport={"width": largura, "height": 900})
                page.goto(base, wait_until="networkidle", timeout=180000)
                page.evaluate(
                    """(t) => {
                      localStorage.setItem("dashboard-campo-tenente-tema", t);
                      document.documentElement.setAttribute("data-tema", t);
                    }""",
                    tema,
                )
                page.reload(wait_until="networkidle")
                page.evaluate(JS_HELPERS)
                page.wait_for_selector("#sel-vereador", state="attached", timeout=120000)
                page.wait_for_selector("#bloco-votado-sessao .card-header", timeout=120000)
                page.wait_for_timeout(500)

                if largura >= 900:
                    page.click('button[data-secao-lateral="camara"]')
                else:
                    page.click('button[data-secao="camara"]')
                page.wait_for_timeout(400)
                for periodo in PERIODOS:
                    _clicar_periodo(page, periodo)
                    registro = verificacao.setdefault(
                        f"camara-{periodo}-{largura}-{tema}", {}
                    )
                    _checar_camara(page, registro, periodo)
                    if largura >= 900:
                        registro["duasColunas"] = page.evaluate(
                            JS_DUAS_COLUNAS, "#painel-camara .painel-camara-interno.ativo"
                        )
                        assert registro["duasColunas"], "camara sem duas colunas em desktop"
                    nome = f"d2b-{largura}-camara-{periodo}-{tema}.png"
                    page.screenshot(path=str(OUT / nome), full_page=True)
                    registro["print"] = nome

                if largura >= 900:
                    page.click('button[data-secao-lateral="vereadores"]')
                else:
                    page.click('button[data-secao="vereadores"]')
                page.wait_for_selector(".perfil-cabecalho", timeout=120000)
                for vid, slug in VEREADORES:
                    page.select_option("#sel-vereador", vid)
                    page.wait_for_timeout(600)
                    chave = f"vereadores-{slug}-{largura}-{tema}"
                    registro = verificacao.setdefault(chave, {})
                    estado = page.evaluate(JS_VEREADORES)
                    registro.update(estado)
                    assert estado["sobrepostos"] == [], f"sobrepostos: {estado['sobrepostos']}"
                    assert estado["legendaFora"] == [], f"legenda fora da linha: {estado['legendaFora']}"
                    assert estado["sw"] <= estado["cw"] + 1, f"scroll horizontal: {estado}"
                    if largura >= 900:
                        assert estado["larguraTitulo"] >= 300, f"titulo estreito: {estado}"
                        assert estado["larguraSeletor"] >= 200, f"seletor estreito: {estado}"
                        registro["duasColunas"] = page.evaluate(JS_DUAS_COLUNAS, "#conteudo-vereadores")
                        assert registro["duasColunas"], "vereadores sem duas colunas em desktop"
                    nome = f"d2b-{largura}-vereadores-{slug}-{tema}.png"
                    page.screenshot(path=str(OUT / nome), full_page=True)
                    registro["print"] = nome
                page.close()
        browser.close()
    servidor.shutdown()

    caminho = OUT / "d2b-verificacao.json"
    caminho.write_text(json.dumps(verificacao, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Prints e verificacao em {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
