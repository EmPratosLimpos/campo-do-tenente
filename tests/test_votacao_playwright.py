"""Playwright: fluxo da votacao popular com Worker e Turnstile falsos."""

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
        page.on("pageerror", lambda e: erros.append(str(e)))
        reqs_externas = []

        def on_req(req):
            u = req.url
            if "127.0.0.1:8809" in u:
                return
            if u.startswith("https://eu.i.posthog.com") or u.startswith("https://eu-assets.i.posthog.com"):
                return
            if "fonts.googleapis" in u or "fonts.gstatic" in u:
                return
            if "goatcounter" in u:
                return
            if "turnstile" in u:
                return
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
        return context, page, erros, reqs_externas

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

    def test_fluxo_completo_e_prints(self):
        with sync_playwright() as p:
            for largura in (390, 1440):
                for tema in ("claro", "escuro"):
                    ctx, page, erros, reqs = self._nova_pagina(p, largura, tema)
                    self._fluxo_completo(page)
                    self.assertEqual(erros, [])
                    self.assertEqual(reqs, [])
                    ov = page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
                    self.assertTrue(ov)
                    nome = f"votacao-fim-{largura}-{tema}.png"
                    page.screenshot(path=str(self.prints / nome), full_page=True)
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


if __name__ == "__main__":
    unittest.main()
