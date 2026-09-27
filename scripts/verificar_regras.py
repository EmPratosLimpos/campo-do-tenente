#!/usr/bin/env python3
"""
Script de verificacao compulsoria de regras de governanca e sanidade.
Executado localmente por qualquer agente ou desenvolvedor antes de commits.
"""

import sys
import subprocess
import pathlib
import hashlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

def main():
    erros = []
    print("=======================================================")
    print("Verificando conformidade com as regras de governanca...")
    print("=======================================================\n")

    # 1. Verificar branch atual
    res = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True)
    branch = res.stdout.strip()
    print(f"Branch atual: {branch}")
    if branch == "main":
        erros.append("VIOLACAO: Nao e permitido realizar trabalho ou commits diretamente na branch 'main'!")

    # 2. Testes de sanidade de dados
    print("\nExecutando coletor/testes_sanidade.py...")
    res = subprocess.run([sys.executable, "coletor/testes_sanidade.py"], cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        erros.append(f"FALHA nos testes de sanidade:\n{res.stdout}\n{res.stderr}")
    else:
        print("OK: Testes de sanidade passaram.")

    # 3. Testes unitarios
    print("\nExecutando unittest em tests/...")
    res = subprocess.run([sys.executable, "-m", "unittest", "tests/test_sanidade_dados.py"], cwd=ROOT, capture_output=True, text=True)
    if res.returncode != 0:
        erros.append(f"FALHA nos testes unitarios:\n{res.stdout}\n{res.stderr}")
    else:
        print("OK: Testes unitarios passaram.")

    # 4. Hash de integridade
    print("\nVerificando hash SHA256...")
    json_path = ROOT / "dados" / "tratados" / "atuacao_vereadores_2026.json"
    hash_path = ROOT / "dados" / "tratados" / "atuacao_vereadores_2026.json.sha256"
    if json_path.exists() and hash_path.exists():
        h = hashlib.sha256(json_path.read_bytes()).hexdigest()
        saved = hash_path.read_text(encoding="utf-8").strip()
        if h != saved:
            erros.append(f"FALHA no hash SHA256: Calculado {h} != Salvo {saved}. Execute python coletor/gerar_hash_integridade.py")
        else:
            print("OK: Hash SHA256 integro.")
    else:
        erros.append("Arquivos de dados ou hash ausentes!")

    # 5. Higiene de travessoes em documentacao
    print("\nVerificando ausencia de caracteres de travessao proibidos...")
    arquivos_norma = ["AGENTS.md", "CLAUDE.md", ".cursorrules", "PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md", "index.html"]
    for nome in arquivos_norma:
        arq = ROOT / nome
        if arq.exists():
            conteudo = arq.read_text(encoding="utf-8")
            if re.search(r"[—–]", conteudo):
                erros.append(f"VIOLACAO: Caractere travessao encontrado em {nome}!")
            else:
                print(f"OK: {nome} limpo.")

    print("\n-------------------------------------------------------")
    if erros:
        print(f"ERROS DETECTADOS ({len(erros)}):")
        for e in erros:
            print(f"- {e}")
        sys.exit(1)
    else:
        print("SUCESSO: Todas as regras de governanca e sanidade foram atendidas!")
        sys.exit(0)

if __name__ == "__main__":
    main()
