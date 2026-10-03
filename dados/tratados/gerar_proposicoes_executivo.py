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
    dados/tratados/vetos_revisados.json (vinculo veto e materia, revisado
    pelo mantenedor; opcional, mesmo espirito de temas_materias.json)
    dados/tratados/autoria_materias.json (autores vereadores)
    dados/tratados/vereadores.json (nomes e mandatos)
    dados/tratados/atuacao_vereadores_<ano>.json (votacoes ordinarias)

Por materia do Executivo (D-058) acrescentamos mais tres coisas, sempre do
SAPL e nunca deduzidas:

    votacao_tipo do voto valido, pelo campo tipo_votacao do item da Ordem do
    Dia ligado ao registro de votacao (votacao_tipo);
    tipo e situacao do veto, pelo começo da ementa oficial e pelo resultado do
    voto valido do proprio veto (veto_tipo e veto_situacao);
    materia_vetada_id, com a materia vetada que o veto aponta. A origem fica
    em materia_vetada_fonte: revisao_mantenedor quando o vinculo vem do
    arquivo vetos_revisados.json, que e decisao do mantenedor e tem
    prioridade; automatica quando os dois criterios automaticos batem ao
    mesmo tempo, numero e ano citados na ementa (sem zero a esquerda)
    levando a materia de projeto de lei e texto da sumula parecendo com a
    ementa dela (similaridade de token de 0,85 para cima, valor medido em
    materia_vetada_similaridade); pendente_revisao quando nenhum dos dois
    vira vinculo, e nesse caso o campo fica nulo.

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

import difflib
import json
import re
import sys
import unicodedata
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
    tipos_veto,
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
ROTULO_SEM_VOTO_VALIDO = "votacao registrada sem voto valido (so 1o turno ou sem deliberacao)"
ROTULO_SEM_VOTO_INDIVIDUAL = "votacao registrada sem voto nominal no SAPL"
ROTULO_SEM_TRAMITACAO = "sem tramitacao registrada no SAPL"
ROTULO_VETADA_SEM_ESTRUTURA = "sem indicacao estruturada no SAPL, ver ementa"
ROTULO_VETADA_REVISADA = "vinculo revisado pelo mantenedor"
ROTULO_VETADA_AUTOMATICA = "numero e texto da ementa levam a uma unica materia do SAPL"
ROTULO_VETADA_PENDENTE = "vinculo do veto pendente de revisao do mantenedor"
SITUACAO_EM_TRAMITACAO = "Em tramitacao"
SITUACAO_SEM_REGISTRO = "Sem registro de votação nem de tramitação no SAPL"
SITUACAO_STATUS_SEM_TEXTO = "status de tramitacao sem texto oficial no SAPL"
VOTACAO_TIPO_NOMINAL = "nominal"
VOTACAO_TIPO_SIMBOLICA = "simbolica"
VOTACAO_TIPO_NAO_INFORMADO = "nao informado no SAPL"
VETO_TIPO_TOTAL = "total"
VETO_TIPO_PARCIAL = "parcial"
VETO_TIPO_NAO_INFORMADO = "nao informado"
VETO_DERRUBADO = "Veto derrubado"
VETO_MANTIDO = "Veto mantido"
VETO_AINDA_VAI_VOTAR = "Camara ainda vai votar"
FONTE_VETADA_AUTOMATICA = "automatica"
FONTE_VETADA_REVISAO = "revisao_mantenedor"
FONTE_VETADA_PENDENTE = "pendente_revisao"
LIMIAR_SIMILARIDADE_VETO = 0.85
ARQUIVO_VETOS_REVISADOS = DIR_SCRIPT / "vetos_revisados.json"
PREFIXOS_VETO = (
    ("VETO INTEGRAL", VETO_TIPO_TOTAL),
    ("VETO TOTAL", VETO_TIPO_TOTAL),
    ("VETO PARCIAL", VETO_TIPO_PARCIAL),
)
PREFIXO_PROJETO = "PROJETO DE LEI"
MARCA_SUMULA = "sumula"
REFERENCIA_PROJETO = re.compile(
    r"(?:\bPROJETO\s+DE\s+LEI|\bPL)\s*(?:N[.º°]?\s*)?(\d{1,4})"
    r"(?:\s*(?:[,/\-]\s*)?DE\s+|\s*/\s*)(\d{4})?"
)
FONTE_VOTACAO = "votacao"
FONTE_TRAMITACAO = "tramitacao"
FONTE_FICHA = "ficha_sapl"
FONTE_SEM_REGISTRO = "sem_registro"
FONTES_SITUACAO = (FONTE_VOTACAO, FONTE_TRAMITACAO, FONTE_FICHA, FONTE_SEM_REGISTRO)
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


