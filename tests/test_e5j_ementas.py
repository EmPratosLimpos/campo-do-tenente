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


# E5k: pares (texto do SAPL, texto na tela) dos nomes proprios de plano, programa,
# sistema e regime que o SAPL gravou em maiusculas e que a tela mostra com a
# grafia oficial. Cada palavra principal com inicial maiuscula, preposicao e
# artigo em minusculo, no mesmo modelo do Plano Municipal de Educacao.
TERMOS_E5K = (
    "Plano Municipal de Cultura",
    "Sistema Municipal de Cultura",
    "Plano Plurianual",
    "Programa Porteira Adentro",
    "Programa Auxílio-Alimentação",
    "Regime Próprio de Previdência Social",
)

EMENTAS_E5K = {
    "plano_cultura": (
        '"APROVA O PLANO MUNICIPAL DE CULTURA DO MUNICÍPIO DE CAMPO DO TENENTE/PR".',
        '"Aprova o Plano Municipal de Cultura do município de Campo do Tenente/PR".',
    ),
    "programa_auxilio": (
        "ALTERA A REDAÇÃO DO ART. 2º DA LEI Nº 1.059/2022, QUE INSTITUI O PROGRAMA "
        "AUXÍLIO-ALIMENTAÇÃO PARA OS SERVIDORES DO MUNICÍPIO DE CAMPO DO TENENTE/PR, "
        "E DÁ OUTRAS PROVIDÊNCIAS.",
        "Altera a redação do art. 2º da Lei nº 1.059/2022, que institui o Programa "
        "Auxílio-Alimentação para os servidores do município de Campo do Tenente/PR, "
        "e dá outras providências.",
    ),
    "programa_porteira": (
        "DISPÕE SOBRE A DIVULGAÇÃO DE INFORMAÇÕES SOBRE OS SERVIÇOS DE SANEAMENTO "
        "BÁSICO E DO PROGRAMA PORTEIRA ADENTRO DO MUNICÍPIO NO SITE OFICIAL DA "
        "PREFEITURA DE CAMPO DO TENENTE - PR.",
        "Dispõe sobre a divulgação de informações sobre os serviços de saneamento "
        "básico e do Programa Porteira Adentro do município no site oficial da "
        "Prefeitura de Campo do Tenente - PR.",
    ),
    "plano_plurianual": (
        "DISPÕE SOBRE O PLANO PLURIANUAL DE GOVERNO DO MUNICÍPIO, PARA O PERÍODO DE "
        "2026 A 2029, E DÁ OUTRAS PROVIDÊNCIAS.",
        "Dispõe sobre o Plano Plurianual de governo do município, para o período de "
        "2026 a 2029, e dá outras providências.",
    ),
    "sistema_cultura": (
        "DISPÕE SOBRE O SISTEMA MUNICIPAL DE  CULTURA DO MUNICÍPIO DE CAMPO DO  "
        "TENENTE/PR , E DÁ OUTRAS PROVIDÊNCIAS.",
        "Dispõe sobre o Sistema Municipal de Cultura do município de Campo do Tenente/PR , "
        "e dá outras providências.",
    ),
    "regime_previdencia": (
        "DISPÕE SOBRE O PARCELAMENTO E REPARCELAMENTO DE DÉBITOS DO MUNICÍPIO DE CAMPO "
        "DO TENENTE/PR COM SEU REGIME PRÓPRIO DE PREVIDÊNCIA SOCIAL - RPPS, DE QUE TRATAM "
        "OS ARTS. 115 E 117 DO ATO DAS DISPOSIÇÕES CONSTITUCIONAIS TRANSITÓRIAS - ADCT, "
        "COM A REDAÇÃO CONFERIDA PELA EMENDA CONSTITUCIONAL Nº 136, DE 9 DE SETEMBRO DE 2025.",
        "Dispõe sobre o parcelamento e reparcelamento de débitos do município de Campo do "
        "Tenente/PR com seu Regime Próprio de Previdência Social - RPPS, de que tratam os "
        "arts. 115 e 117 do Ato das Disposições Constitucionais Transitórias - ADCT, com a "
        "redação conferida pela Emenda Constitucional nº 136, de 9 de setembro de 2025.",
    ),
}


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
        html = ler_html("index.html")
        for termo in ("Campo do Tenente", "Câmara Municipal", "REFIS", "APAE"):
            with self.subTest(termo=termo):
                bloco = bloco_ementa(html)
                self.assertNotIn('"' + termo + '"', bloco)

    def test_funcao_da_ementa_existe_no_index(self):
        self.assertIn("function ementaExibicao", self.bloco)
        self.assertIn("function ementaBusca", self.bloco)

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

    def test_nomes_de_planos_programas_e_sistemas_ficam_com_inicial_maiuscula(self):
        """E5k: cada termo novo sai com a grafia oficial e o resto da ementa em
        minusculo, sem estourar o limite de 80 por cento de letras maiusculas."""
        for chave, (sapl, esperado) in EMENTAS_E5K.items():
            with self.subTest(termo=chave):
                saida = self._exibicao("e5k_" + chave)
                self.assertEqual(saida, esperado)
                self.assertLessEqual(proporcao_maiusculas(saida), 0.8, saida)
                for termo in TERMOS_E5K:
                    if termo in sapl.upper().replace("  ", " "):
                        with self.subTest(termo_preservado=termo):
                            self.assertIn(termo, saida)

    def test_termos_novos_estao_no_config_e_nao_no_codigo(self):
        lista = self.config["ementa_termos_preservados"]["lista"]
        for termo in TERMOS_E5K:
            with self.subTest(termo=termo):
                self.assertIn(termo, lista)
        bloco = bloco_ementa(ler_html("index.html"))
        for termo in TERMOS_E5K:
            with self.subTest(termo=termo):
                self.assertNotIn('"' + termo + '"', bloco)


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
    for chave, (sapl, _esperado) in EMENTAS_E5K.items():
        casos["e5k_" + chave] = sapl
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
                                "#bloco-votado-" + periodo + " .materia-assunto",
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
                    textos = page.eval_on_selector_all(
                        f"#bloco-votado-{periodo} .materia-assunto",
                        "els => els.map(e => e.textContent.trim())",
                    )
                    for assunto in textos:
                        if len(assunto) < 20:
                            continue
                        achou = True
                        with self.subTest(periodo=periodo):
                            self.assertLessEqual(
                                proporcao_maiusculas(assunto), 0.8, assunto
                            )
                self.assertTrue(achou, "nenhum assunto de materia na lista")
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
                        page.click("button.voto-card[data-voto-card='sim']")
                        page.wait_for_timeout(700)
                        ementas = page.eval_on_selector_all(
                            ".lista-votos .materia-assunto",
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
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(500)
                campo = page.locator("#filtro-texto")
                campo.fill("refis")
                page.wait_for_timeout(700)
                ementas = page.eval_on_selector_all(
                    ".lista-votos .materia-assunto",
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
                tag = None
                for periodo in PERIODOS:
                    self._clicar_periodo(page, periodo)
                    candidata = page.locator(
                        f"#bloco-votado-{periodo} .tag-categoria.tag-explicavel, "
                        f"#bloco-votado-{periodo} .tag-turno.tag-explicavel"
                    ).first
                    if candidata.count() > 0:
                        tag = candidata
                        break
                if tag is None:
                    self.skipTest("nenhum periodo com tag explicavel nesta base")
                self.assertEqual(tag.count(), 1)
                tag.click()
                page.wait_for_timeout(300)
                caixa = page.locator("#folha-generica-backdrop.ativo")
                self.assertEqual(caixa.count(), 1)
                self.assertTrue(page.locator("#folha-generica-corpo").inner_text().strip())
                self.assertEqual(erros, [])
                page.close()

    def test_programa_porteira_adentro_aparece_com_nome_proprio_na_tela_1440(self):
        """E5k: o nome do programa aparece na aba Camara com inicial maiuscula."""
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page()
                erros = self._erros(page)
                self._abrir_camara(page, "1440", "claro")
                achou = False
                for periodo in PERIODOS:
                    self._clicar_periodo(page, periodo)
                    busca = page.locator("#busca-materia-" + periodo)
                    if busca.count():
                        busca.fill("Porteira Adentro")
                        page.wait_for_timeout(400)
                    textos = page.eval_on_selector_all(
                        "#bloco-votado-" + periodo + " .materia-assunto",
                        "els => els.map(e => e.textContent.trim())",
                    )
                    for texto in textos:
                        if "Porteira Adentro" in texto:
                            achou = True
                            self.assertIn(
                                "do Programa Porteira Adentro do município",
                                texto,
                            )
                            self.assertNotIn("porteira adentro", texto.lower().replace(
                                "programa porteira adentro", ""
                            ))
                            self.assertLessEqual(proporcao_maiusculas(texto), 0.8, texto)
                self.assertTrue(achou, "nenhuma ementa com o Programa Porteira Adentro na tela")
                self.assertEqual(erros, [], msg=str(erros))
                page.close()

    def test_plano_plurianual_aparece_com_nome_proprio_no_historico_de_votos_1440(self):
        """E5k: o nome do plano aparece no historico de votos do vereador.

        Observacao de dado: das ementas com nome proprio novo, o Plano Municipal
        de Cultura (PLEX 26/2025) e o Sistema Municipal de Cultura (PLEX 23/2025)
        nao chegam a ser exibidos hoje, porque a materia de origem do Executivo
        nao tem votos nominais registrados e nao esta na lista de materias
        votadas da aba Camara. A grafia delas fica conferida no teste de unidade,
        que roda a funcao real do index.html com a ementa do SAPL.
        """
        with sync_playwright() as p:
            with _navegador(p) as browser:
                page = browser.new_page()
                erros = self._erros(page)
                page.set_viewport_size({"width": 1440, "height": 900})
                page.goto(self.base, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector("#sel-vereador", state="attached", timeout=60000)
                try:
                    page.click("button[data-secao-lateral='vereadores']", timeout=5000)
                except Exception:
                    page.click('button[data-secao="vereadores"]', timeout=15000)
                page.wait_for_selector("#sel-vereador", state="visible", timeout=30000)
                page.select_option("#sel-vereador", VEREADOR_HISTORICO)
                page.wait_for_timeout(600)
                page.click("button.voto-card[data-voto-card='sim']")
                page.wait_for_timeout(700)
                visiveis = page.eval_on_selector_all(
                    ".lista-votos .materia-assunto",
                    "els => els.map(e => e.textContent.trim())",
                )
                alvo = "Plano Plurianual"
                achou = [t for t in visiveis if alvo in t]
                self.assertTrue(
                    achou,
                    "Plano Plurianual nao apareceu no texto visivel: " + str(visiveis),
                )
                for texto in achou:
                    self.assertNotIn("plano plurianual", texto.lower().replace(
                        "plano plurianual", ""
                    ))
                    self.assertLessEqual(proporcao_maiusculas(texto), 0.8, texto)
                self.assertEqual(erros, [], msg=str(erros))
                self.assertLessEqual(self._rolagem_lateral(page), 1)
                page.close()


if __name__ == "__main__":
    unittest.main()