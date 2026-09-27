"""Leitura unica de config_cidade.json.

Nenhum script inventa cidade, endereco do SAPL, ano ou piso.
Valor ausente ou nulo e tratado como desconhecido.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARQUIVO_CONFIG = RAIZ / "config_cidade.json"
PAUSA_SAPL_SEGUNDOS = 2.5


class PisoNaoDefinido(Exception):
    """Piso de sanidade ainda nao foi definido pelo mantenedor."""


def carregar_config() -> dict:
    if not ARQUIVO_CONFIG.exists():
        raise SystemExit(
            "Arquivo config_cidade.json nao encontrado na raiz do repositorio."
        )
    try:
        dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise SystemExit(f"config_cidade.json invalido: {erro}") from erro
    if not isinstance(dados, dict):
        raise SystemExit("config_cidade.json deve ser um objeto JSON.")
    return dados


def nome_cidade(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else carregar_config()
    return str(cfg["cidade"]["nome"])


def uf_cidade(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else carregar_config()
    return str(cfg["cidade"]["uf"])


def endereco_sapl(cfg: dict | None = None) -> str:
    cfg = cfg if cfg is not None else carregar_config()
    return str(cfg["sapl"]["endereco_base"]).rstrip("/")


def link_materia(materia_id: int, cfg: dict | None = None) -> str:
    return f"{endereco_sapl(cfg)}/materia/{materia_id}"


def link_sessao(sessao_id: int, cfg: dict | None = None) -> str:
    return f"{endereco_sapl(cfg)}/sessao/{sessao_id}"


def link_parlamentar(caminho: str, cfg: dict | None = None) -> str:
    if caminho.startswith("http://") or caminho.startswith("https://"):
        return caminho
    if not caminho.startswith("/"):
        caminho = "/" + caminho
    return endereco_sapl(cfg) + caminho


def anos_recorte(cfg: dict | None = None) -> list[int]:
    cfg = cfg if cfg is not None else carregar_config()
    anos = cfg["recorte"]["anos"]
    if not isinstance(anos, list) or not anos:
        raise SystemExit("config_cidade.json: recorte.anos deve ser uma lista com ao menos um ano.")
    return [int(ano) for ano in anos]


def id_tipo_sessao_ordinaria(cfg: dict | None = None) -> int:
    cfg = cfg if cfg is not None else carregar_config()
    return int(cfg["sapl"]["id_tipo_sessao_ordinaria"])


def id_legislatura_atual(cfg: dict | None = None) -> int:
    cfg = cfg if cfg is not None else carregar_config()
    return int(cfg["sapl"]["id_legislatura_atual"])


def numero_vereadores_esperado(cfg: dict | None = None):
    cfg = cfg if cfg is not None else carregar_config()
    valor = cfg["vereadores"]["numero_esperado"]
    if valor is None:
        return None
    return int(valor)


def pisos_sanidade(cfg: dict | None = None) -> dict:
    cfg = cfg if cfg is not None else carregar_config()
    pisos = cfg["pisos_sanidade"]
    vereadores = pisos.get("vereadores")
    if vereadores is None:
        vereadores = cfg["vereadores"]["numero_esperado"]
    return {
        "sessoes_ordinarias": pisos.get("sessoes_ordinarias"),
        "plls": pisos.get("plls"),
        "vereadores": vereadores,
    }


def exigir_piso(nome: str, valor):
    if valor is None:
        raise PisoNaoDefinido(
            f"O piso '{nome}' ainda nao foi definido em config_cidade.json. "
            "O mantenedor precisa definir esse valor depois da coleta. "
            "Nao vou seguir com um numero inventado."
        )
    return valor


def user_agent_http(cfg: dict | None = None) -> str:
    slug = nome_cidade(cfg).lower().replace(" ", "-")
    return f"painel-camara-{slug}/0.1 (projeto de transparencia)"


def garantir_path_coletor() -> Path:
    pasta = Path(__file__).resolve().parent
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    return pasta