def sem_acento(texto) -> str:
    """Texto em maiuscula e sem acento, para comparar com a grafia do SAPL."""
    return "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(caractere) != "Mn"
    ).upper()


def carregar_tipos_votacao_oficial() -> dict[int, str]:
    """Nome oficial de cada tipo de votacao, se a tabela estiver nos brutos.

    D-058: quando existe a tabela tipovotacao do SAPL, o codigo do item da
    Ordem do Dia vira rotulo pelo texto oficial. Sem tabela, a funcao
    devolve vazio e quem decide o rotulo e o proprio registro de votacao.
    """
    achados: list[Path] = []
    for pasta in sorted(DIR_BRUTOS.glob("lote_*")):
        if pasta.is_dir():
            achados.extend(sorted(pasta.glob("tipovotacao_p*.json")))
    achados.extend(sorted(DIR_BRUTOS.glob("tipovotacao_p*.json")))
    saida: dict[int, str] = {}
    for caminho in achados:
        for item in carregar_json(caminho).get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            nome = str(item.get("nome") or item.get("descricao") or "").strip()
            if nome:
                saida[int(item["id"])] = nome
    return saida


def carregar_ordens_do_dia() -> dict[tuple[int, int], dict]:
    """Item da Ordem do Dia por (sessao, id do item), dos brutos por sessao.

    D-058: o proprio SAPL faz a ligacao. O registro de votacao traz o id do
    item da ordem no campo ordem, e o item traz o campo tipo_votacao. Nada
    e casado por numero de materia nem por data.
    """
    saida: dict[tuple[int, int], dict] = {}
    for caminho in sorted(DIR_BRUTOS.glob("sessao_*_ordemdia.json")):
        partes = caminho.name.split("_")
        try:
            sessao_id = int(partes[1])
        except (IndexError, ValueError):
            continue
        for item in carregar_json(caminho).get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            saida[(sessao_id, int(item["id"]))] = {
                "tipo_votacao": item.get("tipo_votacao"),
                "resultado_item_sapl": item.get("resultado") or "",
            }
    if not saida:
        raise SystemExit(
            "Nenhum item de Ordem do Dia em dados/brutos. "
            "O tipo de votacao nao pode ser lido."
        )
    return saida


def codigo_do_item_da_ordem(registro: dict, ordens: dict[tuple[int, int], dict]):
    """Codigo tipo_votacao do item da Ordem do Dia ligado a uma votacao."""
    if not ordens:
        return None
    sessao_id = registro.get("sessao_id")
    if sessao_id is None or registro.get("ordem") is None:
        return None
    item = ordens.get((int(sessao_id), int(registro["ordem"])))
    if item is None:
        return None
    codigo = item.get("tipo_votacao")
    return int(codigo) if codigo is not None else None


def rotulo_do_nome_oficial(nome: str) -> str:
    """Rotulo de votacao pelo nome oficial da tabela tipovotacao do SAPL."""
    texto = sem_acento(nome)
    if texto.startswith("NOMINAL"):
        return VOTACAO_TIPO_NOMINAL
    if texto.startswith("SIMB"):
        return VOTACAO_TIPO_SIMBOLICA
    return VOTACAO_TIPO_NAO_INFORMADO


def rotulos_votacao_confirmados(
    votacoes: dict[int, list[dict]],
    ordens: dict[tuple[int, int], dict],
    oficial: dict[int, str],
) -> dict[int, str]:
    """Rotulo de cada codigo tipo_votacao, confirmado pelos proprios votos.

    D-058: a tabela oficial tem prioridade. Sem ela, o codigo so vira rotulo
    quando os votos validos ligados a ele concordam entre si: todo voto com
    voto individual registrado e nominal, todo voto sem voto individual e
    simbolica. Codigo sem votacao valida ligado, ou com evidencia que se
    contradiz, fica de fora do mapa e vira nao informado no SAPL.
    """
    if oficial:
        saida: dict[int, str] = {}
        for codigo, nome in oficial.items():
            rotulo = rotulo_do_nome_oficial(nome)
            if rotulo != VOTACAO_TIPO_NAO_INFORMADO:
                saida[int(codigo)] = rotulo
        return saida
    evidencia: dict[int, set[bool]] = {}
    for registros in votacoes.values():
        for registro in registros:
            if not voto_valido(registro):
                continue
            codigo = codigo_do_item_da_ordem(registro, ordens)
            if codigo is None:
                continue
            estado = bool(registro.get("voto_individual_registrado"))
            evidencia.setdefault(codigo, set()).add(estado)
    saida: dict[int, str] = {}
    for codigo, estados in evidencia.items():
        if len(estados) != 1:
            continue
        saida[codigo] = (
            VOTACAO_TIPO_NOMINAL
            if next(iter(estados))
            else VOTACAO_TIPO_SIMBOLICA
        )
    return saida


