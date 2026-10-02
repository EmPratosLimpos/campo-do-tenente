#!/usr/bin/env python3
"""Baixa fotos oficiais de vereadores do SAPL (uma vez, com pausa de 2,5 s)."""

from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    carregar_config,
    conferir_host_final,
    conferir_url_permitida,
    host_da_url,
)

PAUSA = 2.5
SAIDA = RAIZ / "dados" / "brutos" / "fotos_vereadores"


def baixar(url: str, destino: pathlib.Path, cfg: dict) -> bool:
    """So https e host do config. Recusa antes de abrir qualquer conexao."""
    conferir_url_permitida(url, cfg, rotulo=f"foto {destino.name}")
    req = urllib.request.Request(url, headers={"User-Agent": "EmPratosLimpos-coletor/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        conferir_host_final(host_da_url(resp.geturl()), cfg, destino.name)
        data = resp.read()
    if len(data) < 200:
        return False
    destino.write_bytes(data)
    return True


def main():
    cfg = carregar_config()
    sapl = cfg["sapl"]["endereco_base"].rstrip("/")
    vereadores = json.loads((RAIZ / "dados" / "tratados" / "vereadores.json").read_text(encoding="utf-8"))
    SAIDA.mkdir(parents=True, exist_ok=True)
    indice_path = SAIDA / "indice.json"
    indice = {}
    if indice_path.exists():
        indice = json.loads(indice_path.read_text(encoding="utf-8"))

    ids = sorted({v["id_sapl"] for v in vereadores.get("vereadores", [])})
    for i, vid in enumerate(ids):
        rel = f"dados/brutos/fotos_vereadores/{vid}.jpg"
        if rel in indice.values() and (SAIDA / f"{vid}.jpg").exists():
            continue
        v = next(x for x in vereadores["vereadores"] if x["id_sapl"] == vid)
        foto = v.get("foto_url") or ""
        if not foto.startswith("http"):
            foto = sapl + foto if foto.startswith("/") else ""
        if not foto:
            continue
        if foto.startswith("http://"):
            foto = "https://" + foto[len("http://") :]
        dest = SAIDA / f"{vid}.jpg"
        if i > 0:
            time.sleep(PAUSA)
        try:
            if baixar(foto, dest, cfg):
                indice[str(vid)] = rel
                print(f"OK foto {vid}")
            else:
                print(f"Pulando foto {vid} (resposta pequena)")
        except OSError as err:
            print(f"Falha foto {vid}: {err}")

    indice_path.write_text(json.dumps(indice, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
