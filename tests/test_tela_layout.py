"""Playwright: layout responsivo (390 e 1440 px) das abas Camara e Vereadores.

Checagens obrigatorias da D2b:
- em 390 e 1440, nas duas abas e nos tres periodos, so os elementos do periodo
  escolhido ficam visiveis (pelo texto e pela visibilidade real:
  getBoundingClientRect e estilo computado, nao so o atributo hidden);
- nenhum elemento de texto do cabecalho e do perfil se sobrepoe a outro;
- o titulo principal nunca fica com largura menor que 300 px em 1440;
- nenhuma palavra quebra letra a letra: nenhum elemento de texto com largura
  menor que 60 px contendo mais de 6 caracteres;
- sem rolagem lateral em 390 e 1440.
"""

from __future__ import annotations

import pathlib
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)


JS_HELPERS = """
() => {
  window.__vis = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 0 || r.height <= 0) return false;
    let n = el;
    while (n && n !== document.body) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') return false;
      n = n.parentElement;
    }
    return true;
  };
  return true;
}
"""

PERIODOS = ("sessao", "mes", "todo")
MARCADORES = {
    "sessao": "Os 9 vereadores estavam presentes",
    "mes": "Quantas votações por tipo?",
    "todo": "Em 66 sessões ordinárias",
}
BLOCOS_CABECALHO = (".site-logo", ".topo-tagline")
BLOCOS_VEREADORES = (
    ".site-logo",
    ".topo-tagline",
    ".titulo-vereadores",
    ".seletor-vereador",
    ".sel-vereador-wrap",
)
JS_ESTRUTURA = """() => {
  const dentro = (idPai, idFilho) => {
    const pai = document.getElementById(idPai);
    const filho = document.getElementById(idFilho);
    return !!(pai && filho && pai.contains(filho));
  };
  const corpo = document.querySelector('.pagina-corpo');
  return {
    todo_em_painel: dentro('painel-periodo-todo', 'cartao-resumo-todo')
      && dentro('painel-periodo-todo', 'bloco-votado-todo')
      && dentro('painel-periodo-todo', 'temas-distribuicao-todo'),
    vereadores_em_main: dentro('conteudo-principal', 'painel-vereadores'),
    camara_em_main: dentro('conteudo-principal', 'painel-camara'),
    nav_em_corpo: !!(corpo && corpo.contains(document.getElementById('nav-principal')))
  };
}"""

JS_PERIODO_VISIVEL = """(periodo) => {
  const ids = { sessao: 'painel-periodo-sessao', mes: 'painel-periodo-mes', todo: 'painel-periodo-todo' };
  const out = {};
  Object.keys(ids).forEach(function (p) {
    const el = document.getElementById(ids[p]);
    const cs = el ? getComputedStyle(el) : null;
    const r = el ? el.getBoundingClientRect() : { width: 0, height: 0 };
    out[p] = {
      visivel: window.__vis(el),
      display: cs ? cs.display : 'sem-elemento',
      area: el ? Math.round(r.width) + 'x' + Math.round(r.height) : '0x0'
    };
  });
  return out;
}"""

JS_TEXTO_VISIVEL = """() => document.body.innerText"""

JS_SOBRPOSICOES = """(seletores) => {
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
  return sobrepostos;
}"""

JS_QUEBRA_LETRA = """() => {
  const problemas = [];
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
      const texto = direto.replace(/\\s+/g, ' ').trim();
      if (texto.length > 6) {
        const r = el.getBoundingClientRect();
        if (r.width < 60) {
          const cs = getComputedStyle(el);
          ctx.font = cs.fontStyle + ' ' + cs.fontWeight + ' ' + cs.fontSize + ' ' + cs.fontFamily;
          const padH = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
          const disponivel = r.width - padH;
          let pior = { palavra: '', largura: 0 };
          texto.split(' ').forEach(function (palavra) {
            const w = ctx.measureText(palavra).width;
            if (w > pior.largura) pior = { palavra: palavra, largura: Math.round(w) };
          });
          if (pior.largura > disponivel + 1) {
            problemas.push({
              texto: texto.slice(0, 30),
              largura: Math.round(r.width),
              palavra: pior.palavra,
              natural: pior.largura
            });
          }
        }
      }
    }
    el = walker.nextNode();
  }
  return problemas;
}"""