def votacao_tipo_de(
    registro: dict | None,
    ordens: dict[tuple[int, int], dict],
    rotulos: dict[int, str],
) -> str:
    """Rotulo do tipo de votacao do voto valido. Ausencia vira rotulo."""
    if registro is None:
        return VOTACAO_TIPO_NAO_INFORMADO
    codigo = codigo_do_item_da_ordem(registro, ordens)
    if codigo is None:
        return VOTACAO_TIPO_NAO_INFORMADO
    return rotulos.get(int(codigo), VOTACAO_TIPO_NAO_INFORMADO)


def veto_tipo_de(ementa: str) -> str:
    """Integral, parcial ou nao informado, pelo começo da ementa oficial.

    Nao ha dicionario de veto no codigo: o rotulo vem da frase que o SAPL
    escreveu na ementa. Ementa que nao comeca com nenhuma delas fica como
    nao informado.
    """
    texto = sem_acento(ementa).strip()
    for prefixo, rotulo in PREFIXOS_VETO:
        if texto.startswith(prefixo):
            return rotulo
    return VETO_TIPO_NAO_INFORMADO


def veto_situacao_de(votacao: dict | None) -> str:
    """Situacao do veto pelo resultado do voto valido do proprio veto.

    Rejeitado derruba o veto, Aprovado mantem. Sem voto valido, a Camara
    ainda vai votar. Nenhum outro resultado e deduzido: o script para.
    """
    if votacao is None:
        return VETO_AINDA_VAI_VOTAR
    oficial = votacao.get("situacao_oficial_sapl")
    if oficial == "Rejeitado":
        return VETO_DERRUBADO
    if oficial == "Aprovado":
        return VETO_MANTIDO
    raise SystemExit(
        f"Voto do veto {votacao.get('registro_votacao_id')} com resultado "
        f"'{oficial}', fora de Aprovado e Rejeitado. Nao vou deduzir a "
        "situacao do veto."
    )


def numero_normalizado(numero) -> str:
    """Numero de materia sem zero a esquerda. A ementa do SAPL escreve 008/2025.

    A ficha e a ementa precisam apontar para a mesma chave: sem isso, um
    veto com numero com zero a esquerda nunca encontraria a materia.
    """
    texto = str(numero or "").strip()
    if texto.isdigit():
        return str(int(texto))
    return texto


def referencia_da_ementa(ementa: str) -> tuple[str | None, str | None]:
    """Numero e ano do projeto citado na ementa do veto, ou (None, None)."""
    achado = REFERENCIA_PROJETO.search(sem_acento(ementa))
    if achado is None:
        return None, None
    return achado.group(1), achado.group(2)


def normaliza_texto(texto) -> str:
    """Minuscula, sem acento, so palavra e numero, com espaco unico.

    E o texto que entra na comparacao do veto com o projeto. A grafia
    exata da ementa do SAPL muda entre um registro e outro, por isso a
    comparacao nao usa a string original.
    """
    base = re.sub(r"[^a-z0-9]+", " ", sem_acento(texto).lower())
    return " ".join(base.split())


def texto_da_sumula(ementa: str) -> str:
    """Texto do veto, depois da marca sumula que o SAPL escreve na ementa.

    A ementa do veto vem como "Veto Parcial ao PROJETO DE LEI Nº 013, DE
    2025 - Sumula: <texto>". Sem a marca, a ementa inteira e o texto.
    """
    partes = normaliza_texto(ementa).split(MARCA_SUMULA)
    if len(partes) > 1:
        return partes[-1].strip()
    return normaliza_texto(ementa)


