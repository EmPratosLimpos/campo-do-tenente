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


CHAVES_PISO = (
    "vereadores",
    "sessoes_ordinarias",
    "projetos_lei_legislativo_e_executivo",
)


def pisos_sanidade(ano: int, cfg: dict | None = None) -> dict:
    """Pisos do ano (D-016). Ano sem bloco ou chave ausente fica nulo.

    vereadores e exato. sessoes_ordinarias e
    projetos_lei_legislativo_e_executivo (PLEG e PLEX somados) sao minimos.
    """
    cfg = cfg if cfg is not None else carregar_config()
    por_ano = (cfg.get("pisos_sanidade") or {}).get("por_ano") or {}
    bloco = por_ano.get(str(int(ano))) or {}
    return {chave: bloco.get(chave) for chave in CHAVES_PISO}


def exigir_piso(nome: str, valor, ano: int | None = None):
    if valor is None:
        rotulo = f"{nome}' de {ano}" if ano is not None else f"{nome}'"
        raise PisoNaoDefinido(
            f"O piso '{rotulo} ainda nao foi definido em config_cidade.json. "
            "O mantenedor precisa definir esse valor depois da coleta. "
            "Nao vou seguir com um numero inventado."
        )
    return valor


def categorias(cfg: dict | None = None) -> list[dict]:
    """Categorias de tema da cidade (D-021), na ordem de exibicao.

    Cada item tem nome e descricao. Nome repetido ou vazio e erro.
    """
    cfg = cfg if cfg is not None else carregar_config()
    lista = (cfg.get("categorias") or {}).get("lista")
    if not isinstance(lista, list) or not lista:
        raise SystemExit("config_cidade.json: categorias.lista deve ser uma lista com ao menos uma categoria.")
    saida = []
    vistos = set()
    for item in lista:
        nome = str((item or {}).get("nome") or "").strip()
        descricao = str((item or {}).get("descricao") or "").strip()
        if not nome or not descricao:
            raise SystemExit("config_cidade.json: toda categoria precisa de nome e descricao.")
        if nome in vistos:
            raise SystemExit(f"config_cidade.json: categoria repetida: {nome}.")
        vistos.add(nome)
        saida.append({"nome": nome, "descricao": descricao})
    return saida


def nomes_categorias(cfg: dict | None = None) -> list[str]:
    return [item["nome"] for item in categorias(cfg)]


def rotulos_especiais_tema(cfg: dict | None = None) -> dict:
    """Rotulos fora das categorias: nao_se_aplica (ATA e OFEX) e sem_ementa."""
    cfg = cfg if cfg is not None else carregar_config()
    bloco = (cfg.get("categorias") or {}).get("rotulos_especiais") or {}
    saida = {}
    for chave in ("nao_se_aplica", "sem_ementa"):
        valor = str(bloco.get(chave) or "").strip()
        if not valor:
            raise SystemExit(f"config_cidade.json: categorias.rotulos_especiais.{chave} ausente.")
        saida[chave] = valor
    return saida


def tipos_tramitacao_coleta(cfg: dict | None = None) -> list[str]:
    """Siglas da coleta de tramitacao (C8). Nenhuma sigla fixa no codigo."""
    cfg = cfg if cfg is not None else carregar_config()
    lista = (cfg.get("tramitacao") or {}).get("tipos_coleta")
    if not isinstance(lista, list) or not lista:
        raise SystemExit("config_cidade.json: tramitacao.tipos_coleta deve ser uma lista com ao menos uma sigla.")
    saida = []
    for sigla in lista:
        texto = str(sigla or "").strip()
        if not texto:
            raise SystemExit("config_cidade.json: tramitacao.tipos_coleta com sigla vazia.")
        saida.append(texto)
    return saida


def tipos_proposicoes(cfg: dict | None = None) -> list[str]:
    cfg = cfg if cfg is not None else carregar_config()
    lista = (cfg.get("tramitacao") or {}).get("tipos_proposicoes")
    if not isinstance(lista, list) or not lista:
        raise SystemExit("config_cidade.json: tramitacao.tipos_proposicoes ausente.")
    return [str(sigla or "").strip() for sigla in lista]


def tipos_executivo(cfg: dict | None = None) -> list[str]:
    cfg = cfg if cfg is not None else carregar_config()
    lista = (cfg.get("tramitacao") or {}).get("tipos_executivo")
    if not isinstance(lista, list) or not lista:
        raise SystemExit("config_cidade.json: tramitacao.tipos_executivo ausente.")
    return [str(sigla or "").strip() for sigla in lista]


def piso_status_decodificados(cfg: dict | None = None) -> int:
    cfg = cfg if cfg is not None else carregar_config()
    valor = (cfg.get("tramitacao") or {}).get("piso_status_decodificados")
    if valor is None:
        raise PisoNaoDefinido(
            "O piso 'piso_status_decodificados' ainda nao foi definido em config_cidade.json. "
            "O mantenedor precisa definir esse valor depois da coleta. "
            "Nao vou seguir com um numero inventado."
        )
    return int(valor)


def user_agent_http(cfg: dict | None = None) -> str:
    slug = nome_cidade(cfg).lower().replace(" ", "-")
    return f"painel-camara-{slug}/0.1 (projeto de transparencia)"


def tipos_dois_turnos(cfg: dict | None = None) -> set[str]:
    """Siglas com votacao em dois turnos (D-049). O resto e turno unico."""
    cfg = cfg if cfg is not None else carregar_config()
    lista = (cfg.get("turnos_votacao") or {}).get("dois_turnos")
    if not isinstance(lista, list) or not lista:
        raise SystemExit("config_cidade.json: turnos_votacao.dois_turnos deve ser uma lista com ao menos uma sigla.")
    saida = set()
    for sigla in lista:
        texto = str(sigla or "").strip()
        if not texto:
            raise SystemExit("config_cidade.json: sigla vazia em turnos_votacao.dois_turnos.")
        if texto in saida:
            raise SystemExit(f"config_cidade.json: sigla repetida em turnos_votacao.dois_turnos: {texto}.")
        saida.add(texto)
    return saida


def garantir_path_coletor() -> Path:
    pasta = Path(__file__).resolve().parent
    if str(pasta) not in sys.path:
        sys.path.insert(0, str(pasta))
    return pasta
