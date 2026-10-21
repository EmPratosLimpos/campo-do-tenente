"""Testes da H5: disparo manual com forcar pula a trava da semana.

Leem o workflow como texto, sem PyYAML e sem rede.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOW = RAIZ / ".github" / "workflows" / "atualizacao_semanal.yml"

CRONS_ESPERADOS = [
    "- cron: '0 13 * * 3'",
    "- cron: '0 19 * * 3'",
    "- cron: '0 13 * * 4'",
]


def _indentacao(linha: str) -> int:
    return len(linha) - len(linha.lstrip(" "))


def _bloco(linhas, indice, indentacao_pai):
    """Linhas seguintes mais indentadas que a linha pai."""
    inicio = indice + 1
    fim = inicio
    while fim < len(linhas):
        linha = linhas[fim]
        if linha.strip() and _indentacao(linha) <= indentacao_pai:
            break
        fim += 1
    return linhas[inicio:fim]


def _blocos_run(linhas):
    blocos = []
    for indice, linha in enumerate(linhas):
        if re.match(r"^\s*run:\s*\|", linha):
            blocos.append(
                "\n".join(_bloco(linhas, indice, _indentacao(linha)))
            )
    return blocos


class TestDisparoManualComForcar(unittest.TestCase):
    def setUp(self):
        self.linhas = WORKFLOW.read_text(encoding="utf-8").splitlines()

    def _indice(self, texto, indentacao=None):
        for indice, linha in enumerate(self.linhas):
            if linha.strip() == texto and (
                indentacao is None or _indentacao(linha) == indentacao
            ):
                return indice
        self.fail(f"Linha nao encontrada no workflow: {texto}")

    def _gatilho_manual(self):
        indice = self._indice("workflow_dispatch:", 2)
        return _bloco(self.linhas, indice, 2)

    def _passo_da_trava(self):
        indice = self._indice("- name: Ver se a semana ja foi publicada", 6)
        return _bloco(self.linhas, indice, 6)

    def test_input_forcar_existe_com_boolean_e_default_false(self):
        gatilho = self._gatilho_manual()
        indices = [
            i for i, linha in enumerate(gatilho)
            if linha.strip() == "forcar:"
        ]
        self.assertEqual(len(indices), 1)
        indice = indices[0]
        indentacao = _indentacao(gatilho[indice])
        opcoes = {}
        for linha in _bloco(gatilho, indice, indentacao):
            if ":" in linha:
                chave, valor = linha.strip().split(":", 1)
                opcoes[chave] = valor.strip().strip("'\"")
        self.assertEqual(opcoes.get("type"), "boolean")
        self.assertEqual(opcoes.get("default").lower(), "false")

    def test_passo_da_trava_recebe_forcar_por_env(self):
        passo = self._passo_da_trava()
        indices = [
            i for i, linha in enumerate(passo) if linha.strip() == "env:"
        ]
        self.assertEqual(len(indices), 1)
        env = _bloco(passo, indices[0], _indentacao(passo[indices[0]]))
        linhas_forcar = [
            linha for linha in env if linha.strip().startswith("FORCAR:")
        ]
        self.assertEqual(len(linhas_forcar), 1)
        valor = linhas_forcar[0]
        self.assertIn("github.event_name == 'workflow_dispatch'", valor)
        self.assertIn("inputs.forcar", valor)

    def test_run_testa_forcar_antes_do_git_log(self):
        passo = self._passo_da_trava()
        indices = [
            i for i, linha in enumerate(passo)
            if re.match(r"^\s*run:\s*\|", linha)
        ]
        self.assertEqual(len(indices), 1)
        corpo = "\n".join(
            _bloco(passo, indices[0], _indentacao(passo[indices[0]]))
        )
        self.assertIn('"$FORCAR" == "true"', corpo)
        self.assertLess(corpo.index('"$FORCAR"'), corpo.index("git log"))
        self.assertIn('echo "ja=false"', corpo)
        self.assertIn("Disparo manual com forcar: trava da semana pulada.", corpo)

    def test_nenhum_run_interpola_inputs_forcar(self):
        for corpo in _blocos_run(self.linhas):
            self.assertNotIn("${{ inputs.forcar }}", corpo)

    def test_os_tres_cron_continuam_presentes(self):
        crons = [
            linha.strip()
            for linha in self.linhas
            if linha.strip().startswith("- cron:")
        ]
        self.assertEqual(crons, CRONS_ESPERADOS)

    def test_forcar_nao_aparece_no_schedule(self):
        indice = self._indice("schedule:", 2)
        agendamento = "\n".join(_bloco(self.linhas, indice, 2))
        self.assertNotIn("forcar", agendamento)


if __name__ == "__main__":
    unittest.main()