def similaridade(primeiro: str, segundo: str) -> float:
    """Semelhanca de dois textos ja normalizados, de 0 a 1.

    Token a token, na ordem em que aparecem. Vem da biblioteca padrao do
    Python: nenhum pacote novo e nenhum numero fora do codigo.
    """
    if not primeiro or not segundo:
        return 0.0
    return difflib.SequenceMatcher(
        None, primeiro.split(), segundo.split()
    ).ratio()


def e_projeto_de_lei(
    ficha: dict, siglas_por_tipo: dict[int, str], catalogo: dict[str, str]
) -> bool:
    """Projeto de lei pelo nome oficial do tipo, lido do catalogo do SAPL.

    Nao ha sigla fixa no codigo: o nome vem da tabela tipomaterialegislativa.
    """
    tipo_id = ficha.get("tipo_id")
    sigla = siglas_por_tipo.get(int(tipo_id)) if tipo_id is not None else None
    return PREFIXO_PROJETO in sem_acento(catalogo.get(str(sigla or ""), ""))


def indexar_projetos(
    fichas: dict[int, dict], siglas_por_tipo: dict[int, str], catalogo: dict[str, str]
) -> tuple[dict[str, list[int]], dict[int, str]]:
    """Dois indices dos projetos de lei: por ano e numero, e ementa limpa.

    D-058: o SAPL repete numero entre tipos, entao a busca por ano e numero
    pode trazer mais de uma materia. Ementa normalizada serve para a
    comparacao de texto do veto com o do projeto.
    """
    por_ano_numero: dict[str, list[int]] = {}
    ementas: dict[int, str] = {}
    for materia_id, ficha in sorted(fichas.items()):
        if not e_projeto_de_lei(ficha, siglas_por_tipo, catalogo):
            continue
        ementa = normaliza_texto(ficha.get("ementa") or "")
        if ementa:
            ementas[int(materia_id)] = ementa
        numero = numero_normalizado(ficha.get("numero"))
        ano = str(ficha.get("ano") or "").strip()
        if not numero or not ano:
            continue
        por_ano_numero.setdefault(f"{ano}|{numero}", []).append(int(materia_id))
    return por_ano_numero, ementas


def carregar_vetos_revisados(caminho: Path) -> dict[int, int]:
    """Vinculo veto -> materia vetada decidido pelo mantenedor (D-058).

    Arquivo opcional, no mesmo espirito de temas_materias.json: quem escreve
    e o mantenedor, e o gerador so le. Cada entrada precisa dizer quem
    revisou, quando e com que criterio. Veto repetido, id ausente ou
    entrada sem revisao humana e erro: melhor parar do que publicar um
    vinculo sem rastro.
    """
    if not caminho.exists():
        return {}
    dados = carregar_json(caminho)
    itens = dados if isinstance(dados, list) else dados.get("vetoes") or []
    saida: dict[int, int] = {}
    for entrada in itens:
        if not isinstance(entrada, dict):
            raise SystemExit(f"{rel(caminho)}: entrada de veto nao e um objeto.")
        veto_id = entrada.get("veto_id")
        materia_id = entrada.get("materia_vetada_id")
        if veto_id is None or materia_id is None:
            raise SystemExit(
                f"{rel(caminho)}: entrada sem veto_id ou materia_vetada_id."
            )
        if entrada.get("revisada_por_humano") is not True:
            raise SystemExit(
                f"{rel(caminho)}: veto {veto_id} sem revisao humana registrada."
            )
        for campo in ("revisado_por", "data_revisao", "criterio"):
            if not str(entrada.get(campo) or "").strip():
                raise SystemExit(f"{rel(caminho)}: veto {veto_id} sem {campo}.")
        if int(veto_id) in saida:
            raise SystemExit(f"{rel(caminho)}: veto {veto_id} repetido.")
        saida[int(veto_id)] = int(materia_id)
    return saida


