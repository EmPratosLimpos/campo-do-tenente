"""E5g: caixa explicativa das tags e quadros clicaveis na aba Vereadores."""

from __future__ import annotations

import json
import pathlib
import re
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

CHAVES_EXPLICACOES = (
    "tipo_materia",
    "turno_1o",
    "turno_2o",
    "turno_unico",
    "resultado_unanimidade",
    "resultado_maioria",
    "resultado_rejeitado",
    "resultado_sem_deliberacao",
    "placar",
    "cassado",
    "categoria",
    "situacao_aprovado",
    "situacao_rejeitado",
    "situacao_tramitacao",
    "coautoria",
    "voto_sim",
    "voto_nao",
    "voto_abstencao",
    "voto_nao_votou",
    "voto_presidente",
    "sem_registro_sapl",
    "voto_ausente",
    "voto_ausente_justificativa",
    "voto_ausente_sem_justificativa",
    "voto_presente_sem_registro",
)


class TestConfigExplicacoes(unittest.TestCase):
    def test_bloco_explicacoes_sem_cidade_fixa(self):
        cfg = json.loads((RAIZ / "config_cidade.json").read_text(encoding="utf-8"))
        bloco = cfg.get("explicacoes_tags")
        self.assertIsInstance(bloco, dict)
        for chave in CHAVES_EXPLICACOES:
            with self.subTest(chave=chave):
                texto = bloco.get(chave)
                self.assertIsInstance(texto, str)
                self.assertTrue(str(texto).strip())
        juntos = " ".join(str(bloco[k]) for k in CHAVES_EXPLICACOES)
        for proibido in ("Campo do Tenente", "Campo Largo", "\u2014", "\u2013"):
            self.assertNotIn(proibido, juntos)
        for esperado in ("votação", "matéria", "sessão", "prevê"):
            self.assertIn(esperado, juntos)


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, *args):
        pass


def registros_sim_vereador_2() -> int:
    """Votos nominais Sim do vereador 2, lidos do proprio arquivo da tela."""
    dados = json.loads(
        (RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json").read_text(
            encoding="utf-8"
        )
    )
    vereador = next(v for v in dados["vereadores"] if v.get("id_sapl") == 2)
    return sum(1 for n in vereador["votos"]["nominais"] if n.get("estado") == "sim")


