"""Testes CR-121b: teto maior, nova tentativa em resposta cortada e motivo do invalido. Nenhum pedido a internet."""

from __future__ import annotations

import copy
import io
import json
import sys
import tempfile
import threading
import unittest
import unittest.mock
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

import classificar_temas as modulo  # noqa: E402
from config_cidade import carregar_config  # noqa: E402

CHAVE_FALSA = "CHAVE-FALSA-SO-PARA-TESTE-99999"
TEMA_A = "Ruas, trânsito e transporte"
TEMA_B = "Saúde"


def resposta_json(tema, confianca="alta", justificativa="justificativa de teste"):
    return json.dumps(
        {"tema": tema, "confianca": confianca, "justificativa": justificativa},
        ensure_ascii=False,
    )


class ServidorCorte:
    """Servidor falso que devolve finish_reason e raciocinio e registra o teto."""

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
                teto = dados.get("max_tokens") or dados.get("max_output_tokens") or 0
                pedidos.append({"modelo": dados.get("model"), "teto": int(teto or 0), "corpo": dados})
                vez = roteiro.get(dados.get("model")) or []
                passo = vez.pop(0) if vez else {"status": 500, "content": "sem roteiro"}
                status = int(passo.get("status", 200))
                if status != 200:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"erro": passo.get("content", "x")}).encode("utf-8"))
                    return
                conteudo = passo.get("content", "")
                finish = passo.get("finish_reason", "stop")
                raciocinio = int(passo.get("reasoning_tokens", 0))
                tokens = int(passo.get("tokens", 10))
                saida = {
                    "choices": [{"message": {"content": conteudo}, "finish_reason": finish}],
                    "usage": {
                        "total_tokens": tokens,
                        "completion_tokens_details": {"reasoning_tokens": raciocinio},
                    },
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
    def __init__(self):
        self.criadas = []

    def __call__(self, cmd, **kwargs):
        class Resultado:
            pass

        resultado = Resultado()
        if "list" in cmd:
            resultado.returncode = 0
            resultado.stdout = "[]"
            resultado.stderr = ""
            return resultado
        if "create" in cmd:
            resultado.returncode = 0
            resultado.stdout = "https://exemplo.invalid/issue/1"
            resultado.stderr = ""
            self.criadas.append({"titulo": cmd[cmd.index("--title") + 1], "corpo": cmd[cmd.index("--body") + 1]})
            return resultado
        resultado.returncode = 1
        resultado.stdout = ""
        resultado.stderr = "x"
        return resultado


def cfg_falsa(base, teto=100):
    cfg = copy.deepcopy(carregar_config())
    cfg["classificacao_temas"] = {
        "endpoint": f"{base}/chat",
        "modelos": [
            {"id": "m1", "endpoint": f"{base}/chat"},
            {"id": "m2", "endpoint": f"{base}/chat"},
            {"id": "m3", "endpoint": f"{base}/chat"},
        ],
        "tempo_limite_s": 10,
        "max_tokens_resposta": teto,
    }
    return cfg


BRUTA = {"id": 900, "ano": 2026, "sigla": "IND", "numero": 37, "ementa": "PODA DE ARVORES NA AVENIDA", "link": "https://exemplo.invalid/materia/900"}


class TestCortada(unittest.TestCase):
    def test_length_tenta_com_dobro_e_aceita_segunda(self):
        roteiro = {
            "m1": [
                {"content": '{"tema": "Sa', "finish_reason": "length", "tokens": 60},
                {"content": resposta_json(TEMA_A), "finish_reason": "stop", "tokens": 20},
            ],
            "m2": [{"content": resposta_json(TEMA_A), "finish_reason": "stop"}],
            "m3": [{"content": resposta_json(TEMA_A), "finish_reason": "stop"}],
        }
        with ServidorCorte(roteiro) as falso:
            cfg = cfg_falsa(falso.base, teto=100)
            conf = modulo.ler_conf_classificacao(cfg)
            votos = modulo.classificar_materia(BRUTA, cfg, CHAVE_FALSA, "sessao-x", conf)
        validos = [v for v in votos if v.get("tema")]
        self.assertEqual(len(validos), 3)
        self.assertTrue(all(v["tema"] == TEMA_A for v in validos))
        tetos_m1 = [p["teto"] for p in falso.pedidos if p["modelo"] == "m1"]
        self.assertEqual(tetos_m1, [100, 200])
        self.assertEqual(len(falso.pedidos), 4)

    def test_vazia_com_raciocinio_tenta_de_novo(self):
        roteiro = {
            "m1": [
                {"content": "", "finish_reason": "stop", "reasoning_tokens": 98, "tokens": 98},
                {"content": resposta_json(TEMA_B), "finish_reason": "stop", "tokens": 20},
            ],
            "m2": [{"content": resposta_json(TEMA_B), "finish_reason": "stop"}],
            "m3": [{"content": resposta_json(TEMA_B), "finish_reason": "stop"}],
        }
        with ServidorCorte(roteiro) as falso:
            cfg = cfg_falsa(falso.base, teto=100)
            conf = modulo.ler_conf_classificacao(cfg)
            votos = modulo.classificar_materia(BRUTA, cfg, CHAVE_FALSA, "sessao-y", conf)
        self.assertEqual(modulo.consenso_de(votos)["tema"], TEMA_B)
        tetos_m1 = [p["teto"] for p in falso.pedidos if p["modelo"] == "m1"]
        self.assertEqual(tetos_m1, [100, 200])

    def test_cortada_duas_vezes_vira_motivo(self):
        roteiro = {
            "m1": [
                {"content": '{"tema":', "finish_reason": "length"},
                {"content": '{"tema":', "finish_reason": "length"},
            ],
            "m2": [{"content": resposta_json(TEMA_A), "finish_reason": "stop"}],
            "m3": [{"content": resposta_json(TEMA_B), "finish_reason": "stop"}],
        }
        with ServidorCorte(roteiro) as falso:
            cfg = cfg_falsa(falso.base, teto=100)
            conf = modulo.ler_conf_classificacao(cfg)
            votos = modulo.classificar_materia(BRUTA, cfg, CHAVE_FALSA, "sessao-z", conf)
        por = {v["modelo"]: v for v in votos}
        self.assertIsNone(por["m1"]["tema"])
        self.assertIn("resposta cortada pelo limite", por["m1"]["motivo"])
        self.assertEqual(por["m1"]["finish_reason"], "length")


class TestMotivo(unittest.TestCase):
    def test_motivo_na_sondagem_e_na_issue(self):
        import tempfile

        roteiro = {
            "m1": [
                {"content": '{"tema":', "finish_reason": "length"},
                {"content": '{"tema":', "finish_reason": "length"},
            ],
            "m2": [{"content": resposta_json(TEMA_A), "finish_reason": "stop"}],
            "m3": [{"content": resposta_json(TEMA_A), "finish_reason": "stop"}],
        }
        revisada = {
            "id": 900, "ano": 2026, "sigla": "IND", "numero": 37, "tema": TEMA_A,
            "confianca": "alta", "justificativa": "rev", "link": "x",
            "classificado_por": "consenso D-047: m2, m3", "revisada_por_humano": True,
            "revisado_por": "mantenedor", "data": "2099-01-01",
        }
        with ServidorCorte(roteiro) as falso, tempfile.TemporaryDirectory() as tmp:
            lote = Path(tmp) / "lote_20990101"
            lote.mkdir(parents=True)
            (lote / "tipomaterialegislativa_p1.json").write_text(
                json.dumps({"results": [{"id": 10, "sigla": "IND"}]}), encoding="utf-8")
            (lote / "materialegislativa_ano2026_p1.json").write_text(
                json.dumps({"results": [{"id": 900, "tipo": 10, "numero": 37, "ano": 2026, "ementa": "PODA"}]}),
                encoding="utf-8")
            arquivo = Path(tmp) / "temas_materias.json"
            arquivo.write_text(json.dumps({"descricao": "t", "fonte": "t", "total": 1, "materias": [revisada]}),
                               encoding="utf-8")
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)):
                cfg = cfg_falsa(falso.base)
                saida = modulo.sondar_ultimas_revisadas(cfg, CHAVE_FALSA)
                texto = io.StringIO()
                with redirect_stdout(texto):
                    modulo.imprimir_sondagem(saida)
                votos_issue = [
                    {"modelo": "m1", "tema": None, "motivo": "resposta cortada pelo limite",
                     "finish_reason": "length", "tokens": 0, "tempo_s": 1.0},
                    {"modelo": "m2", "tema": TEMA_A, "confianca": "alta", "justificativa": "frase",
                     "motivo": "", "finish_reason": "stop", "tokens": 5, "tempo_s": 0.5},
                    {"modelo": "m3", "tema": TEMA_A, "confianca": "alta", "justificativa": "frase",
                     "motivo": "", "finish_reason": "stop", "tokens": 5, "tempo_s": 0.5},
                ]
                corpo = modulo.corpo_revisao(BRUTA, votos_issue, ["m1", "m2", "m3"])
        impresso = texto.getvalue()
        self.assertIn("resposta cortada pelo limite", impresso)
        self.assertIn("length", impresso)
        self.assertIn("resposta cortada pelo limite", corpo)
        self.assertNotIn(CHAVE_FALSA, impresso + corpo)

    def test_tema_fora_da_lista_mostra_tema(self):
        cfg = copy.deepcopy(carregar_config())
        materia = {"sigla": "IND", "numero": 1, "ano": 2026, "ementa": "texto"}
        resposta = {"tema": "Tema Inventado", "confianca": "alta", "justificativa": "frase"}
        motivo = modulo.motivo_resposta_invalida(resposta, materia, cfg)
        self.assertIn("tema fora da lista", motivo)
        self.assertIn("Tema Inventado", motivo)

        def pedir_falso(modelo, ponta, prompt, chave, sessao, limite, teto):
            if modelo == "m1":
                return {"tema": "Tema Inventado", "confianca": "alta", "justificativa": "frase"}, None, 5, 0.1, ""
            return {"tema": TEMA_A, "confianca": "alta", "justificativa": "frase"}, None, 5, 0.1, ""

        conf = {"modelos": [{"id": "m1", "endpoint": "x"}, {"id": "m2", "endpoint": "x"}, {"id": "m3", "endpoint": "x"}], "tempo_limite_s": 10, "max_tokens_resposta": 100}
        votos = modulo.classificar_materia(materia, cfg, CHAVE_FALSA, "s", conf, pedir_falso)
        por = {v["modelo"]: v for v in votos}
        self.assertIn("Tema Inventado", por["m1"]["motivo"])
        corpo = modulo.corpo_revisao(dict(materia, id=1, link="https://exemplo.invalid/materia/1"), votos, ["m1", "m2", "m3"])
        self.assertIn("Tema Inventado", corpo)


class TestConfig(unittest.TestCase):
    def test_teto_padrao_2000(self):
        cfg = carregar_config()
        self.assertEqual(int(cfg["classificacao_temas"]["max_tokens_resposta"]), 2000)


if __name__ == "__main__":
    unittest.main()
