"""D3: presenca da legislatura, projetos sem motivos_fora, ids unicos no clone lateral."""

import json
import pathlib
import re
import threading
import time
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado"

RAIZ = pathlib.Path(__file__).resolve().parent.parent
TRATADOS = RAIZ / "dados" / "tratados"


def _carregar(nome: str) -> dict:
    return json.loads((TRATADOS / nome).read_text(encoding="utf-8"))


def _vereador_por_slug(dados: dict, slug: str) -> dict:
    for v in dados.get("vereadores") or []:
        if v.get("slug_codigo") == slug:
            return v
    raise AssertionError(f"vereador {slug} ausente")


class TestD3PresencaLegislatura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.leg = _carregar("atuacao_vereadores_legislatura.json")
        cls.por_ano = {
            int(a): _carregar(f"atuacao_vereadores_{a}.json")
            for a in cls.leg["meta"]["anos_recorte"]
        }

    def test_jorge_quege_legislatura(self):
        v = _vereador_por_slug(self.leg, "jorge-quege")
        p = v["presenca"]
        self.assertEqual(p["sessoes_ordinarias"], 60)
        self.assertEqual(p["presencas"], 36)
        self.assertEqual(p["faltas_com_justificativa"], 1)
        self.assertEqual(p["faltas_sem_justificativa"], 0)
        self.assertEqual(p["faltas_totais"], 1)
        self.assertAlmostEqual(p["taxa_presenca"], 60.0)
        self.assertAlmostEqual(p["percentual_faltas"], round(1 * 100 / 60, 2))
        self.assertEqual(p["sessoes_licenca"], 23)
        self.assertEqual(p["sessoes_fora_do_mandato"], 5)
        vereadores = json.loads(
            (TRATADOS / "vereadores.json").read_text(encoding="utf-8")
        )
        fim = next(
            item["data_fim_mandato"]
            for item in vereadores["vereadores"]
            if item.get("slug_codigo") == "jorge-quege"
        )
        self.assertTrue(p["por_sessao"])
        for item in p["por_sessao"]:
            self.assertLessEqual(item["data_sessao"], fim)
            self.assertNotEqual(item["situacao"], "fora_do_mandato")
        for nominal in v["votos"]["nominais"]:
            self.assertLessEqual(nominal["data_sessao"], fim)
        self.assertEqual(v["votos"]["fora_do_mandato"], 0)

    def test_presenca_legislatura_soma_dos_anos(self):
        campos = (
            "sessoes_ordinarias",
            "presencas",
            "faltas_totais",
            "faltas_com_justificativa",
            "faltas_sem_justificativa",
            "sessoes_licenca",
            "sessoes_fora_do_mandato",
        )
        for vleg in self.leg.get("vereadores") or []:
            vid = vleg["id_sapl"]
            soma = {c: 0 for c in campos}
            for ano, dados in self.por_ano.items():
                va = next((x for x in dados["vereadores"] if x["id_sapl"] == vid), None)
                if not va:
                    continue
                pa = va["presenca"]
                for c in campos:
                    soma[c] += pa.get(c) or 0
            pleg = vleg["presenca"]
            for c in campos:
                self.assertEqual(
                    pleg.get(c),
                    soma[c],
                    msg=f"id {vid} campo {c}",
                )
            taxa_esperada = (
                round(pleg["presencas"] * 100 / pleg["sessoes_ordinarias"], 2)
                if pleg["sessoes_ordinarias"]
                else 0.0
            )
            self.assertAlmostEqual(pleg["taxa_presenca"], taxa_esperada, msg=f"id {vid} taxa")

    def test_nenhum_projeto_com_motivos_fora(self):
        for p in self.leg.get("projetos_lei") or []:
            self.assertNotIn(
                "motivos_fora_do_mandato",
                p,
                msg=f"projeto id {p.get('id')}",
            )

    def test_lacuna_por_ano_na_meta_legislatura(self):
        meta = self.leg["meta"]
        self.assertNotIn("lacuna_sessoes_ordinarias", meta)
        lac = meta.get("lacuna_sessoes_ordinarias_por_ano") or {}
        for ano in self.leg["meta"]["anos_recorte"]:
            chave = str(int(ano))
            self.assertIn(chave, lac)
            orig = self.por_ano[int(ano)]["meta"].get("lacuna_sessoes_ordinarias")
            self.assertEqual(lac[chave], orig)


class _Handler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestD3TelaPlaywright(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8796), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8796/index.html"
        time.sleep(0.35)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def test_ids_unicos_na_pagina(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(self.base, wait_until="networkidle", timeout=60000)
            duplicados = page.evaluate(
                """() => {
                  const vistos = new Set();
                  const dup = [];
                  document.querySelectorAll('[id]').forEach(el => {
                    const id = el.id;
                    if (!id) return;
                    if (vistos.has(id)) dup.push(id);
                    else vistos.add(id);
                  });
                  return dup;
                }"""
            )
            browser.close()
            self.assertEqual(duplicados, [], msg=f"ids duplicados: {duplicados}")

    def test_jorge_quege_taxa_presenca_na_tela(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(self.base, wait_until="networkidle", timeout=60000)
            page.click("button[data-secao-lateral='vereadores']")
            page.wait_for_selector(".perfil-cabecalho", timeout=60000)
            page.select_option("#sel-vereador", label="Jorge Quege (Cassado)")
            page.wait_for_timeout(800)
            presenca_card = page.locator("#tit-presenca").locator("xpath=ancestor::details[1]")
            if not presenca_card.evaluate("node => node.open"):
                page.locator("#tit-presenca").locator("xpath=ancestor::summary[1]").click()
                page.wait_for_timeout(400)
            texto = page.inner_text("body")
            taxa = _carregar("atuacao_vereadores_legislatura.json")
            jorge = next(
                v for v in taxa["vereadores"] if v.get("slug_codigo") == "jorge-quege"
            )
            esperado = f"{jorge['presenca']['taxa_presenca']:.1f}".replace(".", ",")
            self.assertIn(esperado, texto)
            self.assertNotIn("Fora do mandato naquela data", texto)
            browser.close()


class TestD3IndexEstatico(unittest.TestCase):
    def test_link_cassacao_usa_url_segura(self):
        html = (RAIZ / "index.html").read_text(encoding="utf-8")
        m = re.search(
            r"function renderBadgeCassacao\(v\) \{[\s\S]*?\n  \}",
            html,
        )
        self.assertIsNotNone(m)
        bloco = m.group(0)
        self.assertIn("urlSegura(", bloco)
        self.assertIn("encodeURIComponent", bloco)
        self.assertNotRegex(
            bloco,
            r'SAPL_ORIGEM \+ "/materia/" \+ cassacao\.materia_id',
        )


if __name__ == "__main__":
    unittest.main()
