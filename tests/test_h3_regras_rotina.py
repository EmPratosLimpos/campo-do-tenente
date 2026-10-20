"""Testes da H3: a rotina semanal confere as regras sem a checagem de branch.

Nao dependem da branch real da maquina e nao abrem rede.
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "coletor"))

import atualizar_semana  # noqa: E402
import verificar_regras  # noqa: E402

LINHA_DISPENSA = (
    "Rotina semanal: checagem de branch dispensada; "
    "o workflow confere que so dados mudaram"
)


class TestConferirBranch(unittest.TestCase):
    def test_main_sem_opcao_e_violacao(self):
        erros = verificar_regras.conferir_branch("main")
        self.assertEqual(len(erros), 1)
        self.assertIn("VIOLACAO", erros[0])
        self.assertIn("main", erros[0])

    def test_main_com_opcao_nao_e_violacao_e_imprime_linha(self):
        saida = io.StringIO()
        with redirect_stdout(saida):
            erros = verificar_regras.conferir_branch("main", rotina_semanal=True)
        self.assertEqual(erros, [])
        self.assertIn(LINHA_DISPENSA, saida.getvalue())

    def test_outra_branch_sem_violacao_nos_dois_casos(self):
        for rotina in (False, True):
            with self.subTest(rotina_semanal=rotina):
                saida = io.StringIO()
                with redirect_stdout(saida):
                    erros = verificar_regras.conferir_branch(
                        "EmPratosLimpos/h3-regras-rotina", rotina_semanal=rotina
                    )
                self.assertEqual(erros, [])
                self.assertNotIn(LINHA_DISPENSA, saida.getvalue())


class TestChamadaDaRotina(unittest.TestCase):
    def test_atualizar_semana_chama_verificar_regras_com_a_opcao(self):
        with mock.patch.object(atualizar_semana, "rodar") as rodar:
            atualizar_semana.verificar_regras_da_rotina()
        rodar.assert_called_once()
        argumentos = rodar.call_args.args[0]
        self.assertEqual(argumentos[0], "scripts/verificar_regras.py")
        self.assertIn("--rotina-semanal", argumentos)

    def test_workflow_semanal_chama_verificar_regras_com_a_opcao(self):
        workflow = RAIZ / ".github" / "workflows" / "atualizacao_semanal.yml"
        chamadas = [
            linha
            for linha in workflow.read_text(encoding="utf-8").splitlines()
            if "verificar_regras.py" in linha
        ]
        self.assertTrue(chamadas)
        for linha in chamadas:
            with self.subTest(linha=linha.strip()):
                self.assertIn("--rotina-semanal", linha)


if __name__ == "__main__":
    unittest.main()