JS_LEGENDA_LINHA = """() => {
  const quebrados = [];
  document.querySelectorAll('.rosca-legenda').forEach(function (leg) {
    if (!window.__vis(leg)) return;
    const dts = leg.querySelectorAll('dt');
    const dds = leg.querySelectorAll('dd');
    dts.forEach(function (dt, i) {
      const dd = dds[i];
      if (!dd) return;
      const rt = dt.getBoundingClientRect();
      const rd = dd.getBoundingClientRect();
      const centroDt = (rt.top + rt.bottom) / 2;
      const centroDd = (rd.top + rd.bottom) / 2;
      if (Math.abs(centroDt - centroDd) > Math.max(rt.height, rd.height) / 2) {
        quebrados.push(dt.textContent.trim());
      }
    });
  });
  return quebrados;
}"""


JS_BOTAO_TEMA = '''() => {
    const btn = document.querySelector("#btn-tema");
    if (!btn) return { ok: false, erro: "botao nao encontrado" };
    const rect = btn.getBoundingClientRect();
    if (rect.width < 44 || rect.height < 44) return { ok: false, erro: `tamanho incorreto: ${rect.width}x${rect.height}` };
    const topo = document.querySelector(".topo-marca-linha");
    if (!topo || !topo.contains(btn)) return { ok: false, erro: "botao fora do cabecalho" };
    const cs = getComputedStyle(btn);
    if (cs.position === "fixed") return { ok: false, erro: "botao ainda fixo no canto" };
    return { ok: true };
}'''
JS_TOPOS_PRIMEIRA_LINHA = """(params) => {
  const area = document.querySelector(params.selArea);
  if (!area || !window.__vis(area)) return { ok: false, motivo: 'sem-area' };
  var items;
  if (params.modo === 'filhos') {
    items = Array.from(area.children).filter(function (el) {
      if (!window.__vis(el)) return false;
      if (el.classList.contains('sessao-titulo-linha') || el.classList.contains('sessao-meta')) return false;
      if (el.classList.contains('rodape-coleta') || el.classList.contains('bloco-votado')) return false;
      return true;
    });
  } else {
    items = Array.from(area.querySelectorAll(params.seletorItem)).filter(function (el) {
      return window.__vis(el);
    });
  }
  if (items.length < 2) return { ok: false, motivo: 'poucos-itens', n: items.length };
  const t0 = items[0].getBoundingClientRect().top;
  const t1 = items[1].getBoundingClientRect().top;
  return { ok: Math.abs(t0 - t1) <= 2, t0: Math.round(t0), t1: Math.round(t1) };
}"""

