"""Testes da rodada da votacao popular. Sem rede, sem base real.

Os dados de teste sao montados aqui, sem numero nem data fixa da base
real. So o ultimo teste le a base real, e confere apenas a forma.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))

import gerar_rodada_votacao as rodada  # noqa: E402

ELEGIVEIS = ["PLEG", "PLEX", "PRE", "REQ", "MOC", "IND"]
EXCLUIDAS = ["ATA", "COMPR", "EMD"]
CABECALHO_PAUTA = [
    "sessao_id",
    "item_ordem_id",
    "resultado",
    "materia_id",
    "numero",
    "ano",
    "tipo_sigla",
    "tipo_descricao",
    "ementa",
    "tema",
    "confianca",
    "classificado_por",
    "revisada_por_humano",
    "fonte_oficial",
]


def montar_base(
    raiz: Path,
    sessoes: list[dict],
    pauta: list[dict],
    registros: list[dict],
    dias_maximos: int = 60,
) -> None:
    """Base sintetica minima: config, atuacao, pauta e proposicoes."""
    (raiz / "dados" / "tratados").mkdir(parents=True, exist_ok=True)
    (raiz / "config_cidade.json").write_text(
        json.dumps(
            {
                "recorte": {"anos": [2026]},
                "votacao_popular": {
                    "siglas_elegiveis": ELEGIVEIS,
                    "siglas_excluidas": EXCLUIDAS,
                    "dias_maximos_rodada": dias_maximos,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (raiz / "dados" / "tratados" / "atuacao_vereadores_2026.json").write_text(
        json.dumps({"sessoes": sessoes}, ensure_ascii=False), encoding="utf-8"
    )
    with (raiz / "dados" / "tratados" / "tema-votacoes-2026.csv").open(
        "w", encoding="utf-8", newline=""
    ) as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=CABECALHO_PAUTA)
        escritor.writeheader()
        for linha in pauta:
            escritor.writerow({chave: linha.get(chave, "") for chave in CABECALHO_PAUTA})
    (raiz / "dados" / "tratados" / "proposicoes_2026.json").write_text(
        json.dumps({"todo": registros}, ensure_ascii=False), encoding="utf-8"
    )
    (raiz / "dados" / "tratados" / "executivo_2026.json").write_text(
        json.dumps({"todo": []}, ensure_ascii=False), encoding="utf-8"
    )


def linha_pauta(
    sessao: int, ordem: int, resultado: str, mid: int, sigla: str, numero="1"
) -> dict:
    return {
        "sessao_id": sessao,
        "item_ordem_id": ordem,
        "resultado": resultado,
        "materia_id": mid,
        "numero": numero,
        "ano": "2026",
        "tipo_sigla": sigla,
        "tipo_descricao": f"Tipo {sigla}",
        "ementa": f"Ementa oficial da materia {mid}.",
        "tema": "Tema",
        "confianca": "alta",
        "classificado_por": "teste",
        "revisada_por_humano": "sim",
        "fonte_oficial": f"https://exemplo.invalid/materia/{mid}",
    }


def registro(mid: int, sessao: int, deliberativa: bool) -> dict:
    return {
        "id": mid,
        "votacoes_registradas": [
            {
                "sessao_id": sessao,
                "deliberativa": deliberativa,
                "tipo_resultado_nome": (
                    "Aprovada por Unanimidade" if deliberativa else "Pedido de Vistas"
                ),
            }
        ],
    }


SESSOES = [
    {"id": 10, "numero": 1, "data": "2026-02-10"},
    {"id": 11, "numero": 2, "data": "2026-02-17"},
    {"id": 12, "numero": 3, "data": "2026-02-24"},
]


def gerar_na_base(tmp: str) -> dict:
    raiz = Path(tmp)
    rodada.gerar(raiz)
    return json.loads(
        (raiz / "dados" / "tratados" / "votacao_rodada.json").read_text(encoding="utf-8")
    )


def chaves_proibidas(valor) -> list:
    achadas = []
    if isinstance(valor, dict):
        for chave, item in valor.items():
            if any(parte in str(chave).lower() for parte in ("autor", "partido", "vereador")):
                achadas.append(chave)
            achadas.extend(chaves_proibidas(item))
    elif isinstance(valor, list):
        for item in valor:
            achadas.extend(chaves_proibidas(item))
    return achadas


class TestesRodada(unittest.TestCase):
    def test_escolhe_a_ultima_sessao_ordinaria(self):
        pauta = [linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "REQ")]
        pauta.append(linha_pauta(11, 1, "Aprovada por Unanimidade", 100, "REQ"))
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), SESSOES, pauta, [registro(101, 12, True)])
            saida = gerar_na_base(tmp)
        self.assertEqual(saida["rodada_id"], "sessao:12")
        self.assertEqual(saida["sessao_id"], 12)
        self.assertEqual(saida["data_sessao"], "2026-02-24")
        self.assertEqual(saida["status"], "aberta")
        self.assertEqual([materia["id"] for materia in saida["materias"]], [101])

    def test_exclui_sigla_excluida_e_fora_da_lista(self):
        pauta = [
            linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "ATA"),
            linha_pauta(12, 2, "Aprovada por Unanimidade", 102, "COMPR"),
            linha_pauta(12, 3, "Aprovada por Unanimidade", 103, "EMD"),
            linha_pauta(12, 4, "Aprovada por Unanimidade", 104, "OFEX"),
            linha_pauta(12, 5, "Aprovada por Unanimidade", 105, "REQ"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), SESSOES, pauta, [registro(105, 12, True)])
            saida = gerar_na_base(tmp)
        self.assertEqual([materia["id"] for materia in saida["materias"]], [105])
        self.assertEqual(saida["status"], "aberta")

    def test_exclui_votacao_procedimental(self):
        pauta = [
            linha_pauta(12, 1, "Pedido de Vistas", 101, "PLEG"),
            linha_pauta(12, 2, "Adiada", 102, "PRE"),
            linha_pauta(12, 3, "Aprovada por Unanimidade", 103, "IND"),
        ]
        registros = [
            registro(101, 12, False),
            registro(103, 12, True),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), SESSOES, pauta, registros)
            saida = gerar_na_base(tmp)
        self.assertEqual([materia["id"] for materia in saida["materias"]], [103])

    def test_materia_repetida_entra_uma_vez(self):
        pauta = [
            linha_pauta(12, 2, "Aprovada por Unanimidade", 101, "REQ"),
            linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "REQ"),
            linha_pauta(12, 3, "Aprovada por Unanimidade", 102, "IND"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(
                Path(tmp),
                SESSOES,
                pauta,
                [registro(101, 12, True), registro(102, 12, True)],
            )
            saida = gerar_na_base(tmp)
        ids = [materia["id"] for materia in saida["materias"]]
        self.assertEqual(ids, [101, 102])
        self.assertEqual(len(ids), len(set(ids)))

    def test_ordem_da_pauta(self):
        pauta = [
            linha_pauta(12, 30, "Aprovada por Unanimidade", 101, "REQ"),
            linha_pauta(12, 10, "Aprovada por Unanimidade", 102, "IND"),
            linha_pauta(12, 20, "Aprovada por Unanimidade", 103, "MOC"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(
                Path(tmp),
                SESSOES,
                pauta,
                [
                    registro(101, 12, True),
                    registro(102, 12, True),
                    registro(103, 12, True),
                ],
            )
            saida = gerar_na_base(tmp)
        self.assertEqual(
            [materia["id"] for materia in saida["materias"]], [102, 103, 101]
        )
        self.assertEqual(
            [materia["ordem_pauta"] for materia in saida["materias"]], [10, 20, 30]
        )

    def test_sem_elegivel_registra_sem_materias(self):
        pauta = [linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "ATA")]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), SESSOES, pauta, [])
            saida = gerar_na_base(tmp)
        self.assertEqual(saida["status"], "sem_materias_elegiveis")
        self.assertEqual(saida["materias"], [])

    def test_nenhuma_chave_de_autor_partido_ou_vereador(self):
        pauta = [linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "REQ")]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), SESSOES, pauta, [registro(101, 12, True)])
            saida = gerar_na_base(tmp)
        self.assertEqual(chaves_proibidas(saida), [])

    def test_ementa_e_link_saem_como_estao_nos_dados(self):
        pauta = [linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "REQ")]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), SESSOES, pauta, [registro(101, 12, True)])
            saida = gerar_na_base(tmp)
        materia = saida["materias"][0]
        self.assertEqual(materia["ementa"], "Ementa oficial da materia 101.")
        self.assertEqual(materia["link_sapl"], "https://exemplo.invalid/materia/101")

    def test_idempotente_byte_a_byte(self):
        pauta = [linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "REQ")]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), SESSOES, pauta, [registro(101, 12, True)])
            raiz = Path(tmp)
            rodada.gerar(raiz)
            caminho = raiz / "dados" / "tratados" / "votacao_rodada.json"
            antes = caminho.read_bytes()
            rodada.gerar(raiz)
            depois = caminho.read_bytes()
        self.assertEqual(antes, depois)
        self.assertNotIn(b"\r", antes)
        self.assertTrue(antes.endswith(b"\n"))

    def test_fecha_ate_soma_os_dias_do_config(self):
        sessoes = [{"id": 12, "numero": 3, "data": "2026-03-10"}]
        pauta = [linha_pauta(12, 1, "Aprovada por Unanimidade", 101, "REQ")]
        with tempfile.TemporaryDirectory() as tmp:
            montar_base(Path(tmp), sessoes, pauta, [registro(101, 12, True)])
            saida = gerar_na_base(tmp)
        esperado = (date(2026, 3, 10) + timedelta(days=60)).isoformat()
        self.assertEqual(saida["fecha_ate"], esperado)


class TesteFormaNaBaseReal(unittest.TestCase):
    def test_rodada_real_tem_forma_valida(self):
        """So a forma: chaves, siglas permitidas e sem autor."""
        from config_cidade import carregar_config  # noqa: E402

        cfg = carregar_config()
        bloco = cfg.get("votacao_popular") or {}
        elegiveis = set(bloco.get("siglas_elegiveis") or [])
        excluidas = set(bloco.get("siglas_excluidas") or [])
        caminho = RAIZ / "dados" / "tratados" / "votacao_rodada.json"
        saida = json.loads(caminho.read_text(encoding="utf-8"))
        for chave in (
            "rodada_id",
            "sessao_id",
            "data_sessao",
            "status",
            "fecha_ate",
            "materias",
            "gerado_de",
        ):
            self.assertIn(chave, saida)
        self.assertIn(saida["status"], ("aberta", "sem_materias_elegiveis"))
        self.assertEqual(chaves_proibidas(saida), [])
        self.assertIsInstance(saida["materias"], list)
        for materia in saida["materias"]:
            self.assertIn(materia["sigla"], elegiveis)
            self.assertNotIn(materia["sigla"], excluidas)


if __name__ == "__main__":
    unittest.main()