def materia_vetada(
    veto_id: int,
    ementa: str,
    revisados: dict[int, int],
    por_ano_numero: dict[str, list[int]],
    ementas_de_projeto: dict[int, str],
) -> tuple[int | None, str, float | None]:
    """Materia vetada, a fonte do vinculo e a semelhanca medida.

    D-058, em ordem de prioridade:

    1. revisao do mantenedor em vetos_revisados.json: e decisao humana e
       manda, sem conferenca automatica;
    2. regra automatica, que exige os dois criterios juntos: o numero e o
       ano citados na ementa do veto, sem zero a esquerda, precisam levar a
       materia de projeto de lei, e o texto da sumula do veto precisa
       parecer com a ementa dela (similaridade de token acima do limiar);
    3. qualquer outra coisa fica nula, com materia_vetada_fonte
       pendente_revisao. Um criterio sozinho, ou mais de um candidato,
       nunca vira vinculo.
    """
    if int(veto_id) in revisados:
        return int(revisados[int(veto_id)]), FONTE_VETADA_REVISAO, None
    numero, ano = referencia_da_ementa(ementa)
    por_numero: list[int] = []
    if numero and ano:
        por_numero = list(por_ano_numero.get(f"{ano}|{numero_normalizado(numero)}", []))
    texto = texto_da_sumula(ementa)
    por_texto = sorted(
        materia_id
        for materia_id, ementa_projeto in ementas_de_projeto.items()
        if similaridade(texto, ementa_projeto) >= LIMIAR_SIMILARIDADE_VETO
    )
    juntos = sorted(set(por_numero) & set(por_texto))
    if len(juntos) != 1:
        return None, FONTE_VETADA_PENDENTE, None
    achado = juntos[0]
    return (
        int(achado),
        FONTE_VETADA_AUTOMATICA,
        round(similaridade(texto, ementas_de_projeto[int(achado)]), 3),
    )


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


def situacao_final(
    registros: list[dict],
    sigla: str,
    dois_turnos: set[str],
    ultima: dict | None,
    em_tramitacao_ficha,
) -> tuple[str, str]:
    """Situacao final e a fonte dela, sem deduzir nada.

    Ordem da regra, nenhuma etapa pula a anterior:

    1. voto valido (2o turno ou turno unico, deliberativo) ou rejeicao no
       1o turno: devolve a situacao oficial do SAPL, com fonte votacao;
    2. sem voto valido, mas com ultima tramitacao: devolve o texto
       oficial do status, exatamente como o SAPL escreve, com fonte
       tramitacao;
    3. sem registro nenhum: usa o campo em_tramitacao da ficha. True vira
       Em tramitacao, com fonte ficha_sapl. False vira o rotulo de
       ausencia, com fonte sem_registro.

    Ausencia de registro nunca autoriza escrever Em tramitacao.
    """
    deliberativos = [registro for registro in registros if registro_deliberativo(registro)]
    if sigla in dois_turnos:
        escolhida, segue_em_tramitacao = escolher_por_turno(
            [(registro, registro.get("turno")) for registro in deliberativos]
        )
    else:
        escolhida = escolher_votacao(deliberativos) if deliberativos else None
        segue_em_tramitacao = False
    if escolhida is not None and not segue_em_tramitacao:
        try:
            return situacao_da_votacao_escolhida(escolhida), FONTE_VOTACAO
        except SystemExit as erro:
            raise SystemExit(f"{sigla}: {erro}") from erro
    if ultima is not None:
        oficial = str(ultima.get("status_descricao") or "").strip()
        if oficial:
            return oficial, FONTE_TRAMITACAO
        return SITUACAO_STATUS_SEM_TEXTO, FONTE_TRAMITACAO
    if em_tramitacao_ficha is True:
        return SITUACAO_EM_TRAMITACAO, FONTE_FICHA
    return SITUACAO_SEM_REGISTRO, FONTE_SEM_REGISTRO


def rotulo_de_votacao(votacao: dict | None, registradas: list[dict]) -> str | None:
    """Rotulo da votacao: ausencia so quando nao existe registro nenhum.

    Materia com registro, mas sem voto valido (so 1o turno ou registro sem
    deliberacao), recebe rotulo proprio: existe votacao no SAPL, ela nao e
    a que decide.
    """
    if votacao is not None:
        return None
    if registradas:
        return ROTULO_SEM_VOTO_VALIDO
    return ROTULO_SEM_VOTACAO