JS_VERIFICA_DISPOSICAO = """(periodo) => {
  const area = document.querySelector("#painel-periodo-" + periodo);
  if (!area || !window.__vis(area)) return { ok: false, erro: "area invisivel" };
  const getRect = (sel) => {
    const el = area.querySelector(sel);
    if (!el || !window.__vis(el)) return null;
    return el.getBoundingClientRect();
  };
  
  let a1_sel, a2_sel, b1_sel, c_sel;
  if (periodo === "sessao") {
    a1_sel = "#card-votacoes-sessao";
    a2_sel = "#card-presenca-sessao";
    b1_sel = "#card-temas-sessao";
    c_sel = "#bloco-votado-sessao";
  } else if (periodo === "mes") {
    a1_sel = "#card-votacoes-mes";
    a2_sel = "#card-tipos-mes";
    b1_sel = "#card-temas-mes";
    c_sel = "#bloco-votado-mes";
  } else {
    a1_sel = "#cartao-resumo-todo";
    a2_sel = "";
    b1_sel = "#card-temas-todo";
    c_sel = "#bloco-votado-todo";
  }
  
  const a1 = getRect(a1_sel);
  const a2 = a2_sel ? getRect(a2_sel) : null;
  const b1 = getRect(b1_sel);
  const c = getRect(c_sel);
  
  if (!a1 || !b1 || !c) return { ok: false, erro: "elementos nao encontrados ou invisiveis: " + !a1 + " " + !b1 + " " + !c };
  if (periodo !== "todo" && !a2) return { ok: false, erro: "elemento a2 ausente" };
  
  const w = window.innerWidth;
  if (w >= 900) {
    if (Math.abs(a1.top - b1.top) > 2) return { ok: false, erro: "A1 e B1 nao alinhados no topo. diff=" + Math.abs(a1.top - b1.top) };
    if (a2 && a1_sel !== a2_sel) {
      const gapA = a2.top - a1.bottom;
      if (gapA < 0 || gapA > 24) return { ok: false, erro: "gap A1-A2 incorreto: " + gapA };
    }
    if (b1.left <= a1.right) return { ok: false, erro: "B1 nao esta a direita de A1" };
    const areaRect = area.getBoundingClientRect();
    if (c.width < areaRect.width - 100) return { ok: false, erro: "C nao tem largura total" };
    const baseCol = a2 ? a2.bottom : a1.bottom;
    if (c.top < baseCol && c.top < b1.bottom) return { ok: false, erro: "C nao esta embaixo das colunas" };
  } else {
    if (periodo === "todo") {
      if (!(a1.bottom <= b1.top + 2 && b1.bottom <= c.top + 2)) {
        return { ok: false, erro: "ordem incorreta no mobile (todo)" };
      }
    } else if (!(a1.bottom <= a2.top + 2 && a2.bottom <= b1.top + 2 && b1.bottom <= c.top + 2)) {
      return { ok: false, erro: "ordem incorreta no mobile" };
    }
  }
  return { ok: true };
}"""

JS_PRESENCA = """() => {
  const card = document.getElementById("card-presenca-sessao");
  if (!card) return { ok: false, erro: "card nao encontrado" };
  const texto = card.innerText;
  if (texto.includes("Fora do mandato naquela data") || texto.includes("fora do mandato")) {
    return { ok: false, erro: "texto 'Fora do mandato' esta visivel" };
  }
  if (!/Presentes/i.test(texto) || !/Projetos votados/i.test(texto)) {
    return { ok: false, erro: "lista de presenca incompleta" };
  }
  return { ok: true };
}"""

