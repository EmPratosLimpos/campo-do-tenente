#!/usr/bin/env python3
"""Classifica o tema de materias novas por consenso de tres modelos (D-047).

Regra D-047: materia nova do recorte sem tema em
dados/tratados/temas_materias.json e classificada por tres modelos do
plano OpenCode Go, de familias diferentes, cada um sem ver a resposta
dos outros. Dois ou tres votos iguais (nome exato de uma categoria):
o tema e gravado com classificado_por "consenso D-047: <modelos que
concordaram>", revisada_por_humano false, confianca e justificativa
do voto, data do dia. Tres votos diferentes, ou menos de duas
respostas validas: a materia fica SEM tema (nao grava entrada) e a
execucao abre issue "Tema para revisao: <sigla numero/ano>" com a
ementa, o link do SAPL e as tres respostas. O resto da semana sai
normalmente. Entrada com revisada_por_humano true NUNCA e alterada.
Entrada ja classificada por consenso nao e classificada de novo.

A chave e lida so da variavel de ambiente OPENCODE_ZEN_API_KEY. Sem
a chave, nada e classificado, a execucao NAO falha: as materias novas
voltam como pendentes (aviso no CHANGELOG e issue de revisao).
A chave nunca aparece em log, mensagem, issue ou arquivo.

Endpoint e modelos vem de config_cidade.json (bloco
classificacao_temas), nunca fixos aqui. Categorias com descricao vem
do bloco categorias do config, nunca fixas aqui. "nao se aplica" vale
so para atas (ATA) e oficios do Executivo (OFEX). Um pedido por
modelo por materia, um de cada vez, sem paralelismo, com tempo limite
e no maximo uma tentativa extra. Resposta curta (temperatura 0,
max_tokens pequeno) para o custo ficar em centavos.

Nenhum pedido ao SAPL aqui: as materias novas saem dos brutos ja
coletados (lote mais recente) comparados com temas_materias.json.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import uuid
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import (  # noqa: E402
    carregar_config,
    categorias,
    endereco_sapl,
    link_materia,
    rotulos_especiais_tema,
)

ARQUIVO_TEMAS = RAIZ / "dados" / "tratados" / "temas_materias.json"
BRUTOS = RAIZ / "dados" / "brutos"

NOME_VAR_CHAVE = "OPENCODE_ZEN_API_KEY"
AGENTE_HTTP = "painel-temas/1.0"
TIPOS_SEM_TEMA = ("ATA", "OFEX")
CONFIANCAS_VALIDAS = ("alta", "media", "baixa")
PREFIXO_CONSENSO = "consenso D-047"


def ler_chave(import_os=None) -> str | None:
    """Chave do classificador, so da variavel de ambiente. Nunca de arquivo."""
    import os as _os

    ambiente = import_os if import_os is not None else _os.environ
    chave = (ambiente.get(NOME_VAR_CHAVE) or "").strip()
    return chave or None


def ler_conf_classificacao(cfg: dict) -> dict:
    """Bloco classificacao_temas do config, com endpoint, modelos e limites."""
    bloco = (cfg or {}).get("classificacao_temas")
    if not isinstance(bloco, dict):
        raise SystemExit(
            "config_cidade.json: bloco classificacao_temas ausente. "
            "O mantenedor precisa declarar endpoint e modelos (D-047)."
        )
    padrao = str(bloco.get("endpoint") or "").strip()
    modelos = []
    for item in bloco.get("modelos") or []:
        if not isinstance(item, dict):
            raise SystemExit("config_cidade.json: classificacao_temas.modelos deve ter objetos com id.")
        mid = str(item.get("id") or "").strip()
        if not mid:
            raise SystemExit("config_cidade.json: classificacao_temas.modelos com id vazio.")
        ponta = str(item.get("endpoint") or "").strip() or padrao
        if not ponta:
            raise SystemExit(
                f"config_cidade.json: modelo {mid} sem endpoint e sem endpoint padrao."
            )
        if mid in [m["id"] for m in modelos]:
            raise SystemExit(f"config_cidade.json: modelo repetido: {mid}.")
        modelos.append({"id": mid, "endpoint": ponta})
    if len(modelos) < 2:
        raise SystemExit(
            "config_cidade.json: classificacao_temas precisa de ao menos dois modelos "
            "para haver consenso (D-047)."
        )
    try:
        limite = int(bloco.get("tempo_limite_s", 60))
        teto_tokens = int(bloco.get("max_tokens_resposta", 300))
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"config_cidade.json: classificacao_temas com numero invalido: {exc}") from exc
    if limite < 1 or teto_tokens < 1:
        raise SystemExit("config_cidade.json: classificacao_temas com tempo_limite_s ou max_tokens_resposta menor que 1.")
    return {"modelos": modelos, "tempo_limite_s": limite, "max_tokens_resposta": teto_tokens}


def montar_prompt(materia: dict, cfg: dict) -> str:
    """Prompt do classificador, seguindo o texto da tarefa TEMA-D047.

    Categorias com descricao vem do config, nunca fixas aqui. "nao se
    aplica" so para atas e oficios. Ementa vazia usa o rotulo de sem
    ementa do config.
    """
    especiais = rotulos_especiais_tema(cfg)
    linhas = [
        "Classifique o tema da materia abaixo em UMA das categorias, usando o nome EXATO.",
        "",
        "CATEGORIAS:",
    ]
    for item in categorias(cfg):
        linhas.append(f"- {item['nome']}: {item['descricao']}")
    linhas.extend(
        [
            f"- {especiais['nao_se_aplica']}: SO para atas (ATA) e oficios do Executivo (OFEX), "
            "que registram a reuniao ou encaminham documentos e nao tratam de um tema proprio.",
            "",
            "MATERIA:",
            f"Tipo: {materia.get('sigla')} {materia.get('numero')}/{materia.get('ano')}",
            f"Ementa oficial do SAPL: {materia.get('ementa') or '(sem ementa registrada no SAPL)'}",
            "",
            "Responda SOMENTE com JSON, sem cerca de codigo e sem texto fora do JSON:",
            '{"tema": "<nome exato de uma categoria ou rotulo especial>", '
            '"confianca": "alta|media|baixa", "justificativa": "<uma frase curta>"}',
        ]
    )
    if not (materia.get("ementa") or "").strip():
        linhas.append(
            f"Materia sem ementa: use o tema exato {especiais['sem_ementa']!r}."
        )
    return "\n".join(linhas)


def extrair_json_resposta(texto: str) -> dict:
    """Le o JSON da resposta, tirando a cerca ```json ... ``` quando houver.

    O mimo envolve a resposta em cerca de codigo; sem tirar a cerca o
    JSON nao e lido. Devolve dicionario ou levanta ValueError.
    """
    limpo = (texto or "").strip()
    if limpo.startswith("```"):
        linhas = limpo.splitlines()
        linhas = linhas[1:]
        if linhas and linhas[-1].strip() == "```":
            linhas = linhas[:-1]
        limpo = "\n".join(linhas).strip()
    dados = json.loads(limpo)
    if not isinstance(dados, dict):
        raise ValueError("resposta JSON nao e um objeto")
    return dados


def sem_travessao(texto: str) -> str:
    """Troca travessao por virgula na justificativa gravada."""
    return (texto or "").replace("\u2014", ",").replace("\u2013", ",")


def _corpo_chat(modelo_id: str, prompt: str, teto_tokens: int) -> dict:
    return {
        "model": modelo_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": int(teto_tokens),
    }


def _corpo_responses(modelo_id: str, prompt: str, teto_tokens: int) -> dict:
    return {
        "model": modelo_id,
        "input": prompt,
        "temperature": 0,
        "max_output_tokens": int(teto_tokens),
    }


def _texto_e_tokens_chat(dados: dict) -> tuple[str | None, int]:
    try:
        escolhas = dados.get("choices") or []
        texto = (((escolhas[0] or {}).get("message") or {}).get("content")) or ""
        uso = dados.get("usage") or {}
        tokens = int(uso.get("total_tokens") or 0)
        if not tokens:
            tokens = int(uso.get("prompt_tokens") or 0) + int(uso.get("completion_tokens") or 0)
        return texto, max(0, tokens)
    except (IndexError, TypeError, ValueError, AttributeError):
        return None, 0


def _texto_e_tokens_responses(dados: dict) -> tuple[str | None, int]:
    try:
        partes: list[str] = []
        for bloco in dados.get("output") or []:
            for item in (bloco or {}).get("content") or []:
                texto = (item or {}).get("text")
                if texto:
                    partes.append(str(texto))
        uso = dados.get("usage") or {}
        tokens = int(uso.get("total_tokens") or 0)
        if not tokens:
            tokens = int(uso.get("input_tokens") or 0) + int(uso.get("output_tokens") or 0)
        return ("\n".join(partes) if partes else ""), max(0, tokens)
    except (TypeError, ValueError, AttributeError):
        return None, 0


def _e_limite_de_uso(status: int | None, corpo: str) -> bool:
    if status == 429:
        return True
    texto = (corpo or "").lower()
    return any(
        marca in texto
        for marca in ("rate limit", "limite de uso", "limite do plano", "quota", "usage limit", "too many requests")
    )


def pedir_modelo(
    modelo_id: str,
    endpoint: str,
    prompt: str,
    chave: str,
    sessao_id: str,
    tempo_limite: int,
    teto_tokens: int,
) -> tuple[dict | None, str | None, int, float]:
    """Um pedido ao modelo, com no maximo uma tentativa extra.

    Devolve (resposta, erro, tokens, segundos). Resposta e o dicionario
    {tema, confianca, justificativa} ou None. Erro e texto curto sem a
    chave quando a chamada falhou. Erro de limite de uso do plano conta
    como resposta invalida daquele modelo.
    """
    e_responses = "responses" in (endpoint or "")
    corpo = (
        _corpo_responses(modelo_id, prompt, teto_tokens)
        if e_responses
        else _corpo_chat(modelo_id, prompt, teto_tokens)
    )
    dados_envio = json.dumps(corpo).encode("utf-8")
    ultimo_erro = "sem resposta"
    comeco = time.monotonic()
    for _tentativa in range(2):
        pedido = urllib.request.Request(
            endpoint,
            data=dados_envio,
            method="POST",
            headers={
                "Authorization": "Bearer xxx",
                "Content-Type": "application/json",
                "User-Agent": AGENTE_HTTP,
                "x-opencode-session": sessao_id,
            },
        )
        # A chave real entra so no objeto ja montado, nunca em texto de log.
        pedido.add_header("Authorization", f"Bearer {chave}")
        try:
            with urllib.request.urlopen(pedido, timeout=int(tempo_limite)) as resposta:
                bruto = resposta.read(200000).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            try:
                corpo_erro = exc.read(20000).decode("utf-8", errors="replace")
            except (OSError, ValueError):
                corpo_erro = ""
            if _e_limite_de_uso(exc.code, corpo_erro):
                return None, "limite de uso do plano", 0, time.monotonic() - comeco
            ultimo_erro = f"HTTP {exc.code}: {corpo_erro[:200]}"
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            ultimo_erro = f"falha de rede: {exc}"[:200]
            continue
        try:
            dados = json.loads(bruto)
        except ValueError:
            ultimo_erro = f"resposta sem JSON: {bruto[:200]}"
            continue
        if e_responses:
            texto, tokens = _texto_e_tokens_responses(dados)
        else:
            texto, tokens = _texto_e_tokens_chat(dados)
        if texto is None:
            ultimo_erro = f"formato inesperado: {bruto[:200]}"
            continue
        try:
            return extrair_json_resposta(texto), None, tokens, time.monotonic() - comeco
        except ValueError as exc:
            ultimo_erro = f"JSON invalido na resposta: {exc}"
            continue
    return None, ultimo_erro, 0, time.monotonic() - comeco


def validar_resposta(resposta: dict, materia: dict, cfg: dict) -> tuple[str, str, str] | None:
    """Resposta valida: tema na lista do config, confianca e justificativa.

    "nao se aplica" so vale para ATA e OFEX. Resposta fora da lista
    conta como invalida e nao entra no consenso.
    """
    aceitos = set(t["nome"] for t in categorias(cfg))
    especiais = rotulos_especiais_tema(cfg)
    aceitos |= {especiais["nao_se_aplica"], especiais["sem_ementa"]}
    tema = str((resposta or {}).get("tema") or "").strip()
    confianca = str((resposta or {}).get("confianca") or "").strip().lower()
    justificativa = sem_travessao(str((resposta or {}).get("justificativa") or "").strip())
    if tema not in aceitos or confianca not in CONFIANCAS_VALIDAS or not justificativa:
        return None
    if tema == especiais["nao_se_aplica"] and str(materia.get("sigla")) not in TIPOS_SEM_TEMA:
        return None
    if tema == especiais["sem_ementa"] and (materia.get("ementa") or "").strip():
        return None
    return tema, confianca, justificativa


def classificar_materia(
    materia: dict,
    cfg: dict,
    chave: str,
    sessao_id: str,
    conf: dict,
    pedir=pedir_modelo,
) -> list[dict]:
    """Um pedido por modelo, um de cada vez, sem paralelismo.

    Devolve os votos validos: [{modelo, tema, confianca, justificativa,
    tokens, tempo_s}]. Voto invalido ou com limite de uso nao entra.
    """
    votos: list[dict] = []
    prompt = montar_prompt(materia, cfg)
    for modelo in conf["modelos"]:
        resposta, _erro, tokens, segundos = pedir(
            modelo["id"],
            modelo["endpoint"],
            prompt,
            chave,
            sessao_id,
            conf["tempo_limite_s"],
            conf["max_tokens_resposta"],
        )
        if resposta is None:
            continue
        valido = validar_resposta(resposta, materia, cfg)
        if valido is None:
            continue
        tema, confianca, justificativa = valido
        votos.append(
            {
                "modelo": modelo["id"],
                "tema": tema,
                "confianca": confianca,
                "justificativa": justificativa,
                "tokens": int(tokens),
                "tempo_s": round(float(segundos), 1),
            }
        )
    return votos


def consenso_de(votos: list[dict]) -> dict | None:
    """Dois ou tres votos iguais formam consenso; senao, None."""
    contagem: dict[str, list[dict]] = {}
    for voto in votos or []:
        contagem.setdefault(voto["tema"], []).append(voto)
    for tema, iguais in contagem.items():
        if len(iguais) >= 2:
            primeiro = iguais[0]
            modelos = sorted({v["modelo"] for v in iguais})
            return {
                "tema": tema,
                "confianca": primeiro["confianca"],
                "justificativa": primeiro["justificativa"],
                "modelos": modelos,
            }
    return None


def pasta_lote_mais_recente() -> Path:
    candidatas = [
        caminho
        for caminho in BRUTOS.glob("lote_*")
        if caminho.is_dir()
        and not caminho.name.endswith("_autoria")
        and "porsessao" not in caminho.name
        and "tramitacao" not in caminho.name
        and next(caminho.glob("materialegislativa_ano*_p*.json"), None) is not None
    ]
    if not candidatas:
        raise SystemExit("Nenhuma pasta de lote com materias em dados/brutos.")
    return sorted(candidatas)[-1]


def mapa_siglas(pasta_lote: Path) -> dict[int, str]:
    """Id do tipo de materia para sigla, lido do catalogo do lote."""
    mapa: dict[int, str] = {}
    for caminho in sorted(pasta_lote.glob("tipomaterialegislativa_p*.json")):
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for item in (dados.get("results") or []):
            if isinstance(item, dict) and item.get("id") is not None:
                mapa[int(item["id"])] = str(item.get("sigla") or "").strip()
    return mapa


def ler_materias_brutas(pasta_lote: Path, cfg: dict) -> dict[int, dict]:
    """Materias do recorte no lote mais recente, por id."""
    siglas = mapa_siglas(pasta_lote)
    base = endereco_sapl(cfg)
    materias: dict[int, dict] = {}
    for caminho in sorted(pasta_lote.glob("materialegislativa_ano*_p*.json")):
        if "_t" in caminho.name.rsplit(".json", 1)[0].rsplit("_p", 1)[-1]:
            continue
        try:
            dados = json.loads(caminho.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            continue
        for item in dados.get("results") or []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            mid = int(item["id"])
            tipo = item.get("tipo")
            sigla = siglas.get(int(tipo)) if tipo is not None else ""
            materias[mid] = {
                "id": mid,
                "ano": int(item.get("ano") or 0),
                "sigla": sigla or "",
                "numero": item.get("numero"),
                "ementa": str(item.get("ementa") or ""),
                "link": f"{base}/materia/{mid}",
            }
    return materias


def ler_temas() -> dict:
    if not ARQUIVO_TEMAS.is_file():
        raise SystemExit(f"Arquivo ausente: {ARQUIVO_TEMAS.name}.")
    return json.loads(ARQUIVO_TEMAS.read_text(encoding="utf-8"))


def materias_sem_tema(brutas: dict[int, dict], dados_temas: dict) -> list[dict]:
    """Materias do recorte ainda sem entrada em temas_materias.json."""
    conhecidos = {int(item["id"]) for item in dados_temas.get("materias") or []}
    novas = [info for mid, info in brutas.items() if mid not in conhecidos]
    return sorted(novas, key=lambda item: int(item["id"]))


def entrada_de_consenso(consenso: dict, materia: dict, hoje: str) -> dict:
    modelos = ", ".join(consenso["modelos"])
    numero = materia.get("numero")
    return {
        "id": int(materia["id"]),
        "ano": int(materia["ano"]),
        "sigla": str(materia.get("sigla") or ""),
        "numero": int(numero) if numero is not None else numero,
        "tema": consenso["tema"],
        "confianca": consenso["confianca"],
        "justificativa": consenso["justificativa"],
        "link": link_materia(int(materia["id"])),
        "classificado_por": f"{PREFIXO_CONSENSO}: {modelos}",
        "revisada_por_humano": False,
        "revisado_por": "",
        "data": hoje,
    }


def gravar_entradas(entradas: list[dict]) -> None:
    """Acrescenta as entradas mantendo a ordem por id e atualiza o total."""
    dados = ler_temas()
    lista = list(dados.get("materias") or [])
    ids = {int(item["id"]) for item in lista}
    for entrada in entradas:
        if int(entrada["id"]) not in ids:
            lista.append(entrada)
            ids.add(int(entrada["id"]))
    lista.sort(key=lambda item: int(item["id"]))
    dados["materias"] = lista
    dados["total"] = len(lista)
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    ARQUIVO_TEMAS.write_bytes(texto.encode("utf-8"))


def titulo_revisao(materia: dict) -> str:
    return f"Tema para revisao: {materia.get('sigla')} {materia.get('numero')}/{materia.get('ano')}"


def corpo_revisao(materia: dict, votos: list[dict], modelos: list[str], motivo: str = "") -> str:
    if motivo == "sem chave do classificador na execucao":
        primeira = (
            "A materia nova ficou sem tema porque a execucao nao tinha "
            "a chave do classificador (D-047)."
        )
    else:
        primeira = "A materia nova ficou sem tema porque os modelos nao formaram consenso (D-047)."
    linhas = [
        primeira,
        "",
        f"Materia: {materia.get('sigla')} {materia.get('numero')}/{materia.get('ano')} (id {materia.get('id')}).",
        f"Ementa oficial: {(materia.get('ementa') or '').strip() or '(sem ementa no SAPL)'}",
        f"Link do SAPL: {materia.get('link')}",
        "",
        "Respostas dos modelos:",
    ]
    por_modelo = {v["modelo"]: v for v in votos}
    for nome in modelos:
        voto = por_modelo.get(nome)
        if voto is None:
            linhas.append(f"- {nome}: sem resposta valida.")
        else:
            linhas.append(
                f"- {nome}: tema {voto['tema']!r}, confianca {voto['confianca']}, {voto['justificativa']}"
            )
    return "\n".join(linhas) + "\n"


def issue_aberta_existe(titulo: str, correr=None) -> bool:
    """Procura issue aberta com o mesmo titulo antes de abrir outra."""
    import subprocess as _sp

    executar = correr or _sp.run
    resultado = executar(
        ["gh", "issue", "list", "--search", f"{titulo} in:title", "--state", "open", "--json", "number,title"],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        return False
    try:
        achadas = json.loads(resultado.stdout or "[]")
    except ValueError:
        return False
    return any(str(item.get("title") or "").strip() == titulo for item in achadas)


def garantir_issue(titulo: str, corpo: str, correr=None) -> str:
    """Abre a issue de revisao, sem duplicar titulo aberto. Devolve aviso ou vazio."""
    import subprocess as _sp

    executar = correr or _sp.run
    try:
        if issue_aberta_existe(titulo, executar):
            return f"issue ja aberta: {titulo}"
        resultado = executar(
            ["gh", "issue", "create", "--title", titulo, "--body", corpo],
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError) as exc:
        return f"issue nao aberta ({titulo}): {exc}"[:200]
    if resultado.returncode != 0:
        detalhe = ((resultado.stderr or "") + " " + (resultado.stdout or "")).strip()
        return f"issue nao aberta ({titulo}): {detalhe[:160]}"
    return ""


def abrir_issues_revisao(resultado: dict, correr=None) -> list[str]:
    """Abre as issues de revisao das pendentes. So chama no fim, quando publica.

    Se a semana falhar antes (sanidade, testes, regras), nao abre: a
    materia volta a ser tentada na semana seguinte. Devolve os avisos.
    """
    avisos: list[str] = []
    modelos = resultado.get("modelos") or []
    for pendente in resultado.get("pendentes") or []:
        materia = pendente["materia"]
        corpo = corpo_revisao(materia, pendente["votos"], modelos, pendente.get("motivo") or "")
        aviso = garantir_issue(titulo_revisao(materia), corpo, correr)
        if aviso:
            avisos.append(aviso)
    return avisos


def classificar_novas(
    cfg: dict | None = None,
    chave: str | None = None,
    hoje: str | None = None,
    pedir=pedir_modelo,
    correr=None,
    gravar: bool = True,
    abrir_issues: bool = True,
) -> dict:
    """Classifica as materias novas do recorte sem tema.

    Sem a chave, nao classifica e nao falha: tudo volta como pendente.
    Entrada com revisada_por_humano true nunca e alterada; entrada ja
    classificada por consenso nao e classificada de novo (ambas ja tem
    entrada no arquivo, por isso nem aparecem como novas). Devolve
    {novas, consenso, pendentes, avisos, tokens_total}.

    Com abrir_issues False, as issues de revisao nao sao abertas aqui:
    quem chama abre depois, com abrir_issues_revisao, so quando a semana
    vai mesmo publicar.
    """
    cfg = cfg if cfg is not None else carregar_config()
    conf = ler_conf_classificacao(cfg)
    dados_temas = ler_temas()
    pasta_lote = pasta_lote_mais_recente()
    brutas = ler_materias_brutas(pasta_lote, cfg)
    novas = materias_sem_tema(brutas, dados_temas)
    dia = hoje or date.today().isoformat()
    nomes_modelos = [m["id"] for m in conf["modelos"]]
    resultado: dict = {
        "novas": [m["id"] for m in novas],
        "consenso": [],
        "pendentes": [],
        "avisos": [],
        "tokens_total": 0,
        "modelos": list(nomes_modelos),
    }
    if not novas:
        return resultado
    if chave:
        sessao_id = uuid.uuid4().hex
        for materia in novas:
            votos = classificar_materia(materia, cfg, chave, sessao_id, conf, pedir)
            resultado["tokens_total"] += sum(int(v.get("tokens") or 0) for v in votos)
            consenso = consenso_de(votos)
            if consenso is None:
                resultado["pendentes"].append(
                    {"materia": materia, "votos": votos, "motivo": "sem consenso entre os modelos"}
                )
                continue
            resultado["consenso"].append(entrada_de_consenso(consenso, materia, dia))
        if gravar and resultado["consenso"]:
            gravar_entradas(resultado["consenso"])
    else:
        for materia in novas:
            resultado["pendentes"].append(
                {"materia": materia, "votos": [], "motivo": "sem chave do classificador na execucao"}
            )
    if abrir_issues:
        resultado["avisos"].extend(abrir_issues_revisao(resultado, correr))
    return resultado


def linhas_changelog_temas(resultado: dict, sem_chave: bool) -> list[str]:
    """Linhas da semana: quantas por consenso, quantas aguardam revisao."""
    novas = resultado.get("novas") or []
    if not novas:
        return []
    n_consenso = len(resultado.get("consenso") or [])
    n_pendentes = len(resultado.get("pendentes") or [])
    if sem_chave:
        return [
            f"Temas de {len(novas)} materias novas aguardam classificacao "
            "(a execucao nao tinha a chave do classificador)."
        ]
    return [
        f"Temas de materias novas: {n_consenso} por consenso de tres modelos (D-047), "
        f"{n_pendentes} aguardam revisao do mantenedor."
    ]


def sondar_ultimas_revisadas(cfg: dict | None = None, chave: str | None = None, pedir=pedir_modelo) -> dict:
    """Sondagem manual: roda os modelos nas ultimas 7 revisadas, sem gravar.

    Mostra no log, para cada modelo, se respondeu, o tempo, o tema dado
    e se bateu com o tema revisado, mais o consenso por materia e o
    total de tokens. Nunca grava nada nem faz commit.
    """
    cfg = cfg if cfg is not None else carregar_config()
    conf = ler_conf_classificacao(cfg)
    dados_temas = ler_temas()
    revisadas = [m for m in dados_temas.get("materias") or [] if m.get("revisada_por_humano") is True]
    alvo = revisadas[-7:]
    pasta_lote = pasta_lote_mais_recente()
    brutas = ler_materias_brutas(pasta_lote, cfg)
    nomes_modelos = [m["id"] for m in conf["modelos"]]
    sessao_id = uuid.uuid4().hex
    saida: dict = {"materias": [], "tokens_total": 0}
    for entrada in alvo:
        mid = int(entrada["id"])
        bruta = brutas.get(mid, {"id": mid, "ano": entrada.get("ano"), "sigla": entrada.get("sigla"),
                                 "numero": entrada.get("numero"), "ementa": "", "link": entrada.get("link")})
        votos = classificar_materia(bruta, cfg, chave, sessao_id, conf, pedir)
        consenso = consenso_de(votos)
        por_modelo = {v["modelo"]: v for v in votos}
        linhas_modelos = []
        for nome in nomes_modelos:
            voto = por_modelo.get(nome)
            if voto is None:
                linhas_modelos.append({"modelo": nome, "respondeu": False, "tempo_s": None,
                                        "tema": None, "bateu": False, "tokens": 0})
            else:
                bateu = voto["tema"] == entrada.get("tema")
                linhas_modelos.append({"modelo": nome, "respondeu": True, "tempo_s": voto["tempo_s"],
                                        "tema": voto["tema"], "bateu": bateu, "tokens": voto["tokens"]})
                saida["tokens_total"] += int(voto.get("tokens") or 0)
        bateu_consenso = consenso is not None and consenso["tema"] == entrada.get("tema")
        saida["materias"].append(
            {
                "id": mid,
                "sigla": entrada.get("sigla"),
                "numero": entrada.get("numero"),
                "ano": entrada.get("ano"),
                "tema_revisado": entrada.get("tema"),
                "modelos": linhas_modelos,
                "consenso": (consenso["tema"] if consenso else None),
                "consenso_bateu": bateu_consenso,
            }
        )
    return saida


def imprimir_sondagem(saida: dict) -> None:
    for item in saida.get("materias") or []:
        print(f"Materia {item['sigla']} {item['numero']}/{item['ano']} (id {item['id']}): tema revisado {item['tema_revisado']!r}.")
        for linha in item["modelos"]:
            if not linha["respondeu"]:
                print(f"  {linha['modelo']}: sem resposta valida.")
                continue
            bateu = "bateu" if linha["bateu"] else "divergiu"
            print(
                f"  {linha['modelo']}: respondeu em {linha['tempo_s']} s, "
                f"tema {linha['tema']!r}, {bateu} do revisado, {linha['tokens']} tokens."
            )
        if item["consenso"] is None:
            print("  Consenso: sem consenso (tres votos diferentes ou menos de duas respostas validas).")
        else:
            estado = "bate com o revisado" if item["consenso_bateu"] else "diverge do revisado"
            print(f"  Consenso: {item['consenso']!r} ({estado}).")
    print(f"Total de tokens usados na sondagem: {saida.get('tokens_total') or 0}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classifica temas de materias novas por consenso D-047.")
    parser.add_argument(
        "--sondagem",
        action="store_true",
        help="Roda os modelos nas ultimas 7 materias revisadas, sem gravar nada.",
    )
    args = parser.parse_args(argv)
    cfg = carregar_config()
    chave = ler_chave()
    if args.sondagem:
        if not chave:
            print("Sondagem sem a chave do classificador: nada foi consultado e nada foi gravado.")
            return 0
        saida = sondar_ultimas_revisadas(cfg, chave)
        imprimir_sondagem(saida)
        return 0
    resultado = classificar_novas(cfg, chave)
    for linha in linhas_changelog_temas(resultado, sem_chave=not chave):
        print(linha)
    for aviso in resultado.get("avisos") or []:
        print(f"Aviso: {aviso}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