def montar_votacao(
    materia_id: int,
    votacoes: dict[int, list[dict]],
    ordens: dict[tuple[int, int], dict] | None = None,
) -> tuple[dict | None, str | None]:
    """Votacao que define a materia, ou rotulo de ausencia.

    Escolhe a mais recente entre as validas. Materia sem voto valido
    devolve o rotulo, nunca aprovacao deduzida. Passando os itens da Ordem
    do Dia, o codigo tipo_votacao do item ligado entra como numero cru
    (D-058); sem eles o campo nem entra, porque so o grupo Executivo usa.
    Quem vira rotulo e o voto, nunca o codigo.
    """
    registros = votacoes.get(int(materia_id)) or []
    escolhida = escolher_votacao(votacoes_validas(registros))
    if escolhida is None:
        return None, ROTULO_SEM_VOTACAO
    totais = escolhida.get("totais_oficiais") or {}
    votacao = {
        "data_sessao": escolhida.get("data_sessao"),
        "sessao_id": escolhida.get("sessao_id"),
        "registro_votacao_id": escolhida.get("id"),
        "turno": escolhida.get("turno"),
        "tipo_votacao_codigo": codigo_do_item_da_ordem(escolhida, ordens or {}),
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
    }
    # O codigo do item da Ordem do Dia so entra no grupo Executivo.
    if not ordens:
        votacao.pop("tipo_votacao_codigo")
    return votacao, None


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
        self.ordens_do_dia = carregar_ordens_do_dia()
        self.tipos_votacao_oficial = carregar_tipos_votacao_oficial()
        self.siglas_veto = set(tipos_veto(self.cfg))
        self.projetos, self.ementas_de_projeto = indexar_projetos(
            self.fichas, self.siglas_por_tipo, self.catalogo
        )
        self.vetos_revisados = carregar_vetos_revisados(ARQUIVO_VETOS_REVISADOS)
        self.conferir_vetos_revisados(self.vetos_revisados)

    def conferir_vetos_revisados(self, revisados: dict[int, int]) -> None:
        """A revisao do mantenedor so vale se os ids existirem no SAPL.

        Veto que nao e veto, materia que nao existe ou materia igual ao
        proprio veto sao erro: e arquivo de revisao com conteudo errado, e
        isso precisa aparecer na hora, nao na tela.
        """
        for veto_id, materia_id in sorted(revisados.items()):
            if self.sigla_da_materia(veto_id) not in self.siglas_veto:
                raise SystemExit(
                    f"Veto {veto_id} em vetos_revisados.json nao e materia de veto "
                    f"no SAPL. Nada foi gravado."
                )
            ficha = self.fichas.get(int(materia_id))
            if ficha is None:
                raise SystemExit(
                    f"Materia {materia_id} de vetos_revisados.json nao existe no SAPL. "
                    "Nada foi gravado."
                )
            if int(materia_id) == int(veto_id):
                raise SystemExit(
                    f"Veto {veto_id} apontando para ele mesmo em vetos_revisados.json."
                )
            if not e_projeto_de_lei(ficha, self.siglas_por_tipo, self.catalogo):
                raise SystemExit(
                    f"Materia {materia_id} do veto {veto_id} nao e projeto de lei no "
                    f"SAPL. Nada foi gravado."
                )

    def tipo_da_materia(self, materia_id: int) -> str | None:
        """Sigla, numero e ano da materia, no mesmo formato do campo tipo."""
        ficha = self.fichas.get(int(materia_id))
        if ficha is None:
            return None
        sigla = self.sigla_da_materia(int(materia_id))
        if not sigla:
            return None
        return f"{sigla} {ficha.get('numero')}/{ficha.get('ano')}"

    def rotulos_votacao(self, votacoes: dict[int, list[dict]]) -> dict[int, str]:
        """Rotulo de cada codigo tipo_votacao, pela tabela oficial ou pelos votos.

        D-058: a tabela tipovotacao do SAPL manda quando existe. Sem ela, o
        rotulo so sai quando os votos validos do proprio codigo concordam
        entre si sobre o voto individual.
        """
        return rotulos_votacao_confirmados(
            votacoes, self.ordens_do_dia, self.tipos_votacao_oficial
        )

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
        rotulos_por_codigo: dict[int, str],
    ) -> dict:
        ficha = self.fichas.get(int(materia_id)) or {}
        numero = ficha.get("numero")
        ano = ficha.get("ano")
        registros = votacoes.get(int(materia_id)) or []
        ultima, rotulo_tram = montar_ultima_tramitacao(
            int(materia_id), historico, status, unidades
        )
        votacao, _rotulo_descartado = montar_votacao(
            int(materia_id),
            votacoes,
            self.ordens_do_dia if grupo == "executivo" else None,
        )
        registradas = registrar_votacoes(registros)
        tema, revisada = tema_da_materia(int(materia_id), self.indice_temas)
        valida = escolher_votacao(votacoes_validas(registros))
        nominais = votos_nominais(valida, self.vereadores)
        rotulo_votacao = rotulo_de_votacao(votacao, registradas)
        if nominais:
            rotulo_nominal = None
        elif votacao is None:
            rotulo_nominal = (
                ROTULO_SEM_VOTACAO if not registradas else ROTULO_SEM_VOTO_VALIDO
            )
        else:
            rotulo_nominal = ROTULO_SEM_VOTO_INDIVIDUAL
        situacao, fonte = situacao_final(
            registros,
            sigla,
            dois_turnos,
            ultima,
            ficha.get("em_tramitacao"),
        )
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
            "situacao_final": situacao,
            "situacao_final_fonte": fonte,
            "em_tramitacao": ficha.get("em_tramitacao"),
            "resultado_ficha_sapl": ficha.get("resultado_ficha_sapl"),
            "ultima_tramitacao": ultima,
            "ultima_tramitacao_rotulo": rotulo_tram,
            "votacoes_registradas": registradas,
            "votacao": votacao,
            "votacao_rotulo": rotulo_votacao,
            "votos_nominais": nominais,
            "votos_nominais_rotulo": rotulo_nominal,
            "link_sapl": link_materia(int(materia_id), self.cfg),
        }
        if grupo == "executivo":
            item["votacao_tipo"] = votacao_tipo_de(
                valida, self.ordens_do_dia, rotulos_por_codigo
            )
            item["materia_vetada_id"] = None
            item["materia_vetada_fonte"] = None
            item["materia_vetada_tipo"] = None
            item["materia_vetada_link"] = None
            item["materia_vetada_rotulo"] = ROTULO_VETADA_SEM_ESTRUTURA
            if sigla in self.siglas_veto:
                ementa = ficha.get("ementa") or ""
                item["veto_tipo"] = veto_tipo_de(ementa)
                item["veto_situacao"] = veto_situacao_de(votacao)
                vetada, fonte, semelhanca = materia_vetada(
                    int(materia_id),
                    ementa,
                    self.vetos_revisados,
                    self.projetos,
                    self.ementas_de_projeto,
                )
                item["materia_vetada_fonte"] = fonte
                item["materia_vetada_similaridade"] = semelhanca
                if vetada is None:
                    item["materia_vetada_rotulo"] = ROTULO_VETADA_PENDENTE
                else:
                    item["materia_vetada_id"] = vetada
                    item["materia_vetada_tipo"] = self.tipo_da_materia(vetada)
                    item["materia_vetada_link"] = link_materia(vetada, self.cfg)
                    item["materia_vetada_rotulo"] = (
                        ROTULO_VETADA_REVISADA
                        if fonte == FONTE_VETADA_REVISAO
                        else ROTULO_VETADA_AUTOMATICA
                    )
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


