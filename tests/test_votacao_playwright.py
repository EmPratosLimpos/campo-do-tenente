"""Playwright: fluxo da votacao popular com Worker e Turnstile falsos (V4b)."""

from __future__ import annotations

import json
import pathlib
import re
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ORIGEM = "http://127.0.0.1:8809"
WORKER = ORIGEM
TURNSTILE_FALSO = "1x00000000000000000000AA"
WORKER_STATE = {}

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"


def _cfg_com_worker():
    cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))
    vp = dict(cfg.get("votacao_popular") or {})
    vp["worker_url"] = WORKER
    vp["turnstile_site_key"] = TURNSTILE_FALSO
    cfg["votacao_popular"] = vp
    return cfg


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, fmt, *args):
        return

    def _json(self, status, corpo):
        data = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        st = WORKER_STATE
        if self.path.startswith("/api/rodada"):
            if st.get("falha_rodada"):
                return self._json(500, {"codigo": "erro_interno", "erro": "fora"})
            return self._json(200, st.get("rodada") or {})
        if self.path.startswith("/api/resultados"):
            return self._json(200, st.get("resultados") or {})
        return super().do_GET()

    def do_POST(self):
        st = WORKER_STATE
        length = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(length) if length else b""
        if self.path.startswith("/api/verificar"):
            cod = st.get("verificar_erro")
            if cod == "limite_pedidos":
                self.send_response(429)
                self.send_header("Retry-After", "12")
                self.send_header("Content-Type", "application/json")
                body = json.dumps(
                    {"codigo": cod, "erro": "Muitos pedidos.", "tentar_depois_s": 12}
                ).encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if cod:
                status = 409 if cod in ("ja_votou", "teto_endereco") else 400
                return self._json(status, {"codigo": cod, "erro": "msg teste"})
            return self._json(
                200,
                {
                    "ok": True,
                    "rodada_id": (st.get("rodada") or {}).get("rodada_id"),
                    "autorizacao": st.get("autorizacao", "tok.teste"),
                    "dentro_do_municipio": True,
                    "ja_votou": False,
                },
            )
        if self.path.startswith("/api/votar"):
            return self._json(
                200,
                {"ok": True, "rodada_id": (st.get("rodada") or {}).get("rodada_id")},
            )
        self.send_error(404)


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestVotacaoPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8809), _Handler)
        threading.Thread(target=cls.servidor.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:8809/index.html"
        cls.prints = RAIZ / "tmp_prints"
        cls.prints.mkdir(exist_ok=True)
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()
        cls.servidor.server_close()

    def setUp(self):
        self.estado_worker = {
            "rodada": {
                "rodada_id": "sessao:999",
                "sessao_id": 999,
                "data_sessao": "2026-10-01",
                "status": "aberta",
                "materias": [
                    {
                        "id": 101,
                        "sigla": "PLEG",
                        "numero": "1",
                        "ano": "2026",
                        "ementa": "Ementa teste um.",
                        "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/101",
                    },
                    {
                        "id": 102,
                        "sigla": "REQ",
                        "numero": "2",
                        "ano": "2026",
                        "ementa": "Ementa teste dois.",
                        "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/102",
                    },
                ],
            },
            "ja_votou": False,
            "autorizacao": "tok.teste.assinatura",
            "resultados": {
                "atualizado_em": "2026-10-09T12:00:00-03:00",
                "rodadas": [
                    {
                        "rodada_id": "sessao:999",
                        "status": "aberta",
                        "materias": [
                            {
                                "materia_id": 101,
                                "respostas": 42,
                                "percentual_util": 60,
                                "percentual_inutil": 40,
                            },
                            {
                                "materia_id": 102,
                                "respostas": "menos de 10",
                                "percentual_util": None,
                                "percentual_inutil": None,
                            },
                        ],
                    }
                ],
            },
        }
        WORKER_STATE.clear()
        WORKER_STATE.update(
            {
                "rodada": self.estado_worker["rodada"],
                "resultados": self.estado_worker["resultados"],
                "autorizacao": self.estado_worker["autorizacao"],
            }
        )

    def _config_route(self, page):
        corpo = json.dumps(_cfg_com_worker(), ensure_ascii=False)

        def handle(route):
            route.fulfill(status=200, content_type="application/json", body=corpo)

        page.route("**/config_cidade.json", handle)

    def _sync_worker_state(self):
        WORKER_STATE["rodada"] = self.estado_worker["rodada"]
        WORKER_STATE["resultados"] = self.estado_worker["resultados"]
        WORKER_STATE["verificar_erro"] = self.estado_worker.get("verificar_erro")

    def _turnstile_route(self, page):
        page.route("**/turnstile/**", lambda r: r.fulfill(status=200, body="/* mock */"))

    def _url_permitida(self, u: str) -> bool:
        if "127.0.0.1:8809" in u:
            return True
        if u.startswith("https://eu.i.posthog.com") or u.startswith(
            "https://eu-assets.i.posthog.com"
        ):
            return True
        if "fonts.googleapis" in u or "fonts.gstatic" in u:
            return True
        if "goatcounter" in u:
            return True
        if "challenges.cloudflare.com" in u or "turnstile" in u:
            return True
        return False

    def _nova_pagina(self, p, largura, tema, geo=None):
        context = p.chromium.launch().new_context(
            viewport={"width": largura, "height": 900},
            geolocation=geo or {"latitude": -25.95, "longitude": -49.68},
            permissions=["geolocation"],
        )
        page = context.new_page()
        page.add_init_script(
            "window.turnstile = { render: function(el, o) { if (o.callback) o.callback('fake'); return 1; } };"
        )
        erros = []
        console_erros = []

        def on_console(msg):
            if msg.type == "error":
                console_erros.append(msg.text)

        page.on("console", on_console)
        page.on("pageerror", lambda e: erros.append(str(e)))
        reqs_externas = []
        todas_reqs = []

        def on_req(req):
            u = req.url
            todas_reqs.append(u)
            if not self._url_permitida(u):
                reqs_externas.append(u)

        page.on("request", on_req)
        self._sync_worker_state()
        self._config_route(page)
        self._turnstile_route(page)
        page.goto(self.base, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_load_state("networkidle", timeout=90000)
        if tema == "escuro":
            page.evaluate("document.documentElement.setAttribute('data-tema','escuro')")
        else:
            page.evaluate("document.documentElement.removeAttribute('data-tema')")
        page._vp_console_erros = console_erros
        page._vp_todas_reqs = todas_reqs
        return context, page, erros, reqs_externas

    def _assert_sem_vazamento_layout(self, page, seletor_modal="#votacao-modal"):
        ok = page.evaluate(
            """(sel) => {
              const modal = document.querySelector(sel);
              if (!modal) return { ok: true };
              const mr = modal.getBoundingClientRect();
              const vw = window.innerWidth;
              const vh = window.innerHeight;
              if (document.documentElement.scrollWidth > vw + 1) return { ok: false, why: 'scroll-x' };
              const nodes = modal.querySelectorAll('p, span, li, button, h2, h3, div');
              for (const n of nodes) {
                const st = getComputedStyle(n);
                if (st.display === 'none' || st.visibility === 'hidden') continue;
                const r = n.getBoundingClientRect();
                if (r.width < 2 || r.height < 2) continue;
                if (r.right > mr.right + 1 || r.left < mr.left - 1) return { ok: false, why: 'overflow-card', el: n.className };
              }
              const acoes = modal.querySelector('.votacao-acoes');
              if (acoes) acoes.scrollIntoView({ block: 'end', behavior: 'instant' });
              const btns = modal.querySelectorAll('.votacao-acoes button, .votacao-cabecalho button');
              for (const b of btns) {
                if (b.hidden || b.offsetParent === null) continue;
                if (b.closest('[hidden]')) continue;
                const st = getComputedStyle(b);
                if (st.display === 'none' || st.visibility === 'hidden') continue;
                const r = b.getBoundingClientRect();
                if (r.right > vw + 1 || r.left < -1) return { ok: false, why: 'button-horizontal' };
                if (r.width < 1 || r.height < 1) return { ok: false, why: 'button-zero' };
              }
              const ids = {};
              document.querySelectorAll('[id]').forEach(el => { ids[el.id] = (ids[el.id]||0)+1; });
              const dup = Object.keys(ids).filter(k => ids[k] > 1);
              if (dup.length) return { ok: false, why: 'dup-id', dup };
              const body = modal.innerText || '';
              if (/\\besc\\(|undefined|NaN|\\bnull\\b/.test(body)) return { ok: false, why: 'leak-text' };
              return { ok: true };
            }""",
            seletor_modal,
        )
        self.assertTrue(ok.get("ok"), ok)

    def _screenshot(self, page, tela, largura, tema):
        nome = f"votacao-{tela}-{largura}-{tema}.png"
        page.screenshot(path=str(self.prints / nome), full_page=True)
        return nome

    def _ir_camara(self, page):
        largura = page.viewport_size["width"] if page.viewport_size else 390
        if largura >= 900:
            page.locator("button[data-secao-lateral='camara']").click(timeout=15000)
        else:
            page.locator("#nav-principal button[data-secao='camara']").click(timeout=15000)
        page.wait_for_selector("#painel-camara.ativo", timeout=30000)

    def _ir_vereador(self, page, id_sapl: str):
        largura = page.viewport_size["width"] if page.viewport_size else 390
        if largura >= 900:
            page.locator("button[data-secao-lateral='vereadores']").click(timeout=15000)
        else:
            page.locator("#nav-principal button[data-secao='vereadores']").click(timeout=15000)
        page.wait_for_selector("#painel-vereadores.ativo", timeout=30000)
        page.wait_for_selector("#sel-vereador", timeout=60000)
        page.select_option("#sel-vereador", id_sapl)
        page.wait_for_timeout(600)

    def _aguardar_botao_votar(self, page):
        page.wait_for_selector("#btn-votar-fab:not([hidden])", timeout=30000)

    def _fluxo_completo(self, page):
        self._aguardar_botao_votar(page)
        page.locator("#btn-votar-fab").click()
        page.evaluate("window.turnstile = { render: function(el, o) { if (o.callback) o.callback('fake'); return 1; } };")
        page.locator("#votacao-btn-localizacao").click()
        page.wait_for_selector("#votacao-passo-cartoes:not([hidden])", timeout=15000)
        page.locator("#votacao-btn-util").click()
        page.locator("#votacao-btn-inutil").click()
        page.wait_for_selector("#votacao-passo-resumo:not([hidden])", timeout=10000)
        page.locator("#votacao-btn-enviar").click()
        page.wait_for_selector("#votacao-passo-fim:not([hidden])", timeout=15000)

    def test_fluxo_completo_sem_erros_rede(self):
        with sync_playwright() as p:
            for largura in (390, 1440):
                for tema in ("claro", "escuro"):
                    ctx, page, erros, reqs = self._nova_pagina(p, largura, tema)
                    self._fluxo_completo(page)
                    self.assertEqual(erros, [])
                    self.assertEqual(reqs, [])
                    self.assertEqual(page._vp_console_erros, [])
                    avisos = page.locator("#votacao-fim-corpo .votacao-aviso").count()
                    self.assertEqual(avisos, 1)
                    self.assertIn("Útil", page.locator("#votacao-fim-corpo").inner_text())
                    self.assertIn("Inútil", page.locator("#votacao-fim-corpo").inner_text())
                    self._assert_sem_vazamento_layout(page)
                    ctx.close()

    def test_sem_worker_url_esconde_botao(self):
        with sync_playwright() as p:
            page = p.chromium.launch().new_page()
            page.route(
                "**/config_cidade.json",
                lambda r: r.fulfill(
                    status=200,
                    content_type="application/json",
                    body=(RAIZ / "config_cidade.json").read_text(encoding="utf-8"),
                ),
            )
            page.goto(self.base, wait_until="networkidle", timeout=90000)
            self.assertTrue(page.locator("#btn-votar-fab").is_hidden())
            page.close()

    def test_ja_votou(self):
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.evaluate(
                "localStorage.setItem('epl_vp_votou:sessao:999','1');"
            )
            page.reload(wait_until="networkidle", timeout=90000)
            page.wait_for_timeout(800)
            self.assertTrue(page.locator("#btn-votar-fab").is_hidden())
            self.assertIn("já votou", page.locator("#votacao-ja-votou-msg").inner_text().lower())
            ctx.close()

    def test_gps_negado(self):
        with sync_playwright() as p:
            context = p.chromium.launch().new_context(
                viewport={"width": 390, "height": 900},
            )
            context.add_init_script(
                "navigator.geolocation = { getCurrentPosition: function(ok, err) { if (typeof err === 'function') err({ code: 1 }); } };"
            )
            page = context.new_page()
            cfg = _cfg_com_worker()
            cfg["votacao_popular"]["turnstile_site_key"] = ""
            corpo = json.dumps(cfg, ensure_ascii=False)
            page.route(
                "**/config_cidade.json",
                lambda r: r.fulfill(status=200, content_type="application/json", body=corpo),
            )
            self._sync_worker_state()
            page.goto(self.base, wait_until="networkidle", timeout=90000)
            self._aguardar_botao_votar(page)
            page.locator("#btn-votar-fab").click()
            page.locator("#votacao-btn-localizacao").click()
            page.wait_for_selector("#votacao-erro-msg:not([hidden])", timeout=10000)
            txt = page.locator("#votacao-erro-msg").inner_text().lower()
            self.assertIn("localiza", txt)
            context.close()

    def test_fora_municipio(self):
        self.estado_worker["verificar_erro"] = "fora_do_municipio"
        self._sync_worker_state()
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.locator("#btn-votar-fab").click()
            page.evaluate("window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };")
            page.locator("#votacao-btn-localizacao").click()
            page.wait_for_selector("#votacao-erro-msg:not([hidden])", timeout=10000)
            self.assertIn("fora", page.locator("#votacao-erro-msg").inner_text().lower())
            ctx.close()

    def test_precisao_ruim(self):
        self.estado_worker["verificar_erro"] = "precisao_ruim"
        self._sync_worker_state()
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.locator("#btn-votar-fab").click()
            page.evaluate("window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };")
            page.locator("#votacao-btn-localizacao").click()
            page.wait_for_selector("#votacao-erro-msg:not([hidden])", timeout=10000)
            self.assertIn("fraco", page.locator("#votacao-erro-msg").inner_text().lower())
            ctx.close()

    def test_limite_429(self):
        self.estado_worker["verificar_erro"] = "limite_pedidos"
        self._sync_worker_state()
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.locator("#btn-votar-fab").click()
            page.evaluate("window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };")
            page.locator("#votacao-btn-localizacao").click()
            page.wait_for_selector("#votacao-erro-msg:not([hidden])", timeout=10000)
            self.assertIn("12", page.locator("#votacao-erro-msg").inner_text())
            ctx.close()

    def test_servidor_fora(self):
        WORKER_STATE["falha_rodada"] = True
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.reload(wait_until="networkidle", timeout=90000)
            self.assertTrue(page.locator("#btn-votar-fab").is_hidden())
            ctx.close()

    def test_rodada_fechada_resultados_sem_botao(self):
        self.estado_worker["rodada"]["status"] = "fechada"
        self.estado_worker["rodada"]["materias"] = []
        self._sync_worker_state()
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.evaluate("localStorage.setItem('epl_vp_votou:sessao:999','1');")
            page.reload(wait_until="networkidle")
            self.assertTrue(page.locator("#btn-votar-fab").is_hidden())
            ctx.close()

    def test_botoes_mesmo_tamanho_e_cor(self):
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            self._aguardar_botao_votar(page)
            page.locator("#btn-votar-fab").click()
            page.evaluate("window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };")
            page.locator("#votacao-btn-localizacao").click()
            page.wait_for_selector("#votacao-passo-cartoes:not([hidden])", timeout=15000)
            dims = page.evaluate(
                """() => {
                const u = document.getElementById('votacao-btn-util');
                const i = document.getElementById('votacao-btn-inutil');
                const gu = getComputedStyle(u);
                const gi = getComputedStyle(i);
                return {
                  wu: u.offsetWidth, wi: i.offsetWidth, hu: u.offsetHeight, hi: i.offsetHeight,
                  bu: gu.backgroundColor, bi: gi.backgroundColor,
                  cu: gu.color, ci: gi.color
                };
              }"""
            )
            self.assertEqual(dims["wu"], dims["wi"])
            self.assertEqual(dims["hu"], dims["hi"])
            self.assertEqual(dims["bu"], dims["bi"])
            self.assertEqual(dims["cu"], dims["ci"])
            ctx.close()

    def test_teclado_completa_voto(self):
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            self._aguardar_botao_votar(page)
            page.locator("#btn-votar-fab").click()
            page.evaluate("window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };")
            page.locator("#votacao-btn-localizacao").click()
            page.wait_for_selector("#votacao-passo-cartoes:not([hidden])", timeout=15000)
            page.keyboard.press("ArrowRight")
            page.keyboard.press("ArrowLeft")
            page.wait_for_selector("#votacao-passo-resumo:not([hidden])", timeout=10000)
            ctx.close()

    def test_cartao_sem_autor_no_dom(self):
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            self._aguardar_botao_votar(page)
            page.locator("#btn-votar-fab").click()
            page.evaluate("window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };")
            page.locator("#votacao-btn-localizacao").click()
            page.wait_for_selector("#votacao-cartao-palco", timeout=15000)
            html = page.locator("#votacao-cartao-palco").inner_html().lower()
            self.assertNotIn("partido", html)
            self.assertNotIn("autor", html)
            self.assertNotIn("vereador", html)
            ctx.close()

    def test_menos_de_dez_respostas_sem_barra(self):
        self.estado_worker["resultados"]["rodadas"][0]["materias"] = [
            {
                "materia_id": 101,
                "respostas": 4,
                "percentual_util": None,
                "percentual_inutil": None,
            },
            {
                "materia_id": 102,
                "respostas": 42,
                "percentual_util": 50,
                "percentual_inutil": 50,
            },
        ]
        self._sync_worker_state()
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            self._fluxo_completo(page)
            txt = page.locator("#votacao-fim-corpo").inner_text().lower()
            self.assertIn("menos de 10", txt)
            self.assertEqual(
                page.locator(
                    "#votacao-fim-corpo .votacao-resultado-materia[data-vp-materia='101'] .vp-barra-resultado"
                ).count(),
                0,
            )
            ctx.close()

    def test_consolidado_vereador_autor(self):
        rodada_mats = [
            {
                "id": 66,
                "sigla": "PLEG",
                "numero": "1",
                "ano": "2026",
                "ementa": "Ementa consolidado A.",
                "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/66",
            },
            {
                "id": 67,
                "sigla": "PLEG",
                "numero": "2",
                "ano": "2026",
                "ementa": "Ementa consolidado B.",
                "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/67",
            },
        ]
        self.estado_worker["rodada"]["materias"] = rodada_mats
        self.estado_worker["resultados"]["rodadas"][0]["materias"] = [
            {
                "materia_id": 66,
                "respostas": 40,
                "percentual_util": 60,
                "percentual_inutil": 40,
            },
            {
                "materia_id": 67,
                "respostas": 20,
                "percentual_util": 80,
                "percentual_inutil": 20,
            },
        ]
        util = round(0.6 * 40 + 0.8 * 20)
        inutil = round(0.4 * 40 + 0.2 * 20)
        soma = util + inutil
        pu = round((util / soma) * 100)
        pi = round((inutil / soma) * 100)
        self._sync_worker_state()
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.evaluate("localStorage.setItem('epl_vp_votou:sessao:999','1');")
            page.reload(wait_until="networkidle", timeout=90000)
            self._ir_vereador(page, "5")
            card = page.locator(".votacao-consolidado")
            self.assertEqual(card.count(), 1)
            texto = card.inner_text()
            self.assertIn(f"Útil {pu}%", texto)
            self.assertIn(f"Inútil {pi}%", texto)
            self.assertEqual(page.locator(".votacao-consolidado .votacao-aviso").count(), 1)
            self._ir_vereador(page, "100")
            self.assertEqual(page.locator(".votacao-consolidado").count(), 0)
            ctx.close()

    def test_pedidos_so_dominios_permitidos(self):
        with sync_playwright() as p:
            ctx, page, _, reqs = self._nova_pagina(p, 390, "claro")
            self._fluxo_completo(page)
            self.assertEqual(reqs, [])
            bloqueados = [u for u in page._vp_todas_reqs if not self._url_permitida(u)]
            self.assertEqual(bloqueados, [])
            ctx.close()

    def test_console_sem_erros_no_fluxo(self):
        with sync_playwright() as p:
            ctx, page, erros, _ = self._nova_pagina(p, 390, "claro")
            self._fluxo_completo(page)
            self.assertEqual(erros, [])
            self.assertEqual(page._vp_console_erros, [])
            ctx.close()

    def test_layout_fluxo_varias_larguras(self):
        with sync_playwright() as p:
            for largura in (320, 390, 900, 1440):
                ctx, page, _, _ = self._nova_pagina(p, largura, "claro")
                self._aguardar_botao_votar(page)
                self._screenshot(page, "botao", largura, "claro")
                page.locator("#btn-votar-fab").click()
                self._assert_sem_vazamento_layout(page)
                page.evaluate(
                    "window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };"
                )
                page.locator("#votacao-btn-localizacao").click()
                page.wait_for_selector("#votacao-passo-cartoes:not([hidden])", timeout=15000)
                self._assert_sem_vazamento_layout(page)
                page.locator("#votacao-btn-util").click()
                page.locator("#votacao-btn-inutil").click()
                page.wait_for_selector("#votacao-passo-resumo:not([hidden])", timeout=10000)
                self._assert_sem_vazamento_layout(page)
                page.locator("#votacao-btn-enviar").click()
                page.wait_for_selector("#votacao-passo-fim:not([hidden])", timeout=15000)
                self._assert_sem_vazamento_layout(page)
                ctx.close()

    def test_aviso_uma_vez_camara(self):
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            page.evaluate("localStorage.setItem('epl_vp_votou:sessao:999','1');")
            page.reload(wait_until="networkidle", timeout=90000)
            self._ir_camara(page)
            cab = page.locator("#bloco-votado-sessao .votacao-bloco-resultados-cab .votacao-aviso")
            self.assertEqual(cab.count(), 1)
            self.assertEqual(
                page.locator("#bloco-votado-sessao .votacao-resultado-materia .votacao-aviso").count(),
                0,
            )
            ctx.close()

    def test_botao_fechar_mesmo_estilo_padrao(self):
        with sync_playwright() as p:
            ctx, page, _, _ = self._nova_pagina(p, 390, "claro")
            self._fluxo_completo(page)
            estilos = page.evaluate(
                """() => {
                const fechar = document.getElementById('votacao-btn-fechar-fim');
                const ref = document.getElementById('votacao-btn-enviar');
                const gf = getComputedStyle(fechar);
                const gr = getComputedStyle(ref);
                return {
                  bg: gf.backgroundColor === gr.backgroundColor,
                  col: gf.color === gr.color,
                  fw: gf.fontWeight === gr.fontWeight,
                  br: gf.borderRadius === gr.borderRadius,
                };
              }"""
            )
            self.assertTrue(all(estilos.values()), estilos)
            ctx.close()

    def test_gerar_prints_votacao(self):
        quatro = [
            {
                "id": 201,
                "sigla": "PLEG",
                "numero": "1",
                "ano": "2026",
                "ementa": "Print um.",
                "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/201",
            },
            {
                "id": 202,
                "sigla": "REQ",
                "numero": "2",
                "ano": "2026",
                "ementa": "Print dois.",
                "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/202",
            },
            {
                "id": 203,
                "sigla": "PLEG",
                "numero": "3",
                "ano": "2026",
                "ementa": "Print tres.",
                "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/203",
            },
            {
                "id": 204,
                "sigla": "IND",
                "numero": "4",
                "ano": "2026",
                "ementa": "Print quatro.",
                "link_sapl": "https://sapl.campodotenente.pr.leg.br/materia/204",
            },
        ]
        self.estado_worker["rodada"]["materias"] = quatro
        mats_res = [
            {"materia_id": 201, "respostas": 42, "percentual_util": 55, "percentual_inutil": 45},
            {"materia_id": 202, "respostas": "menos de 10", "percentual_util": None, "percentual_inutil": None},
            {"materia_id": 203, "respostas": 30, "percentual_util": 70, "percentual_inutil": 30},
            {"materia_id": 204, "respostas": 25, "percentual_util": 40, "percentual_inutil": 60},
        ]
        self.estado_worker["resultados"]["rodadas"][0]["materias"] = mats_res
        self._sync_worker_state()
        gerados = []
        with sync_playwright() as p:
            for largura in (390, 1440):
                for tema in ("claro", "escuro"):
                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    self._aguardar_botao_votar(page)
                    gerados.append(self._screenshot(page, "botao", largura, tema))
                    page.locator("#btn-votar-fab").click()
                    gerados.append(self._screenshot(page, "termos", largura, tema))
                    ctx.close()

                    ctx = p.chromium.launch().new_context(
                        viewport={"width": largura, "height": 900},
                        geolocation={"latitude": -25.95, "longitude": -49.68},
                        permissions=["geolocation"],
                    )
                    page = ctx.new_page()
                    page.add_init_script(
                        "navigator.geolocation = { getCurrentPosition: function(ok, err) { if (typeof err === 'function') err({ code: 1 }); } };"
                    )
                    self._config_route(page)
                    self._sync_worker_state()
                    page.goto(self.base, wait_until="networkidle", timeout=90000)
                    if tema == "escuro":
                        page.evaluate("document.documentElement.setAttribute('data-tema','escuro')")
                    self._aguardar_botao_votar(page)
                    page.locator("#btn-votar-fab").click()
                    page.locator("#votacao-btn-localizacao").click()
                    page.wait_for_selector("#votacao-erro-msg:not([hidden])", timeout=10000)
                    gerados.append(self._screenshot(page, "erro-gps", largura, tema))
                    ctx.close()

                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    self.estado_worker["verificar_erro"] = "fora_do_municipio"
                    self._sync_worker_state()
                    page.reload(wait_until="networkidle")
                    self._aguardar_botao_votar(page)
                    page.locator("#btn-votar-fab").click()
                    page.evaluate(
                        "window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };"
                    )
                    page.locator("#votacao-btn-localizacao").click()
                    page.wait_for_selector("#votacao-erro-msg:not([hidden])", timeout=10000)
                    gerados.append(self._screenshot(page, "erro-fora", largura, tema))
                    self.estado_worker["verificar_erro"] = None
                    ctx.close()

                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    self._aguardar_botao_votar(page)
                    page.locator("#btn-votar-fab").click()
                    page.evaluate(
                        "window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };"
                    )
                    page.locator("#votacao-btn-localizacao").click()
                    page.wait_for_selector("#votacao-passo-cartoes:not([hidden])", timeout=15000)
                    gerados.append(self._screenshot(page, "cartao", largura, tema))
                    page.locator("#votacao-btn-util").focus()
                    gerados.append(self._screenshot(page, "cartao-foco", largura, tema))
                    page.locator("#votacao-btn-util").click()
                    page.locator("#votacao-btn-inutil").click()
                    page.locator("#votacao-btn-util").click()
                    page.locator("#votacao-btn-inutil").click()
                    page.wait_for_selector("#votacao-passo-resumo:not([hidden])", timeout=10000)
                    gerados.append(self._screenshot(page, "resumo", largura, tema))
                    page.locator("#votacao-btn-enviar").click()
                    page.wait_for_selector("#votacao-passo-fim:not([hidden])", timeout=15000)
                    gerados.append(self._screenshot(page, "fim", largura, tema))
                    ctx.close()

                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    page.evaluate("localStorage.setItem('epl_vp_votou:sessao:999','1');")
                    page.reload(wait_until="networkidle")
                    gerados.append(self._screenshot(page, "ja-votou", largura, tema))
                    ctx.close()

                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    page.evaluate("localStorage.setItem('epl_vp_votou:sessao:999','1');")
                    page.reload(wait_until="networkidle")
                    self._ir_camara(page)
                    gerados.append(self._screenshot(page, "camara", largura, tema))
                    ctx.close()

                    self.estado_worker["rodada"]["materias"] = quatro[:2]
                    self.estado_worker["rodada"]["materias"][0]["id"] = 66
                    self.estado_worker["rodada"]["materias"][1]["id"] = 67
                    self.estado_worker["resultados"]["rodadas"][0]["materias"] = [
                        {
                            "materia_id": 66,
                            "respostas": 40,
                            "percentual_util": 60,
                            "percentual_inutil": 40,
                        },
                        {
                            "materia_id": 67,
                            "respostas": 20,
                            "percentual_util": 80,
                            "percentual_inutil": 20,
                        },
                    ]
                    self._sync_worker_state()
                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    page.evaluate("localStorage.setItem('epl_vp_votou:sessao:999','1');")
                    page.reload(wait_until="networkidle")
                    self._ir_vereador(page, "5")
                    gerados.append(self._screenshot(page, "perfil", largura, tema))
                    ctx.close()

                    self.estado_worker["rodada"]["materias"] = quatro
                    self.estado_worker["resultados"]["rodadas"][0]["materias"] = [
                        {
                            "materia_id": 201,
                            "respostas": 3,
                            "percentual_util": None,
                            "percentual_inutil": None,
                        }
                    ]
                    self._sync_worker_state()
                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    self._aguardar_botao_votar(page)
                    page.locator("#btn-votar-fab").click()
                    page.evaluate(
                        "window.turnstile = { render: function(el, o) { o.callback('f'); return 1; } };"
                    )
                    page.locator("#votacao-btn-localizacao").click()
                    page.wait_for_selector("#votacao-passo-cartoes:not([hidden])", timeout=15000)
                    for _ in quatro:
                        page.locator("#votacao-btn-util").click()
                    page.locator("#votacao-btn-enviar").click()
                    page.wait_for_selector("#votacao-passo-fim:not([hidden])", timeout=15000)
                    gerados.append(self._screenshot(page, "menos-respostas", largura, tema))
                    ctx.close()
                    self.estado_worker["rodada"]["materias"] = quatro

                    self.estado_worker["rodada"]["status"] = "fechada"
                    self.estado_worker["rodada"]["materias"] = []
                    self._sync_worker_state()
                    ctx, page, _, _ = self._nova_pagina(p, largura, tema)
                    page.evaluate("localStorage.setItem('epl_vp_votou:sessao:999','1');")
                    page.reload(wait_until="networkidle")
                    gerados.append(self._screenshot(page, "rodada-fechada", largura, tema))
                    self.estado_worker["rodada"]["status"] = "aberta"
                    self.estado_worker["rodada"]["materias"] = quatro
                    ctx.close()
        self.assertGreaterEqual(len(gerados), 52)


if __name__ == "__main__":
    unittest.main()