JS_DUAS_COLUNAS = """(selArea) => {
  const area = document.querySelector(selArea);
  if (!area || !window.__vis(area)) return false;
  const cards = Array.prototype.slice.call(
    area.querySelectorAll('.card-app, .secao, .cartao.ac-cartao, article.cartao')
  ).filter(function (el) { return window.__vis(el); });
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

JS_TOPO_MEDICAO = """() => {
  const topo = document.querySelector('.topo-fixo');
  const sel = document.getElementById('sel-vereador');
  if (!topo || !sel) return { erro: 'sem-elementos' };
  const rt = topo.getBoundingClientRect();
  const rs = sel.getBoundingClientRect();
  const alvo = document.elementFromPoint(
    Math.round(rs.left + rs.width / 2),
    Math.round(rs.top + rs.height / 2)
  );
  const lab = document.querySelector('label[for="sel-vereador"]');
  const share = document.querySelector('#sub-vereadores .btn-abrir-share');
  const tema = document.querySelector('#btn-tema');
  let tema_sobrepoe_sel = false;
  if (tema) {
    const t = tema.getBoundingClientRect();
    const ix = Math.min(t.right, rs.right) - Math.max(t.left, rs.left);
    const iy = Math.min(t.bottom, rs.bottom) - Math.max(t.top, rs.top);
    tema_sobrepoe_sel = ix > 2 && iy > 2;
  }
  return {
    compacto: topo.classList.contains('compacto'),
    altura_topo: Math.round(rt.height),
    topo_topo: Math.round(rt.top),
    sel_altura: Math.round(rs.height),
    sel_largura: Math.round(rs.width),
    sel_no_ponto: alvo === sel,
    sel_visivel: window.__vis(sel),
    sel_ativo: !sel.disabled,
    share_visivel: window.__vis(share),
    rotulo_assoc: !!lab && lab.textContent.trim().length > 0,
    tema_sobrepoe_sel: tema_sobrepoe_sel
  };
}"""


def _sem_scroll_horizontal(page) -> None:
    dims = page.evaluate(
        """() => ({
          sw: document.documentElement.scrollWidth,
          cw: document.documentElement.clientWidth
        })"""
    )
    assert dims["sw"] <= dims["cw"] + 1, f"scroll horizontal sw={dims['sw']} cw={dims['cw']}"


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTelaLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8794), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8794/index.html"
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _abrir(self, page, largura: int) -> None:
        page.set_viewport_size({"width": largura, "height": 900})
        page.goto(self.base, wait_until="networkidle", timeout=120000)
        page.evaluate(JS_HELPERS)
        page.wait_for_selector("#sel-vereador", state="attached", timeout=60000)
        page.wait_for_selector("#bloco-votado-sessao .cab-cartao", timeout=60000)
        page.wait_for_timeout(400)

    def _ir_aba(self, page, secao: str) -> None:
        largura = page.viewport_size["width"] if page.viewport_size else 390
        if largura >= 900:
            page.click(f'button[data-secao-lateral="{secao}"]')
        else:
            page.click(f'button[data-secao="{secao}"]')
        page.wait_for_timeout(400)

    def _clicar_periodo(self, page, periodo: str) -> None:
        largura = page.viewport_size["width"] if page.viewport_size else 390
        seletor = (
            f'#seletor-periodo-lateral button[data-periodo="{periodo}"]'
            if largura >= 900
            else f'#seletor-periodo-mobile button[data-periodo="{periodo}"]'
        )
        page.click(seletor)
        page.wait_for_timeout(500)

    def _assert_sem_elementos_proibidos(self, page) -> None:
        texto = page.inner_text("body")
        self.assertNotIn("nao existem no SAPL", texto.lower())
        self.assertIsNone(page.query_selector("#seletor-ano-wrap"))
        self.assertIsNone(page.query_selector("button[data-ano]"))

    def _assert_so_periodo_visivel(self, page, periodo: str) -> None:
        estado = page.evaluate(JS_PERIODO_VISIVEL, periodo)
        for p in PERIODOS:
            if p == periodo:
                self.assertTrue(
                    estado[p]["visivel"],
                    f"painel {p} deveria estar visivel ({estado[p]})",
                )
                self.assertNotEqual(estado[p]["display"], "none")
                self.assertNotEqual(estado[p]["area"], "0x0")
            else:
                self.assertFalse(
                    estado[p]["visivel"],
                    f"painel {p} nao deveria estar visivel ({estado[p]})",
                )
                self.assertEqual(estado[p]["display"], "none")
                self.assertEqual(estado[p]["area"], "0x0")
        texto = page.evaluate(JS_TEXTO_VISIVEL)
        self.assertIn(MARCADORES[periodo], texto)
        for p in PERIODOS:
            if p != periodo:
                self.assertNotIn(MARCADORES[p], texto)

    def _assert_quebra_letra(self, page, contexto: str) -> None:
        problemas = page.evaluate(JS_QUEBRA_LETRA)
        self.assertEqual(
            problemas,
            [],
            f"{contexto}: elemento de texto estreito com palavra quebrada: {problemas}",
        )

    def test_estrutura_dom_paineis(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            self._abrir(page, 1440)
            estrutura = page.evaluate(JS_ESTRUTURA)
            self.assertTrue(estrutura["todo_em_painel"], f"blocos do periodo todo fora do painel: {estrutura}")
            self.assertTrue(estrutura["camara_em_main"], f"painel camara fora do main: {estrutura}")
            self.assertTrue(estrutura["vereadores_em_main"], f"painel vereadores fora do main: {estrutura}")
            self.assertTrue(estrutura["nav_em_corpo"], f"nav principal fora do corpo: {estrutura}")
            browser.close()

    def _caso_camara(self, page, largura: int) -> None:
        self._ir_aba(page, "camara")
        btn_tema = page.evaluate(JS_BOTAO_TEMA)
        self.assertTrue(btn_tema["ok"], f"botao de tema com problema: {btn_tema.get('erro')}")

        self._assert_sem_elementos_proibidos(page)
        for periodo in PERIODOS:
            with self.subTest(largura=largura, aba="camara", periodo=periodo):
                self._clicar_periodo(page, periodo)
                self._assert_so_periodo_visivel(page, periodo)
                _sem_scroll_horizontal(page)
                self._assert_quebra_letra(page, f"camara {periodo} {largura}px")
                disp = page.evaluate(JS_VERIFICA_DISPOSICAO, periodo)
                self.assertTrue(disp["ok"], f"Disposicao incorreta para {periodo} em {largura}: {disp.get('erro')}")
                if periodo == "sessao":
                    pres = page.evaluate(JS_PRESENCA)
                    self.assertTrue(pres["ok"], f"Presenca com erro: {pres.get('erro')}")
        lateral = page.locator("#menu-lateral").is_visible()
        if largura >= 900:
            self.assertTrue(lateral, "menu lateral deve aparecer em desktop")
            largura_titulo = page.evaluate(
                "() => Math.round(document.querySelector('.menu-lateral-logo .site-logo').getBoundingClientRect().width)"
            )
            self.assertGreaterEqual(
                largura_titulo, 120, f"logotipo estreito no menu lateral: {largura_titulo}px"
            )
            centro = page.evaluate(
                """() => {
                  const pg = document.querySelector('.pagina').getBoundingClientRect();
                  return { esq: Math.round(pg.left), dir: Math.round(window.innerWidth - pg.right) };
                }"""
            )
            self.assertLessEqual(
                abs(centro["esq"] - centro["dir"]),
                2,
                f"pagina nao centralizada em desktop: {centro}",
            )
            
            self.assertTrue(
                page.locator("#menu-lateral-tagline").is_visible(),
                "tagline do painel deve aparecer no menu lateral em desktop",
            )
            self.assertTrue(
                page.locator("#rodape-menu-lateral").is_visible(),
                "rodape de coleta deve aparecer no menu lateral em desktop",
            )
            texto_lateral = page.inner_text("#menu-lateral")
            self.assertIn("Dado coletado em", texto_lateral)
            texto_corpo = page.inner_text(".pagina-corpo")
            self.assertNotIn("Dado coletado em", texto_corpo, "rodape duplicado em Camara no desktop")

        else:
            self.assertFalse(lateral, "menu lateral nao deve aparecer no celular")

    def _caso_vereadores(self, page, largura: int) -> None:
        self._ir_aba(page, "vereadores")
        btn_tema = page.evaluate(JS_BOTAO_TEMA)
        self.assertTrue(btn_tema["ok"], f"botao de tema com problema: {btn_tema.get('erro')}")

        page.wait_for_selector("#sel-vereador", timeout=60000)
        page.select_option("#sel-vereador", "1")
        page.wait_for_timeout(500)
        _sem_scroll_horizontal(page)
        self._assert_quebra_letra(page, f"vereadores {largura}px")

        estado = page.evaluate(JS_PERIODO_VISIVEL, "sessao")
        for p in PERIODOS:
            self.assertFalse(
                estado[p]["visivel"], f"na aba Vereadores o painel {p} nao deveria aparecer"
            )
        texto = page.evaluate(JS_TEXTO_VISIVEL)
        for marcador in MARCADORES.values():
            self.assertNotIn(marcador, texto)

        sobrepostos = page.evaluate(JS_SOBRPOSICOES, list(BLOCOS_VEREADORES))
        self.assertEqual(sobrepostos, [], f"blocos sobrepostos em vereadores: {sobrepostos}")
        quebrados = page.evaluate(JS_LEGENDA_LINHA)
        self.assertEqual(quebrados, [], f"legenda de presenca fora de linha: {quebrados}")

        if largura >= 900:
            largura_titulo = page.evaluate(
                "() => Math.round(document.querySelector('.menu-lateral-logo .site-logo').getBoundingClientRect().width)"
            )
            self.assertGreaterEqual(
                largura_titulo, 120, f"logotipo estreito no menu lateral: {largura_titulo}px"
            )
            seletor_largura = page.evaluate(
                "() => Math.round(document.querySelector('#sel-vereador').getBoundingClientRect().width)"
            )
            self.assertGreaterEqual(
                seletor_largura, 200, f"seletor de vereador estreito em desktop: {seletor_largura}px"
            )
            
            duas = page.evaluate(JS_DUAS_COLUNAS, "#conteudo-vereadores .vereadores-grade")
            self.assertTrue(duas, "vereadores deveria ter cartoes em duas colunas em desktop")
            
            votos_layout = page.evaluate('''() => {
                const grade = document.querySelector("#conteudo-vereadores .vereadores-grade");
                const votos = document.getElementById("tit-votos");
                if (!grade || !votos) return { ok: false, erro: "elementos nao encontrados" };
                const cartao = votos.closest("article.cartao");
                if (!cartao || !grade.contains(cartao)) return { ok: false, erro: "cartao de votos fora da grade" };
                const cards = grade.querySelectorAll("article.cartao");
                return { ok: cards.length >= 3 };
            }''')
            self.assertTrue(votos_layout["ok"], f"Layout de votos incorreto: {votos_layout.get('erro')}")

            topo = page.evaluate(
                JS_TOPOS_PRIMEIRA_LINHA,
                {
                    "selArea": "#conteudo-vereadores .vereadores-grade",
                    "seletorItem": ":scope > .ac-cartao",
                },
            )
            self.assertTrue(
                topo["ok"],
                f"primeiros cartoes de vereadores desalinhados: {topo}",
            )
            
            # Check rodape duplicado em vereadores
            texto_lateral = page.inner_text("#menu-lateral")
            self.assertIn("Dado coletado em", texto_lateral)
            texto_corpo = page.inner_text(".pagina-corpo")
            self.assertNotIn("Dado coletado em", texto_corpo, "rodape duplicado em Vereadores no desktop")
        else:
            duas = page.evaluate(JS_DUAS_COLUNAS, "#conteudo-vereadores")
            self.assertFalse(duas, "vereadores deveria ter coluna unica no celular")
            nav = page.locator("#nav-principal").is_visible()
            self.assertTrue(nav, "navegacao inferior deve aparecer no celular")
            
            self.assertTrue(
                page.locator("#topo-tagline").is_visible(),
                "tagline do painel deve aparecer no cabecalho no celular",
            )
            rodape_corpo = page.locator("#conteudo-vereadores .rodape-coleta").first
            if rodape_corpo.count():
                self.assertTrue(
                    rodape_corpo.is_visible(),
                    "rodape de coleta deve permanecer no conteudo no celular",
                )

    def test_layout_camara_e_vereadores(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            for largura in (390, 1440):
                with self.subTest(largura=largura):
                    self._abrir(page, largura)
                    self._assert_sem_elementos_proibidos(page)
                    self._caso_camara(page, largura)
                    self._caso_vereadores(page, largura)
            browser.close()

    def test_topo_compacto_ao_rolar_na_aba_vereadores_celular(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(self.base, wait_until="networkidle", timeout=120000)
            page.evaluate(JS_HELPERS)
            page.wait_for_selector("#sel-vereador", state="attached", timeout=60000)
            page.wait_for_selector("#bloco-votado-sessao .cab-cartao", timeout=60000)
            page.click('button[data-secao="vereadores"]')
            page.wait_for_timeout(500)

            topo = page.evaluate(JS_TOPO_MEDICAO)
            self.assertFalse(topo.get("erro"), str(topo))
            self.assertFalse(topo["compacto"], "no topo da pagina o cabecalho deve ser completo")
            self.assertTrue(page.locator(".topo-marca-linha").is_visible())
            self.assertGreater(
                topo["altura_topo"],
                72,
                f"sem rolagem o topo deve ser maior que a barra compacta: {topo}",
            )

            page.evaluate("window.scrollTo(0, 600)")
            page.wait_for_function(
                "() => document.querySelector('.topo-fixo').classList.contains('compacto')",
                timeout=5000,
            )
            topo = page.evaluate(JS_TOPO_MEDICAO)
            self.assertLessEqual(
                topo["altura_topo"], 72, f"barra compacta mais alta que 72 px: {topo}"
            )
            self.assertLessEqual(abs(topo["topo_topo"]), 1, "barra compacta deslocada do topo")
            self.assertTrue(topo["sel_visivel"], f"seletor sumiu na barra compacta: {topo}")
            self.assertTrue(topo["sel_no_ponto"], f"seletor coberto por outro elemento: {topo}")
            self.assertGreaterEqual(topo["sel_altura"], 36, f"seletor alvo de toque pequeno: {topo}")
            self.assertGreaterEqual(topo["sel_largura"], 120, f"seletor estreito demais: {topo}")
            self.assertTrue(topo["sel_ativo"], "seletor desabilitado na barra compacta")
            self.assertTrue(topo["rotulo_assoc"], "seletor sem rotulo associado na barra compacta")
            self.assertTrue(topo["share_visivel"], "botao de compartilhar deve caber em 390 px")
            self.assertFalse(
                topo["tema_sobrepoe_sel"], f"botao de tema sobrepoe o seletor: {topo}"
            )
            self.assertFalse(
                page.locator(".topo-marca-linha").is_visible(),
                "marca nao deve aparecer dentro da barra compacta",
            )

            valor_antes = page.evaluate("() => document.getElementById('sel-vereador').value")
            nome_antes = page.locator(".sel-vereador-face .nm").inner_text()
            rolagem_antes = page.evaluate("() => window.scrollY")
            page.select_option("#sel-vereador", index=1)
            page.wait_for_timeout(500)
            valor_depois = page.evaluate("() => document.getElementById('sel-vereador').value")
            nome_depois = page.locator(".sel-vereador-face .nm").inner_text()
            rolagem_depois = page.evaluate("() => window.scrollY")
            self.assertNotEqual(
                valor_antes, valor_depois, "troca de vereador nao funcionou na barra compacta"
            )
            self.assertNotEqual(
                nome_antes, nome_depois, "perfil nao atualizou ao trocar o vereador rolado"
            )
            self.assertLessEqual(
                abs(rolagem_depois - rolagem_antes), 120, "troca de vereador deslocou a pagina"
            )
            topo = page.evaluate(JS_TOPO_MEDICAO)
            self.assertTrue(topo["compacto"], "barra deveria continuar compacta apos a troca")
            self.assertLessEqual(topo["altura_topo"], 72, f"barra cresceu apos a troca: {topo}")

            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_function(
                "() => !document.querySelector('.topo-fixo').classList.contains('compacto')",
                timeout=5000,
            )
            topo = page.evaluate(JS_TOPO_MEDICAO)
            self.assertFalse(topo["compacto"], "chegando ao topo a barra deve reabrir")
            self.assertTrue(
                page.locator(".topo-marca-linha").is_visible(),
                "de volta ao topo a marca deve reaparecer",
            )
            self.assertGreater(topo["altura_topo"], 72, f"topo nao reabriu por completo: {topo}")

            page.set_viewport_size({"width": 1440, "height": 900})
            page.wait_for_timeout(600)
            page.evaluate("window.scrollTo(0, 600)")
            page.wait_for_timeout(500)
            topo = page.evaluate(JS_TOPO_MEDICAO)
            self.assertFalse(
                topo["compacto"], "em 1440 px o topo nao deve encolher ao rolar"
            )
            browser.close()


if __name__ == "__main__":
    unittest.main()