def contagem_de(itens: list[dict], chave: str) -> dict:
    """Contagem por valor do campo, em ordem de quantidade e depois de nome."""
    valores = [str(item.get(chave)) for item in itens if item.get(chave)]
    return dict(
        sorted(Counter(valores).items(), key=lambda par: (-par[1], par[0]))
    )


def meta_de(
    grupo: str,
    escopo: dict,
    anos: list[int],
    pasta: Path,
    decodificados: int,
    itens: list[dict],
) -> dict:
    """Contagens do arquivo. A situacao final e texto livre do SAPL.

    Por isso a contagem sai por valor, e nao por uma lista fixa de
    situacoes. A coluna de fonte mostra de onde cada situacao veio.
    """
    contagem = Counter(item["situacao_final"] for item in itens)
    por_fonte = Counter(item["situacao_final_fonte"] for item in itens)
    meta = {
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
        "por_situacao_final": dict(
            sorted(contagem.items(), key=lambda par: (-par[1], par[0]))
        ),
        "por_situacao_final_fonte": {fonte: por_fonte.get(fonte, 0) for fonte in FONTES_SITUACAO},
        "itens_com_votacao_valida": sum(1 for item in itens if item["votacao"] is not None),
        "itens_sem_votacao_valida": sum(1 for item in itens if item["votacao"] is None),
        "votos_nominais_registrados": sum(len(item["votos_nominais"]) for item in itens),
        "rotulo_sem_votacao": ROTULO_SEM_VOTACAO,
        "rotulo_sem_voto_valido": ROTULO_SEM_VOTO_VALIDO,
        "rotulo_sem_voto_individual": ROTULO_SEM_VOTO_INDIVIDUAL,
        "rotulo_sem_tramitacao": ROTULO_SEM_TRAMITACAO,
        "situacao_sem_registro": SITUACAO_SEM_REGISTRO,
        "observacao": (
            "Votacao e votos nominais saem so do voto valido: 2o turno ou "
            "turno unico, e so registro deliberativo, lido pelo id do tipo "
            "de resultado do SAPL. Pedido de Vistas, materia adiada e "
            "retirada de pauta nao sao votacao e ficam como fato de "
            "tramitacao. Materia votada so no 1o turno nao tem voto "
            "valido. Voto nominal so entra de quem estava no mandato na "
            "data da sessao. A situacao final nunca e deduzida: com voto "
            "valido ou rejeicao no 1o turno vem do registro de votacao; "
            "sem voto valido, mas com tramitacao, vem do texto oficial do "
            "status do SAPL; sem registro nenhum, vem do campo "
            "em_tramitacao da ficha, e False vira o rotulo de ausencia. "
            "O campo situacao_final_fonte diz de onde cada uma veio."
        ),
    }
    meta.update(meta_do_executivo(itens))
    return meta