@contextmanager
def _navegador(p):
    browser = p.chromium.launch()
    try:
        yield browser
    finally:
        try:
            browser.close()
        except Exception:
            pass


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTagsCaixa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8799), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8799/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _abrir_vereador(self, page, slug_id="3"):
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(
            "button[data-secao-lateral='vereadores'], button[data-secao='vereadores']",
            state="attached",
            timeout=60000,
        )
        try:
            page.click("button[data-secao-lateral='vereadores']", timeout=5000)
        except Exception:
            page.click('button[data-secao="vereadores"]', timeout=15000)
        page.wait_for_selector("#sel-vereador", state="visible", timeout=30000)
        page.select_option("#sel-vereador", slug_id)
        page.wait_for_timeout(400)

    def _abrir_secao(self, page, titulo_id):
        page.wait_for_selector("#" + titulo_id, state="visible", timeout=15000)
        page.wait_for_timeout(200)

    def test_caixa_da_tag_tipo_com_descricao_do_sapl(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                erros = []
                page.on("pageerror", lambda e: erros.append(str(e)))
                self._abrir_vereador(page, "2")
                self._abrir_secao(page, "tit-votos")
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(500)
                tag = page.locator(".lista-votos .tag-categoria.tag-explicavel").first
                texto_tag = tag.inner_text()
                self.assertEqual(tag.evaluate("n => n.tagName"), "BUTTON")
                self.assertEqual(tag.get_attribute("aria-expanded"), "false")
                tag.click()
                page.wait_for_timeout(300)
                caixa = page.locator("#folha-generica-backdrop.ativo")
                self.assertEqual(caixa.count(), 1)
                dialogo = page.locator("#folha-generica")
                self.assertEqual(dialogo.get_attribute("role"), "dialog")
                texto = caixa.inner_text()
                self.assertIn("categorias do projeto", texto)
                self.assertIn(texto_tag, texto)
                self.assertEqual(tag.get_attribute("aria-expanded"), "true")
                self.assertEqual(
                    tag.get_attribute("aria-controls"), "folha-generica"
                )
                dentro = caixa.evaluate(
                    "n => { var r = n.getBoundingClientRect(); "
                    "return r.left >= 0 && r.right <= window.innerWidth; }"
                )
                self.assertTrue(dentro)
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                self.assertEqual(page.locator("#folha-generica-backdrop.ativo").count(), 0)
                self.assertEqual(erros, [])

    def test_teclado_e_esc_e_uma_aberta_por_vez(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                self._abrir_vereador(page, "2")
                self._abrir_secao(page, "tit-votos")
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(500)
                tag_cat = page.locator(".lista-votos .tag-categoria.tag-explicavel").first
                tag_cat.focus()
                page.keyboard.press("Enter")
                page.wait_for_timeout(300)
                self.assertEqual(page.locator("#folha-generica-backdrop.ativo").count(), 1)
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                tag_cat = page.locator(".lista-votos .tag-categoria.tag-explicavel").first
                texto_cat = tag_cat.inner_text()
                tag_cat.click()
                page.wait_for_timeout(300)
                self.assertEqual(page.locator("#folha-generica-backdrop.ativo").count(), 1)
                texto = page.locator("#folha-generica-backdrop.ativo").inner_text()
                self.assertIn("13 categorias do projeto", texto)
                self.assertIn(texto_cat, texto)
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                self.assertEqual(page.locator("#folha-generica-backdrop.ativo").count(), 0)

    def test_turno_cita_regimento_e_cassado_traz_data(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                self._abrir_vereador(page, "2")
                self._abrir_secao(page, "tit-votos")
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(500)
                turno = page.locator(".lista-votos .tag-turno.tag-explicavel").first
                turno.click()
                page.wait_for_timeout(300)
                texto = page.locator("#folha-generica-backdrop.ativo").inner_text()
                self.assertIn("arts. 177 e 178", texto)
                page.keyboard.press("Escape")
                page.wait_for_timeout(200)
                page.select_option("#sel-vereador", "1")
                page.wait_for_timeout(500)
                cassado = page.locator(
                    ".perfil-nome button.tag-explicavel[data-tag='cassado']"
                )
                self.assertEqual(cassado.count(), 1)
                cassado.click()
                page.wait_for_timeout(300)
                texto_cas = page.locator("#folha-generica-backdrop.ativo").inner_text()
                self.assertIn("18/08/2026", texto_cas)
                self.assertIn("Ver ato no SAPL", texto_cas)

    def test_quadro_sim_filtra_e_clique_novo_limpa(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                erros = []
                page.on("pageerror", lambda e: erros.append(str(e)))
                page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                page.click("button[data-secao-lateral='vereadores']")
                page.wait_for_selector("#sel-vereador", timeout=60000)
                page.select_option("#sel-vereador", "2")
                page.wait_for_timeout(600)
                self.assertEqual(page.locator("#filtro-voto").count(), 0)
                sim = page.locator("button.voto-card[data-voto-card='sim']")
                self.assertEqual(sim.get_attribute("aria-pressed"), "false")
                sim.click()
                page.wait_for_timeout(600)
                self.assertEqual(
                    page.locator(
                        "button.voto-card[data-voto-card='sim']"
                    ).get_attribute("aria-pressed"),
                    "true",
                )
                texto = page.inner_text("body")
                esperado = f"{registros_sim_vereador_2()} registros"
                self.assertIn(esperado, texto)
                selos = page.locator(".lista-votos .pilula").all_inner_texts()
                self.assertTrue(selos)
                for selo in selos:
                    self.assertEqual(selo.strip(), "Votou Sim")
                page.fill("#filtro-texto", "habitacionais")
                page.wait_for_timeout(800)
                texto_busca = page.inner_text("body")
                self.assertNotIn(esperado, texto_busca)
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(600)
                self.assertEqual(
                    page.locator("button.voto-card[data-voto-card='sim']").get_attribute(
                        "aria-pressed"
                    ),
                    "false",
                )
                page.fill("#filtro-texto", "")
                page.wait_for_timeout(800)
                texto_limpo = page.locator("#conteudo-vereadores").inner_text()
                self.assertIn("Lista de votações nominais", texto_limpo)
                self.assertEqual(erros, [])

    def test_quadros_projetos_abrem_lista_certa(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                self._abrir_vereador(page, "5")
                self._abrir_secao(page, "tit-pll")
                self.assertEqual(page.locator(".btn-filtro-pll").count(), 0)
                texto_vazio = page.locator("#conteudo-vereadores").inner_text()
                self.assertIn("Nenhum projeto na lista", texto_vazio)
                page.click("button.contagem-item[data-pl-filtro='aprovado']")
                page.wait_for_timeout(600)
                lista = page.locator(".lista-pll").inner_text()
                self.assertIn("Administração e finanças", lista)
                self.assertEqual(
                    page.locator(
                        "button.contagem-item[data-pl-filtro='aprovado']"
                    ).get_attribute("aria-pressed"),
                    "true",
                )
                page.click("button.contagem-item[data-pl-filtro='aprovado']")
                page.wait_for_timeout(600)
                texto_fechado = page.locator("#conteudo-vereadores").inner_text()
                self.assertIn("Nenhum projeto na lista", texto_fechado)

    def test_tema_escuro_caixa_e_quadros(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                erros = []
                page.on("pageerror", lambda e: erros.append(str(e)))
                self._abrir_vereador(page, "2")
                page.locator(".alternar-tema").first.click()
                page.wait_for_timeout(400)
                self.assertEqual(
                    page.evaluate("document.documentElement.getAttribute('data-tema')"),
                    "escuro",
                )
                self._abrir_secao(page, "tit-votos")
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(500)
                tag = page.locator(".lista-votos .tag-categoria.tag-explicavel").first
                tag.click()
                page.wait_for_timeout(300)
                self.assertEqual(page.locator("#folha-generica-backdrop.ativo").count(), 1)
                dentro = page.locator("#folha-generica-backdrop.ativo").evaluate(
                    "n => { var r = n.getBoundingClientRect(); "
                    "return r.left >= 0 && r.right <= window.innerWidth; }"
                )
                self.assertTrue(dentro)
                texto = page.inner_text("body")
                self.assertIn(f"{registros_sim_vereador_2()} registros", texto)
                self.assertEqual(erros, [])

    def test_sem_rolagem_lateral_e_sem_erro_console(self):
        with sync_playwright() as p:
            for largura in (390, 1440):
                with _navegador(p) as browser:
                    page = browser.new_page(viewport={"width": largura, "height": 900})
                    erros = []
                    page.on("pageerror", lambda e: erros.append(str(e)))
                    self._abrir_vereador(page, "2")
                    for titulo in ("tit-presenca", "tit-pll", "tit-votos"):
                        self._abrir_secao(page, titulo)
                    page.click("button.voto-card[data-voto-card='sim']")
                    page.wait_for_timeout(500)
                    tag = page.locator(".lista-votos .tag-categoria.tag-explicavel").first
                    tag.click()
                    page.wait_for_timeout(300)
                    overflow = page.evaluate(
                        "document.documentElement.scrollWidth <= window.innerWidth + 1"
                    )
                    self.assertTrue(overflow, msg=f"rolagem lateral em {largura}px")
                    corpo = page.inner_text("body")
                    for literal in ("esc(", "' +", "+ '", "undefined", "NaN"):
                        self.assertNotIn(literal, corpo)
                    self.assertEqual(erros, [])


PALAVRAS_SEM_ACENTO = (
    "votacao",
    "materia",
    "sessao",
    "camara",
    "tercos",
    "preve",
    "numero",
    "decisao",
    "reuniao",
    "eleicao",
)


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestE5hAcabamento(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8800), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8800/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _abrir_vereador(self, page, slug_id="2"):
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(
            "button[data-secao-lateral='vereadores'], button[data-secao='vereadores']",
            state="attached",
            timeout=60000,
        )
        try:
            page.click("button[data-secao-lateral='vereadores']", timeout=5000)
        except Exception:
            page.click('button[data-secao="vereadores"]', timeout=15000)
        page.wait_for_selector("#sel-vereador", state="visible", timeout=30000)
        page.select_option("#sel-vereador", slug_id)
        page.wait_for_timeout(400)

    def test_tag_com_visual_antigo_10px(self):
        with sync_playwright() as p:
            for largura in (390, 1440):
                with _navegador(p) as browser:
                    page = browser.new_page(viewport={"width": largura, "height": 900})
                    self._abrir_vereador(page, "2")
                    page.click("button.voto-card[data-voto-card='sim']")
                    page.wait_for_timeout(500)
                    tag = page.locator(".lista-votos .tag-categoria.tag-explicavel").first
                    estilo = tag.evaluate(
                        "n => { var c = getComputedStyle(n); "
                        "return n.tagName + '|' + c.fontSize + '|' + c.paddingTop "
                        "+ ' ' + c.paddingRight + ' ' + c.paddingBottom + ' ' + c.paddingLeft; }"
                    )
                    with self.subTest(largura=largura):
                        self.assertEqual(estilo, "BUTTON|13px|2px 8px 2px 8px")

    def test_sem_palavra_sem_acento_nas_abas(self):
        with sync_playwright() as p:
            for largura in (390, 1440):
                with _navegador(p) as browser:
                    page = browser.new_page(viewport={"width": largura, "height": 900})
                    page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_selector(
                        "#bloco-votado-sessao .item-votado", timeout=60000
                    )
                    page.wait_for_timeout(500)
                    texto_camara = page.inner_text("body").lower()
                    for palavra in PALAVRAS_SEM_ACENTO:
                        with self.subTest(largura=largura, aba="camara", palavra=palavra):
                            padrao = r"\b" + palavra + r"\b"
                            self.assertIsNone(
                                re.search(padrao, texto_camara),
                                msg=f"{palavra} visivel na aba Camara",
                            )
                    self._abrir_vereador(page, "2")
                    page.click("button.voto-card[data-voto-card='sim']")
                    page.wait_for_timeout(500)
                    texto_ver = page.inner_text("body").lower()
                    for palavra in PALAVRAS_SEM_ACENTO:
                        with self.subTest(
                            largura=largura, aba="vereadores", palavra=palavra
                        ):
                            self.assertIsNone(
                                re.search(r"\b" + palavra + r"\b", texto_ver),
                                msg=f"{palavra} visivel na aba Vereadores",
                            )

    def test_ordinais_com_simbolo_de_ordinal(self):
        with sync_playwright() as p:
            for largura in (390, 1440):
                with _navegador(p) as browser:
                    page = browser.new_page(viewport={"width": largura, "height": 900})
                    self._abrir_vereador(page, "2")
                    page.click("button.voto-card[data-voto-card='sim']")
                    page.wait_for_timeout(500)
                    texto = page.locator("#conteudo-vereadores").inner_text()
                    with self.subTest(largura=largura):
                        self.assertIn("2º turno", texto)
                        self.assertNotIn("1o turno", texto)
                        self.assertNotIn("2o turno", texto)
                        self.assertNotIn("par. 1o", texto)

    def test_tag_e_ementa_separadas(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page(viewport={"width": 390, "height": 900})
                self._abrir_vereador(page, "2")
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(500)
                item = page.locator(".lista-votos li").first
                primeiro = item.inner_text()
                self.assertIsNotNone(re.search(r"º turno", primeiro))
                fora = item.evaluate(
                    "n => Array.from(n.querySelectorAll('.tag-explicavel'))"
                    ".filter(e => !e.closest('.materia-tags')).length"
                )
                self.assertEqual(fora, 0)
                ementa = item.locator(".materia-assunto").first
                self.assertEqual(ementa.count(), 1)
                self.assertEqual(
                    ementa.evaluate("n => getComputedStyle(n).display"), "block"
                )


if __name__ == "__main__":
    unittest.main()
