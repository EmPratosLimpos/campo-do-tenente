"""Sessao ordinaria futura fica fora da coleta. Sem pedido ao SAPL.

Hoje e injetado no teste, nunca lido do relogio. A sessao de amanha sai
do alvo com a linha no log. A de hoje continua no alvo, inclusive com a
recusa por presenca zerada. O piso de sessoes segue conferido na lista
inteira, antes do corte.
"""

from __future__ import annotations

import ast
import builtins
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "coletor"))

from calendario import data_da_sessao  # noqa: E402
from coletar_por_sessao import (  # noqa: E402
    coletar_sessao_completa,
    exigir_minimo_de_sessoes,
    sessoes_desta_execucao,
)

HOJE = date(2026, 10, 19)


def cfg_piso(piso: int, ano: int = 2026) -> dict:
    return {
        "recorte": {"anos": [ano]},
        "pisos_sanidade": {
            "por_ano": {
                str(ano): {
                    "vereadores": 1,
                    "sessoes_ordinarias": piso,
                    "projetos_lei_legislativo_e_executivo": 1,
                }
            }
        },
    }


def sessoes_de_teste() -> list[dict]:
    return [
        {"id": 275, "numero": 35, "data_inicio": "2026-10-18"},
        {"id": 276, "numero": 36, "data_inicio": "2026-10-19"},
        {"id": 277, "numero": 37, "data_inicio": "2026-10-20"},
    ]


def pagina(total: int, linhas: list, sessao_id: int) -> dict:
    return {
        "pagination": {
            "total_entries": total,
            "total_pages": 1,
            "page": 1,
            "links": {"next": None, "previous": None},
            "next_page": None,
        },
        "results": linhas,
    }


class ColetorFalso:
    """Grava a pagina 1 no disco como o coletor real, sem abrir rede."""

    def __init__(self, pasta: Path, sid: int):
        self.pasta = pasta
        self.sid = sid

    def pedir(self, _caminho, _params, arquivo, refrescar=False):
        if "_sessaoplenariapresenca_" in arquivo or "_presencaordemdia_" in arquivo:
            dados = pagina(0, [], self.sid)
        else:
            dados = pagina(1, [{"id": 1, "sessao_plenaria": self.sid}], self.sid)
        (self.pasta / arquivo).write_text(
            json.dumps(dados), encoding="utf-8"
        )
        return dados


class TestSessaoFuturaFicaFora(unittest.TestCase):
    def test_amanha_sai_do_alvo_com_linha_no_log(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            vigentes, futuras = sessoes_desta_execucao(sessoes_de_teste(), HOJE)
        self.assertEqual([item["id"] for item in vigentes], [275, 276])
        self.assertEqual([item["id"] for item in futuras], [277])
        log = saida.getvalue()
        self.assertIn(
            "sessao 277 numero 37 de 2026-10-20 ainda nao aconteceu: "
            "fica para a proxima execucao",
            log,
        )

    def test_hoje_continua_no_alvo(self):
        vigentes, futuras = sessoes_desta_execucao(sessoes_de_teste(), HOJE)
        self.assertIn(276, [item["id"] for item in vigentes])
        self.assertNotIn(276, [item["id"] for item in futuras])

    def test_data_invalida_continua_no_alvo(self):
        sessoes = [{"id": 900, "numero": 99, "data_inicio": "data errada"}]
        self.assertIsNone(data_da_sessao(sessoes[0]))
        vigentes, futuras = sessoes_desta_execucao(sessoes, HOJE)
        self.assertEqual([item["id"] for item in vigentes], [900])
        self.assertEqual(futuras, [])

    def test_hoje_com_presenca_zerada_fica_adiada(self):
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            coletor = ColetorFalso(pasta, 276)
            with mock.patch(
                "coletar_por_sessao.hoje_na_cidade", return_value=HOJE
            ):
                resumo = coletar_sessao_completa(
                    coletor,
                    276,
                    e_nova=True,
                    numero=36,
                    data_inicio=HOJE.isoformat(),
                )
            self.assertTrue(resumo["adiada"])
            self.assertTrue((pasta / "sessao_276_adiada.json").is_file())
            self.assertFalse((pasta / "sessao_276_recusada.json").exists())

    def test_piso_continua_conferido_na_lista_inteira(self):
        cheia = sessoes_de_teste()
        exigir_minimo_de_sessoes(cheia, cfg_piso(3))
        vigentes, _futuras = sessoes_desta_execucao(cheia, HOJE)
        with self.assertRaises(SystemExit) as ctx:
            exigir_minimo_de_sessoes(vigentes, cfg_piso(3))
        self.assertIn("2026: piso 3, achei 2", str(ctx.exception))


def _nomes_do_modulo(arvore: ast.Module) -> set[str]:
    """Nomes que o modulo define no escopo global: imports, defs e atribuicoes."""
    definidos: set[str] = set()
    for no in arvore.body:
        if isinstance(no, ast.Import):
            for apelido in no.names:
                definidos.add((apelido.asname or apelido.name).split(".")[0])
        elif isinstance(no, ast.ImportFrom):
            for apelido in no.names:
                definidos.add(apelido.asname or apelido.name)
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            definidos.add(no.name)
        elif isinstance(no, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
            for alvo in alvos:
                for nome in ast.walk(alvo):
                    if isinstance(nome, ast.Name):
                        definidos.add(nome.id)
    return definidos


def _nomes_locais(no_funcao: ast.AST) -> set[str]:
    """Nomes que a funcao amarra: args, atribuicoes, for, with, except e defs."""
    locais: set[str] = set()
    for no in ast.walk(no_funcao):
        if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store):
            locais.add(no.id)
        elif isinstance(no, ast.arg):
            locais.add(no.arg)
        elif isinstance(no, ast.ExceptHandler) and no.name:
            locais.add(no.name)
        elif isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            locais.add(no.name)
    return locais


def nomes_indefinidos_em_main(fonte: str) -> set[str]:
    """Nomes usados no main que nao sao locais, builtins nem do modulo."""
    arvore = ast.parse(fonte)
    definidos_no_modulo = _nomes_do_modulo(arvore)
    main = next(
        no
        for no in arvore.body
        if isinstance(no, ast.FunctionDef) and no.name == "main"
    )
    locais = _nomes_locais(main)
    usados = {
        no.id
        for no in ast.walk(main)
        if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Load)
    }
    conhecidos = definidos_no_modulo | set(dir(builtins))
    return usados - locais - conhecidos


class TestMainSemNomeIndefinido(unittest.TestCase):
    """O main do coletor por sessao nao pode usar nome que o modulo nao define.

    O commit da sessao futura trocou o import de datetime por date e deixou
    o datetime.now() no nome da pasta, um NameError que a rotina semanal nao
    alcanca porque ela nao passa por esse main.
    """

    def test_todo_nome_do_main_esta_definido_no_modulo(self):
        caminho = RAIZ / "coletor" / "coletar_por_sessao.py"
        fonte = caminho.read_text(encoding="utf-8")
        compile(fonte, str(caminho), "exec")
        indefinidos = nomes_indefinidos_em_main(fonte)
        self.assertEqual(
            indefinidos,
            set(),
            f"nomes usados no main sem definicao no modulo: {sorted(indefinidos)}",
        )


if __name__ == "__main__":
    unittest.main()
