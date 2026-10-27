"""C5: sessao nova sem presenca lancada fica para a proxima execucao.

Sem pedido ao SAPL. O coletor e falso e grava as paginas em pasta
temporaria. Hoje e injetado no teste, nunca lido do relogio.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "coletor"))
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "tests"))

import atualizar_semana as rotina  # noqa: E402
import coletar_por_sessao as ps  # noqa: E402
from config_cidade import carregar_config  # noqa: E402
from derivar_insumos import derivar  # noqa: E402
from test_insumos import materializar, pagina  # noqa: E402

HOJE = date(2026, 10, 27)
LIMITE = int(carregar_config()["coleta"]["dias_max_espera_presenca"])


class ColetorFalso:
    """Grava a pagina no disco como o coletor real, sem abrir rede."""

    def __init__(
        self,
        pasta: Path,
        presenca: int = 0,
        ordem: list | None = None,
        registros: dict | None = None,
        votos: dict | None = None,
    ):
        self.pasta = pasta
        self.presenca = presenca
        self.ordem = list(ordem or [])
        self.registros = dict(registros or {})
        self.votos = dict(votos or {})

    def pedir(self, caminho, params, arquivo, refrescar=False):
        del refrescar
        if caminho == ps.CAMINHO_REGISTRO:
            linhas = list(self.registros.get(int(params.get("ordem")), []))
        elif caminho == ps.CAMINHO_VOTO:
            linhas = list(self.votos.get(int(params.get("votacao")), []))
        else:
            sid = int(params.get("sessao_plenaria"))
            if caminho == ps.CAMINHO_MESA:
                linhas = []
            elif "sessaoplenariapresenca" in caminho:
                linhas = (
                    [{"id": 900 + sid, "sessao_plenaria": sid}]
                    if self.presenca
                    else []
                )
            elif "presencaordemdia" in caminho:
                linhas = (
                    [{"id": 910 + sid, "sessao_plenaria": sid}]
                    if self.presenca
                    else []
                )
            elif "ordemdia" in caminho:
                linhas = list(self.ordem)
            else:
                linhas = []
        dado = pagina(linhas)
        (self.pasta / arquivo).write_text(
            json.dumps(dado), encoding="utf-8"
        )
        return dado


def _aviso(pasta: Path, sid: int) -> Path:
    return pasta / f"sessao_{sid}_adiada.json"


def _recusada(pasta: Path, sid: int) -> Path:
    return pasta / f"sessao_{sid}_recusada.json"


class TestAdiamentoDaSessaoNova(unittest.TestCase):
    def test_presenca_zerada_recente_adia_e_restaura_arquivos_previos(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            antigo = pasta / "sessao_276_ordemdia_p1.json"
            antigo.write_bytes(b"ORDEM ANTIGA")
            coletor = ColetorFalso(
                pasta,
                presenca=0,
                ordem=[{"id": 10, "sessao_plenaria": 276}],
            )
            saida = io.StringIO()
            with mock.patch.object(ps, "hoje_na_cidade", return_value=HOJE):
                with contextlib.redirect_stdout(saida):
                    resumo = ps.coletar_sessao_completa(
                        coletor,
                        276,
                        e_nova=True,
                        numero=36,
                        data_inicio=HOJE.isoformat(),
                    )
            self.assertTrue(resumo["adiada"])
            self.assertEqual(resumo["recurso"], "sessaoplenariapresenca")
            self.assertEqual(antigo.read_bytes(), b"ORDEM ANTIGA")
            self.assertFalse(
                (pasta / "sessao_276_sessaoplenariapresenca_p1.json").exists()
            )
            self.assertFalse(_recusada(pasta, 276).exists())
            aviso = json.loads(_aviso(pasta, 276).read_text(encoding="utf-8"))
            self.assertEqual(aviso["sessao_id"], 276)
            self.assertEqual(aviso["recurso"], "sessaoplenariapresenca")
            self.assertEqual(aviso["data_inicio"], HOJE.isoformat())
            self.assertEqual(aviso["data_execucao"], HOJE.isoformat())
            self.assertIn("presenca ainda nao foi lancada", aviso["motivo"])
            self.assertIn(
                "sessao 276 numero 36 de 2026-10-27 sem presenca lancada "
                "no SAPL: fica para a proxima execucao",
                saida.getvalue(),
            )

    def test_presenca_zerada_mais_antiga_que_o_limite_continua_recusada(self):
        data_antiga = (HOJE - timedelta(days=LIMITE + 1)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = ColetorFalso(pasta, presenca=0)
            with mock.patch.object(ps, "hoje_na_cidade", return_value=HOJE):
                with self.assertRaises(SystemExit) as ctx:
                    ps.coletar_sessao_completa(
                        coletor,
                        277,
                        e_nova=True,
                        numero=37,
                        data_inicio=data_antiga,
                    )
            self.assertIn("sessao 277 recusada", str(ctx.exception))
            self.assertTrue(_recusada(pasta, 277).is_file())
            self.assertFalse(_aviso(pasta, 277).exists())

    def test_no_limite_de_dias_ainda_adia(self):
        data_limite = (HOJE - timedelta(days=LIMITE)).isoformat()
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = ColetorFalso(pasta, presenca=0)
            with mock.patch.object(ps, "hoje_na_cidade", return_value=HOJE):
                resumo = ps.coletar_sessao_completa(
                    coletor,
                    278,
                    e_nova=True,
                    numero=38,
                    data_inicio=data_limite,
                )
            self.assertTrue(resumo["adiada"])
            self.assertTrue(_aviso(pasta, 278).is_file())

    def test_ordem_com_itens_e_zero_registros_continua_recusando(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = ColetorFalso(
                pasta,
                presenca=1,
                ordem=[{"id": 10, "sessao_plenaria": 279}],
            )
            with mock.patch.object(ps, "hoje_na_cidade", return_value=HOJE):
                with self.assertRaises(SystemExit) as ctx:
                    ps.coletar_sessao_completa(
                        coletor,
                        279,
                        e_nova=True,
                        numero=39,
                        data_inicio=HOJE.isoformat(),
                    )
            self.assertIn("zero registros", str(ctx.exception))
            self.assertTrue(_recusada(pasta, 279).is_file())

    def test_registros_sem_votos_continua_recusando(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = ColetorFalso(
                pasta,
                presenca=1,
                ordem=[{"id": 10, "sessao_plenaria": 280}],
                registros={10: [{"id": 700}]},
            )
            with mock.patch.object(ps, "hoje_na_cidade", return_value=HOJE):
                with self.assertRaises(SystemExit) as ctx:
                    ps.coletar_sessao_completa(
                        coletor,
                        280,
                        e_nova=True,
                        numero=40,
                        data_inicio=HOJE.isoformat(),
                    )
            self.assertIn("zero votos", str(ctx.exception))
            self.assertTrue(_recusada(pasta, 280).is_file())

    def test_aviso_some_quando_a_sessao_vem_completa_depois(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            aviso = _aviso(pasta, 281)
            aviso.write_text('{"sessao_id": 281}', encoding="utf-8")
            coletor = ColetorFalso(
                pasta,
                presenca=1,
                ordem=[{"id": 10, "sessao_plenaria": 281}],
                registros={10: [{"id": 700}]},
                votos={700: [{"id": 800, "votacao": 700, "parlamentar": 5}]},
            )
            with mock.patch.object(ps, "hoje_na_cidade", return_value=HOJE):
                resumo = ps.coletar_sessao_completa(
                    coletor,
                    281,
                    e_nova=True,
                    numero=41,
                    data_inicio=HOJE.isoformat(),
                )
            self.assertFalse(resumo.get("adiada"))
            self.assertFalse(aviso.exists())
            self.assertTrue(
                (pasta / "sessao_281_ordemdia_p1.json").is_file()
            )


def _pagina_por_sessao(pasta: Path, sid: int, recurso: str, linhas: list) -> None:
    (pasta / f"sessao_{sid}_{recurso}_p1.json").write_text(
        json.dumps(pagina(linhas)), encoding="utf-8"
    )


class TestDerivacaoSemSessaoAdiada(unittest.TestCase):
    def test_adiada_fica_fora_e_a_valida_segue(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            lote = raiz / "lote_minimo"
            lote.mkdir()
            materializar(lote)
            por_sessao = raiz / "porsessao"
            por_sessao.mkdir()
            _pagina_por_sessao(
                por_sessao,
                4,
                "sessaoplenariapresenca",
                [{"id": 1, "sessao_plenaria": 4, "parlamentar": 8}],
            )
            _pagina_por_sessao(
                por_sessao,
                4,
                "presencaordemdia",
                [{"id": 1, "sessao_plenaria": 4, "parlamentar": 8}],
            )
            _pagina_por_sessao(
                por_sessao,
                4,
                "ordemdia",
                [
                    {
                        "id": 10,
                        "sessao_plenaria": 4,
                        "materia": 9,
                        "resultado": "Aprovada por Maioria Absoluta",
                        "numero_ordem": 3,
                    }
                ],
            )
            _pagina_por_sessao(
                por_sessao,
                4,
                "justificativaausencia",
                [{"id": 1, "sessao_plenaria": 4, "parlamentar": 1}],
            )
            _aviso(por_sessao, 37).write_text(
                json.dumps(
                    {
                        "sessao_id": 37,
                        "motivo": "sessao nova sem presenca lancada",
                        "recurso": "sessaoplenariapresenca",
                        "data_inicio": "2026-02-10",
                        "data_execucao": HOJE.isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            saida = raiz / "saida"
            resumo = derivar(
                lote,
                saida,
                [2025, 2026],
                3,
                1,
                pasta_porsessao=por_sessao,
            )
            self.assertEqual(resumo["contagens"]["2025"]["sessoes_ordinarias"], 1)
            self.assertEqual(resumo["contagens"]["2026"]["sessoes_ordinarias"], 0)
            self.assertTrue((saida / "sessao_4_ordemdia.json").is_file())
            self.assertEqual(list(saida.glob("sessao_37_*")), [])


class TestRotinaComSessaoAdiada(unittest.TestCase):
    def test_coleta_registra_a_adiada_no_conjunto(self):
        adiadas = set()
        with mock.patch.object(
            rotina,
            "coletar_sessao_completa",
            return_value={"sessao_id": 7, "adiada": True},
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                devolvido = rotina.coletar_sessoes_novas(
                    object(),
                    [{"id": 7, "numero": 1, "data_inicio": HOJE.isoformat()}],
                    None,
                    {7},
                    adiadas,
                )
        self.assertEqual(devolvido, {7})
        self.assertEqual(adiadas, {7})

    def test_listas_da_execucao_perdem_a_adiada(self):
        novas = [{"id": 7}, {"id": 8}]
        alvo = [{"id": 7}, {"id": 8}, {"id": 9}]
        coletaveis = [{"id": 7}, {"id": 8}, {"id": 9}]
        novas, alvo, coletaveis = rotina.remover_sessoes_adiadas(
            novas, alvo, coletaveis, {7}
        )
        self.assertEqual([item["id"] for item in novas], [8])
        self.assertEqual([item["id"] for item in alvo], [8, 9])
        self.assertEqual([item["id"] for item in coletaveis], [8, 9])

    def test_resumo_lista_as_adiadas_em_ordem(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            rotina.resumo_sessoes_adiadas({9, 7, 8})
        self.assertIn(
            "Sessoes ordinarias adiadas por falta de presenca: 3 (7, 8, 9)",
            saida.getvalue(),
        )
        self.assertEqual(saida.getvalue().count("\n"), 1)


if __name__ == "__main__":
    unittest.main()
