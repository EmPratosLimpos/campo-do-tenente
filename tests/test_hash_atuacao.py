"""O .sha256 do arquivo anual acompanha o arquivo salvo. Sem rede.

O mesmo caminho usado pelo gerador grava o JSON e o hash no mesmo passo.
Um hash de semana passada nao pode passar no teste de integridade.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "coletor"))
sys.path.insert(0, str(RAIZ / "dados" / "tratados"))

from gerar_atuacao_vereadores import escrever_json_com_hash  # noqa: E402
from gerar_hash_integridade import conferir_hash  # noqa: E402


def sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


class TestHashAcompanhaArquivoSalvo(unittest.TestCase):
    def test_hash_e_regravado_junto_com_o_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "atuacao_vereadores_2026.json"
            hash_path = alvo.with_name(alvo.name + ".sha256")
            escrever_json_com_hash(alvo, '{"versao": 1}\n')
            self.assertEqual(
                hash_path.read_text(encoding="utf-8").strip(), sha256(alvo)
            )
            conferir_hash(alvo, hash_path)
            escrever_json_com_hash(alvo, '{"versao": 2}\n')
            self.assertEqual(
                hash_path.read_text(encoding="utf-8").strip(), sha256(alvo)
            )
            conferir_hash(alvo, hash_path)

    def test_hash_da_semana_passada_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "atuacao_vereadores_2026.json"
            hash_path = alvo.with_name(alvo.name + ".sha256")
            escrever_json_com_hash(alvo, '{"versao": 1}\n')
            alvo.write_bytes(b'{"versao": 2}\n')
            with self.assertRaises(SystemExit) as ctx:
                conferir_hash(alvo, hash_path)
            self.assertIn("nao confere", str(ctx.exception))

    def test_hash_ausente_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            alvo = Path(tmp) / "atuacao_vereadores_2026.json"
            alvo.write_bytes(b'{"versao": 1}\n')
            hash_path = alvo.with_name(alvo.name + ".sha256")
            with self.assertRaises(SystemExit) as ctx:
                conferir_hash(alvo, hash_path)
            self.assertIn("Hash ausente", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
