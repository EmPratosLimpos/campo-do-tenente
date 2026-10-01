"""E5j: ementas do SAPL em maiusculas aparecem em texto normal na tela (D-055).

Duas partes:
- unidade: a funcao ementaExibicao() do index.html, rodada em Node com o
  config_cidade.json de verdade, sem navegador e sem pedido ao SAPL;
- navegador: Playwright em 390 e 1440, tema claro e escuro, aba Camara nos tres
  periodos e historico de votos do Dr. Marcos Rodrigues depois de clicar em Sim.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path(__file__).resolve().parent

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

NODE = shutil.which("node")

LIMITES = ("390", "1440")
TEMAS = ("claro", "escuro")
PERIODOS = ("sessao", "mes", "todo")
VEREADOR_HISTORICO = "Dr. Marcos Rodrigues"

# ementas do SAPL cadastradas todas em maiusculas, conferidas nos dados
EMENTAS_MAIUSCULAS = (
    "DISPÕE SOBRE A RESERVA DE VAGAS PARA NEGROS E PARDOS EM CONCURSOS PÚBLICOS E PROCESSOS SELETIVOS SIMPLIFICADOSNO ÂMBITO DA CÂMARA MUNICIPAL DE CAMPO DO TENENTE E DÁ OUTRAS PROVIDÊNCIAS.",
    "INSTITUI O PROGRAMA DE RECUPERAÇÃO FISCAL- REFIS NO MUNICÍPIO DE CAMPO DO TENENTE/PR",
    "ALTERA O ART. 46 DA LEI 686/2010, AMPLIANDO A QUANTIDADE DE TEMPO DESTINADO A HORA-ATIVIDADE DOS\r\nPROFESSORES E EDUCADORES INFANTIS",
    "CONCEDE REVISÃO GERAL ANUAL AOS SERVIDORES EFETIVOS E COMISSIONADOS DA CÂMARA MUNICIPAL DE CAMPO DO TENENTE.",
    "DISPÕE ACERCA DA IMPLANTAÇÃO DE CÓDIGO QR EM TODAS AS PLACAS DE OBRAS PÚBLICAS MUNICIPAIS PARA LEITURA E FISCALIZAÇÃO ELETRÔNICA.",
    "REGULAMENTA A LEI FEDERAL Nº 12.527/2011- LEI DE ACESSO À INFORMAÇÃO - LAI, NO ÂMBITO DA CÂMARA MUNICIPAL DE CAMPO DO TENENTE – PR.",
    "INSTITUI O PARLAMENTO MUNICIPAL DA PESSOA COM DEFICIÊNCIA NO MUNICÍPIO DE CAMPO DO TENENTE, DESTINADO A ESTUDANTES DA APAE, COM FINS EDUCATIVOS E DE CIDADANIA, E DÁ OUTRAS PROVIDÊNCIAS.",
    "INSTITUI O SELO \"EMPRESA AMIGA DA JUVENTUDE\"",
    "DISPÕE SOBRE OS CRITÉRIOS PARA  A DENOMINAÇÃO DE PRÉDIOS E EQUIPAMENTOS PÚBLICOS MUNICIPAIS NO ÂMBITO DO MUNICÍPIO DE CAMPO DO TENENTE, E DÁ OUTRAS PROVIDÊNCIAS.",
    "DISPÕE SOBRE A CRIAÇÃO, CONSTITUIÇÃO E FUNCIONAMENTO DO FUNDO MUNICIPAL DE ESPORTES - FME E INSTITUI O SEU CONSELHO GESTOR.",
    "VISA ALTERAÇÃO DO ARTIGO 11, CAPUT, DA LEI MUNICIPAL N° 920/2017, REDUZINDO O VALOR DO LICENCIAMENTO ANUAL DO SERVIÇO DE TÁXI NO MUNICÍPIO DE CAMPO DO TENENTE-PR.",
)

EMENTA_JA_NORMAL = (
    "Dispõe sobre a criação do Orçamento Participativo Digital no município de "
    "Campo do Tenente e dá outras providências."
)

# casos de unidade exigidos no enunciado
CASO_MAIUSCULAS = (
    "ALTERA O ART. 46 DA LEI 686/2010, AMPLIANDO PRAZO PARA O PR E O REFIS "
    "NO MUNICÍPIO DE CAMPO DO TENENTE, NOS TERMOS DO ART. IV E DÁ OUTRAS PROVIDÊNCIAS."
)
SAIDA_MAIUSCULAS = (
    "Altera o art. 46 da Lei 686/2010, ampliando prazo para o PR e o REFIS "
    "no município de Campo do Tenente, nos termos do art. IV e dá outras providências."
)


def ler_html(nome: str) -> str:
    return (RAIZ / nome).read_text(encoding="utf-8")


def bloco_ementa(html: str) -> str:
    inicio = html.index("var LIMITE_MAIUSCULAS_EMENTA")
    fim = html.index("function urlSegura(url)")
    return html[inicio:fim]


def proporcao_maiusculas(texto: str) -> float:
    letras = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]", texto)
    if not letras:
        return 0.0
    maiusculas = [c for c in letras if c.isupper()]
    return len(maiusculas) / len(letras)


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, *args):
        pass


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


@unittest.skipUnless(NODE, "node nao instalado")
class TestEmentaExibicaoUnidade(unittest.TestCase):
    """Roda a funcao real do index.html em Node, sem navegador e sem SAPL."""

    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(ler_html("config_cidade.json"))
        cls.bloco = bloco_ementa(ler_html("index.html"))
        cls.bloco_modelo = bloco_ementa(ler_html("tela/modelo.html"))
        cls.resultado = cls._rodar(cls.bloco, cls.config, _casos_unidade())

    @staticmethod
    def _rodar(bloco: str, config: dict, casos: dict) -> dict:
        script = (
            "const CONFIG_CIDADE = "
            + json.dumps(config, ensure_ascii=False)
            + ";\n"
            + bloco
            + "\nconst entradas = "
            + json.dumps(casos, ensure_ascii=False)
            + ";\n"
            + "const saida = {};\n"
            + "for (const chave of Object.keys(entradas)) {\n"
            + "  saida[chave] = ementaExibicao(entradas[chave]);\n"
            + "}\n"
            + "saida.__busca = ementaBusca(entradas.busca_refis || '');\n"
            + "process.stdout.write(JSON.stringify(saida));"
        )
        proc = subprocess.run(
            [NODE, "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            cwd=str(RAIZ),
        )
        if proc.returncode != 0:
            raise AssertionError("node falhou: " + proc.stderr[:2000])
        return json.loads(proc.stdout)

    def _exibicao(self, chave: str) -> str:
        return self.resultado[chave]

    def test_ementa_maiuscula_vira_texto_normal_com_termos_preservados(self):
        self.assertEqual(self._exibicao("maiusculas"), SAIDA_MAIUSCULAS)

    def test_termos_preservados_por_palavra_inteira(self):
        saida = self._exibicao("maiusculas")
        for termo in ("Lei", "PR", "REFIS", "Campo do Tenente", "art.", "art. IV"):
            self.assertIn(termo, saida, termo)
        self.assertNotIn("lei 686", saida)
        self.assertNotIn("Art.", saida)
        self.assertNotIn("REFIS ", saida.replace("o REFIS", ""))

    def test_quebra_de_linha_vira_espaco_simples(self):
        saida = self._exibicao("quebra")
        self.assertNotIn("\n", saida)
        self.assertNotIn("\r", saida)
        self.assertNotIn("  ", saida)
        self.assertIn(
            "Altera o art. 46 da Lei 686/2010, ampliando a quantidade de tempo "
            "destinado a hora-atividade dos professores e educadores infantis",
            saida,
        )

    def test_ementa_ja_normal_nao_muda_nenhuma_letra(self):
        saida = self._exibicao("normal")
        self.assertEqual(saida, EMENTA_JA_NORMAL)
        self.assertEqual(saida.lower(), EMENTA_JA_NORMAL.lower())

    def test_espaco_duplo_do_sapl_vira_espaco_simples(self):
        saida = self._exibicao("espaco_duplo")
        self.assertNotIn("  ", saida)
        self.assertTrue(
            saida.startswith("Dispõe sobre os critérios para a denominação"), saida
        )
        self.assertIn("município de Campo do Tenente", saida)

    def test_aspas_do_sapl_mantem_o_termo_preservado(self):
        saida = self._exibicao("aspas")
        self.assertTrue(saida.startswith('Institui o selo "'), saida)
        self.assertIn('"Empresa Amiga da Juventude"', saida)

    def test_nenhuma_ementa_real_fica_com_mais_de_80_por_ento_de_maiusculas(self):
        for chave, valor in self.resultado.items():
            if not chave.startswith("real_"):
                continue
            with self.subTest(ementa=chave):
                self.assertLessEqual(proporcao_maiusculas(valor), 0.8, valor)

    def test_busca_acha_por_texto_original_e_por_texto_de_exibicao(self):
        busca = self.resultado["__busca"].lower()
        self.assertIn("refis", busca)
        self.assertIn("institui o programa de recuperação fiscal", busca)

    def test_lista_de_termos_preservados_vem_do_config_e_nao_do_codigo(self):
        for nome in ("index.html", "tela/modelo.html"):
            with self.subTest(arquivo=nome):
                html = ler_html(nome)
                for termo in ("Campo do Tenente", "Câmara Municipal", "REFIS", "APAE"):
                    with self.subTest(termo=termo):
                        bloco = bloco_ementa(html)
                        self.assertNotIn('"' + termo + '"', bloco)

    def test_funcao_existe_nos_dois_arquivos_e_estao_iguais(self):
        self.assertEqual(self.bloco, self.bloco_modelo)

    def test_lista_do_config_tem_nota_e_lista_nao_vazia(self):
        bloco = self.config.get("ementa_termos_preservados")
        self.assertIsInstance(bloco, dict)
        self.assertTrue(bloco.get("nota"))
        lista = bloco.get("lista")
        self.assertIsInstance(lista, list)
        self.assertGreaterEqual(len(lista), 10)
        self.assertEqual(len(set(lista)), len(lista))
        for termo in ("PR", "REFIS", "APAE", "Campo do Tenente", "Lei", "I", "II"):
            self.assertIn(termo, lista)


def _casos_unidade() -> dict:
    casos = {
        "maiusculas": CASO_MAIUSCULAS,
        "normal": EMENTA_JA_NORMAL,
        "quebra": EMENTAS_MAIUSCULAS[2],
        "espaco_duplo": EMENTAS_MAIUSCULAS[8],
        "aspas": EMENTAS_MAIUSCULAS[7],
        "busca_refis": EMENTAS_MAIUSCULAS[1],
    }
    for indice, ementa in enumerate(EMENTAS_MAIUSCULAS):
        casos["real_" + str(indice)] = ementa
    return casos


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestEmentaTextoNormalNaTela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8821), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8821/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.servidor.shutdown()
        finally:
            cls.servidor.server_close()

    def _erros(self, page):
        erros = []
        page.on("pageerror", lambda e: erros.append(str(e)))
        page.on(
            "console",
            lambda m: erros.append("console: " + m.text) if m.type == "error" else None,
        )
        return erros

    def _clicar_periodo(self, page, periodo: str) -> None:
        largura = page.viewport_size["width"] if page.viewport_size else 390
        seletor = (
            f'#seletor-periodo-lateral button[data-periodo="{periodo}"]'
            if largura >= 900
            else f'#seletor-periodo-mobile button[data-periodo="{periodo}"]'
        )
        page.click(seletor)
        page.wait_for_timeout(600)

    def _rolagem_lateral(self, page) -> int:
        return page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )

    def _abrir_camara(self, page, largura: str, tema: str):
        page.set_viewport_size({"width": int(largura), "height": 900})
        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("#bloco-votado-sessao .item-votado", timeout=60000)
        page.wait_for_timeout(400)
        if tema == "escuro":
            page.locator(".alternar-tema").first.click()
            page.wait_for_timeout(300)

    def test_aba_camara_nos_tres_periodos_sem_ementa_em_maiusculas(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                for largura in LIMITES:
                    for tema in TEMAS:
                        page = browser.new_page()
                        erros = self._erros(page)
                        self._abrir_camara(page, largura, tema)
                        for periodo in PERIODOS:
                            self._clicar_periodo(page, periodo)
                            for seletor in (
                                "#bloco-votado-" + periodo + " .materia-ementa",
                                "#bloco-votado-" + periodo + " .item-pll .ementa",
                            ):
                                textos = page.eval_on_selector_all(
                                    seletor, "els => els.map(e => e.textContent.trim())"
                                )
                                for texto in textos:
                                    with self.subTest(
                                        largura=largura,
                                        tema=tema,
                                        periodo=periodo,
                                        seletor=seletor,
                                    ):
                                        self.assertTrue(texto)
                                        self.assertLessEqual(
                                            proporcao_maiusculas(texto),
                                            0.8,
                                            texto,
                                        )
                        self.assertEqual(erros, [], msg=f"{largura}px {tema}: {erros}")
                        self.assertLessEqual(self._rolagem_lateral(page), 1)
                        page.close()

    def test_folha_de_resumo_usa_texto_de_exibicao(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page()
                erros = self._erros(page)
                self._abrir_camara(page, "1440", "claro")
                achou = False
                for periodo in PERIODOS:
                    self._clicar_periodo(page, periodo)
                    for card in page.locator(
                        f"#bloco-votado-{periodo} .materia-link"
                    ).all():
                        card.click()
                        page.wait_for_timeout(400)
                        texto = page.locator(
                            "#resumo-sheet-corpo .resumo-campo-valor"
                        ).all_text_contents()
                        ementas = [t for t in texto if len(t) > 40]
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(300)
                        if not ementas:
                            continue
                        achou = True
                        for ementa in ementas:
                            with self.subTest(periodo=periodo):
                                self.assertLessEqual(
                                    proporcao_maiusculas(ementa), 0.8, ementa
                                )
                self.assertTrue(achou, "nenhuma folha de resumo aberta")
                self.assertEqual(erros, [])
                page.close()

    def test_historico_do_marcos_rodrigues_depois_de_clicar_sim(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                for largura in LIMITES:
                    for tema in TEMAS:
                        page = browser.new_page()
                        erros = self._erros(page)
                        page.set_viewport_size(
                            {"width": int(largura), "height": 900}
                        )
                        page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector(
                            "#sel-vereador", state="attached", timeout=60000
                        )
                        try:
                            page.click("button[data-secao-lateral='vereadores']", timeout=5000)
                        except Exception:
                            page.click('button[data-secao="vereadores"]', timeout=15000)
                        page.wait_for_selector("#sel-vereador", state="visible", timeout=30000)
                        page.select_option("#sel-vereador", VEREADOR_HISTORICO)
                        page.wait_for_timeout(500)
                        if tema == "escuro":
                            page.locator(".alternar-tema").first.click()
                            page.wait_for_timeout(300)
                        bloco = page.locator("#tit-votos").locator(
                            "xpath=ancestor::details[1]"
                        )
                        if not bloco.evaluate("n => n.open"):
                            page.locator("#tit-votos").locator(
                                "xpath=ancestor::summary[1]"
                            ).click()
                            page.wait_for_timeout(400)
                        page.click("button.voto-card[data-voto-card='sim']")
                        page.wait_for_timeout(700)
                        ementas = page.eval_on_selector_all(
                            ".lista-votos .ementa-voto",
                            "els => els.map(e => (e.getAttribute('title') || e.textContent).trim())",
                        )
                        self.assertTrue(ementas, "historico sem ementas")
                        for ementa in ementas:
                            with self.subTest(largura=largura, tema=tema):
                                self.assertLessEqual(
                                    proporcao_maiusculas(ementa), 0.8, ementa
                                )
                        self.assertEqual(erros, [], msg=f"{largura}px {tema}: {erros}")
                        self.assertLessEqual(self._rolagem_lateral(page), 1)
                        page.close()

    def test_busca_refis_encontra_a_materia_no_historico_de_votos(self):
        """Busca "refis" na aba Vereadores acha a materia pelo texto de exibicao."""
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page()
                erros = self._erros(page)
                page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector("#sel-vereador", state="attached", timeout=60000)
                try:
                    page.click("button[data-secao-lateral='vereadores']", timeout=5000)
                except Exception:
                    page.click('button[data-secao="vereadores"]', timeout=15000)
                page.wait_for_selector("#sel-vereador", state="visible", timeout=30000)
                page.select_option("#sel-vereador", VEREADOR_HISTORICO)
                page.wait_for_timeout(600)
                bloco = page.locator("#tit-votos").locator("xpath=ancestor::details[1]")
                if not bloco.evaluate("n => n.open"):
                    page.locator("#tit-votos").locator("xpath=ancestor::summary[1]").click()
                    page.wait_for_timeout(400)
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(500)
                campo = page.locator("#filtro-texto")
                campo.fill("refis")
                page.wait_for_timeout(700)
                ementas = page.eval_on_selector_all(
                    ".lista-votos .ementa-voto",
                    "els => els.map(e => (e.getAttribute('title') || e.textContent).trim())",
                )
                self.assertTrue(ementas, "busca refis nao achou materia nenhuma")
                for ementa in ementas:
                    self.assertIn("refis", ementa.lower(), ementa)
                    self.assertLessEqual(proporcao_maiusculas(ementa), 0.8, ementa)
                campo.fill("")
                page.wait_for_timeout(400)
                self.assertEqual(erros, [])
                page.close()

    def test_caixas_explicativas_das_tags_continuam_abrindo(self):
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page()
                erros = self._erros(page)
                self._abrir_camara(page, "1440", "claro")
                tag = page.locator("#bloco-votado-sessao .tag-tipo.tag-explicavel").first
                self.assertEqual(tag.count(), 1)
                tag.click()
                page.wait_for_timeout(300)
                caixa = page.locator("#tag-caixa-explicativa")
                self.assertEqual(caixa.count(), 1)
                self.assertTrue(caixa.inner_text().strip())
                self.assertEqual(erros, [])
                page.close()


if __name__ == "__main__":
    unittest.main()