#!/usr/bin/env python3
"""Gera cloudflare-worker/src/dados_cidade.js a partir do config e do contorno.

Leitura (nenhum numero fixo aqui, tudo vem destes arquivos):
    - config_cidade.json: cidade.codigo_ibge, votacao_popular.siglas_elegiveis,
      votacao_popular.siglas_excluidas, votacao_popular.limites,
      votacao_popular.dias_maximos_rodada;
    - dados/territorio/<codigo>_contorno_simplificado.json: geometria do
      primeiro Feature (Polygon ou MultiPolygon).

Saida:
    - cloudflare-worker/src/dados_cidade.js, que exporta DADOS_CIDADE.

Deterministico: chaves ordenadas, UTF-8, quebra de linha LF. Idempotente:
sem mudanca no conteudo, o arquivo nao e regravado.

Uso:
    python cloudflare-worker/gerar_dados_worker.py
    python cloudflare-worker/gerar_dados_worker.py --check  (falha se desatualizado)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_CONFIG = RAIZ / "config_cidade.json"
PASTA_TERRITORIO = RAIZ / "dados" / "territorio"
PASTA_SRC = RAIZ / "cloudflare-worker" / "src"
ARQUIVO_SAIDA = PASTA_SRC / "dados_cidade.js"

CABECALHO = (
    "// Arquivo GERADO por cloudflare-worker/gerar_dados_worker.py a partir de\n"
    "// config_cidade.json e dados/territorio/<codigo>_contorno_simplificado.json.\n"
    "// Nao edite a mao. Nenhum segredo aqui, so limites publicos e contorno.\n"
)

CHAVES_LIMITES = (
    "limite_geral_pedidos",
    "limite_geral_janela_s",
    "limite_geral_por_endereco",
    "limite_votar_pedidos",
    "limite_votar_janela_s",
    "limite_votar_por_endereco",
    "teto_votos_por_endereco_por_rodada",
    "validade_autorizacao_min",
    "precisao_gps_max_m",
    "margem_divisa_m",
    "minimo_respostas_por_materia",
    "retencao_identificadores_dias",
)


def carregar_config() -> dict:
    try:
        return json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"config_cidade.json ilegivel: {exc}")


def montar_dados() -> dict:
    config = carregar_config()
    cidade = config.get("cidade") or {}
    codigo = str(cidade.get("codigo_ibge") or "").strip()
    if not codigo.isdigit():
        raise SystemExit(
            "config_cidade.json: cidade.codigo_ibge ausente ou invalido."
        )
    bloco = config.get("votacao_popular") or {}
    siglas_elegiveis = bloco.get("siglas_elegiveis")
    siglas_excluidas = bloco.get("siglas_excluidas")
    limites = bloco.get("limites") or {}
    dias_maximos = bloco.get("dias_maximos_rodada")
    if not isinstance(siglas_elegiveis, list) or not siglas_elegiveis:
        raise SystemExit("config_cidade.json: siglas_elegiveis ausente ou vazia.")
    if not isinstance(siglas_excluidas, list):
        raise SystemExit("config_cidade.json: siglas_excluidas ausente.")
    faltando = [c for c in CHAVES_LIMITES if c not in limites]
    if faltando:
        raise SystemExit(f"config_cidade.json: limites sem {', '.join(faltando)}.")
    if not isinstance(dias_maximos, int) or dias_maximos <= 0:
        raise SystemExit("config_cidade.json: dias_maximos_rodada invalido.")

    caminho_contorno = PASTA_TERRITORIO / f"{codigo}_contorno_simplificado.json"
    try:
        contorno = json.loads(caminho_contorno.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Contorno ilegivel ({caminho_contorno}): {exc}")
    try:
        geometria = (contorno.get("features") or [])[0]["geometry"]
    except (IndexError, KeyError, TypeError):
        raise SystemExit("Contorno sem features com geometria.")
    if geometria.get("type") not in ("Polygon", "MultiPolygon"):
        raise SystemExit(
            f"Contorno com geometria nao suportada: {geometria.get('type')!r}."
        )
    if not geometria.get("coordinates"):
        raise SystemExit("Contorno sem coordenadas.")

    return {
        "codigo_ibge": codigo,
        "siglas_elegiveis": list(siglas_elegiveis),
        "siglas_excluidas": list(siglas_excluidas),
        "limites": {chave: limites[chave] for chave in CHAVES_LIMITES},
        "dias_maximos_rodada": dias_maximos,
        "contorno": geometria,
    }


def texto_saida(dados: dict) -> str:
    corpo = json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True)
    return CABECALHO + "export const DADOS_CIDADE = " + corpo + ";\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gera src/dados_cidade.js do Worker.")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    texto = texto_saida(montar_dados())
    if args.check:
        if not ARQUIVO_SAIDA.is_file():
            print("dados_cidade.js ausente. Rode gerar_dados_worker.py.")
            return 1
        atual = ARQUIVO_SAIDA.read_text(encoding="utf-8")
        if atual != texto:
            print("dados_cidade.js desatualizado. Rode gerar_dados_worker.py.")
            return 1
        print("dados_cidade.js atualizado.")
        return 0
    if ARQUIVO_SAIDA.is_file():
        atual = ARQUIVO_SAIDA.read_text(encoding="utf-8")
        if atual == texto:
            print("dados_cidade.js ja atualizado, nada a gravar.")
            return 0
    PASTA_SRC.mkdir(parents=True, exist_ok=True)
    with open(ARQUIVO_SAIDA, "w", encoding="utf-8", newline="\n") as arquivo:
        arquivo.write(texto)
    print("dados_cidade.js gravado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
