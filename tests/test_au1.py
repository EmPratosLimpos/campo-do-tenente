"""Testes da tarefa AU-1 (autoria estavel com o=id). Nenhum faz pedido ao SAPL."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

from atualizar_semana import coletar_autoria_estavel  # noqa: E402
from coletar_autoria import conferir_autoria  # noqa: E402
from coletar_lote import ColetorLote, OrcamentoEsgotado, PedidoPendente  # noqa: E402

CFG = {
    "cidade": {"nome": "Cidade Teste", "uf": "PR"},
    "sapl": {"endereco_base": "https://exemplo.invalid"},
    "campos_pessoais_removidos": {"lista": ["ip", "user"]},
    "rede": {
        "teto_bytes_resposta": 65536,
        "esquemas_permitidos": ["https"],
        "hosts_permitidos_extra": [],
    },
}


class Resposta:
    status = 200

    def __init__(self, corpo: bytes, url: str = "https://exemplo.invalid/api/materia/autoria/"):
        self.corpo = corpo
        self.url = url

    def geturl(self):
        return self.url

    def read(self, tamanho=None):
        if tamanho is None:
            return self.corpo
        return self.corpo[:tamanho]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def pagina(ids, total, total_pages, page):
    return json.dumps(
        {
            "pagination": {
                "total_entries": total,
                "total_pages": total_pages,
                "page": page,
            },
            "results": [{"id": i, "materia": 100 + i, "autor": 1} for i in ids],
        }
    ).encode("utf-8")


def servidor(paginas: dict[int, bytes], chamadas: list, erro=None):
    def urlopen(req, timeout=None):
        del timeout
        chamadas.append(req.full_url)
        if erro is not None:
            raise erro
        import urllib.parse

        consulta = urllib.parse.parse_qs(urllib.parse.urlparse(req.full_url).query)
        num = int((consulta.get("page") or ["1"])[0])
        return Resposta(paginas[num])

    return urlopen


class TestAu1Estavel(unittest.TestCase):
    def test_lista_estavel_nao_duplica_nem_perde(self):
        chamadas: list = []
        paginas = {
            1: pagina([1, 2], 6, 3, 1),
            2: pagina([3, 4], 6, 3, 2),
            3: pagina([5, 6], 6, 3, 3),
        }
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = ColetorLote(CFG, pasta, teto=20)
            coletor.adiar_falha = True
            pendentes: list = []
            with mock.patch("coletar_lote.time.sleep", lambda _s: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", servidor(paginas, chamadas)
            ):
                coletar_autoria_estavel(coletor, False, pendentes)
            self.assertEqual(pendentes, [])
            self.assertTrue(all("o=id" in url for url in chamadas))
            ok, _detalhe = conferir_autoria(pasta)
            self.assertTrue(ok)

    def test_ordem_trocada_nao_fecha_e_vale_o_antigo(self):
        chamadas: list = []
        paginas = {
            1: pagina([1, 2], 4, 2, 1),
            2: pagina([2, 3], 4, 2, 2),
        }
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            velho_p1 = pagina([1, 2], 4, 2, 1)
            velho_p2 = pagina([3, 4], 4, 2, 2)
            (pasta / "autoria_p1.json").write_bytes(velho_p1)
            (pasta / "autoria_p2.json").write_bytes(velho_p2)
            ok_antes, _ = conferir_autoria(pasta)
            self.assertTrue(ok_antes)
            coletor = ColetorLote(CFG, pasta, teto=20)
            coletor.adiar_falha = True
            pendentes: list = []
            with mock.patch("coletar_lote.time.sleep", lambda _s: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", servidor(paginas, chamadas)
            ):
                coletar_autoria_estavel(coletor, False, pendentes)
            self.assertEqual((pasta / "autoria_p1.json").read_bytes(), velho_p1)
            self.assertEqual((pasta / "autoria_p2.json").read_bytes(), velho_p2)
            self.assertEqual(len(pendentes), 1)
            self.assertIn("nao fecha", pendentes[0]["descricao"])

    def test_resposta_vazia_nao_grava_e_vira_pendente(self):
        bom = pagina([1, 2], 2, 1, 1)

        class Vazia(Resposta):
            def read(self, tamanho=None):
                del tamanho
                return b""

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "autoria_p1.json").write_bytes(bom)
            coletor = ColetorLote(CFG, pasta, teto=20)
            coletor.adiar_falha = True
            pendentes: list = []
            with mock.patch("coletar_lote.time.sleep", lambda _s: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", lambda *a, **k: Vazia(b"")
            ):
                coletar_autoria_estavel(coletor, False, pendentes)
            self.assertEqual((pasta / "autoria_p1.json").read_bytes(), bom)
            self.assertEqual(len(pendentes), 1)
            self.assertEqual(pendentes[0]["arquivo"], "autoria_p1.json")

    def test_falha_503_vira_pendente_com_arquivo_antigo(self):
        bom = pagina([1, 2], 2, 1, 1)
        chamadas: list = []
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            (pasta / "autoria_p1.json").write_bytes(bom)
            coletor = ColetorLote(CFG, pasta, teto=20)
            coletor.adiar_falha = True
            pendentes: list = []
            with mock.patch("coletar_lote.time.sleep", lambda _s: None), mock.patch(
                "coletar_lote.urllib.request.urlopen",
                servidor({1: bom}, chamadas, erro=urllib.error.URLError("fora")),
            ):
                coletar_autoria_estavel(coletor, False, pendentes)
            self.assertEqual((pasta / "autoria_p1.json").read_bytes(), bom)
            self.assertEqual(len(pendentes), 1)
            self.assertIn("autoria pagina 1", pendentes[0]["descricao"])

    def test_teto_estourado_para_em_vez_de_publicar_parcial(self):
        chamadas: list = []
        paginas = {
            1: pagina([1, 2], 6, 3, 1),
            2: pagina([3, 4], 6, 3, 2),
            3: pagina([5, 6], 6, 3, 3),
        }
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = ColetorLote(CFG, pasta, teto=2)
            coletor.adiar_falha = True
            with mock.patch("coletar_lote.time.sleep", lambda _s: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", servidor(paginas, chamadas)
            ):
                with self.assertRaises(OrcamentoEsgotado):
                    coletar_autoria_estavel(coletor, False, [])
            self.assertLessEqual(len(chamadas), 2)


if __name__ == "__main__":
    unittest.main()
