#!/usr/bin/env python3
import hashlib
import datetime
import pathlib

ARQUIVO_JSON = pathlib.Path("dados/tratados/atuacao_vereadores_2026.json")
ARQUIVO_HASH = pathlib.Path("dados/tratados/atuacao_vereadores_2026.json.sha256")


def calcular_hash_sha256(caminho):
    sha256 = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            sha256.update(bloco)
    return sha256.hexdigest()


def main():
    if not ARQUIVO_JSON.exists():
        raise SystemExit(f"Arquivo não encontrado: {ARQUIVO_JSON}")

    hash_hex = calcular_hash_sha256(ARQUIVO_JSON)
    data_hora = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ARQUIVO_HASH.parent.mkdir(parents=True, exist_ok=True)
    with ARQUIVO_HASH.open("w", encoding="utf-8") as f:
        f.write(hash_hex + "\n")

    print(f"Arquivo: {ARQUIVO_JSON}")
    print(f"SHA256: {hash_hex}")
    print(f"Data/hora: {data_hora}")
    print(f"Hash salvo em: {ARQUIVO_HASH}")


if __name__ == "__main__":
    main()
