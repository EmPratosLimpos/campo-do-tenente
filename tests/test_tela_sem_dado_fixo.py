"""Garante que a tela exibe apenas dados rastreáveis de Campo do Tenente (sem exemplo fixo)."""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import threading
import time
import unittest
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

RAIZ = pathlib.Path(__file__).resolve().parent.parent

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_OK = True
    PLAYWRIGHT_MOTIVO = ""
except ImportError:
    PLAYWRIGHT_OK = False
    PLAYWRIGHT_MOTIVO = "playwright nao instalado (pip install playwright && playwright install chromium)"


def ids_sapl_brutos() -> tuple[set[int], set[int]]:
    sessoes: set[int] = set()
    materias: set[int] = set()
    brutos = RAIZ / "dados" / "brutos"
    for path in brutos.rglob("*.json"):
        nome = path.name.lower()
        if "sessaoplenaria" not in nome and "materialegislativa" not in nome:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        resultados = payload.get("results") or payload.get("resultados") or []
        if not isinstance(resultados, list):
            continue
        for item in resultados:
            if not isinstance(item, dict):
                continue
            rid = item.get("id")
            if rid is None:
                continue
            try:
                iid = int(rid)
            except (TypeError, ValueError):
                continue
            if "sessaoplenaria" in nome:
                sessoes.add(iid)
            else:
                materias.add(iid)
    return sessoes, materias


def meta_ano(ano: int) -> dict:
    path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
    dados = json.loads(path.read_text(encoding="utf-8"))
    return dados["meta"]


def meta_legislatura() -> dict:
    path = RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json"
    dados = json.loads(path.read_text(encoding="utf-8"))
    return dados["meta"]


def data_coleta_exibida(meta: dict) -> str:
    raw = meta.get("dado_coletado_em") or ""
    dia = raw.split("T")[0]
    partes = dia.split("-")
    if len(partes) != 3:
        return ""
    data = f"{partes[2]}/{partes[1]}/{partes[0]}"
    if "T" not in raw:
        return data
    hora = raw.split("T", 1)[1].replace("-03:00", "").replace("+00:00", "")[:5]
    if hora:
        return f"{data} às {hora}"
    return data


def datas_sessoes_ano(ano: int) -> set[str]:
    path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
    dados = json.loads(path.read_text(encoding="utf-8"))
    out = set()
    for s in dados.get("sessoes") or []:
        d = s.get("data")
        if not d:
            continue
        p = d.split("-")
        if len(p) == 3:
            out.add(f"{p[2]}/{p[1]}/{p[0]}")
    return out


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)


def _servir(porta: int) -> ThreadingHTTPServer:
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), _Handler)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    return servidor


@unittest.skipUnless(PLAYWRIGHT_OK, PLAYWRIGHT_MOTIVO)
class TestTelaSemDadoFixo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessoes_brutas, cls.materias_brutas = ids_sapl_brutos()
        cls.servidor = _servir(8791)
        cls.base = "http://127.0.0.1:8791/index.html"
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown()

    def _texto_pagina(self, page):
        page.goto(self.base, wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(800)
        for periodo in ("sessao", "mes", "todo"):
            page.click(f'button[data-periodo="{periodo}"]')
            page.wait_for_timeout(400)
        return page.inner_text("body")

    def _links_sapl(self, page):
        hrefs = page.eval_on_selector_all(
            'a[href*="sapl.campodotenente.pr.leg.br"]',
            "els => els.map(e => e.href)",
        )
        return hrefs or []

    def test_legislatura_sem_dado_fixo(self):
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            meta = meta_legislatura()
            data_coleta = data_coleta_exibida(meta)
            datas_ok: set[str] = set()
            for ano in (2025, 2026):
                datas_ok |= datas_sessoes_ano(ano)

            page.goto(self.base, wait_until="networkidle", timeout=120000)
            page.wait_for_timeout(1200)
            page.click('button[data-periodo="sessao"]')
            rodape = page.locator("#painel-periodo-sessao .rodape-coleta")
            page.wait_for_function(
                """(sel) => {
                  var el = document.querySelector(sel);
                  return el && el.innerText.indexOf('Dado coletado') !== -1;
                }""",
                arg="#painel-periodo-sessao .rodape-coleta",
                timeout=15000,
            )
            rodapes = rodape.inner_text()
            self.assertIn(data_coleta, rodapes, "data de coleta do meta da legislatura")

            texto = page.inner_text("body")
            if "parlamentar" in texto:
                leg = json.loads(
                    (RAIZ / "dados" / "tratados" / "atuacao_vereadores_legislatura.json").read_text(
                        encoding="utf-8"
                    )
                )
                sessoes = [s for s in (leg.get("sessoes") or []) if s.get("data")]
                ultima = max(sessoes, key=lambda s: (s.get("data") or "", s.get("id") or 0))
                banca_sessao = (
                    int(ultima.get("n_presentes") or 0)
                    + int(ultima.get("n_faltas_com_justificativa") or 0)
                    + int(ultima.get("n_faltas_sem_justificativa") or 0)
                    + int(ultima.get("n_licenca") or 0)
                )
                self.assertIn(str(banca_sessao), texto, "banca da ultima sessao")

            for href in self._links_sapl(page):
                m_sess = re.search(r"/sessao/(\d+)", href)
                if m_sess:
                    sid = int(m_sess.group(1))
                    self.assertIn(sid, self.sessoes_brutas, f"sessao {sid}")
                m_mat = re.search(r"/materia/(\d+)", href)
                if m_mat:
                    mid = int(m_mat.group(1))
                    self.assertIn(mid, self.materias_brutas, f"materia {mid}")

            for periodo in ("sessao", "mes", "todo"):
                page.click(f'button[data-periodo="{periodo}"]')
                page.wait_for_timeout(500)
                bloco = page.inner_text("body")
                for data_sess in re.findall(r"\b\d{2}/\d{2}/\d{4}\b", bloco):
                    if data_sess in data_coleta:
                        continue
                    if data_coleta.startswith(data_sess):
                        continue
                    self.assertIn(
                        data_sess,
                        datas_ok,
                        f"data de sessao {data_sess} fora do consolidado ({periodo})",
                    )

            browser.close()


if __name__ == "__main__":
    unittest.main()
