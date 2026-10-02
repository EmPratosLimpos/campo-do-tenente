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


ESPACOS = " \t\r\n"
_DECODER = json.JSONDecoder()


def esquemas_permitidos(cfg: dict | None = None) -> list[str]:
    cfg = cfg if cfg is not None else carregar_config()
    lista = (cfg.get("rede") or {}).get("esquemas_permitidos")
    if not isinstance(lista, list) or not lista:
        raise SystemExit(
            "config_cidade.json: rede.esquemas_permitidos deve ser uma lista com ao menos um esquema."
        )
    return [str(item or "").strip().lower() for item in lista]


def teto_bytes_resposta(cfg: dict | None = None) -> int:
    """Teto de bytes de uma resposta. Acima disso, nada e gravado."""
    cfg = cfg if cfg is not None else carregar_config()
    valor = (cfg.get("rede") or {}).get("teto_bytes_resposta")
    if valor is None:
        raise SystemExit(
            "config_cidade.json: rede.teto_bytes_resposta nao foi definido. "
            "O mantenedor precisa definir esse valor. Nao vou seguir com um numero inventado."
        )
    return int(valor)


def host_da_url(url: str) -> str:
    import urllib.parse

    return (urllib.parse.urlparse(str(url or "")).hostname or "").lower()


def hosts_permitidos(cfg: dict | None = None) -> set[str]:
    """Host do SAPL mais os extras declarados no config."""
    cfg = cfg if cfg is not None else carregar_config()
    extras = (cfg.get("rede") or {}).get("hosts_permitidos_extra") or []
    if not isinstance(extras, list):
        raise SystemExit("config_cidade.json: rede.hosts_permitidos_extra deve ser uma lista.")
    hosts = {host_da_url(endereco_sapl(cfg))}
    for item in extras:
        texto = host_da_url(str(item or "")) or str(item or "").strip().lower()
        if not texto:
            raise SystemExit("config_cidade.json: rede.hosts_permitidos_extra tem host vazio.")
        hosts.add(texto)
    return {host for host in hosts if host}


def conferir_url_permitida(url: str, cfg: dict | None = None, rotulo: str = "") -> str:
    """So https e host do config. file:, data:, ftp: e outro host sao recusados."""
    import urllib.parse

    cfg = cfg if cfg is not None else carregar_config()
    endereco = str(url or "").strip()
    onde = rotulo or endereco
    if not endereco:
        raise SystemExit(f"URL vazia: {onde}")
    partes = urllib.parse.urlparse(endereco)
    esquema = (partes.scheme or "").lower()
    permitidos = esquemas_permitidos(cfg)
    if esquema not in permitidos:
        raise SystemExit(
            f"Esquema '{esquema or 'sem esquema'}' recusado em {onde}. "
            f"Somente {', '.join(permitidos)}."
        )
    host = (partes.hostname or "").lower()
    liberados = hosts_permitidos(cfg)
    if host not in liberados:
        raise SystemExit(
            f"Host '{host or 'sem host'}' fora da lista do config em {onde}. "
            f"Liberados: {', '.join(sorted(liberados))}."
        )
    return endereco


def conferir_host_final(host: str, cfg: dict | None = None, onde: str = "") -> None:
    """Recusa resposta que veio de outro host, mesmo depois de redirecionar."""
    cfg = cfg if cfg is not None else carregar_config()
    liberados = hosts_permitidos(cfg)
    recebido = (host or "").lower()
    if not recebido:
        raise SystemExit(
            f"Resposta sem host final em {onde}. Nao da para conferir a origem. Nada foi gravado."
        )
    if recebido not in liberados:
        raise SystemExit(
            f"Resposta veio de '{recebido}', que nao esta no config, em {onde}. "
            f"Liberados: {', '.join(sorted(liberados))}. Nada foi gravado."
        )



def campos_pessoais(cfg: dict | None = None) -> list[str]:
    """Campos que identificam quem operou o SAPL. Lista vem do config."""
    cfg = cfg if cfg is not None else carregar_config()
    lista = (cfg.get("campos_pessoais_removidos") or {}).get("lista")
    if not isinstance(lista, list) or not lista:
        raise SystemExit(
            "config_cidade.json: campos_pessoais_removidos.lista deve ser uma lista "
            "com ao menos uma chave."
        )
    saida = []
    for chave in lista:
        texto = str(chave or "").strip()
        if not texto:
            raise SystemExit(
                "config_cidade.json: campos_pessoais_removidos.lista tem chave vazia."
            )
        if texto not in saida:
            saida.append(texto)
    return saida


def _sem_campos(valor, chaves: set[str]):
    if isinstance(valor, dict):
        return {
            chave: _sem_campos(item, chaves)
            for chave, item in valor.items()
            if chave not in chaves
        }
    if isinstance(valor, list):
        return [_sem_campos(item, chaves) for item in valor]
    return valor


def remover_campos_pessoais(valor, cfg: dict | None = None):
    """Tira as chaves pessoais em qualquer nivel, sem mexer em nenhum outro valor."""
    return _sem_campos(valor, set(campos_pessoais(cfg)))


def contem_campos_pessoais(valor, cfg: dict | None = None) -> bool:
    chaves = set(campos_pessoais(cfg))

    def busca(item) -> bool:
        if isinstance(item, dict):
            if chaves & set(item.keys()):
                return True
            return any(busca(sub) for sub in item.values())
        if isinstance(item, list):
            return any(busca(sub) for sub in item)
        return False

    return busca(valor)


