"""Testes das guardas de rede do coletor (SEG2 item C).

Nenhum teste aqui abre rede. Tudo usa fixture local.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
for caminho in (RAIZ / "coletor", RAIZ / "scripts"):
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))

from coletar_lote import (  # noqa: E402
    ColetorLote,
    host_final_da_resposta,
    ler_limitado,
)
from config_cidade import (  # noqa: E402
    carregar_config,
    conferir_host_final,
    conferir_url_permitida,
    esquemas_permitidos,
    host_da_url,
    hosts_permitidos,
    teto_bytes_resposta,
)

CFG = {
    "cidade": {"nome": "Cidade Teste", "uf": "PR"},
    "sapl": {"endereco_base": "https://sapl.exemplo.invalid"},
    "campos_pessoais_removidos": {"lista": ["ip", "user"]},
    "rede": {
        "teto_bytes_resposta": 64,
        "esquemas_permitidos": ["https"],
        "hosts_permitidos_extra": ["fotos.exemplo.invalid"],
    },
}
CORPO = b'{"pagination":{"total_pages":1},"results":[]}'


class RespostaLocal:
    status = 200

    def __init__(self, corpo: bytes = CORPO, url: str = "https://sapl.exemplo.invalid/api/"):
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


class TestConfigRede(unittest.TestCase):
    def test_lista_vem_do_config(self):
        self.assertEqual(esquemas_permitidos(CFG), ["https"])
        self.assertEqual(teto_bytes_resposta(CFG), 64)
        self.assertEqual(
            hosts_permitidos(CFG),
            {"sapl.exemplo.invalid", "fotos.exemplo.invalid"},
        )

    def test_config_real_tem_o_bloco_de_rede(self):
        cfg = carregar_config()
        self.assertEqual(esquemas_permitidos(cfg), ["https"])
        self.assertGreater(teto_bytes_resposta(cfg), 0)
        self.assertIn(
            host_da_url(cfg["sapl"]["endereco_base"]),
            hosts_permitidos(cfg),
        )

    def test_sem_teto_definido_a_coleta_e_recusada(self):
        cfg = dict(CFG)
        cfg["rede"] = dict(CFG["rede"])
        cfg["rede"].pop("teto_bytes_resposta")
        with self.assertRaises(SystemExit):
            teto_bytes_resposta(cfg)


class TestHostFinal(unittest.TestCase):
    def test_host_final_da_resposta(self):
        self.assertEqual(
            host_final_da_resposta(RespostaLocal(url="https://sapl.exemplo.invalid/api/x")),
            "sapl.exemplo.invalid",
        )
        self.assertEqual(
            host_final_da_resposta(RespostaLocal(url="https://OUTRO.exemplo.invalid/api/x")),
            "outro.exemplo.invalid",
        )

    def test_resposta_redirecionada_para_outro_host_e_recusada(self):
        with self.assertRaises(SystemExit) as contexto:
            conferir_host_final(
                "outro.exemplo.invalid", CFG, "lista_p1.json"
            )
        self.assertIn("nao esta no config", str(contexto.exception))
        self.assertIn("Nada foi gravado", str(contexto.exception))

    def test_resposta_do_host_permitido_passa(self):
        conferir_host_final("sapl.exemplo.invalid", CFG, "lista_p1.json")
        conferir_host_final("fotos.exemplo.invalid", CFG, "foto.jpg")

    def test_resposta_sem_host_e_recusada(self):
        with self.assertRaises(SystemExit):
            conferir_host_final("", CFG, "lista_p1.json")


class TestTetoDeBytes(unittest.TestCase):
    def test_Resposta_dentro_do_teto_passa(self):
        self.assertEqual(ler_limitado(RespostaLocal(), 64, "x.json"), CORPO)

    def test_Resposta_acima_do_teto_falha(self):
        grande = b'{"a":"' + b"x" * 200 + b'"}'
        with self.assertRaises(SystemExit) as contexto:
            ler_limitado(RespostaLocal(corpo=grande), 64, "x.json")
        self.assertIn("teto", str(contexto.exception))
        self.assertIn("Nada foi gravado", str(contexto.exception))


class TestColetorLoteGuardas(unittest.TestCase):
    def _coletor(self, pasta):
        return ColetorLote(CFG, pasta, teto=10)

    def test_resposta_de_outro_host_nao_grava(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = self._coletor(pasta)
            resposta = RespostaLocal(url="https://outro.exemplo.invalid/api/x")
            with mock.patch("coletar_lote.time.sleep", lambda *a: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", lambda *a, **k: resposta
            ):
                with self.assertRaises(SystemExit):
                    coletor.pedir("/api/um/", None, "um.json")
            self.assertFalse((pasta / "um.json").exists())
            self.assertFalse(coletor.gravou)

    def test_resposta_acima_do_teto_nao_grava(self):
        grande = json.dumps({"results": [{"id": 1, "nota": "y" * 200}]}).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = self._coletor(pasta)
            with mock.patch("coletar_lote.time.sleep", lambda *a: None), mock.patch(
                "coletar_lote.urllib.request.urlopen",
                lambda *a, **k: RespostaLocal(corpo=grande),
            ):
                with self.assertRaises(SystemExit):
                    coletor.pedir("/api/um/", None, "um.json")
            self.assertFalse((pasta / "um.json").exists())
            self.assertFalse(coletor.gravou)

    def test_resposta_valida_grava_e_tira_campo_pessoal(self):
        corpo = b'{"results":[{"id":1,"ip":"10.0.0.1","user":5}],"total":1}'
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = self._coletor(pasta)
            with mock.patch("coletar_lote.time.sleep", lambda *a: None), mock.patch(
                "coletar_lote.urllib.request.urlopen",
                lambda *a, **k: RespostaLocal(corpo=corpo),
            ):
                dados = coletor.pedir("/api/um/", None, "um.json")
            self.assertEqual(dados, {"results": [{"id": 1}], "total": 1})
            self.assertEqual(
                json.loads((pasta / "um.json").read_text(encoding="utf-8")),
                {"results": [{"id": 1}], "total": 1},
            )


class TestUrlDosBaixadores(unittest.TestCase):
    RECUSADAS = (
        "file:///etc/passwd",
        "data:text/html;base64,PGI+b2k8L2I+",
        "ftp://sapl.exemplo.invalid/ata.pdf",
        "http://sapl.exemplo.invalid/ata.pdf",
        "https://outro.exemplo.invalid/ata.pdf",
        "https://sapl.exemplo.invalid.evil.invalid/ata.pdf",
        "",
        "javascript:alert(1)",
    )

    def test_url_fora_das_regras_e_recusada(self):
        for url in self.RECUSADAS:
            with self.subTest(url=url):
                with self.assertRaises(SystemExit):
                    conferir_url_permitida(url, CFG, "ata.pdf")

    def test_url_https_do_host_permitido_passa(self):
        self.assertEqual(
            conferir_url_permitida("https://sapl.exemplo.invalid/a/b.pdf", CFG),
            "https://sapl.exemplo.invalid/a/b.pdf",
        )
        self.assertEqual(
            conferir_url_permitida("https://fotos.exemplo.invalid/1.jpg", CFG),
            "https://fotos.exemplo.invalid/1.jpg",
        )

    def test_baixar_textos_originais_recusa_sem_abrir_conexao(self):
        import baixar_textos_originais as baixa

        def nao_deve_chamar(*_args, **_kwargs):
            raise AssertionError("o download nao pode abrir conexao com URL recusada")

        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "ata.pdf"
            with mock.patch.object(baixa.urllib.request, "urlopen", nao_deve_chamar):
                with self.assertRaises(SystemExit):
                    baixa.baixar(
                        "file:///etc/passwd", destino, "agente", CFG
                    )
            self.assertFalse(destino.exists())

    def test_baixar_fotos_recusa_sem_abrir_conexao(self):
        import baixar_fotos_vereadores as baixa

        def nao_deve_chamar(*_args, **_kwargs):
            raise AssertionError("o download nao pode abrir conexao com URL recusada")

        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "1.jpg"
            with mock.patch.object(baixa.urllib.request, "urlopen", nao_deve_chamar):
                for url in ("data:text/plain,x", "ftp://sapl.exemplo.invalid/1.jpg"):
                    with self.subTest(url=url):
                        with self.assertRaises(SystemExit):
                            baixa.baixar(url, destino, CFG)
            self.assertFalse(destino.exists())

    def test_baixar_fotos_grava_quando_o_host_passa(self):
        import baixar_fotos_vereadores as baixa

        dados = b"x" * 300
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "1.jpg"
            resposta = RespostaLocal(
                corpo=dados, url="https://fotos.exemplo.invalid/1.jpg"
            )
            with mock.patch.object(
                baixa.urllib.request, "urlopen", lambda *a, **k: resposta
            ):
                self.assertTrue(
                    baixa.baixar("https://fotos.exemplo.invalid/1.jpg", destino, CFG)
                )
            self.assertEqual(destino.read_bytes(), dados)


class TestRegraDoPauser(unittest.TestCase):
    def test_pausa_do_sapl_nao_cai_abaixo_de_2_5(self):
        from config_cidade import PAUSA_SAPL_SEGUNDOS

        self.assertGreaterEqual(PAUSA_SAPL_SEGUNDOS, 2.5)

    def test_coletor_recusa_pausa_curta(self):
        with mock.patch("coletar_lote.PAUSA_SAPL_SEGUNDOS", 1.0):
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(SystemExit):
                    ColetorLote(CFG, Path(tmp), teto=1)


if __name__ == "__main__":
    unittest.main()
