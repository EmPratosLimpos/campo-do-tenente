"""Testes da tarefa E6a (D-047). Nenhum faz pedido a internet:
tudo passa por um servidor falso local que imita o plano OpenCode Go."""

from __future__ import annotations

import copy
import io
import json
import sys
import threading
import unittest
import unittest.mock
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

import classificar_temas as modulo  # noqa: E402
from config_cidade import carregar_config  # noqa: E402

CHAVE_FALSA = "CHAVE-FALSA-SO-PARA-TESTE-12345"
TEMA_A = "Ruas, tr\u00e2nsito e transporte"
TEMA_B = "Sa\u00fade"
TEMA_C = "Educa\u00e7\u00e3o"


def resposta_json(tema, confianca="alta", justificativa="justificativa de teste"):
    return json.dumps(
        {"tema": tema, "confianca": confianca, "justificativa": justificativa},
        ensure_ascii=False,
    )


class ServidorFalso:
    """Servidor falso do plano Go: respostas programadas por modelo."""

    def __init__(self, roteiro):
        self.roteiro = roteiro
        self.pedidos = []
        self.servidor = HTTPServer(("127.0.0.1", 0), self._fabrica())
        self.fio = threading.Thread(target=self.servidor.serve_forever, daemon=True)

    def _fabrica(self):
        roteiro = self.roteiro
        pedidos = self.pedidos

        class Manipulador(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(tamanho)
                try:
                    dados = json.loads(corpo.decode("utf-8"))
                except ValueError:
                    dados = {}
                pedidos.append(
                    {
                        "caminho": self.path,
                        "modelo": dados.get("model"),
                        "user_agent": self.headers.get("User-Agent"),
                        "sessao": self.headers.get("x-opencode-session"),
                        "auth": self.headers.get("Authorization"),
                        "corpo": dados,
                    }
                )
                vez = roteiro.get(dados.get("model")) or []
                passo = vez.pop(0) if vez else {"status": 500, "content": "sem roteiro"}
                status = int(passo.get("status", 200))
                if status != 200:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps({"erro": passo.get("content", "limite")}).encode("utf-8")
                    )
                    return
                conteudo = passo.get("content", "")
                tokens = int(passo.get("tokens", 10))
                if self.path.endswith("/responses"):
                    saida = {
                        "output": [{"content": [{"text": conteudo}]}],
                        "usage": {"input_tokens": tokens, "output_tokens": 3},
                    }
                else:
                    saida = {
                        "choices": [{"message": {"content": conteudo}}],
                        "usage": {"total_tokens": tokens},
                    }
                bruto = json.dumps(saida).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(bruto)))
                self.end_headers()
                self.wfile.write(bruto)

        return Manipulador

    def __enter__(self):
        self.fio.start()
        return self

    def __exit__(self, *args):
        self.servidor.shutdown()
        self.servidor.server_close()
        self.fio.join(timeout=10)

    @property
    def base(self):
        porta = self.servidor.server_address[1]
        return f"http://127.0.0.1:{porta}"


class FakeGh:
    """Imita o gh: lista issues abertas e registra criacoes."""

    def __init__(self, abertas=()):
        self.abertas = list(abertas)
        self.criadas = []

    def __call__(self, cmd, **kwargs):
        class Resultado:
            pass

        resultado = Resultado()
        if "list" in cmd:
            resultado.returncode = 0
            resultado.stdout = json.dumps(
                [{"number": 1, "title": titulo} for titulo in self.abertas]
            )
            resultado.stderr = ""
            return resultado
        if "create" in cmd:
            titulo = cmd[cmd.index("--title") + 1]
            corpo = cmd[cmd.index("--body") + 1]
            self.criadas.append({"titulo": titulo, "corpo": corpo})
            resultado.returncode = 0
            resultado.stdout = "https://exemplo.invalid/issue/1"
            resultado.stderr = ""
            return resultado
        resultado.returncode = 1
        resultado.stdout = ""
        resultado.stderr = "comando desconhecido"
        return resultado


def cfg_falsa(base, caminho="chat"):
    cfg = copy.deepcopy(carregar_config())
    cfg["classificacao_temas"] = {
        "endpoint": f"{base}/{caminho}",
        "modelos": [
            {"id": "m1", "endpoint": f"{base}/{caminho}"},
            {"id": "m2", "endpoint": f"{base}/{caminho}"},
            {"id": "m3", "endpoint": f"{base}/{caminho}"},
        ],
        "tempo_limite_s": 10,
        "max_tokens_resposta": 300,
    }
    return cfg


