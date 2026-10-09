"""D-051: historico so com voto valido e ordem do seletor."""

from __future__ import annotations

import json
import pathlib
import re
import sys
import threading
import time
import unicodedata
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

ESTADOS = (
    "sim",
    "nao",
    "abstencao",
    "nao_votou",
    "presidente_que_nao_votou",
    "ausente_com_justificativa",
    "ausente_sem_justificativa",
    "fora_do_mandato",
    "presente_sem_voto_individual_registrado",
)
TURNOS_VALIDOS = ("2o turno", "turno unico")


def carregar(nome: str) -> dict:
    return json.loads((RAIZ / "dados" / "tratados" / nome).read_text(encoding="utf-8"))


def chave_ordenacao(nome: str) -> str:
    texto = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z ]", "", texto.lower()).strip()


class TestTotalIgualSoma(unittest.TestCase):
    def test_total_igual_soma_em_todos_os_periodos(self):
        for nome in (
            "atuacao_vereadores_2025.json",
            "atuacao_vereadores_2026.json",
            "atuacao_vereadores_legislatura.json",
        ):
            dados = carregar(nome)
            for v in dados.get("vereadores") or []:
                vo = v["votos"]
                with self.subTest(arquivo=nome, vereador=v.get("slug_codigo")):
                    self.assertEqual(vo["total_registros"], len(vo["nominais"]))
                    self.assertEqual(vo["total_registros"], sum(vo[k] for k in ESTADOS))
                    for n in vo["nominais"]:
                        self.assertIn(n.get("turno"), TURNOS_VALIDOS, n.get("votacao_id"))

    def test_marcos_rodrigues_legislatura_soma_dos_anos(self):
        leg = carregar("atuacao_vereadores_legislatura.json")
        v = next(x for x in leg["vereadores"] if x.get("slug_codigo") == "dr-marcos-rodrigues")
        esperado_total = 0
        ids_anos = set()
        for ano in leg["meta"]["anos_recorte"]:
            dados = carregar(f"atuacao_vereadores_{int(ano)}.json")
            va = next(
                (x for x in dados["vereadores"] if x["id_sapl"] == v["id_sapl"]),
                None,
            )
            if va is None:
                continue
            esperado_total += va["votos"]["total_registros"]
            ids_anos.update(n.get("votacao_id") for n in va["votos"]["nominais"])
        self.assertEqual(v["votos"]["total_registros"], esperado_total)
        self.assertEqual(
            {n.get("votacao_id") for n in v["votos"]["nominais"]}, ids_anos
        )


class TestSeletorEstatico(unittest.TestCase):
    def test_regra_sem_nome_fixo_no_index(self):
        for caminho in (RAIZ / "index.html",):
            with self.subTest(arquivo=caminho.name):
                texto = caminho.read_text(encoding="utf-8")
                self.assertIn('localeCompare', texto)
                self.assertIn('"pt-BR"', texto)
                self.assertIn("motivos_fora_do_mandato", texto)
                self.assertIn("data_fim_mandato", texto)
                for proibido in ("Quege", "quege", "Gabardo", "gabardo"):
                    self.assertNotIn(proibido, texto)


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, format, *args):
        pass


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestSeletorPrevia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servidor = ThreadingHTTPServer(("127.0.0.1", 8798), _Handler)
        thread = threading.Thread(target=cls.servidor.serve_forever, daemon=True)
        thread.start()
        cls.base = "http://127.0.0.1:8798/index.html"
        time.sleep(0.4)
        leg = carregar("atuacao_vereadores_legislatura.json")
        ativos = [
            v["nome_parlamentar"]
            for v in leg["vereadores"]
            if not (v.get("motivos_fora_do_mandato") or [])
        ]
        cassados = [
            v["nome_parlamentar"]
            for v in leg["vereadores"]
            if v.get("motivos_fora_do_mandato") or []
        ]
        cls.esperados = sorted(ativos, key=chave_ordenacao) + sorted(
            cassados, key=chave_ordenacao
        )

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _abrir(self, page, largura: int = 390):
        page.goto(self.base, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("#bloco-votado-sessao .cab-cartao", timeout=60000)
        if largura >= 900:
            page.click("button[data-secao-lateral='vereadores']")
        else:
            page.click('button[data-secao="vereadores"]')
        page.wait_for_selector("#sel-vereador", timeout=60000)
        page.wait_for_timeout(400)

    def _opcoes(self, page) -> list[str]:
        return page.eval_on_selector(
            "#sel-vereador",
            "el => Array.from(el.options).map(o => o.text.replace(/\\s*\\(Cassado\\)\\s*$/, ''))",
        )

    def test_ordem_e_padrao(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for largura in (390, 1440):
                page = browser.new_page(viewport={"width": largura, "height": 900})
                self._abrir(page, largura)
                with self.subTest(largura=largura):
                    self.assertEqual(self._opcoes(page), self.esperados)
                    selecionado = page.eval_on_selector(
                        "#sel-vereador", "el => el.options[el.selectedIndex].text"
                    )
                    self.assertTrue(selecionado.startswith(self.esperados[0]))
                    perfil = page.locator(".sel-vereador-face .nm").inner_text()
                    self.assertIn(self.esperados[0], perfil)
                    anterior = page.locator("#btn-ver-anterior")
                    self.assertTrue(anterior.is_disabled())
                page.close()
            browser.close()

    def test_anterior_e_proximo_seguem_a_ordem(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            self._abrir(page, 1440)
            page.click("#btn-ver-proximo")
            page.wait_for_timeout(500)
            perfil = page.locator(".sel-vereador-face .nm").inner_text()
            self.assertIn(self.esperados[1], perfil)
            for _ in range(len(self.esperados) - 2):
                page.click("#btn-ver-proximo")
                page.wait_for_timeout(250)
            ultimo = page.locator(".sel-vereador-face .nm").inner_text()
            self.assertIn(self.esperados[-1], ultimo)
            self.assertTrue(page.locator("#btn-ver-proximo").is_disabled())
            page.click("#btn-ver-anterior")
            page.wait_for_timeout(500)
            volta = page.locator(".sel-vereador-face .nm").inner_text()
            self.assertIn(self.esperados[-2], volta)
            browser.close()


if __name__ == "__main__":
    unittest.main()
