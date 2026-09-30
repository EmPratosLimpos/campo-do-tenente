#!/usr/bin/env python3
"""Atualiza os dados da semana a partir do SAPL.

Ordem: lote pequeno, sessoes ordinarias novas mais a ultima ja coletada,
autoria, derivacao, vereadores, presidencia, autoria tratada, atuacao por
ano, temas, dados da tela, sanidade, hash, testes e regras.

As listas grandes (presencas, ordem do dia, registrovotacao,
votoparlamentar, justificativa e mesa) nao sao mais baixadas em lote.
Elas saem da coleta por sessao, das ordinarias novas e sempre da ultima
ja coletada para pegar lancamento atrasado. Listas pequenas que fecham
(sessaoplenaria do ano, materias do ano, autoria) continuam em lote.
A primeira coleta completa de muitas sessoes precisa ser feita em partes,
fora da rotina semanal, por causa do teto de pedidos por execucao.

Um pedido por vez. Pausa de PAUSA_SAPL_SEGUNDOS (2,5 s). No maximo
400 pedidos nesta execucao. Anos saem de config_cidade.json. O ano
corrente so entra depois de um pedido ao SAPL confirmar ao menos uma
sessao ordinaria nesse ano. Sem sessao, o recorte nao muda.

Modo simulado (--simulado): nao abre rede. Usa os brutos ja salvos.
Se nao houver dado novo, nao regrava os tratados.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

import coletar_lote  # noqa: E402
from coletar_autoria import PLANO, total_entries  # noqa: E402
from coletar_lote import (  # noqa: E402
    PAGE_SIZE,
    ColetorLote,
    OrcamentoEsgotado,
    continuar_apos_primeira,
    plano_de_coleta,
)
from coletar_por_sessao import (  # noqa: E402
    CAMINHO_MESA,
    RECURSO_MESA,
    RECURSO_REGISTRO,
    RECURSO_VOTO,
    RECURSOS,
    coletar_sessao_completa,
    conferir_prefixo,
    gravar_conferencia,
    sessoes_ordinarias,
)
from config_cidade import (  # noqa: E402
    ARQUIVO_CONFIG,
    PAUSA_SAPL_SEGUNDOS,
    anos_recorte,
    carregar_config,
    endereco_sapl,
    id_tipo_sessao_ordinaria,
)
from derivar_insumos import (  # noqa: E402
    BRUTOS,
    pasta_lote_mais_recente,
    pasta_porsessao_mais_recente,
)

TETO_EXECUCAO = 400
CHANGELOG = RAIZ / "CHANGELOG.md"
RESUMO_INSUMOS = BRUTOS / "resumo_insumos.json"

GERADORES = (
    "dados/tratados/gerar_tabela_vereadores.py",
    "dados/tratados/gerar_presidencia_sessoes.py",
    "dados/tratados/gerar_autoria_materias.py",
    "dados/tratados/gerar_atuacao_vereadores.py",
    "dados/tratados/gerar_temas_votacoes.py",
    "dados/tratados/gerar_dados_tela.py",
)

PREFIXOS_GRANDES_POR_SESSAO = frozenset(
    {
        "sessaoplenariapresenca",
        "presencaordemdia",
        "ordemdia",
        "registrovotacao",
        "votoparlamentar",
        "justificativaausencia",
        "integrantemesa",
    }
)


class OrcamentoExecucao:
    """Conta os pedidos novos desta execucao, somando lote, sessao e autoria."""

    def __init__(self, teto: int = TETO_EXECUCAO):
        if isinstance(teto, bool) or not isinstance(teto, int) or teto < 1 or teto > TETO_EXECUCAO:
            raise ValueError(
                f"O teto por execucao fica entre 1 e {TETO_EXECUCAO} pedidos."
            )
        self.teto = teto
        self.pedidos = 0


def anos_da_execucao(cfg: dict, hoje: date) -> list[int]:
    """Anos ja gravados no config. O ano corrente nao entra sozinho."""
    if not isinstance(hoje, date):
        raise SystemExit("Data da execucao invalida.")
    return sorted(anos_recorte(cfg))


def ano_corrente_candidato(cfg: dict, hoje: date) -> int | None:
    """Ano de hoje se estiver na legislatura e ainda nao estiver no recorte."""
    anos = list(anos_recorte(cfg))
    inicio = int(cfg["sapl"]["legislatura_inicio"])
    fim = int(cfg["sapl"]["legislatura_fim"])
    if inicio <= hoje.year <= fim and hoje.year not in anos:
        return int(hoje.year)
    return None


def ha_sessao_ordinaria(dados: dict, tipo_ordinaria: int) -> bool:
    if not isinstance(dados, dict):
        return False
    resultados = dados.get("results")
    if isinstance(resultados, list) and resultados:
        return any(
            isinstance(item, dict) and int(item.get("tipo") or 0) == int(tipo_ordinaria)
            for item in resultados
        )
    paginacao = dados.get("pagination") or {}
    total = paginacao.get("total_entries")
    if total is None and isinstance(dados.get("count"), int) and not isinstance(dados.get("count"), bool):
        total = dados.get("count")
    return isinstance(total, int) and not isinstance(total, bool) and total >= 1


def confirmar_sessao_ordinaria_no_ano(coletor: ColetorLote, ano: int, tipo_ordinaria: int) -> bool:
    """Um pedido ao SAPL, com a pausa do coletor. Nao pagina."""
    dados = coletor.pedir(
        "/api/sessao/sessaoplenaria/",
        {
            "data_inicio__year": int(ano),
            "tipo": int(tipo_ordinaria),
            "page": 1,
            "page_size": 1,
        },
        f"sonda_ordinaria_ano{int(ano)}.json",
        refrescar=True,
    )
    return ha_sessao_ordinaria(dados, tipo_ordinaria)


def incluir_ano_se_confirmado(cfg: dict, hoje: date, simulado: bool, confirmar) -> tuple[list[int], bool]:
    """Acrescenta o ano corrente so quando o SAPL tem sessao ordinaria.

    No modo simulado nao ha pedido. Sem sessao, o recorte segue como esta.
    """
    anos = anos_da_execucao(cfg, hoje)
    candidato = ano_corrente_candidato(cfg, hoje)
    if candidato is None:
        return anos, False
    if simulado:
        print(
            f"Ano {candidato} esta na legislatura. "
            "Modo simulado nao consulta o SAPL. O ano nao entrou no recorte."
        )
        return anos, False
    if confirmar(candidato):
        print(f"Ano {candidato} confirmado no SAPL e incluido no recorte.")
        return sorted(anos + [candidato]), True
    print(f"Ano {candidato} sem sessao ordinaria no SAPL. O recorte nao mudou.")
    return anos, False


def gravar_anos_no_config(anos: list[int]) -> None:
    dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    dados["recorte"]["anos"] = [int(ano) for ano in anos]
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    ARQUIVO_CONFIG.write_bytes(texto.encode("utf-8"))


def pasta_autoria_mais_recente(brutos: Path) -> Path:
    candidatas = [
        caminho
        for caminho in brutos.glob("lote_*_autoria")
        if caminho.is_dir() and (caminho / "indice.json").exists()
    ]
    if not candidatas:
        raise SystemExit("Nenhuma pasta de autoria em dados/brutos. Nada foi baixado.")
    return sorted(candidatas)[-1]


def preparar_coletor(cfg: dict, pasta: Path, orcamento: OrcamentoExecucao, simulado: bool) -> ColetorLote:
    coletor = ColetorLote(cfg, pasta, teto=orcamento.teto)
    coletor.orcamento_execucao = orcamento
    coletor.simulado = simulado
    coletor.teto = coletor.pedidos + orcamento.teto
    return coletor


def sessao_tem_arquivo(pasta: Path, sid: int) -> bool:
    return all(
        (pasta / f"sessao_{sid}_{recurso}_p1.json").is_file()
        for _caminho, recurso in RECURSOS
    )


def sessoes_novas(pasta_porsessao: Path | None, sessoes: list[dict]) -> list[dict]:
    """Ordinarias que ainda nao tem arquivo na pasta por sessao."""
    if pasta_porsessao is None:
        return list(sessoes)
    return [
        sessao
        for sessao in sessoes
        if not sessao_tem_arquivo(pasta_porsessao, int(sessao["id"]))
    ]


def ultima_sessao_coletada(
    pasta_porsessao: Path | None, sessoes: list[dict]
) -> dict | None:
    """Ultima ordinaria ja coletada, para pegar lancamento atrasado no SAPL."""
    if pasta_porsessao is None:
        return None
    coletadas = [
        sessao
        for sessao in sessoes
        if sessao_tem_arquivo(pasta_porsessao, int(sessao["id"]))
    ]
    if not coletadas:
        return None
    return sorted(
        coletadas,
        key=lambda item: (
            str(item.get("data_inicio") or ""),
            int(item.get("numero") or 0),
            int(item["id"]),
        ),
    )[-1]


PEDIDOS_MINIMOS_POR_SESSAO = len(RECURSOS) + 1


def custo_minimo_sessoes(n_sessoes: int) -> int:
    """Piso de pedidos da coleta por sessao: 4 recursos mais a mesa.

    Registros por ordem e votos por registro custam a mais e variam
    por sessao, por isso o retorno e minimo, nunca teto.
    """
    return max(0, int(n_sessoes)) * PEDIDOS_MINIMOS_POR_SESSAO


def sessoes_alvo_para_coleta(
    sessoes: list[dict], pasta_porsessao: Path | None
) -> tuple[list[dict], list[dict]]:
    """Novas mais sempre a ultima ja coletada para revisao de lancamento atrasado.

    Mesmo sem sessao nova, a ultima e refeita para pegar lancamento
    atrasado no SAPL. Sem nenhuma coletada, o alvo sao as novas.
    """
    novas = sessoes_novas(pasta_porsessao, sessoes)
    ultima = ultima_sessao_coletada(pasta_porsessao, sessoes)
    if ultima is None:
        return novas, list(novas)
    ids_novas = {int(item["id"]) for item in novas}
    alvo = list(novas)
    if int(ultima["id"]) not in ids_novas:
        alvo.append(ultima)
    alvo = sorted(
        alvo,
        key=lambda item: (
            str(item.get("data_inicio") or ""),
            int(item.get("numero") or 0),
            int(item["id"]),
        ),
    )
    return novas, alvo


def plano_sem_listas_grandes(anos: list[int], indice: dict) -> list[dict]:
    """Plano em lote sem as listas grandes que agora saem por sessao."""
    plano = plano_de_coleta(anos, indice)
    return [
        item
        for item in plano
        if str(item.get("prefixo") or "") not in PREFIXOS_GRANDES_POR_SESSAO
        and not str(item.get("prefixo") or "").endswith("_por_id")
    ]


def atualizar_paginas(coletor: ColetorLote, caminho: str, params: dict, prefixo: str, simulado: bool) -> None:
    """Reconfere a primeira pagina. So repete as seguintes se ela mudou ou faltar arquivo."""
    params = dict(params)
    params["page_size"] = PAGE_SIZE
    params["page"] = 1
    primeiro = coletor.pedir(caminho, params, f"{prefixo}_p1.json", refrescar=not simulado)
    if not isinstance(primeiro, dict):
        raise SystemExit(f"{prefixo}: resposta sem objeto JSON")
    pagina1_igual = simulado or bool(coletor.ultimo_igual)

    def baixar(pagina: int):
        params["page"] = pagina
        arquivo = f"{prefixo}_p{pagina}.json"
        existe = (coletor.pasta / arquivo).is_file()
        refrescar = (not simulado) and existe and (not pagina1_igual)
        dados = coletor.pedir(caminho, params, arquivo, refrescar=refrescar)
        if not isinstance(dados, dict):
            raise SystemExit(f"{prefixo}: resposta sem objeto JSON")
        return dados

    continuar_apos_primeira(primeiro, prefixo, baixar)


def estimar_sondas(pasta_lote: Path, anos: list[int]) -> tuple[int, int]:
    """Pedidos se a primeira pagina nao mudar. As listas grandes nao entram.

    O primeiro numero e a conferencia das listas pequenas ja salvas.
    O segundo e zero, mantido para compatibilidade: nao ha mais leitura
    ordering=id em lote, pois as listas grandes saem por sessao.
    """
    indice_path = pasta_lote / "api_indice.json"
    if not indice_path.is_file():
        return 0, 0
    indice = json.loads(indice_path.read_text(encoding="utf-8"))
    plano = plano_sem_listas_grandes(anos, indice)
    conferencia = 1 + len(plano) + len(PLANO) + len(anos)
    return conferencia, 0


def baixar_lote(coletor: ColetorLote, anos: list[int], simulado: bool) -> None:
    """Lote pequeno: catalogos, sessoes do ano, materias do ano e expediente.

    As listas grandes de presenca, ordem, voto, justificativa e mesa ficam
    de fora. Elas sao coletadas por sessao, so das novas e da ultima.
    """
    indice = coletor.pedir("/api/", None, "api_indice.json", refrescar=not simulado)
    if not isinstance(indice, dict):
        raise SystemExit("Indice da API nao e um objeto JSON.")
    plano = plano_sem_listas_grandes(anos, indice)
    for item in plano:
        print(item["prefixo"])
        atualizar_paginas(coletor, item["caminho"], item["params"], item["prefixo"], simulado)


def coletar_sessoes_novas(coletor: ColetorLote, sessoes: list[dict]) -> None:
    """Coleta por sessao dos pacotes grandes, com mesa, registros e votos."""
    for sessao in sessoes:
        sid = int(sessao["id"])
        print(f"sessao {sid} numero {sessao.get('numero')} {sessao.get('data_inicio')}")
        resumo = coletar_sessao_completa(coletor, sid)
        print(
            f"  ordem {resumo['n_ordem']}, "
            f"registros {resumo['n_registros']}, votos {resumo['n_votos']}"
        )


def coletar_autoria(coletor: ColetorLote, anos: list[int], simulado: bool) -> None:
    for caminho, prefixo in PLANO:
        print(prefixo)
        atualizar_paginas(coletor, caminho, {}, prefixo, simulado)
    primeiro = coletor.pedir(
        "/api/materia/autoria/",
        {"page_size": PAGE_SIZE, "page": 1},
        "autoria_p1.json",
        refrescar=False,
    )
    total_sem_filtro = total_entries(primeiro)
    for ano in anos:
        print(f"autoria_materia_ano{ano}")
        prefixo = f"autoria_materia_ano{ano}"
        params = {"materia__ano": ano, "page_size": PAGE_SIZE, "page": 1}
        pagina = coletor.pedir(
            "/api/materia/autoria/",
            params,
            f"{prefixo}_p1.json",
            refrescar=not simulado,
        )
        total = total_entries(pagina)
        if total is None or (total_sem_filtro is not None and total >= total_sem_filtro):
            print(f"  filtro materia__ano={ano} ignorado pelo SAPL, nao pagina")
            continue
        if not isinstance(pagina, dict):
            raise SystemExit(f"{prefixo}: resposta sem objeto JSON")
        pagina1_igual = simulado or bool(coletor.ultimo_igual)

        def baixar(numero: int):
            params["page"] = numero
            arquivo = f"{prefixo}_p{numero}.json"
            existe = (coletor.pasta / arquivo).is_file()
            refrescar = (not simulado) and existe and (not pagina1_igual)
            return coletor.pedir("/api/materia/autoria/", params, arquivo, refrescar=refrescar)

        continuar_apos_primeira(pagina, prefixo, baixar)


def rodar(argumentos: list[str]) -> None:
    print(">", " ".join(argumentos))
    resultado = subprocess.run([sys.executable, *argumentos], cwd=RAIZ)
    if resultado.returncode != 0:
        raise SystemExit(resultado.returncode)


def ler_json(caminho: Path) -> dict:
    if not caminho.is_file():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return dados if isinstance(dados, dict) else {}


def linhas_contagem(antes: dict, depois: dict) -> list[str]:
    rotulos = (
        ("sessoes_ordinarias", "sessões ordinárias"),
        ("votacoes", "votações"),
        ("n_presencas_sessao", "presenças na sessão"),
        ("n_justificativas", "justificativas de ausência"),
    )
    linhas = []
    anos = sorted(set(antes) | set(depois), key=lambda item: int(item))
    for ano in anos:
        bloco_antes = antes.get(ano) or {}
        bloco_depois = depois.get(ano) or {}
        if not isinstance(bloco_depois, dict) or not bloco_depois:
            continue
        partes = []
        for chave, rotulo in rotulos:
            if chave not in bloco_depois:
                continue
            novo = bloco_depois.get(chave)
            velho = bloco_antes.get(chave) if isinstance(bloco_antes, dict) else None
            if velho is None or velho == novo:
                continue
            partes.append(f"{rotulo} de {velho} para {novo}")
        if partes:
            linhas.append(f"{ano}: " + ", ".join(partes) + ".")
    return linhas


def ler_hashes(anos: list[int]) -> dict[str, str]:
    saida = {}
    for ano in anos:
        caminho = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json.sha256"
        if caminho.is_file():
            saida[str(ano)] = caminho.read_text(encoding="utf-8").strip()
    return saida


def linhas_hash(antes: dict, depois: dict) -> list[str]:
    linhas = []
    for ano in sorted(depois, key=lambda item: int(item)):
        if antes.get(ano) == depois.get(ano):
            continue
        linhas.append(f"Hash SHA-256 de atuacao_vereadores_{ano}.json: {depois[ano]}.")
    return linhas


def linhas_sessoes(sessoes: list[dict]) -> list[str]:
    if not sessoes:
        return ["Nenhuma sessão ordinária nova."]
    linhas = []
    for item in sessoes:
        numero = item.get("numero")
        data = item.get("data_inicio") or "data não informada no SAPL"
        if numero is None:
            linhas.append(
                f"Sessão ordinária sem número no SAPL, data {data} (registro {item['id']})."
            )
        else:
            linhas.append(
                f"Sessão ordinária {numero}, data {data} (registro {item['id']})."
            )
    return linhas


def montar_entrada(data_iso: str, fonte: str, pedidos: int, sessoes: list[dict], contagens: list[str], hashes: list[str]) -> str:
    linhas = [
        f"## {data_iso}: atualização semanal dos dados",
        "",
        "**O que mudou nos dados**",
    ]
    for linha in linhas_sessoes(sessoes):
        linhas.append(f"- {linha}")
    if contagens:
        for linha in contagens:
            linhas.append(f"- {linha}")
    else:
        linhas.append("- As contagens acompanhadas permaneceram iguais.")
    if hashes:
        for linha in hashes:
            linhas.append(f"- {linha}")
    else:
        linhas.append("- Nenhum hash de atuação mudou.")
    linhas.append(f"- Pedidos ao SAPL nesta execução: {pedidos}.")
    linhas.extend(
        [
            "",
            "**O que mudou na tela**",
            "- Nenhuma. A tela só muda depois que o mantenedor aprovar.",
            "",
            "**De onde veio**",
            f"- SAPL consultado: {fonte}.",
            f"- Coleta de {data_iso}.",
        ]
    )
    return "\n".join(linhas) + "\n"


def inserir_entrada(texto: str, entrada: str) -> str:
    marca = "\n---\n"
    pos = texto.find(marca)
    if pos < 0:
        raise SystemExit("CHANGELOG.md sem o separador esperado. Nada foi reescrito.")
    ponto = pos + len(marca)
    return texto[:ponto] + "\n" + entrada.strip() + "\n\n" + texto[ponto:].lstrip("\n")


def gravar_changelog(entrada: str) -> None:
    texto = CHANGELOG.read_text(encoding="utf-8")
    novo = inserir_entrada(texto, entrada)
    if "\r" in novo:
        raise SystemExit("CHANGELOG.md ficaria com fim de linha CR. Nao gravei.")
    CHANGELOG.write_bytes(novo.encode("utf-8"))


def bloqueio_de_rede(*_args, **_kwargs):
    raise SystemExit("Modo simulado: pedido de rede bloqueado.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Atualizacao semanal dos dados do SAPL.")
    parser.add_argument(
        "--simulado",
        action="store_true",
        help="Nao abre rede. Usa os brutos ja salvos.",
    )
    args = parser.parse_args(argv)

    if PAUSA_SAPL_SEGUNDOS < 2.5:
        raise SystemExit("A pausa do SAPL esta abaixo de 2,5 s. Nao vou continuar.")

    cfg = carregar_config()
    hoje = date.today()
    fonte = endereco_sapl(cfg)
    orcamento = OrcamentoExecucao(TETO_EXECUCAO)
    pasta_lote = pasta_lote_mais_recente(BRUTOS)
    tipo = id_tipo_sessao_ordinaria(cfg)

    def confirmar_ano(ano: int) -> bool:
        coletor_sonda = preparar_coletor(cfg, pasta_lote, orcamento, False)
        coletor_sonda.pular_pausa = False
        confirmou = confirmar_sessao_ordinaria_no_ano(coletor_sonda, ano, tipo)
        if not confirmou:
            coletor_sonda.gravou = False
        coletores.append(coletor_sonda)
        return confirmou

    coletores = []
    anos, config_alterada = incluir_ano_se_confirmado(cfg, hoje, args.simulado, confirmar_ano)
    if config_alterada and not args.simulado:
        gravar_anos_no_config(anos)
        cfg = carregar_config()
    estimativa, paginas_por_id_ausentes = estimar_sondas(pasta_lote, anos)

    print("Atualizacao semanal")
    print(f"Fonte: {fonte}")
    print(f"Anos: {', '.join(str(ano) for ano in anos)}")
    print("Modo: simulado" if args.simulado else "Modo: rede")
    print(f"Pausa: {PAUSA_SAPL_SEGUNDOS} s. Teto: {TETO_EXECUCAO} pedidos. Um pedido por vez.")
    print(
        f"Estimativa de pedidos numa semana sem sessao nova: {estimativa}. "
        "Listas grandes nao saem mais em lote. "
        f"Cada sessao no alvo custa no minimo {PEDIDOS_MINIMOS_POR_SESSAO} pedidos "
        f"(presencas, ordem, justificativa, mesa, registros por ordem e votos por registro custam a mais)."
    )

    original_urlopen = coletar_lote.urllib.request.urlopen
    lista_novas: list[dict] = []
    try:
        if args.simulado:
            coletar_lote.urllib.request.urlopen = bloqueio_de_rede

        coletor_lote = preparar_coletor(cfg, pasta_lote, orcamento, args.simulado)
        coletores.append(coletor_lote)
        try:
            baixar_lote(coletor_lote, anos, args.simulado)
        except OrcamentoEsgotado as exc:
            print(f"PAROU: {exc}")
            return 2

        tipo = id_tipo_sessao_ordinaria(cfg)
        sessoes = sessoes_ordinarias(pasta_lote, tipo)
        pasta_sessao = pasta_porsessao_mais_recente(BRUTOS)
        if pasta_sessao is None:
            lista_novas = list(sessoes)
            lista_alvo = list(sessoes)
        else:
            lista_novas, lista_alvo = sessoes_alvo_para_coleta(sessoes, pasta_sessao)
        print(f"Sessoes ordinarias no lote: {len(sessoes)}")
        print(f"Sessoes ordinarias novas: {len(lista_novas)}")
        if lista_alvo and len(lista_alvo) > len(lista_novas):
            print(f"Sessoes para revisao de lancamento atrasado: {len(lista_alvo) - len(lista_novas)}")

        minimo_sessoes = custo_minimo_sessoes(len(lista_alvo))
        if lista_alvo and not args.simulado:
            print(
                f"Custo minimo da coleta por sessao: {minimo_sessoes} pedidos "
                f"para {len(lista_alvo)} sessoes no alvo."
            )
            if orcamento.pedidos + minimo_sessoes > orcamento.teto:
                print(
                    f"PAROU: alvo com {len(lista_alvo)} sessoes precisa de ao menos "
                    f"{minimo_sessoes} pedidos e o teto e {orcamento.teto}. "
                    "A primeira coleta completa precisa ser feita em partes, "
                    "fora da rotina semanal. Nada foi publicado."
                )
                return 2

        if lista_alvo and args.simulado:
            print("Modo simulado: sessoes sem arquivo nao foram baixadas.")
        elif lista_alvo:
            if pasta_sessao is None:
                pasta_sessao = BRUTOS / f"lote_{hoje.strftime('%Y%m%d')}_porsessao"
            coletor_sessao = preparar_coletor(cfg, pasta_sessao, orcamento, False)
            coletores.append(coletor_sessao)
            try:
                coletar_sessoes_novas(coletor_sessao, lista_alvo)
            except OrcamentoEsgotado as exc:
                print(f"PAROU: {exc}")
                print(
                    "A primeira coleta completa precisa ser feita em partes, "
                    "fora da rotina semanal. Nada foi publicado."
                )
                return 2
            divergencias = []
            for sessao in sessoes:
                sid = int(sessao["id"])
                for _caminho, recurso in list(RECURSOS) + [(CAMINHO_MESA, RECURSO_MESA)]:
                    prefixo = f"sessao_{sid}_{recurso}"
                    if not (pasta_sessao / f"{prefixo}_p1.json").is_file():
                        continue
                    conf = conferir_prefixo(pasta_sessao, prefixo, sid, recurso)
                    if not conf["bate"]:
                        divergencias.append(conf)
                for recurso in (RECURSO_REGISTRO, RECURSO_VOTO):
                    consolidado = pasta_sessao / f"sessao_{sid}_{recurso}_p1.json"
                    if consolidado.is_file():
                        continue
            gravar_conferencia(pasta_sessao, sessoes, divergencias)

        pasta_autoria = pasta_autoria_mais_recente(BRUTOS)
        coletor_autoria = preparar_coletor(cfg, pasta_autoria, orcamento, args.simulado)
        coletores.append(coletor_autoria)
        try:
            coletar_autoria(coletor_autoria, anos, args.simulado)
        except OrcamentoEsgotado as exc:
            print(f"PAROU: {exc}")
            return 2
    finally:
        coletar_lote.urllib.request.urlopen = original_urlopen

    alterou = config_alterada or any(coletor.gravou for coletor in coletores)
    print(f"Pedidos nesta execucao: {orcamento.pedidos}")
    if args.simulado or not alterou:
        if not alterou:
            print("Nada mudou. Tratados nao foram regravados.")
        return 0

    contagens_antes = ler_json(RESUMO_INSUMOS).get("contagens") or {}
    hashes_antes = ler_hashes(anos)
    rodar(["coletor/derivar_insumos.py"])
    for gerador in GERADORES:
        rodar([gerador])
    rodar(["coletor/testes_sanidade.py"])
    rodar(["-m", "unittest", "discover", "-s", "tests"])
    rodar(["coletor/gerar_hash_integridade.py"])
    rodar(["scripts/verificar_regras.py"])

    contagens_depois = ler_json(RESUMO_INSUMOS).get("contagens") or {}
    hashes_depois = ler_hashes(anos)
    entrada = montar_entrada(
        hoje.isoformat(),
        fonte,
        orcamento.pedidos,
        lista_novas,
        linhas_contagem(contagens_antes, contagens_depois),
        linhas_hash(hashes_antes, hashes_depois),
    )
    gravar_changelog(entrada)
    print("CHANGELOG atualizado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
