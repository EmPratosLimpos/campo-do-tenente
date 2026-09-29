"""Testes do hook commit-msg e da verificacao de marcas de IA em commits."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

from marcas_ia import (  # noqa: E402
    linha_e_marca_ia,
    mensagem_tem_marca_ia,
    sanitizar_mensagem_commit,
    verificar_commits_marcas_ia,
)

HOOK = RAIZ / ".githooks" / "commit-msg"


def _caminho_bash() -> str | None:
    bash = shutil.which("bash")
    if bash:
        return bash
    for candidato in (
        Path(os.environ.get("ProgramFiles", "")) / "Git" / "bin" / "bash.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Git" / "usr" / "bin" / "bash.exe",
    ):
        if candidato.is_file():
            return str(candidato)
    return None


def _rodar_hook(caminho_msg: Path) -> None:
    bash = _caminho_bash()
    if not bash:
        raise unittest.SkipTest("bash nao encontrado")
    subprocess.run(
        [bash, str(HOOK), str(caminho_msg)],
        check=True,
        cwd=RAIZ,
    )


class TestMarcasIaLinhas(unittest.TestCase):
    def test_remove_coautor_cursor_claude_commandcode(self):
        msg = (
            "feat: ajuste\n\n"
            "Co-authored-by: Cursor <cursoragent@cursor.com>\n"
            "Co-Authored-By: Claude <noreply@anthropic.com>\n"
            "Co-authored-by: Bot <bot@commandcode.ai>\n"
        )
        limpa = sanitizar_mensagem_commit(msg)
        self.assertIn("feat: ajuste", limpa)
        self.assertNotIn("Cursor", limpa)
        self.assertNotIn("Claude", limpa)
        self.assertNotIn("commandcode", limpa)

    def test_mantem_coautor_humano(self):
        msg = (
            "fix: correcao\n\n"
            "Co-authored-by: Maria Silva <maria@exemplo.org>\n"
        )
        limpa = sanitizar_mensagem_commit(msg)
        self.assertIn("Maria Silva <maria@exemplo.org>", limpa)

    def test_remove_generated_with(self):
        msg = "titulo\n\nGenerated with Claude Code\n"
        self.assertTrue(linha_e_marca_ia("Generated with Claude Code"))
        limpa = sanitizar_mensagem_commit(msg)
        self.assertEqual(limpa.strip(), "titulo")

    def test_remove_generated_with_emoji_e_link(self):
        linha = (
            "\U0001f916 Generated with [Claude Code]"
            "(https://claude.com/claude-code)"
        )
        self.assertTrue(linha_e_marca_ia(linha))
        msg = f"titulo\n\n{linha}\n"
        limpa = sanitizar_mensagem_commit(msg)
        self.assertEqual(limpa.strip(), "titulo")
        self.assertTrue(mensagem_tem_marca_ia(msg))

    def test_detecta_marca_na_mensagem(self):
        self.assertTrue(mensagem_tem_marca_ia("Co-authored-by: Copilot <x@y>\n"))


@unittest.skipUnless(_caminho_bash() and HOOK.is_file(), "bash ou hook ausente")
class TestHookCommitMsg(unittest.TestCase):
    def test_hook_espelha_sanitizacao(self):
        msg = (
            "feat: teste hook\n\n"
            "Co-authored-by: Cursor <cursoragent@cursor.com>\n"
            "Co-authored-by: Maria Silva <maria@exemplo.org>\n"
            "Generated with Composer\n"
            "\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            arq = Path(tmp) / "msg"
            arq.write_text(msg, encoding="utf-8", newline="\n")
            _rodar_hook(arq)
            resultado = arq.read_text(encoding="utf-8")
        esperado = sanitizar_mensagem_commit(msg)
        self.assertEqual(resultado, esperado)


class TestVerificarCommitsMarcasIa(unittest.TestCase):
    def test_repo_temporario_com_marca_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
            subprocess.run(
                ["git", "config", "user.email", "teste@exemplo.org"],
                cwd=raiz,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Teste"],
                cwd=raiz,
                check=True,
            )
            (raiz / "a.txt").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=raiz, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base limpa", "--no-verify"],
                cwd=raiz,
                check=True,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=raiz,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            (raiz / ".marcas-ia-desde").write_text(base + "\n", encoding="utf-8")

            (raiz / "b.txt").write_text("y\n", encoding="utf-8")
            subprocess.run(["git", "add", "b.txt"], cwd=raiz, check=True)
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "ok\n\nCo-authored-by: Cursor <c@cursor.com>",
                    "--no-verify",
                ],
                cwd=raiz,
                check=True,
            )

            erros, avisos = verificar_commits_marcas_ia(raiz)
            self.assertFalse(avisos)
            self.assertTrue(erros)

    def test_repo_temporario_generated_com_emoji_falha(self):
        linha = (
            "\U0001f916 Generated with [Claude Code]"
            "(https://claude.com/claude-code)"
        )
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
            subprocess.run(
                ["git", "config", "user.email", "teste@exemplo.org"],
                cwd=raiz,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Teste"],
                cwd=raiz,
                check=True,
            )
            (raiz / "a.txt").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=raiz, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base limpa", "--no-verify"],
                cwd=raiz,
                check=True,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=raiz,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            (raiz / ".marcas-ia-desde").write_text(base + "\n", encoding="utf-8")

            (raiz / "b.txt").write_text("y\n", encoding="utf-8")
            subprocess.run(["git", "add", "b.txt"], cwd=raiz, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"ok\n\n{linha}", "--no-verify"],
                cwd=raiz,
                check=True,
            )

            erros, avisos = verificar_commits_marcas_ia(raiz)
            self.assertFalse(avisos)
            self.assertTrue(erros)

    def test_repo_temporario_limpo_passa(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            subprocess.run(["git", "init", "-q"], cwd=raiz, check=True)
            subprocess.run(
                ["git", "config", "user.email", "teste@exemplo.org"],
                cwd=raiz,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Teste"],
                cwd=raiz,
                check=True,
            )
            (raiz / "a.txt").write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "a.txt"], cwd=raiz, check=True)
            subprocess.run(
                ["git", "commit", "-m", "base", "--no-verify"],
                cwd=raiz,
                check=True,
            )
            base = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=raiz,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            (raiz / ".marcas-ia-desde").write_text(base + "\n", encoding="utf-8")

            (raiz / "b.txt").write_text("y\n", encoding="utf-8")
            subprocess.run(["git", "add", "b.txt"], cwd=raiz, check=True)
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "segundo\n\nCo-authored-by: Maria Silva <maria@exemplo.org>",
                    "--no-verify",
                ],
                cwd=raiz,
                check=True,
            )

            erros, avisos = verificar_commits_marcas_ia(raiz)
            self.assertEqual(erros, [])
            self.assertEqual(avisos, [])


if __name__ == "__main__":
    unittest.main()