def meta_do_executivo(itens: list[dict]) -> dict:
    """Contagens do D-058, que so existem nas materias do Executivo.

    As chaves ficam fora do arquivo quando a contagem fica vazia, para o
    arquivo das proposicoes continuar igual ao que era.
    """
    por_votacao_tipo = contagem_de(itens, "votacao_tipo")
    if not por_votacao_tipo:
        return {}
    saida: dict = {
        "por_votacao_tipo": por_votacao_tipo,
        "rotulo_votacao_tipo_nao_informado": VOTACAO_TIPO_NAO_INFORMADO,
        "observacao_executivo": (
            "D-058: votacao_tipo vem do campo tipo_votacao do item da Ordem "
            "do Dia ligado ao registro de votacao, com o mesmo id que o "
            "SAPL usa. O codigo vira rotulo pela tabela oficial tipovotacao "
            "quando ela esta nos brutos. Sem tabela, o rotulo so sai quando "
            "todos os votos validos daquele codigo concordam sobre o voto "
            "individual: com voto individual e nominal, sem voto individual "
            "e simbolica. Codigo sem confirmacao, materia sem voto valido e "
            "item da Ordem do Dia ausente ficam como nao informado no SAPL. "
            "Nos vetos, veto_tipo vem do começo da ementa oficial e "
            "veto_situacao vem do resultado do voto valido do proprio veto. "
            "materia_vetada_id tem prioridade na revisao do mantenedor em "
            "vetos_revisados.json (fonte revisao_mantenedor). Sem revisao, a "
            "regra automatica exige os dois criterios juntos: numero e ano "
            "citados na ementa, sem zero a esquerda, levando a materia de "
            "projeto de lei, e texto da sumula com a ementa dela parecidas, "
            "com similaridade de token de 0,85 para cima (fonte automatica, "
            "com o valor medido em materia_vetada_similaridade). Um criterio "
            "so, ou mais de um candidato, deixa o vinculo nulo com fonte "
            "pendente_revisao."
        ),
    }
    vetoes = [item for item in itens if "veto_situacao" in item]
    if vetoes:
        saida["veto_derrotados"] = sum(
            1 for item in vetoes if item["veto_situacao"] == VETO_DERRUBADO
        )
        saida["veto_mantidos"] = sum(
            1 for item in vetoes if item["veto_situacao"] == VETO_MANTIDO
        )
        saida["veto_sem_voto_valido"] = sum(
            1 for item in vetoes if item["veto_situacao"] == VETO_AINDA_VAI_VOTAR
        )
        saida["por_veto_tipo"] = contagem_de(vetoes, "veto_tipo")
        saida["por_veto_situacao"] = contagem_de(vetoes, "veto_situacao")
        saida["por_materia_vetada_fonte"] = contagem_de(
            vetoes, "materia_vetada_fonte"
        )
        saida["veto_com_materia_vetada"] = sum(
            1 for item in vetoes if item["materia_vetada_id"] is not None
        )
        saida["veto_pendente_de_revisao"] = sum(
            1 for item in vetoes if item["materia_vetada_id"] is None
        )
        saida["fonte_vetos_revisados"] = rel(ARQUIVO_VETOS_REVISADOS)
        saida["limiar_similaridade_veto"] = LIMIAR_SIMILARIDADE_VETO
        saida["rotulo_veto_tipo_nao_informado"] = VETO_TIPO_NAO_INFORMADO
    return saida


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
    rotulos_por_codigo = base.rotulos_votacao(votacoes)
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
                        rotulos_por_codigo,
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