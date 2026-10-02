#!/usr/bin/env python3
"""Consolida proposicoes e Executivo com tramitacao e votacao (C9).

Le os brutos ja coletados e os tratados existentes. Nao pede nada ao SAPL.
Nao inventa dado: ausencia de votacao ou de tramitacao recebe rotulo
explicito. Ausencia nao e voto. Campo de rede nunca vai para dado tratado.

As regras de voto e de resultado NAO sao novas aqui: vem de
dados/tratados/gerar_atuacao_vereadores.py (D-049 turnos, D-050 resultado
oficial pelo id do tipo de resultado do SAPL, mandato pela data). Este
script escolhe, entre as votacoes ja lidas por aquele script, so a que
define a materia: 2o turno ou turno unico. Voto sem deliberacao (Pedido
de Vistas, Adiada, Retirada de Pauta) e 1o turno ficam registrados como
fato de tramitacao e de votacao, e nunca viram voto valido.

Entradas:
    dados/brutos/lote principal (fichas de materialegislativa e catalogo
    tipomaterialegislativa, lidos pela regra de escolha do lote que ignora
    as pastas de tramitacao e de sondagem)
    dados/brutos/lote_*_tramitacao/ (historico, status e unidades)
    dados/tratados/temas_materias.json (tema por materia)
    dados/tratados/autoria_materias.json (autores vereadores)
    dados/tratados/vereadores.json (nomes e mandatos)
    dados/tratados/atuacao_vereadores_<ano>.json (votacoes ordinarias)

Saidas (chamado por gerar_dados_tela.py):
    dados/tratados/proposicoes_<ano>.json e proposicoes_legislatura.json
    dados/tratados/executivo_<ano>.json e executivo_legislatura.json
    complemento da atuacao_vereadores_legislatura.json por vereador:
    lista de proposicoes de autoria dele e votos em materias do Executivo.
    Os arquivos atuacao_vereadores_<ano>.json nao sao tocados.

Uso:
    python dados/tratados/gerar_proposicoes_executivo.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

DIR_SCRIPT = Path(__file__).resolve().parent
DIR_RAIZ = DIR_SCRIPT.parent.parent
DIR_BRUTOS = DIR_SCRIPT.parent / "brutos"
for caminho in (DIR_SCRIPT, DIR_RAIZ / "coletor"):
    if str(caminho) not in sys.path:
        sys.path.insert(0, str(caminho))

from config_cidade import (  # noqa: E402
    anos_recorte,
    carregar_config,
    endereco_sapl,
    link_materia,
    piso_status_decodificados,
    tipos_dois_turnos,
    tipos_executivo,
    tipos_proposicoes,
)
from derivar_insumos import BRUTOS, pasta_lote_mais_recente  # noqa: E402
from gerar_atuacao_vereadores import (  # noqa: E402
    TURNOS_CONTADOS,
    carregar_autoria,
    carregar_catalogo_tipos_materia,
    carregar_json,
    carregar_temas,
    deliberativa_nome,
    dentro_do_mandato,
    escrever_lf,
    escolher_por_turno,
    recusar_ip,
    rel,
    situacao_da_votacao_escolhida,
    tema_da_materia,
)
from gerar_atuacao_vereadores import (  # noqa: E402
    escolher_votacao as escolher_votacao_da_atuacao,
)

SCRIPT_REL = "dados/tratados/gerar_proposicoes_executivo.py"
ROTULO_SEM_VOTACAO = "sem votacao registrada no SAPL"
ROTULO_SEM_VOTO_INDIVIDUAL = "votacao registrada sem voto nominal no SAPL"
ROTULO_SEM_TRAMITACAO = "sem tramitacao registrada no SAPL"
ROTULO_VETADA_SEM_ESTRUTURA = "sem indicacao estruturada no SAPL, ver ementa"
SITUACAO_EM_TRAMITACAO = "Em tramitacao"
SITUACOES_FINAIS = ("Aprovado", "Rejeitado", SITUACAO_EM_TRAMITACAO)
GRUPOS = ("proposicoes", "executivo")
CHAVE_VOTOS_EXECUTIVO = "votos_plex"
CHAVE_PROPOSICOES_AUTORIA = "proposicoes_req_moc_ind"


def gravar_json(caminho: Path, dados) -> None:
    """Grava JSON em LF, como o resto da cadeia oficial."""
    escrever_lf(caminho, json.dumps(dados, ensure_ascii=False, indent=2) + "\n")


def pasta_tramitacao() -> Path:
    candidatas = sorted(
        caminho
        for caminho in DIR_BRUTOS.glob("lote_*_tramitacao")
        if caminho.is_dir() and (caminho / "indice.json").exists()
    )
    if not candidatas:
        raise SystemExit(
            "Nenhuma pasta de tramitacao em dados/brutos. Nada para consolidar."
        )
    return candidatas[-1]


def carregar_siglas_por_tipo(pasta_lote: Path, catalogo: dict[str, str]) -> dict[int, str]:
    """Sigla oficial de cada tipo de materia, lida do catalogo do SAPL.

    D-052: sigla e nome vem da tabela tipomaterialegislativa. Nao ha
    dicionario fixo no codigo. Sigla fora do catalogo oficial e erro.
    """
    achados = sorted(pasta_lote.glob("tipomaterialegislativa_p*.json"))
    if not achados:
        raise SystemExit(
            f"Tabela tipomaterialegislativa nao encontrada em {rel(pasta_lote)}."
        )
    saida: dict[int, str] = {}
    for caminho in achados:
        for item in carregar_json(caminho).get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            sigla = str(item.get("sigla") or "").strip()
            if not sigla:
                continue
            if sigla not in catalogo:
                raise SystemExit(
                    f"Tipo {sigla} fora do catalogo oficial do SAPL. "
                    "Nao vou inventar o nome do tipo."
                )
            saida[int(item["id"])] = sigla
    if not saida:
        raise SystemExit("Tabela tipomaterialegislativa sem sigla.")
    return saida


def carregar_fichas(pasta_lote: Path) -> dict[int, dict]:
    """Ficha da materia por id, do lote principal ja escolhido."""
    fichas: dict[int, dict] = {}
    for caminho in sorted(pasta_lote.glob("materialegislativa_ano*_p*.json")):
        for item in carregar_json(caminho).get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            mid = int(item["id"])
            fichas[mid] = {
                "id": mid,
                "numero": item.get("numero"),
                "ano": item.get("ano"),
                "tipo_id": (int(item["tipo"]) if item.get("tipo") is not None else None),
                "ementa": item.get("ementa") or "",
                "em_tramitacao": item.get("em_tramitacao"),
                "resultado_ficha_sapl": item.get("resultado") or "",
                "data_apresentacao": item.get("data_apresentacao"),
            }
    if not fichas:
        raise SystemExit(f"Nenhuma ficha de materialegislativa em {rel(pasta_lote)}.")
    return fichas


def carregar_status_unidades(pasta: Path) -> tuple[dict[int, dict], dict[int, str]]:
    status: dict[int, dict] = {}
    for caminho in sorted(pasta.glob("statustramitacao_p*.json")):
        for item in carregar_json(caminho).get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            status[int(item["id"])] = {
                "sigla": str(item.get("sigla") or ""),
                "descricao": str(item.get("descricao") or ""),
                "indicador": str(item.get("indicador") or ""),
            }
    unidades: dict[int, str] = {}
    for caminho in sorted(pasta.glob("unidadetramitacao_p*.json")):
        for item in carregar_json(caminho).get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            unidades[int(item["id"])] = str(item.get("__str__") or "")
    return status, unidades


def carregar_historico(pasta: Path) -> dict[int, list[dict]]:
    """Historico por materia, so com campos seguros (sem rede, sem usuario)."""
    historico: dict[int, list[dict]] = {}
    for caminho in sorted(pasta.glob("tramitacao_materia*_p*.json")):
        sufixo = caminho.name.split("_p", 1)[-1]
        if "_t" in sufixo:
            continue
        for item in carregar_json(caminho).get("results") or []:
            if not isinstance(item, dict) or item.get("materia") is None:
                continue
            mid = int(item["materia"])
            historico.setdefault(mid, []).append(
                {
                    "id": int(item["id"]),
                    "data_tramitacao": item.get("data_tramitacao"),
                    "data_encaminhamento": item.get("data_encaminhamento"),
                    "data_fim_prazo": item.get("data_fim_prazo"),
                    "status_id": (
                        int(item["status"]) if item.get("status") is not None else None
                    ),
                    "unidade_origem_id": (
                        int(item["unidade_tramitacao_local"])
                        if item.get("unidade_tramitacao_local") is not None
                        else None
                    ),
                    "unidade_destino_id": (
                        int(item["unidade_tramitacao_destino"])
                        if item.get("unidade_tramitacao_destino") is not None
                        else None
                    ),
                    "texto": item.get("texto") or "",
                    "urgente": bool(item.get("urgente")),
                    "turno": item.get("turno") or "",
                    "resumo_sapl": item.get("__str__") or "",
                }
            )
    return historico


def escolher_ultima(itens: list[dict]) -> dict | None:
    """Ultima situacao: maior data_tramitacao, desempate pelo maior id."""
    if not itens:
        return None

    def chave(item: dict):
        return (item.get("data_tramitacao") or "", int(item.get("id") or 0))

    return sorted(itens, key=chave)[-1]


def decodificar_status(status_id: int | None, tabela: dict[int, dict]) -> dict:
    if status_id is None:
        return {
            "id": None,
            "sigla": None,
            "descricao": None,
            "situacao": "nao informado no SAPL",
        }
    info = tabela.get(int(status_id))
    if info is None:
        return {
            "id": int(status_id),
            "sigla": None,
            "descricao": None,
            "situacao": "nao informado no SAPL",
        }
    indicador = (info.get("indicador") or "").strip().upper()
    if indicador == "F":
        situacao = "fim"
    elif indicador == "R":
        situacao = "em curso"
    else:
        situacao = "nao informado no SAPL"
    return {
        "id": int(status_id),
        "sigla": info.get("sigla") or None,
        "descricao": info.get("descricao") or None,
        "situacao": situacao,
    }


def montar_ultima_tramitacao(
    materia_id: int,
    historico: dict[int, list[dict]],
    status: dict[int, dict],
    unidades: dict[int, str],
) -> tuple[dict | None, str | None]:
    itens = historico.get(int(materia_id)) or []
    ultima = escolher_ultima(itens)
    if ultima is None:
        return None, ROTULO_SEM_TRAMITACAO
    decodificado = decodificar_status(ultima.get("status_id"), status)
    origem_id = ultima.get("unidade_origem_id")
    destino_id = ultima.get("unidade_destino_id")
    return {
        "data": ultima.get("data_tramitacao"),
        "status_id": decodificado["id"],
        "status_sigla": decodificado["sigla"],
        "status_descricao": decodificado["descricao"],
        "situacao": decodificado["situacao"],
        "unidade_origem_id": origem_id,
        "unidade_origem": unidades.get(int(origem_id)) if origem_id is not None else None,
        "unidade_destino_id": destino_id,
        "unidade_destino": unidades.get(int(destino_id)) if destino_id is not None else None,
        "texto": ultima.get("texto") or "",
        "urgente": bool(ultima.get("urgente")),
        "resumo_sapl": ultima.get("resumo_sapl") or "",
    }, None


def carregar_votacoes(anos: list[int]) -> dict[int, list[dict]]:
    """Votacoes ordinarias por materia, a partir da atuacao por ano."""
    por_materia: dict[int, list[dict]] = {}
    for ano in anos:
        caminho = DIR_SCRIPT / f"atuacao_vereadores_{int(ano)}.json"
        if not caminho.exists():
            raise SystemExit(f"Arquivo nao encontrado: {rel(caminho)}")
        dados = carregar_json(caminho)
        for votacao in dados.get("votacoes") or []:
            mid = votacao.get("materia_id")
            if mid is None:
                continue
            por_materia.setdefault(int(mid), []).append(votacao)
    return por_materia


def escolher_votacao(registros: list[dict]) -> dict | None:
    """Ultima votacao pelo criterio da atuacao. Vazio devolve None.

    Nao cria criterio novo: reusa a funcao de gerar_atuacao_vereadores e
    so protege a lista vazia, que aqui e caso normal de materia sem voto.
    """
    if not registros:
        return None
    return escolher_votacao_da_atuacao(registros)


def registro_deliberativo(votacao: dict) -> bool:
    """Deliberativo pela regra da atuacao, sem criar outra.

    O resultado vem do id do tipo de resultado do SAPL. Pedido de Vistas,
    materia adiada e retirada de pauta nao sao votacao. A atuacao so
    grava turno no registro deliberativo, entao turno vazio ja barra o
    registro.
    """
    if votacao.get("turno") is None:
        return False
    nome = votacao.get("tipo_resultado_nome")
    if nome:
        return deliberativa_nome(nome)
    return votacao.get("situacao_oficial_sapl") is not None


def voto_valido(votacao: dict) -> bool:
    """Voto que conta: registro deliberativo em 2o turno ou turno unico."""
    return registro_deliberativo(votacao) and votacao.get("turno") in TURNOS_CONTADOS


def votacoes_validas(registros: list[dict]) -> list[dict]:
    return [registro for registro in registros if voto_valido(registro)]


def situacao_final(registros: list[dict], sigla: str, dois_turnos: set[str]) -> str:
    """Situacao final com a regra da atuacao (D-049 e D-050).

    Rejeitado no 1o turno encerra como rejeitado. Com 2o turno, o 2o
    decide. So com 1o turno aprovado continua em tramitacao. Sem nenhum
    registro deliberativo continua em tramitacao.
    """
    deliberativos = [registro for registro in registros if registro_deliberativo(registro)]
    if sigla in dois_turnos:
        escolhida, em_tramitacao = escolher_por_turno(
            [(registro, registro.get("turno")) for registro in deliberativos]
        )
    else:
        escolhida = escolher_votacao(deliberativos) if deliberativos else None
        em_tramitacao = False
    if escolhida is None or em_tramitacao:
        return SITUACAO_EM_TRAMITACAO
    try:
        return situacao_da_votacao_escolhida(escolhida)
    except SystemExit as erro:
        raise SystemExit(f"{sigla}: {erro}") from erro


def montar_votacao(
    materia_id: int, votacoes: dict[int, list[dict]]
) -> tuple[dict | None, str | None]:
    """Votacao que define a materia, ou rotulo de ausencia.

    Escolhe a mais recente entre as validas. Materia sem voto valido
    devolve o rotulo, nunca aprovacao deduzida.
    """
    registros = votacoes.get(int(materia_id)) or []
    escolhida = escolher_votacao(votacoes_validas(registros))
    if escolhida is None:
        return None, ROTULO_SEM_VOTACAO
    totais = escolhida.get("totais_oficiais") or {}
    return {
        "data_sessao": escolhida.get("data_sessao"),
        "sessao_id": escolhida.get("sessao_id"),
        "registro_votacao_id": escolhida.get("id"),
        "turno": escolhida.get("turno"),
        "resultado_texto_sapl": escolhida.get("resultado_texto_sapl"),
        "situacao_oficial_sapl": escolhida.get("situacao_oficial_sapl"),
        "frase_resultado_sapl": escolhida.get("frase_resultado_sapl"),
        "tipo_resultado_nome": escolhida.get("tipo_resultado_nome"),
        "totais_oficiais": {
            "numero_votos_sim": totais.get("numero_votos_sim"),
            "numero_votos_nao": totais.get("numero_votos_nao"),
            "numero_abstencoes": totais.get("numero_abstencoes"),
        },
        "voto_individual_registrado": bool(escolhida.get("voto_individual_registrado")),
        "link_sessao": escolhida.get("link_sessao"),
        "link_materia": escolhida.get("link_materia"),
    }, None


def registrar_votacoes(registros: list[dict]) -> list[dict]:
    """Todas as votacoes da materia, para nada somir do historico.

    Voto sem deliberacao e 1o turno entram aqui como fato, com o nome
    oficial do SAPL, mas nunca como voto valido.
    """
    return [
        {
            "registro_votacao_id": registro.get("id"),
            "sessao_id": registro.get("sessao_id"),
            "data_sessao": registro.get("data_sessao"),
            "turno": registro.get("turno"),
            "deliberativa": registro_deliberativo(registro),
            "voto_valido": voto_valido(registro),
            "tipo_resultado_nome": registro.get("tipo_resultado_nome"),
            "situacao_oficial_sapl": registro.get("situacao_oficial_sapl"),
            "resultado_texto_sapl": registro.get("resultado_texto_sapl"),
            "frase_resultado_sapl": registro.get("frase_resultado_sapl"),
            "link_sessao": registro.get("link_sessao"),
            "link_materia": registro.get("link_materia"),
        }
        for registro in sorted(
            registros,
            key=lambda item: (
                item.get("data_sessao") or "",
                item.get("data_hora") or "",
                int(item.get("id") or 0),
            ),
        )
    ]


def votos_nominais(registro: dict | None, vereadores: dict[int, dict]) -> list[dict]:
    """Votos nominais do voto valido, so de quem estava no mandato.

    Mesma regra da atuacao: a data da sessao precisa cair dentro do
    mandato da pessoa, pelas datas da tabela de vereadores.
    """
    if registro is None:
        return []
    data = str(registro.get("data_sessao") or "")
    saida = []
    for linha in registro.get("estados_por_vereador") or []:
        pid = linha.get("id_sapl")
        if pid is None:
            continue
        pessoa = vereadores.get(int(pid))
        if pessoa is None:
            raise SystemExit(
                f"Vereador {pid} da votacao {registro.get('id')} "
                "fora da tabela de vereadores."
            )
        if not dentro_do_mandato(pessoa, data):
            continue
        saida.append(
            {
                "parlamentar_id_sapl": int(pid),
                "nome_parlamentar": (
                    pessoa.get("nome_parlamentar") or linha.get("nome_parlamentar") or ""
                ),
                "estado": linha.get("estado"),
                "rotulo": linha.get("rotulo"),
                "turno": registro.get("turno"),
                "voto_texto_sapl": linha.get("voto_texto_sapl"),
                "data_sessao": registro.get("data_sessao"),
                "sessao_id": registro.get("sessao_id"),
                "link_sessao": registro.get("link_sessao"),
                "link_materia": registro.get("link_materia"),
            }
        )
    saida.sort(key=lambda item: item.get("nome_parlamentar") or "")
    return saida


def autores_vereadores(
    materia_id: int, autoria: dict[int, list[dict]], vereadores: dict[int, dict]
) -> list[dict]:
    saida = []
    for item in autoria.get(int(materia_id)) or []:
        pid = item.get("parlamentar_id_sapl")
        if pid is None:
            continue
        pessoa = vereadores.get(int(pid))
        saida.append(
            {
                "parlamentar_id_sapl": int(pid),
                "nome_parlamentar": (pessoa or {}).get("nome_parlamentar")
                or item.get("nome_no_sapl")
                or "",
                "nome_no_sapl": item.get("nome_no_sapl") or "",
                "primeiro_autor": item.get("primeiro_autor"),
            }
        )
    return saida


def carregar_vereadores() -> dict[int, dict]:
    dados = carregar_json(DIR_SCRIPT / "vereadores.json")
    return {int(v["id_sapl"]): v for v in dados.get("vereadores") or []}


class Base:
    """Agrupa o que vem do SAPL e do config para montar os dois grupos."""

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.pasta_lote = pasta_lote_mais_recente(BRUTOS)
        self.catalogo, self.fonte_catalogo = carregar_catalogo_tipos_materia()
        self.siglas_por_tipo = carregar_siglas_por_tipo(self.pasta_lote, self.catalogo)
        self.fichas = carregar_fichas(self.pasta_lote)
        self.indice_temas = carregar_temas()
        self.autoria = {
            int(materia_id): (materia.get("autorias") or [])
            for materia_id, materia in carregar_autoria().items()
        }
        self.vereadores = carregar_vereadores()
        self.por_sigla = self._agrupar_por_sigla()

    def _agrupar_por_sigla(self) -> dict[str, list[int]]:
        agrupado: dict[str, list[int]] = {}
        for mid, ficha in self.fichas.items():
            tipo_id = ficha.get("tipo_id")
            sigla = (
                self.siglas_por_tipo.get(int(tipo_id)) if tipo_id is not None else None
            )
            if sigla:
                agrupado.setdefault(str(sigla), []).append(int(mid))
        return agrupado

    def sigla_da_materia(self, materia_id: int) -> str:
        tipo_id = (self.fichas.get(int(materia_id)) or {}).get("tipo_id")
        if tipo_id is None:
            return ""
        return self.siglas_por_tipo.get(int(tipo_id)) or ""

    def montar(
        self,
        materia_id: int,
        sigla: str,
        grupo: str,
        historico: dict[int, list[dict]],
        status: dict[int, dict],
        unidades: dict[int, str],
        votacoes: dict[int, list[dict]],
        dois_turnos: set[str],
    ) -> dict:
        ficha = self.fichas.get(int(materia_id)) or {}
        numero = ficha.get("numero")
        ano = ficha.get("ano")
        registros = votacoes.get(int(materia_id)) or []
        ultima, rotulo_tram = montar_ultima_tramitacao(
            int(materia_id), historico, status, unidades
        )
        votacao, rotulo_vot = montar_votacao(int(materia_id), votacoes)
        tema, revisada = tema_da_materia(int(materia_id), self.indice_temas)
        valida = escolher_votacao(votacoes_validas(registros))
        nominais = votos_nominais(valida, self.vereadores)
        if nominais:
            rotulo_nominal = None
        elif votacao is None:
            rotulo_nominal = ROTULO_SEM_VOTACAO
        else:
            rotulo_nominal = ROTULO_SEM_VOTO_INDIVIDUAL
        item = {
            "id": int(materia_id),
            "tipo_sigla": sigla,
            "tipo_nome": self.catalogo.get(sigla),
            "tipo": f"{sigla} {numero}/{ano}",
            "numero": str(numero) if numero is not None else None,
            "ano": str(ano) if ano is not None else None,
            "ementa": ficha.get("ementa") or "",
            "tema": tema,
            "revisada_por_humano": revisada,
            "autores": autores_vereadores(
                int(materia_id), self.autoria, self.vereadores
            ),
            "situacao_final": situacao_final(registros, sigla, dois_turnos),
            "em_tramitacao": ficha.get("em_tramitacao"),
            "resultado_ficha_sapl": ficha.get("resultado_ficha_sapl"),
            "ultima_tramitacao": ultima,
            "ultima_tramitacao_rotulo": rotulo_tram,
            "votacoes_registradas": registrar_votacoes(registros),
            "votacao": votacao,
            "votacao_rotulo": rotulo_vot,
            "votos_nominais": nominais,
            "votos_nominais_rotulo": rotulo_nominal,
            "link_sapl": link_materia(int(materia_id), self.cfg),
        }
        if grupo == "executivo":
            item["materia_vetada_id"] = None
            item["materia_vetada_rotulo"] = ROTULO_VETADA_SEM_ESTRUTURA
        return item


def sessoes_do_ano(ano: int) -> list[dict]:
    caminho = DIR_SCRIPT / f"atuacao_vereadores_{int(ano)}.json"
    if not caminho.exists():
        raise SystemExit(f"Arquivo nao encontrado: {rel(caminho)}")
    return carregar_json(caminho).get("sessoes") or []


def dividir_periodos(lista: list[dict], sessoes: list[dict]) -> tuple[list, list, list]:
    """Sessao, mes e todo, com a mesma regra de datas de gerar_dados_tela.

    O corte e feito pela votacao que define a materia. Item sem votacao
    fica so no todo. Nada e estimado.
    """
    if not lista:
        return [], [], []
    datas = sorted({s["data"] for s in sessoes if s.get("data")})
    ultima_data = datas[-1] if datas else None
    sessao_ids_ultima = {s["id"] for s in sessoes if s.get("data") == ultima_data}
    if ultima_data:
        ano_ultima, mes_ultima, _dia = map(int, ultima_data.split("-"))
        mes_ant = mes_ultima - 1
        ano_ant = ano_ultima
        if mes_ant < 1:
            mes_ant = 12
            ano_ant -= 1
    else:
        ano_ant, mes_ant = 0, 0

    def no_mes_anterior(item: dict) -> bool:
        data = str((item.get("votacao") or {}).get("data_sessao") or "")
        partes = data.split("-")
        return (
            len(partes) == 3
            and partes[0] == str(ano_ant)
            and int(partes[1]) == mes_ant
        )

    sessao = [
        item
        for item in lista
        if (item.get("votacao") or {}).get("sessao_id") in sessao_ids_ultima
    ]
    mes = [item for item in lista if no_mes_anterior(item)]
    return sessao, mes, list(lista)


def conferir_periodos(blocos: tuple[list, list, list], total: int) -> None:
    sessao, mes, todo = blocos
    if len(todo) != total:
        raise SystemExit(f"Todo com {len(todo)} itens de {total}.")
    if len({item["id"] for item in todo}) != len(todo):
        raise SystemExit("Id de materia repetido no todo.")
    ids_do_todo = {item["id"] for item in todo}
    for bloco in (sessao, mes):
        fora = [item["id"] for item in bloco if item["id"] not in ids_do_todo]
        if fora:
            raise SystemExit(f"Item de periodo ausente no todo: {fora}")


def meta_de(
    grupo: str,
    escopo: dict,
    anos: list[int],
    pasta: Path,
    decodificados: int,
    itens: list[dict],
) -> dict:
    return {
        "gerado_por": SCRIPT_REL,
        **escopo,
        "grupo": grupo,
        "total": len(itens),
        "fonte_tramitacao": rel(pasta),
        "fonte_atuacao": [
            rel(DIR_SCRIPT / f"atuacao_vereadores_{int(ano)}.json") for ano in anos
        ],
        "status_decodificados": decodificados,
        "por_tipo_sigla": dict(
            sorted(Counter(item["tipo_sigla"] for item in itens).items())
        ),
        "por_situacao_final": {
            situacao: sum(1 for item in itens if item["situacao_final"] == situacao)
            for situacao in SITUACOES_FINAIS
        },
        "itens_com_votacao_valida": sum(1 for item in itens if item["votacao"] is not None),
        "itens_sem_votacao_valida": sum(1 for item in itens if item["votacao"] is None),
        "votos_nominais_registrados": sum(len(item["votos_nominais"]) for item in itens),
        "rotulo_sem_votacao": ROTULO_SEM_VOTACAO,
        "rotulo_sem_voto_individual": ROTULO_SEM_VOTO_INDIVIDUAL,
        "rotulo_sem_tramitacao": ROTULO_SEM_TRAMITACAO,
        "observacao": (
            "Votacao e votos nominais saem so do voto valido: 2o turno ou "
            "turno unico, e so registro deliberativo, lido pelo id do tipo "
            "de resultado do SAPL. Pedido de Vistas, materia adiada e "
            "retirada de pauta nao sao votacao e ficam como fato de "
            "tramitacao. Materia votada so no 1o turno continua em "
            "tramitacao. Voto nominal so entra de quem estava no mandato "
            "na data da sessao. Ausencia de registro recebe rotulo: "
            "nenhuma aprovacao e deduzida."
        ),
    }


def montar_arquivo(
    grupo: str,
    escopo: dict,
    anos: list[int],
    itens: list[dict],
    sessoes: list[dict],
    pasta: Path,
    decodificados: int,
) -> dict:
    sessao, mes, todo = dividir_periodos(itens, sessoes)
    conferir_periodos((sessao, mes, todo), len(itens))
    for bloco in (sessao, mes, todo):
        for item in bloco:
            recusar_ip(item)
    return {
        "meta": meta_de(grupo, escopo, anos, pasta, decodificados, todo),
        "sessao": sessao,
        "mes": mes,
        "todo": todo,
    }


def ordenar(itens: list[dict], por_ano: bool) -> list[dict]:
    return sorted(
        itens,
        key=lambda item: (
            (str(item.get("ano") or "") if por_ano else ""),
            item.get("tipo_sigla") or "",
            str(item.get("numero") or ""),
            item.get("id") or 0,
        ),
    )


def gerar_arquivos(cfg: dict) -> dict:
    anos = anos_recorte(cfg)
    dois_turnos = tipos_dois_turnos(cfg)
    base = Base(cfg)
    pasta = pasta_tramitacao()
    status, unidades = carregar_status_unidades(pasta)
    decodificados = len(status)
    piso = piso_status_decodificados(cfg)
    if decodificados < piso:
        raise SystemExit(
            f"Status decodificados: {decodificados}. O piso minimo e {piso}."
        )
    historico = carregar_historico(pasta)
    votacoes = carregar_votacoes(anos)
    siglas_por_grupo = {
        "proposicoes": tipos_proposicoes(cfg),
        "executivo": tipos_executivo(cfg),
    }
    resumo: dict = {
        "anos": anos,
        "fonte_catalogo_tipos": base.fonte_catalogo,
        "status_decodificados": decodificados,
        "por_tipo": {},
        "por_situacao_final": {},
    }
    sessoes_de_ano = {int(ano): sessoes_do_ano(int(ano)) for ano in anos}
    todas_sessoes: list[dict] = []
    for ano in anos:
        todas_sessoes.extend(sessoes_de_ano[int(ano)])
    for grupo in GRUPOS:
        do_grupo: list[dict] = []
        for sigla in siglas_por_grupo[grupo]:
            for mid in base.por_sigla.get(str(sigla), []):
                do_grupo.append(
                    base.montar(
                        int(mid),
                        str(sigla),
                        grupo,
                        historico,
                        status,
                        unidades,
                        votacoes,
                        dois_turnos,
                    )
                )
        do_grupo = ordenar(do_grupo, por_ano=True)
        arquivo = montar_arquivo(
            grupo,
            {"anos": anos, "escopo": "legislatura"},
            anos,
            do_grupo,
            todas_sessoes,
            pasta,
            decodificados,
        )
        gravar_json(DIR_SCRIPT / f"{grupo}_legislatura.json", arquivo)
        resumo["por_tipo"].setdefault(grupo, {})["legislatura"] = len(do_grupo)
        resumo["por_situacao_final"].setdefault(grupo, {})["legislatura"] = arquivo[
            "meta"
        ]["por_situacao_final"]
        print(f"{grupo} legislatura: todo={len(do_grupo)}")
        for ano in anos:
            do_ano = ordenar(
                [item for item in do_grupo if item.get("ano") == str(ano)],
                por_ano=False,
            )
            arquivo_ano = montar_arquivo(
                grupo,
                {"ano": int(ano)},
                anos,
                do_ano,
                sessoes_de_ano[int(ano)],
                pasta,
                decodificados,
            )
            gravar_json(DIR_SCRIPT / f"{grupo}_{int(ano)}.json", arquivo_ano)
            resumo["por_tipo"].setdefault(grupo, {})[str(ano)] = len(do_ano)
            resumo["por_situacao_final"].setdefault(grupo, {})[str(ano)] = arquivo_ano[
                "meta"
            ]["por_situacao_final"]
            print(f"{grupo} {ano}: todo={len(do_ano)}")
    return resumo


def complementar_legislatura(cfg: dict) -> None:
    """Acrescenta por vereador proposicoes de autoria e votos no Executivo.

    O recorte das materias vem do config. Os votos vem do historico de
    votos validos da atuacao, que ja e o voto valido. Nao toca nos
    arquivos por ano. So reescreve o da legislatura.
    """
    anos = anos_recorte(cfg)
    base = Base(cfg)
    destino = DIR_SCRIPT / "atuacao_vereadores_legislatura.json"
    if not destino.exists():
        raise SystemExit(f"Arquivo nao encontrado: {rel(destino)}")
    consolidado = carregar_json(destino)
    siglas_exec = set(tipos_executivo(cfg))
    siglas_prop_autoria = [
        sigla for sigla in tipos_proposicoes(cfg) if sigla not in siglas_exec
    ]

    for vereador in consolidado.get("vereadores") or []:
        pid = int(vereador["id_sapl"])
        lista_prop = []
        for mid, autores in base.autoria.items():
            if not any(
                autor.get("parlamentar_id_sapl") is not None
                and int(autor["parlamentar_id_sapl"]) == pid
                for autor in autores
            ):
                continue
            sigla = base.sigla_da_materia(int(mid))
            if sigla not in siglas_prop_autoria:
                continue
            ficha = base.fichas.get(int(mid)) or {}
            tema, _revisada = tema_da_materia(int(mid), base.indice_temas)
            lista_prop.append(
                {
                    "id": int(mid),
                    "tipo_sigla": sigla,
                    "tipo_nome": base.catalogo.get(sigla),
                    "numero": (
                        str(ficha.get("numero"))
                        if ficha.get("numero") is not None
                        else None
                    ),
                    "ano": str(ficha.get("ano")) if ficha.get("ano") is not None else None,
                    "ementa": ficha.get("ementa") or "",
                    "tema": tema,
                    "link_sapl": link_materia(int(mid), cfg),
                }
            )
        lista_prop = ordenar(lista_prop, por_ano=True)
        por_tipo: dict[str, int] = {}
        for item in lista_prop:
            por_tipo[item["tipo_sigla"]] = por_tipo.get(item["tipo_sigla"], 0) + 1
        vereador[CHAVE_PROPOSICOES_AUTORIA] = {
            "total": len(lista_prop),
            "por_tipo": por_tipo,
            "lista": lista_prop,
        }
        votos_exec = []
        for nominal in (vereador.get("votos") or {}).get("nominais") or []:
            mid = nominal.get("materia_id")
            if mid is None:
                continue
            sigla = base.sigla_da_materia(int(mid))
            if sigla not in siglas_exec:
                continue
            votos_exec.append(
                {
                    "materia_id": int(mid),
                    "tipo_sigla": sigla,
                    "tipo_nome": base.catalogo.get(sigla),
                    "estado": nominal.get("estado"),
                    "rotulo": nominal.get("rotulo"),
                    "turno": nominal.get("turno"),
                    "voto_texto_sapl": nominal.get("voto_texto_sapl"),
                    "data_sessao": nominal.get("data_sessao"),
                    "sessao_id": nominal.get("sessao_id"),
                    "link_sessao": nominal.get("link_sessao"),
                    "link_materia": nominal.get("link_materia"),
                }
            )
        votos_exec.sort(
            key=lambda item: (
                item.get("data_sessao") or "",
                item.get("materia_id") or 0,
            )
        )
        vereador[CHAVE_VOTOS_EXECUTIVO] = votos_exec
    recusar_ip(consolidado)
    meta = consolidado.get("meta") or {}
    meta["proposicoes_executivo_por"] = SCRIPT_REL
    meta["proposicoes_executivo_anos"] = anos
    meta["proposicoes_executivo_tipos_executivo"] = sorted(siglas_exec)
    meta["proposicoes_executivo_tipos_proposicoes_autoria"] = sorted(siglas_prop_autoria)
    meta["proposicoes_executivo_rotulo_sem_voto_valido"] = ROTULO_SEM_VOTACAO
    consolidado["meta"] = meta
    gravar_json(destino, consolidado)
    print(
        f"Legislatura complementada: {len(consolidado.get('vereadores') or [])} vereadores."
    )


def main() -> int:
    cfg = carregar_config()
    print(f"Consolidacao de proposicoes e Executivo (C9). Fonte: {endereco_sapl(cfg)}")
    gerar_arquivos(cfg)
    complementar_legislatura(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())