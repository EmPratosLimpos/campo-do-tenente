"""Worker da votacao popular: dados gerados atualizados e suite node verde.

Sem rede, sem segredo, sem escrita fora de cloudflare-worker/.
O teste da suite node usa valores falsos gerados no proprio teste e
pula com aviso quando o node nao existe na maquina.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_WORKER = RAIZ / "cloudflare-worker"


class TestWorkerVotacao(unittest.TestCase):
    def test_dados_cidade_atualizados(self):
        gerador = PASTA_WORKER / "gerar_dados_worker.py"
        self.assertTrue(gerador.is_file(), "gerar_dados_worker.py ausente")
        proc = subprocess.run(
            [sys.executable, str(gerador), "--check"],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            "src/dados_cidade.js desatualizado em relacao ao config ou "
            f"ao contorno. Rode python cloudflare-worker/gerar_dados_worker.py. "
            f"Saida: {proc.stdout} {proc.stderr}",
        )

    def test_suite_node_do_worker(self):
        if shutil.which("node") is None:
            self.skipTest("node nao existe nesta maquina, suite do Worker pulada")
        arquivos = sorted((PASTA_WORKER / "test").glob("*.test.js"))
        self.assertTrue(arquivos, "sem arquivos de teste em cloudflare-worker/test")
        proc = subprocess.run(
            ["node", "--test", *(str(a) for a in arquivos)],
            cwd=RAIZ,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"suite node do Worker falhou:\n{proc.stdout}\n{proc.stderr}",
        )
        self.assertIn("fail 0", proc.stdout)

    def test_schema_com_triggers_atomicos(self):
        schema = (PASTA_WORKER / "schema.sql").read_text(encoding="utf-8")
        self.assertIn("trg_vp_teto_endereco", schema)
        self.assertIn("RAISE(ABORT, 'teto_endereco')", schema)
        self.assertIn("trg_vp_autorizacao_uso_unico", schema)
        self.assertIn("RAISE(ABORT, 'autorizacao_reutilizada')", schema)
        self.assertIn("vp_config", schema)
        self.assertIn("trg_vp_participacao_autorizacao", schema)
        self.assertIn("RAISE(ABORT, 'autorizacao_invalida')", schema)
        self.assertIn("COALESCE(", schema)
        self.assertIn("jti TEXT NOT NULL", schema)

    def test_chave_do_teto_em_um_lugar_so_no_codigo(self):
        fonte = (PASTA_WORKER / "src" / "index.js").read_text(encoding="utf-8")
        self.assertIn('const CHAVE_TETO = "teto_votos_por_endereco_por_rodada"', fonte)
        self.assertEqual(
            fonte.count('"teto_votos_por_endereco_por_rodada"'),
            1,
            "chave do teto repetida no codigo, use CHAVE_TETO",
        )
        schema = (PASTA_WORKER / "schema.sql").read_text(encoding="utf-8")
        self.assertIn("chave = 'teto_votos_por_endereco_por_rodada'", schema)

    def test_wrangler_sem_segredo_e_com_dois_ambientes(self):
        toml = (PASTA_WORKER / "wrangler.toml").read_text(encoding="utf-8")
        for ambiente in ("[env.teste]", "[env.producao]"):
            self.assertIn(ambiente, toml)
        for segredo in ("HMAC_SECRET", "TURNSTILE_SECRET_KEY", "MODO_TESTE_SECRETO"):
            self.assertNotIn(segredo, toml)
        self.assertIn("PREENCHER_NA_PARADA_2", toml)


if __name__ == "__main__":
    unittest.main()