BRUTA_900 = {
    "id": 900,
    "__str__": "Indica\u00e7\u00e3o 37 de 2026",
    "tipo": 10,
    "numero": 37,
    "ano": 2026,
    "ementa": "PODA DE ARVORES NA AVENIDA",
}
BRUTA_901 = {
    "id": 901,
    "__str__": "Ata 37 de 2026",
    "tipo": 19,
    "numero": 37,
    "ano": 2026,
    "ementa": "ATA DA SESSAO",
}
TIPOS = {"results": [{"id": 10, "sigla": "IND"}, {"id": 19, "sigla": "ATA"}]}


def montar_cenario(tmp, brutas, temas=()):
    lote = Path(tmp) / "lote_20990101"
    lote.mkdir(parents=True)
    (lote / "tipomaterialegislativa_p1.json").write_text(
        json.dumps(TIPOS), encoding="utf-8"
    )
    (lote / "materialegislativa_ano2026_p1.json").write_text(
        json.dumps({"results": list(brutas)}), encoding="utf-8"
    )
    arquivo = Path(tmp) / "temas_materias.json"
    arquivo.write_text(
        json.dumps(
            {
                "descricao": "cenario de teste",
                "fonte": "teste",
                "total": len(temas),
                "materias": list(temas),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return arquivo


class TestConsenso(unittest.TestCase):
    def test_tres_iguais_gravam(self):
        import tempfile

        roteiro = {
            "m1": [{"content": resposta_json(TEMA_A)}],
            "m2": [{"content": resposta_json(TEMA_A, "media", "outra frase")}],
            "m3": [{"content": resposta_json(TEMA_A)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, hoje="2099-01-02", correr=gh)
            self.assertEqual(resultado["novas"], [900])
            self.assertEqual(len(resultado["consenso"]), 1)
            self.assertEqual(resultado["pendentes"], [])
            entrada = resultado["consenso"][0]
            self.assertEqual(entrada["tema"], TEMA_A)
            self.assertEqual(entrada["classificado_por"], "consenso D-047: m1, m2, m3")
            self.assertIs(entrada["revisada_por_humano"], False)
            gravadas = json.loads(arquivo.read_text(encoding="utf-8"))["materias"]
            self.assertEqual(len(gravadas), 1)
            self.assertEqual(gravadas[0]["data"], "2099-01-02")
            self.assertEqual(gravadas[0]["link"], "https://sapl.campodotenente.pr.leg.br/materia/900")
            self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8"))["total"], 1)

    def test_dois_iguais_gravam_com_quem_concordou(self):
        import tempfile

        roteiro = {
            "m1": [{"content": resposta_json(TEMA_A)}],
            "m2": [{"content": resposta_json(TEMA_B)}],
            "m3": [{"content": resposta_json(TEMA_A)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(len(resultado["consenso"]), 1)
            self.assertEqual(resultado["consenso"][0]["classificado_por"], "consenso D-047: m1, m3")
            self.assertEqual(resultado["pendentes"], [])

    def test_tres_diferentes_nao_gravam_e_geram_issue(self):
        import tempfile

        roteiro = {
            "m1": [{"content": resposta_json(TEMA_A)}],
            "m2": [{"content": resposta_json(TEMA_B)}],
            "m3": [{"content": resposta_json(TEMA_C)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(resultado["consenso"], [])
            self.assertEqual(len(resultado["pendentes"]), 1)
            self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8"))["materias"], [])
            self.assertEqual(len(gh.criadas), 1)
            issue = gh.criadas[0]
            self.assertEqual(issue["titulo"], "Tema para revisao: IND 37/2026")
            self.assertIn("PODA DE ARVORES", issue["corpo"])
            self.assertIn("https://sapl.campodotenente.pr.leg.br/materia/900", issue["corpo"])
            self.assertIn("m1", issue["corpo"])
            self.assertNotIn(CHAVE_FALSA, issue["corpo"])

    def test_resposta_invalida_ou_fora_da_lista_nao_conta(self):
        import tempfile

        roteiro = {
            "m1": [{"content": "isto nao e json"}],
            "m2": [{"content": resposta_json("Tema Inventado")}],
            "m3": [{"content": resposta_json(TEMA_A)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(resultado["consenso"], [])
            self.assertEqual(len(resultado["pendentes"]), 1)

    def test_limite_de_uso_conta_como_invalida(self):
        import tempfile

        roteiro = {
            "m1": [{"status": 429, "content": "limite de uso do plano"}],
            "m2": [{"content": resposta_json(TEMA_A)}],
            "m3": [{"content": resposta_json(TEMA_A)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(len(resultado["consenso"]), 1)
            self.assertEqual(resultado["consenso"][0]["classificado_por"], "consenso D-047: m2, m3")

    def test_cerca_json_do_mimo_e_lida(self):
        import tempfile

        cercada = "```json\n" + resposta_json(TEMA_A) + "\n```"
        roteiro = {
            "m1": [{"content": cercada}],
            "m2": [{"content": resposta_json(TEMA_A)}],
            "m3": [{"content": resposta_json(TEMA_B)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(len(resultado["consenso"]), 1)
            self.assertEqual(resultado["consenso"][0]["classificado_por"], "consenso D-047: m1, m2")

    def test_formato_responses_tambem_funciona(self):
        import tempfile

        roteiro = {
            "m1": [{"content": resposta_json(TEMA_B)}],
            "m2": [{"content": resposta_json(TEMA_B)}],
            "m3": [{"content": resposta_json(TEMA_C)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base, "responses")
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(len(resultado["consenso"]), 1)
            self.assertEqual(resultado["consenso"][0]["tema"], TEMA_B)
            self.assertTrue(all(p["caminho"].endswith("/responses") for p in falso.pedidos))

    def test_cabecalhos_e_sessao_estavel(self):
        import tempfile

        roteiro = {
            "m1": [{"content": resposta_json(TEMA_A)}],
            "m2": [{"content": resposta_json(TEMA_A)}],
            "m3": [{"content": resposta_json(TEMA_A)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(len(falso.pedidos), 3)
            for pedido in falso.pedidos:
                self.assertEqual(pedido["user_agent"], "painel-temas/1.0")
                self.assertTrue((pedido["auth"] or "").startswith("Bearer "))
                self.assertTrue(pedido["sessao"])
            sessoes = {p["sessao"] for p in falso.pedidos}
            self.assertEqual(len(sessoes), 1)
            modelos = [p["modelo"] for p in falso.pedidos]
            self.assertEqual(modelos, ["m1", "m2", "m3"])
            for pedido in falso.pedidos:
                self.assertEqual(pedido["corpo"].get("temperature"), 0)

    def test_nao_se_aplica_so_para_ata_e_oficio(self):
        import tempfile

        cfg_base = carregar_config()
        especiais = {v for v in __import__("config_cidade").rotulos_especiais_tema(cfg_base).values()}
        rotulo = [v for v in especiais if "aplica" in v][0]
        materia_ind = {"sigla": "IND", "numero": 1, "ano": 2026, "ementa": "texto"}
        materia_ata = {"sigla": "ATA", "numero": 1, "ano": 2026, "ementa": "texto"}
        voto = {"tema": rotulo, "confianca": "alta", "justificativa": "ata"}
        self.assertIsNone(modulo.validar_resposta(voto, materia_ind, cfg_base))
        self.assertIsNotNone(modulo.validar_resposta(voto, materia_ata, cfg_base))


class TestSemChave(unittest.TestCase):
    def test_sem_chave_nao_falha_avisa_e_abre_issue(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900, BRUTA_901])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa("http://127.0.0.1:9")
                saida = io.StringIO()
                with redirect_stdout(saida):
                    resultado = modulo.classificar_novas(cfg, None, correr=gh)
                linhas = modulo.linhas_changelog_temas(resultado, sem_chave=True)
            self.assertEqual(resultado["consenso"], [])
            self.assertEqual(len(resultado["pendentes"]), 2)
            self.assertTrue(any("aguardam classificacao" in linha for linha in linhas))
            self.assertIn("2 materias novas", linhas[0])
            self.assertEqual(len(gh.criadas), 2)
            self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8"))["materias"], [])


class TestPreservacao(unittest.TestCase):
    def test_revisada_true_nunca_alterada(self):
        import tempfile

        antiga = {
            "id": 900,
            "ano": 2026,
            "sigla": "IND",
            "numero": 37,
            "tema": TEMA_C,
            "confianca": "alta",
            "justificativa": "texto antigo do mantenedor",
            "link": "https://sapl.campodotenente.pr.leg.br/materia/900",
            "classificado_por": "mantenedor (modelos sem consenso, D-047)",
            "revisada_por_humano": True,
            "revisado_por": "mantenedor",
            "data": "2099-01-01",
        }
        with tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900], temas=[antiga])
            antes = arquivo.read_bytes()
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa("http://127.0.0.1:9")
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(resultado["novas"], [])
            self.assertEqual(arquivo.read_bytes(), antes)

    def test_consenso_gravado_nao_classifica_de_novo(self):
        import tempfile
        from unittest import mock

        gravada = {
            "id": 900,
            "ano": 2026,
            "sigla": "IND",
            "numero": 37,
            "tema": TEMA_A,
            "confianca": "alta",
            "justificativa": "consenso anterior",
            "link": "https://sapl.campodotenente.pr.leg.br/materia/900",
            "classificado_por": "consenso D-047: m1, m2",
            "revisada_por_humano": False,
            "revisado_por": "",
            "data": "2099-01-01",
        }
        with tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900], temas=[gravada])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa("http://127.0.0.1:9")
                with mock.patch.object(modulo, "pedir_modelo") as pedir:
                    resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
                pedir.assert_not_called()
            self.assertEqual(resultado["novas"], [])

    def test_issue_nao_duplica_titulo_aberto(self):
        import tempfile

        roteiro = {
            "m1": [{"content": resposta_json(TEMA_A)}],
            "m2": [{"content": resposta_json(TEMA_B)}],
            "m3": [{"content": resposta_json(TEMA_C)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh(abertas=["Tema para revisao: IND 37/2026"])
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                resultado = modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
            self.assertEqual(len(resultado["pendentes"]), 1)
            self.assertEqual(gh.criadas, [])
            self.assertTrue(any("ja aberta" in aviso for aviso in resultado["avisos"]))


class TestSigilo(unittest.TestCase):
    def test_chave_nunca_aparece_na_saida(self):
        import tempfile

        roteiro = {
            "m1": [{"status": 500, "content": "pane interna"}],
            "m2": [{"content": resposta_json(TEMA_A)}],
            "m3": [{"content": resposta_json(TEMA_A)}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            gh = FakeGh()
            arquivo = montar_cenario(tmp, [BRUTA_900])
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                saida = io.StringIO()
                erros = io.StringIO()
                with redirect_stdout(saida), redirect_stderr(erros):
                    modulo.classificar_novas(cfg, CHAVE_FALSA, correr=gh)
                    modulo.imprimir_sondagem(
                        {"materias": [], "tokens_total": 0}
                    )
                texto_arquivo = arquivo.read_text(encoding="utf-8")
            combinado = saida.getvalue() + erros.getvalue() + texto_arquivo
            for issue in gh.criadas:
                combinado += issue["titulo"] + issue["corpo"]
            self.assertNotIn(CHAVE_FALSA, combinado)


class TestSondagem(unittest.TestCase):
    def test_sondagem_mostra_modelos_consenso_e_tokens_sem_gravar(self):
        import tempfile

        revisada = {
            "id": 900,
            "ano": 2026,
            "sigla": "IND",
            "numero": 37,
            "tema": TEMA_A,
            "confianca": "alta",
            "justificativa": "texto revisado",
            "link": "https://sapl.campodotenente.pr.leg.br/materia/900",
            "classificado_por": "consenso D-047: m1, m2, m3",
            "revisada_por_humano": True,
            "revisado_por": "mantenedor",
            "data": "2099-01-01",
        }
        roteiro = {
            "m1": [{"content": resposta_json(TEMA_A), "tokens": 40}],
            "m2": [{"content": resposta_json(TEMA_B), "tokens": 50}],
            "m3": [{"content": resposta_json(TEMA_A), "tokens": 60}],
        }
        with ServidorFalso(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            arquivo = montar_cenario(tmp, [BRUTA_900], temas=[revisada])
            antes = arquivo.read_bytes()
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                cfg = cfg_falsa(falso.base)
                saida_dados = modulo.sondar_ultimas_revisadas(cfg, CHAVE_FALSA)
                saida = io.StringIO()
                with redirect_stdout(saida):
                    modulo.imprimir_sondagem(saida_dados)
            texto = saida.getvalue()
            self.assertIn("m1", texto)
            self.assertIn("bateu", texto)
            self.assertIn("divergiu", texto)
            self.assertIn("Consenso", texto)
            self.assertIn("Total de tokens usados na sondagem: 150.", texto)
            self.assertNotIn(CHAVE_FALSA, texto)
            self.assertEqual(arquivo.read_bytes(), antes)
            self.assertEqual(saida_dados["tokens_total"], 150)


if __name__ == "__main__":
    unittest.main()
