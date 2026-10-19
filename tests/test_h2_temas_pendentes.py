"""Testes da tarefa H2: materia sem consenso de tema nao trava a semana.

Sem internet e sem chave real: as respostas dos modelos sao falsas,
como em test_e6a_temas e test_cr121b. Provam a regra de cobertura nos
dois sentidos: materia do lote fora dos dois arquivos falha, e o mesmo
id nos dois arquivos falha.
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

import classificar_temas as modulo  # noqa: E402
from config_cidade import carregar_config  # noqa: E402

CHAVE_FALSA = "CHAVE-FALSA-SO-PARA-TESTE-H2"
TEMA_A = "Ruas, tr\u00e2nsito e transporte"
TEMA_B = "Sa\u00fade"
TEMA_C = "Educa\u00e7\u00e3o"

TIPOS = {"results": [{"id": 10, "sigla": "IND"}]}
BRUTA_900 = {"id": 900, "tipo": 10, "numero": 37, "ano": 2026, "ementa": "PODA DE ARVORES"}
BRUTA_901 = {"id": 901, "tipo": 10, "numero": 38, "ano": 2026, "ementa": "MUDANCA DE RUA"}


def cfg_falsa() -> dict:
    cfg = copy.deepcopy(carregar_config())
    cfg["classificacao_temas"] = {
        "endpoint": "http://modelo.invalid/chat",
        "modelos": [
            {"id": "m1", "endpoint": "http://modelo.invalid/chat"},
            {"id": "m2", "endpoint": "http://modelo.invalid/chat"},
            {"id": "m3", "endpoint": "http://modelo.invalid/chat"},
        ],
        "tempo_limite_s": 10,
        "max_tokens_resposta": 300,
    }
    return cfg


def montar_cenario(tmp, brutas, temas=(), pendentes=()):
    lote = Path(tmp) / "lote_20990101"
    lote.mkdir(parents=True, exist_ok=True)
    (lote / "tipomaterialegislativa_p1.json").write_text(
        json.dumps(TIPOS), encoding="utf-8"
    )
    (lote / "materialegislativa_ano2026_p1.json").write_text(
        json.dumps({"results": list(brutas)}), encoding="utf-8"
    )
    arquivo = Path(tmp) / "temas_materias.json"
    arquivo.write_text(
        json.dumps(
            {"descricao": "t", "fonte": "t", "total": len(temas), "materias": list(temas)},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    pendentes_path = Path(tmp) / "temas_pendentes.json"
    pendentes_path.write_text(
        json.dumps(
            {
                "descricao": "t",
                "fonte": "t",
                "total": len(pendentes),
                "pendentes": list(pendentes),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return arquivo


def pedir_fixo(resposta_por_modelo, tokens=5):
    def pedir(modelo, ponta, prompt, chave, sessao, limite, teto):
        return resposta_por_modelo[modelo], None, tokens, 0.1, "stop"

    return pedir


class TestCobertura(unittest.TestCase):
    def test_pendente_registrada_cobre(self):
        sem_registro, duplicados = modulo.cobertura_do_lote(
            [900, 901], [900], [901]
        )
        self.assertEqual(sem_registro, [])
        self.assertEqual(duplicados, [])

    def test_materia_fora_dos_dois_falha(self):
        sem_registro, duplicados = modulo.cobertura_do_lote(
            [900, 901], [900], []
        )
        self.assertEqual(sem_registro, [901])
        self.assertEqual(duplicados, [])

    def test_mesmo_id_nos_dois_falha(self):
        sem_registro, duplicados = modulo.cobertura_do_lote(
            [900, 901], [900, 901], [901]
        )
        self.assertEqual(sem_registro, [])
        self.assertEqual(duplicados, [901])


class TestPendentesGravados(unittest.TestCase):
    def test_tres_votos_diferentes_gravam_pendente_e_nao_tema(self):
        roteiro = {
            "m1": {"tema": TEMA_A, "confianca": "alta", "justificativa": "a"},
            "m2": {"tema": TEMA_B, "confianca": "alta", "justificativa": "b"},
            "m3": {"tema": TEMA_C, "confianca": "alta", "justificativa": "c"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = montar_cenario(tmp, [BRUTA_900])
            pendentes_path = Path(tmp) / "temas_pendentes.json"
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                resultado = modulo.classificar_novas(
                    cfg_falsa(),
                    CHAVE_FALSA,
                    hoje="2099-01-02",
                    pedir=pedir_fixo(roteiro),
                    abrir_issues=False,
                )
            self.assertEqual(resultado["consenso"], [])
            self.assertEqual(len(resultado["pendentes"]), 1)
            self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8"))["materias"], [])
            dados = json.loads(pendentes_path.read_text(encoding="utf-8"))
            self.assertEqual(dados["total"], 1)
            pendente = dados["pendentes"][0]
            self.assertEqual(pendente["id"], 900)
            self.assertEqual(pendente["ano"], 2026)
            self.assertEqual(pendente["sigla"], "IND")
            self.assertEqual(pendente["numero"], 37)
            self.assertEqual(pendente["motivo"], "sem consenso entre os modelos")
            self.assertEqual(pendente["data"], "2099-01-02")
            self.assertEqual(
                pendente["link"], "https://sapl.campodotenente.pr.leg.br/materia/900"
            )
            bruto = pendentes_path.read_bytes()
            self.assertNotIn(b"\r\n", bruto)
            self.assertTrue(bruto.endswith(b"\n"))

    def test_pendente_sai_quando_ganha_tema(self):
        roteiro = {
            "m1": {"tema": TEMA_A, "confianca": "alta", "justificativa": "a"},
            "m2": {"tema": TEMA_A, "confianca": "alta", "justificativa": "b"},
            "m3": {"tema": TEMA_B, "confianca": "alta", "justificativa": "c"},
        }
        pendente_antiga = {
            "id": 900,
            "ano": 2026,
            "sigla": "IND",
            "numero": 37,
            "link": "https://sapl.campodotenente.pr.leg.br/materia/900",
            "motivo": "sem consenso entre os modelos",
            "data": "2099-01-01",
        }
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = montar_cenario(tmp, [BRUTA_900], pendentes=[pendente_antiga])
            pendentes_path = Path(tmp) / "temas_pendentes.json"
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                resultado = modulo.classificar_novas(
                    cfg_falsa(),
                    CHAVE_FALSA,
                    hoje="2099-01-02",
                    pedir=pedir_fixo(roteiro),
                    abrir_issues=False,
                )
            self.assertEqual(len(resultado["consenso"]), 1)
            gravadas = json.loads(arquivo.read_text(encoding="utf-8"))["materias"]
            self.assertEqual([item["id"] for item in gravadas], [900])
            dados = json.loads(pendentes_path.read_text(encoding="utf-8"))
            self.assertEqual(dados["pendentes"], [])

    def test_sem_chave_registra_pendente(self):
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = montar_cenario(tmp, [BRUTA_900, BRUTA_901])
            pendentes_path = Path(tmp) / "temas_pendentes.json"
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                modulo.classificar_novas(cfg_falsa(), None, abrir_issues=False)
            dados = json.loads(pendentes_path.read_text(encoding="utf-8"))
            self.assertEqual([item["id"] for item in dados["pendentes"]], [900, 901])
            self.assertTrue(
                all(
                    item["motivo"] == "sem chave do classificador na execucao"
                    for item in dados["pendentes"]
                )
            )

    def test_gravacao_deterministica(self):
        roteiro = {
            "m1": {"tema": TEMA_A, "confianca": "alta", "justificativa": "a"},
            "m2": {"tema": TEMA_B, "confianca": "alta", "justificativa": "b"},
            "m3": {"tema": TEMA_C, "confianca": "alta", "justificativa": "c"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            arquivo = montar_cenario(tmp, [BRUTA_900, BRUTA_901])
            pendentes_path = Path(tmp) / "temas_pendentes.json"
            with unittest.mock.patch.object(modulo, "ARQUIVO_TEMAS", arquivo), unittest.mock.patch.object(
                modulo, "BRUTOS", Path(tmp)
            ):
                modulo.classificar_novas(
                    cfg_falsa(), CHAVE_FALSA, pedir=pedir_fixo(roteiro), abrir_issues=False
                )
                primeira = pendentes_path.read_bytes()
                modulo.classificar_novas(
                    cfg_falsa(), CHAVE_FALSA, pedir=pedir_fixo(roteiro), abrir_issues=False
                )
                segunda = pendentes_path.read_bytes()
            self.assertEqual(primeira, segunda)


if __name__ == "__main__":
    unittest.main()
