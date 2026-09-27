"""Testes da atualizacao semanal. Nao fazem pedido ao SAPL."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

from atualizar_semana import (  # noqa: E402
    TETO_EXECUCAO,
    OrcamentoExecucao,
    ano_corrente_candidato,
    anos_da_execucao,
    confirmar_sessao_ordinaria_no_ano,
    incluir_ano_se_confirmado,
    inserir_entrada,
    linhas_contagem,
    montar_entrada,
)
from coletar_lote import ColetorLote, OrcamentoEsgotado  # noqa: E402

CFG_COLETOR = {
    "cidade": {"nome": "Cidade Teste", "uf": "PR"},
    "sapl": {"endereco_base": "https://exemplo.invalid"},
}
CORPO = b'{"pagination":{"total_pages":1},"results":[]}'


class Resposta:
    status = 200

    def __init__(self, corpo: bytes):
        self.corpo = corpo

    def read(self) -> bytes:
        return self.corpo

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def cfg_anos(anos, inicio, fim) -> dict:
    return {
        "recorte": {"anos": anos},
        "sapl": {"legislatura_inicio": inicio, "legislatura_fim": fim},
    }


class TestesAnos(unittest.TestCase):
    def test_ano_corrente_nao_entra_sem_confirmacao(self):
        cfg = cfg_anos([2025], 2025, 2028)
        self.assertEqual(anos_da_execucao(cfg, date(2026, 9, 27)), [2025])
        self.assertEqual(ano_corrente_candidato(cfg, date(2026, 9, 27)), 2026)

    def test_ano_fora_da_legislatura_nao_entra(self):
        cfg = cfg_anos([2025], 2025, 2028)
        self.assertEqual(anos_da_execucao(cfg, date(2024, 1, 1)), [2025])
        self.assertEqual(anos_da_execucao(cfg, date(2029, 6, 1)), [2025])
        self.assertIsNone(ano_corrente_candidato(cfg, date(2024, 1, 1)))
        self.assertIsNone(ano_corrente_candidato(cfg, date(2029, 6, 1)))

    def test_ano_que_ja_esta_no_config_nao_repete(self):
        cfg = cfg_anos([2025, 2026], 2025, 2028)
        self.assertEqual(anos_da_execucao(cfg, date(2026, 9, 27)), [2025, 2026])
        self.assertIsNone(ano_corrente_candidato(cfg, date(2026, 9, 27)))

    def test_simulado_nao_consulta_e_nao_acrescenta(self):
        cfg = cfg_anos([2025], 2025, 2028)
        chamadas = []

        def confirmar(ano):
            chamadas.append(ano)
            return True

        anos, mudou = incluir_ano_se_confirmado(cfg, date(2027, 1, 2), True, confirmar)
        self.assertEqual(anos, [2025])
        self.assertFalse(mudou)
        self.assertEqual(chamadas, [])

    def test_sem_sessao_ordinaria_nao_acrescenta(self):
        cfg = cfg_anos([2025], 2025, 2028)
        anos, mudou = incluir_ano_se_confirmado(
            cfg, date(2027, 3, 1), False, lambda _ano: False
        )
        self.assertEqual(anos, [2025])
        self.assertFalse(mudou)

    def test_sessao_ordinaria_confirmada_acrescenta_o_ano(self):
        cfg = cfg_anos([2025], 2025, 2028)
        anos, mudou = incluir_ano_se_confirmado(
            cfg, date(2027, 3, 1), False, lambda _ano: True
        )
        self.assertEqual(anos, [2025, 2027])
        self.assertTrue(mudou)

    def test_um_pedido_com_pausa_confirma_sessao_ordinaria(self):
        dormiu = []
        chamadas = []
        corpo = json.dumps(
            {
                "pagination": {"total_entries": 1, "total_pages": 1},
                "results": [{"id": 10, "tipo": 3, "data_inicio": "2027-02-01"}],
            }
        ).encode("utf-8")

        def urlopen(req, timeout=None):
            del timeout
            chamadas.append(req.full_url)
            return Resposta(corpo)

        with tempfile.TemporaryDirectory() as tmp:
            coletor = ColetorLote(CFG_COLETOR, Path(tmp), teto=10)
            coletor.pular_pausa = False
            with mock.patch("coletar_lote.time.sleep", dormiu.append), mock.patch(
                "coletar_lote.urllib.request.urlopen", urlopen
            ):
                ok = confirmar_sessao_ordinaria_no_ano(coletor, 2027, 3)
        self.assertTrue(ok)
        self.assertEqual(len(chamadas), 1)
        self.assertIn("data_inicio__year=2027", chamadas[0])
        self.assertIn("tipo=3", chamadas[0])
        self.assertIn("page_size=1", chamadas[0])
        self.assertEqual(dormiu, [2.5])

    def test_resposta_sem_ordinaria_nao_confirma(self):
        corpo = json.dumps(
            {
                "pagination": {"total_entries": 1, "total_pages": 1},
                "results": [{"id": 11, "tipo": 9, "data_inicio": "2027-02-01"}],
            }
        ).encode("utf-8")

        def urlopen(req, timeout=None):
            del req, timeout
            return Resposta(corpo)

        with tempfile.TemporaryDirectory() as tmp:
            coletor = ColetorLote(CFG_COLETOR, Path(tmp), teto=10)
            coletor.pular_pausa = False
            with mock.patch("coletar_lote.time.sleep", lambda _segundos: None), mock.patch(
                "coletar_lote.urllib.request.urlopen", urlopen
            ):
                ok = confirmar_sessao_ordinaria_no_ano(coletor, 2027, 3)
        self.assertFalse(ok)


class TestesOrcamento(unittest.TestCase):
    def test_teto_acima_de_400_e_recusado(self):
        with self.assertRaises(ValueError):
            OrcamentoExecucao(TETO_EXECUCAO + 1)

    def test_pausa_entre_pedidos_e_teto_da_execucao(self):
        dormiu = []

        def dormir(segundos):
            dormiu.append(segundos)

        chamadas = {"n": 0}

        def urlopen(*_args, **_kwargs):
            chamadas["n"] += 1
            return Resposta(CORPO)

        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            for nome in ("um.json", "dois.json"):
                (pasta / nome).write_bytes(CORPO)
            orcamento = OrcamentoExecucao(2)
            coletor = ColetorLote(CFG_COLETOR, pasta, teto=10)
            coletor.orcamento_execucao = orcamento
            with mock.patch("coletar_lote.time.sleep", dormir), mock.patch(
                "coletar_lote.urllib.request.urlopen", urlopen
            ):
                coletor.pedir("/api/um/", None, "um.json", refrescar=True)
                coletor.pedir("/api/dois/", None, "dois.json", refrescar=True)
                with self.assertRaises(OrcamentoEsgotado):
                    coletor.pedir("/api/tres/", None, "tres.json", refrescar=True)
            self.assertEqual(chamadas["n"], 2)
            self.assertEqual(dormiu, [2.5])
            self.assertFalse(coletor.gravou)
            self.assertFalse((pasta / "indice.json").exists())
            self.assertEqual((pasta / "um.json").read_bytes(), CORPO)


class TestesChangelog(unittest.TestCase):
    def test_entrada_usa_os_numeros_recebidos(self):
        entrada = montar_entrada(
            "2026-09-27",
            "https://exemplo.invalid",
            12,
            [{"id": 81, "numero": 40, "data_inicio": "2026-09-20"}],
            ["2026: votações de 10 para 12."],
            ["Hash SHA-256 de atuacao_vereadores_2026.json: abc."],
        )
        self.assertIn("Pedidos ao SAPL nesta execução: 12.", entrada)
        self.assertIn("Sessão ordinária 40, data 2026-09-20 (registro 81).", entrada)
        self.assertIn("votações de 10 para 12.", entrada)
        self.assertNotIn("\u2014", entrada)
        self.assertNotIn("\u2013", entrada)
        texto = "# Registro\n\n---\n\n## 2026-09-01: antiga\n"
        novo = inserir_entrada(texto, entrada)
        self.assertLess(novo.index("atualização semanal"), novo.index("2026-09-01: antiga"))

    def test_contagem_so_lista_o_que_mudou(self):
        linhas = linhas_contagem(
            {"2026": {"sessoes_ordinarias": 33, "votacoes": 10}},
            {"2026": {"sessoes_ordinarias": 33, "votacoes": 12}},
        )
        self.assertEqual(linhas, ["2026: votações de 10 para 12."])


class TestesWorkflow(unittest.TestCase):
    def test_workflows_nao_usam_node_20_nem_ubuntu_latest(self):
        pasta = RAIZ / ".github" / "workflows"
        for caminho in pasta.glob("*.yml"):
            texto = caminho.read_text(encoding="utf-8")
            self.assertNotIn("ubuntu-latest", texto, caminho.name)
            self.assertIn("ubuntu-24.04", texto, caminho.name)
            self.assertNotIn("actions/checkout@v4", texto, caminho.name)
            self.assertNotIn("actions/setup-python@v5", texto, caminho.name)
            self.assertIn("actions/checkout@v7", texto, caminho.name)
            self.assertIn("actions/setup-python@v7", texto, caminho.name)
        novo = (pasta / "atualizacao_semanal.yml").read_text(encoding="utf-8")
        self.assertNotIn("\u2014", novo)
        self.assertNotIn("\u2013", novo)

    def test_atualizacao_semanal_abre_pr_publico_sem_merge(self):
        texto = (RAIZ / ".github" / "workflows" / "atualizacao_semanal.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '0 6 * * 1'", texto)
        self.assertIn("workflow_dispatch:", texto)
        self.assertIn("contents: write", texto)
        self.assertIn("pull-requests: write", texto)
        self.assertIn("--base desenvolvimento", texto)
        self.assertIn("atualizacao-dados/", texto)
        self.assertIn("334360115+EmPratosLimpos@users.noreply.github.com", texto)
        self.assertIn('user.name "EmPratosLimpos"', texto)
        self.assertNotIn("pr merge", texto)
        self.assertNotIn("push --force", texto)
        self.assertNotIn("pull_request:", texto)

    def test_script_nao_fixa_cidade_nem_ano(self):
        texto = (RAIZ / "scripts" / "atualizar_semana.py").read_text(encoding="utf-8")
        self.assertNotIn("campodotenente", texto)
        self.assertNotIn("Campo do Tenente", texto)
        self.assertNotIn("[2025", texto)
        self.assertNotIn("[2026", texto)
        self.assertNotIn("\u2014", texto)
        self.assertNotIn("\u2013", texto)


class TesteSimulado(unittest.TestCase):
    def test_simulado_nao_altera_nada_quando_nao_ha_dado_novo(self):
        def porcelana() -> str:
            resultado = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=RAIZ,
                capture_output=True,
                text=True,
                check=True,
            )
            return resultado.stdout

        antes = porcelana()
        resultado = subprocess.run(
            [sys.executable, str(RAIZ / "scripts" / "atualizar_semana.py"), "--simulado"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        self.assertEqual(resultado.returncode, 0, resultado.stdout + "\n" + resultado.stderr)
        self.assertIn("Pedidos nesta execucao: 0", resultado.stdout)
        self.assertIn("Sessoes ordinarias novas: 0", resultado.stdout)
        self.assertIn("Nada mudou.", resultado.stdout)
        self.assertNotIn("pedido de rede bloqueado", resultado.stdout + resultado.stderr)
        self.assertEqual(porcelana(), antes)


if __name__ == "__main__":
    unittest.main()