def _inicio_do_membro(texto: str, posicao: int) -> int:
    """Volta ate o comeco da linha quando o membro so comeca em uma linha nova."""
    i = posicao
    while i > 0 and texto[i - 1] in " \t":
        i -= 1
    if i > 0 and texto[i - 1] == "\n":
        return i
    return posicao


def _virgula_anterior(texto: str, posicao: int) -> int | None:
    i = posicao
    while i > 0 and texto[i - 1] in " \t\r\n":
        i -= 1
    if i > 0 and texto[i - 1] == ",":
        return i - 1
    return None


def _virgula_depois(texto: str, posicao: int) -> int | None:
    i = posicao
    tamanho = len(texto)
    while i < tamanho and texto[i] in ESPACOS:
        i += 1
    if i < tamanho and texto[i] == ",":
        return i
    return None


def _fim_do_valor(texto: str, posicao: int) -> int:
    """Fim do valor que vem depois da chave que termina em posicao."""
    i = posicao
    tamanho = len(texto)
    while i < tamanho and texto[i] in ESPACOS:
        i += 1
    if i < tamanho and texto[i] == ":":
        i += 1
    while i < tamanho and texto[i] in ESPACOS:
        i += 1
    _valor, fim = _DECODER.raw_decode(texto, i)
    return fim


def _objetos_do_texto(texto: str) -> list[list[tuple[int, str, int]]]:
    """Objetos do JSON com a lista de chaves de primeiro nivel, na ordem do arquivo.

    Uma chave e toda string seguida de dois pontos. String que e valor nao conta.
    """
    objetos: list[list[tuple[int, str, int]]] = []
    pilha: list[list[tuple[int, str, int]] | None] = []
    i = 0
    tamanho = len(texto)
    while i < tamanho:
        caractere = texto[i]
        if caractere == "{":
            membros: list[tuple[int, str, int]] = []
            objetos.append(membros)
            pilha.append(membros)
            i += 1
            continue
        if caractere == "[":
            pilha.append(None)
            i += 1
            continue
        if caractere in "}]":
            if pilha:
                pilha.pop()
            i += 1
            continue
        if caractere == '"':
            valor, fim = _DECODER.raw_decode(texto, i)
            j = fim
            while j < tamanho and texto[j] in ESPACOS:
                j += 1
            if j < tamanho and texto[j] == ":":
                membros = pilha[-1] if pilha else None
                if membros is not None:
                    membros.append((i, valor, fim))
            i = fim
            continue
        i += 1
    return objetos


def remover_campos_pessoais_do_texto(texto: str, cfg: dict | None = None) -> str:
    """Tira as chaves pessoais do texto JSON sem mudar o formato do arquivo.

    A remocao e feita no proprio texto, entao a indentacao, a ordem das
    chaves, o LF e o ensure_ascii do arquivo original ficam intactos.
    Serve tanto para a coleta nova quanto para limpar os brutos ja salvos.
    """
    chaves = set(campos_pessoais(cfg))
    if not texto or not chaves:
        return texto
    cortes: list[tuple[int, int]] = []
    for membros in _objetos_do_texto(texto):
        if not any(chave in chaves for _inicio, chave, _fim in membros):
            continue
        limites = []
        for inicio, chave, fim in membros:
            limites.append(
                {
                    "chave": chave,
                    "inicio": inicio,
                    "linha": _inicio_do_membro(texto, inicio),
                    "fim": _fim_do_valor(texto, fim),
                    "depois": _virgula_depois(texto, _fim_do_valor(texto, fim)),
                    "antes": None,
                }
            )
        for indice, item in enumerate(limites):
            if indice:
                limites[indice]["antes"] = limites[indice - 1]["depois"]
        alvo = [i for i, item in enumerate(limites) if item["chave"] in chaves]
        inicio_run = 0
        while inicio_run < len(alvo):
            fim_run = inicio_run
            while (
                fim_run + 1 < len(alvo)
                and alvo[fim_run + 1] == alvo[fim_run] + 1
            ):
                fim_run += 1
            primeiro = limites[alvo[inicio_run]]
            ultimo = limites[alvo[fim_run]]
            if primeiro["antes"] is not None:
                cortes.append((primeiro["antes"], ultimo["fim"]))
            elif ultimo["depois"] is not None:
                cortes.append((primeiro["linha"], ultimo["depois"] + 1))
            else:
                cortes.append((primeiro["linha"], ultimo["fim"]))
            inicio_run = fim_run + 1
    if not cortes:
        return texto
    # Um corte dentro de outro e redundante: o de fora ja leva o texto junto.
    maximas: list[tuple[int, int]] = []
    for inicio, fim in sorted(cortes, key=lambda par: (par[0], -par[1])):
        if maximas and maximas[-1][0] <= inicio and maximas[-1][1] >= fim:
            continue
        maximas.append((inicio, fim))
    saida = texto
    for inicio, fim in reversed(maximas):
        saida = saida[:inicio] + saida[fim:]
    return saida


def limpar_bytes_pessoais(corpo: bytes, cfg: dict | None = None) -> bytes:
    """Aplica a remocao em bytes de resposta do SAPL antes de gravar."""
    if not corpo:
        return corpo
    try:
        texto = corpo.decode("utf-8")
    except UnicodeDecodeError:
        return corpo
    limpo = remover_campos_pessoais_do_texto(texto, cfg)
    if limpo == texto:
        return corpo
    return limpo.encode("utf-8")


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
