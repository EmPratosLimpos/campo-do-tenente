#!/usr/bin/env python3
"""Gera JSON da aba Câmara e consolidado da legislatura (soma dos anos do recorte)."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
from datetime import datetime, timezone, timedelta

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
if str(RAIZ / "coletor") not in sys.path:
    sys.path.insert(0, str(RAIZ / "coletor"))

from config_cidade import anos_recorte, carregar_config  # noqa: E402

TZ = timezone(timedelta(hours=-3))
SUFIXO_LEGISLATURA = "legislatura"

RESULTADO_NAO_MAPEADO = "resultado_nao_mapeado"
RESULTADO_PRIMEIRO_TURNO = "primeiro_turno"
RESULTADO_TURNO_NAO_IDENTIFICADO = "turno_nao_identificado"
TURNO_PRIMEIRO = "1o turno"
TURNO_NAO_IDENTIFICADO = "turno nao identificado"


def resultado_nao_deliberativo(nome_oficial: str | None) -> str | None:
    """Balde proprio para voto sem deliberacao, com o nome oficial."""
    texto = str(nome_oficial or "").strip()
    if not texto:
        return None
    return "nao_deliberativo:" + texto

CHAVES_CONTAGEM_VOTO = (
    "sim",
    "nao",
    "abstencao",
    "nao_votou",
    "presidente_que_nao_votou",
    "ausente_com_justificativa",
    "ausente_sem_justificativa",
    "fora_do_mandato",
    "presente_sem_voto_individual_registrado",
    "licenca_tratamento_saude",
)

CHAVES_META_SOMA = (
    "n_sessoes_ordinarias",
    "n_presencas",
    "n_faltas_com_justificativa",
    "n_faltas_sem_justificativa",
    "n_sessoes_fora_do_mandato",
    "n_sessoes_licenca",
    "n_votacoes",
    "n_registros_votacao",
    "n_votacoes_com_voto_individual",
    "n_votacoes_sem_voto_individual",
    "n_projetos_lei_legislativo",
    "n_projetos_lei_executivo",
    "n_projetos_lei_legislativo_e_executivo",
)


def normalizar_resultado(resultado_texto: str | None, frase: str | None) -> tuple[str, str | None]:
    oficial = " ".join(filter(None, [resultado_texto, frase])).strip()
    texto = oficial.upper()
    if "UNANIM" in texto:
        return "unanimidade", oficial or None
    if "REJEIT" in texto:
        return "rejeitado", oficial or None
    if "MAIORIA" in texto or "ABSOLUT" in texto:
        return "maioria", oficial or None
    if "APROV" in texto and "REJEIT" not in texto:
        return "maioria", oficial or None
    if not texto:
        return RESULTADO_NAO_MAPEADO, oficial or None
    return RESULTADO_NAO_MAPEADO, oficial or None


def placar_resumido(vot: dict) -> str:
    tot = vot.get("totais_oficiais") or {}
    sim = tot.get("numero_votos_sim")
    nao = tot.get("numero_votos_nao")
    if sim is None and nao is None:
        return ""
    return f"{sim or 0} x {nao or 0}"


def tema_display(tema_bruto: str, cfg: dict) -> str:
    especiais = cfg.get("categorias", {}).get("rotulos_especiais", {})
    if tema_bruto in especiais.values() or tema_bruto.lower() in (
        especiais.get("nao_se_aplica", "").lower(),
        especiais.get("sem_ementa", "").lower(),
    ):
        return tema_bruto
    for item in cfg.get("categorias", {}).get("lista", []):
        if item["nome"].lower() == str(tema_bruto).lower():
            return item["nome"]
    return tema_bruto


def carregar_temas() -> dict[int, str]:
    path = RAIZ / "dados" / "tratados" / "temas_materias.json"
    dados = json.loads(path.read_text(encoding="utf-8"))
    return {int(m["id"]): m["tema"] for m in dados.get("materias", [])}


def pll_votados_no_ano(atuacao: dict) -> list[dict]:
    """Um item por materia, com TODAS as votacoes com resultado.

    Vale voto deliberativo com resultado e voto com nome oficial
    (adiada, vistas, retirada). Materia votada em mais de uma sessao
    aparece uma vez por periodo, mostrando a votacao daquele periodo
    e a lista de todas as datas.
    """
    itens = []
    for p in atuacao.get("projetos_lei", []):
        if p.get("tipo_sigla") != "PLEG":
            continue
        votos = [
            v
            for v in (p.get("votacoes_ordinarias") or [])
            if v.get("situacao_oficial_sapl")
            or v.get("resultado_texto_sapl")
            or (v.get("tipo_resultado_nome") or "").strip()
        ]
        if not votos:
            continue
        votos = sorted(
            votos,
            key=lambda v: (v.get("data_sessao") or "", v.get("sessao_id") or 0),
        )
        itens.append(
            {
                "projeto": p,
                "votacoes": votos,
            }
        )
    return itens


def montar_item(
    projeto: dict, voto_mostrado: dict, votacoes: list[dict], cfg: dict, temas: dict[int, str]
) -> dict:
    mid = int(projeto["id"])
    tema_bruto = temas.get(mid) or projeto.get("tema") or "Outros"
    tema = tema_display(tema_bruto, cfg)
    turno = voto_mostrado.get("turno")
    tipo_nome = (voto_mostrado.get("tipo_resultado_nome") or "").strip() or None
    if turno is None and tipo_nome:
        resultado = resultado_nao_deliberativo(tipo_nome)
        resultado_oficial = tipo_nome
    else:
        resultado, resultado_oficial = normalizar_resultado(
            voto_mostrado.get("resultado_texto_sapl"),
            voto_mostrado.get("frase_resultado_sapl"),
        )
        if turno == TURNO_PRIMEIRO:
            resultado = RESULTADO_PRIMEIRO_TURNO
        elif turno == TURNO_NAO_IDENTIFICADO:
            resultado = RESULTADO_TURNO_NAO_IDENTIFICADO
    tipo = f"PLL {projeto.get('numero')}/{projeto.get('ano')}"
    return {
        "id": mid,
        "tipo": tipo,
        "resultado": resultado,
        "resultado_oficial": resultado_oficial,
        "turno": turno,
        "tipo_resultado": tipo_nome,
        "ementa": projeto.get("ementa") or "",
        "categoria": tema,
        "placar": placar_resumido(voto_mostrado),
        "data_sessao": voto_mostrado.get("data_sessao"),
        "sessao_id": voto_mostrado.get("sessao_id"),
        "votacoes": [
            {
                "data_sessao": v.get("data_sessao"),
                "sessao_id": v.get("sessao_id"),
                "turno": v.get("turno"),
                "tipo_resultado": (v.get("tipo_resultado_nome") or "").strip() or None,
            }
            for v in votacoes
        ],
    }


def _voto_mais_recente(votos: list[dict]) -> dict | None:
    if not votos:
        return None
    return max(
        votos,
        key=lambda v: (v.get("data_sessao") or "", v.get("sessao_id") or 0),
    )


def periodos(
    materias: list[dict], sessoes: list[dict], cfg: dict, temas: dict[int, str]
) -> tuple[list, list, list]:
    if not materias:
        return [], [], []
    datas = sorted({s["data"] for s in sessoes if s.get("data")})
    ultima_data = datas[-1] if datas else None
    sessao_ids_ultima = {s["id"] for s in sessoes if s.get("data") == ultima_data}

    if ultima_data:
        y, mo, _ = map(int, ultima_data.split("-"))
        mes_ant = mo - 1
        ano_ant = y
        if mes_ant < 1:
            mes_ant = 12
            ano_ant -= 1
    else:
        ano_ant, mes_ant = 0, 0

    def no_mes_anterior(voto: dict) -> bool:
        data = voto.get("data_sessao") or ""
        partes = data.split("-")
        return (
            len(partes) == 3
            and partes[0] == str(ano_ant)
            and int(partes[1]) == mes_ant
        )

    sessao, mes, todo = [], [], []
    for entry in materias:
        projeto = entry["projeto"]
        votos = entry["votacoes"]
        voto_sessao = _voto_mais_recente(
            [v for v in votos if v.get("sessao_id") in sessao_ids_ultima]
        )
        voto_mes = _voto_mais_recente([v for v in votos if no_mes_anterior(v)])
        voto_todo = _voto_mais_recente(votos)
        if voto_sessao is not None:
            sessao.append(montar_item(projeto, voto_sessao, votos, cfg, temas))
        if voto_mes is not None:
            mes.append(montar_item(projeto, voto_mes, votos, cfg, temas))
        if voto_todo is not None:
            todo.append(montar_item(projeto, voto_todo, votos, cfg, temas))
    return sessao, mes, todo


def filtros_de(lista: list[dict]) -> list[dict]:
    """Contagens por resultado: 1o turno, turno nao identificado e voto
    sem deliberacao tem lista propria e nao entram na contagem."""
    total = len(lista)
    uni = sum(1 for m in lista if m["resultado"] == "unanimidade")
    mai = sum(1 for m in lista if m["resultado"] == "maioria")
    rej = sum(1 for m in lista if m["resultado"] == "rejeitado")
    pri = sum(1 for m in lista if m["resultado"] == RESULTADO_PRIMEIRO_TURNO)
    nao_id = sum(1 for m in lista if m["resultado"] == RESULTADO_TURNO_NAO_IDENTIFICADO)
    nao_delib: dict[str, int] = {}
    for m in lista:
        resultado = m["resultado"] or ""
        if resultado.startswith("nao_deliberativo:"):
            nao_delib[resultado] = nao_delib.get(resultado, 0) + 1
    outro = total - uni - mai - rej - pri - nao_id - sum(nao_delib.values())
    filtros = [
        {"id": "", "rotulo": "Todos", "qtd": total},
        {"id": "unanimidade", "rotulo": "Unânimes", "qtd": uni},
        {"id": "maioria", "rotulo": "Maioria", "qtd": mai},
    ]
    if rej:
        filtros.append({"id": "rejeitado", "rotulo": "Rejeitados", "qtd": rej})
    if pri:
        filtros.append({"id": RESULTADO_PRIMEIRO_TURNO, "rotulo": "1o turno", "qtd": pri})
    for bucket in sorted(nao_delib):
        nome = bucket.split(":", 1)[1] if ":" in bucket else bucket
        filtros.append({"id": bucket, "rotulo": nome.strip() or bucket, "qtd": nao_delib[bucket]})
    if nao_id:
        filtros.append(
            {
                "id": RESULTADO_TURNO_NAO_IDENTIFICADO,
                "rotulo": "Turno não identificado",
                "qtd": nao_id,
            }
        )
    if outro:
        filtros.append(
            {"id": RESULTADO_NAO_MAPEADO, "rotulo": "Resultado não mapeado", "qtd": outro}
        )
    return filtros


def gravar_camara(sufixo: str, sessao: list, mes: list, todo: list, lista: list, out: pathlib.Path) -> None:
    camara = {"sessao": sessao, "mes": mes, "todo": todo}
    tags = {}
    try:
        import json
        with open(RAIZ / "dados" / "tratados" / "temas_materias.json", "r", encoding="utf-8") as f_temas:
            todas = json.load(f_temas)
            for mat in todas.get("materias", []):
                tags[str(mat["id"])] = {
                    "tag_tipo": mat.get("sigla", "Outros"),
                    "tag_tema": mat.get("tema", "Outros")
                }
    except Exception:
        pass
    # Sobrepõe com a lista atual caso necessário
    for m in lista:
        tags[str(m["id"])] = {"tag_tipo": "PLL", "tag_tema": m["categoria"]}
    filtros = {
        "sessao": filtros_de(sessao),
        "mes": filtros_de(mes),
        "todo": filtros_de(todo),
    }
    (out / f"materias_camara_{sufixo}.json").write_bytes(
        (json.dumps(camara, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    (out / f"materias_tags_{sufixo}.json").write_bytes(
        (json.dumps(tags, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    (out / f"filtros_materia_{sufixo}.json").write_bytes(
        (json.dumps(filtros, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )


def gerar_ano(ano: int, cfg: dict) -> None:
    path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
    atuacao = json.loads(path.read_text(encoding="utf-8"))
    temas = carregar_temas()
    bruto = pll_votados_no_ano(atuacao)
    sessao, mes, todo = periodos(bruto, atuacao.get("sessoes") or [], cfg, temas)
    out = RAIZ / "dados" / "tratados"
    gravar_camara(str(ano), sessao, mes, todo, todo, out)
    print(f"Ano {ano}: sessao={len(sessao)} mes={len(mes)} todo={len(todo)} PLL")


def _ordenar_sessoes(sessoes: list[dict]) -> list[dict]:
    vistos: dict[int, dict] = {}
    for s in sessoes:
        sid = s.get("id")
        if sid is None:
            continue
        vistos[int(sid)] = s
    return sorted(vistos.values(), key=lambda x: (x.get("data") or "", x.get("id") or 0))


def _mesclar_por_categoria(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for chave, val in (b or {}).items():
        out[chave] = out.get(chave, 0) + val
    return out


def _mesclar_projetos_lei_vereador(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a or {})
    bb = b or {}
    for chave in (
        "total_propostos",
        "aprovados",
        "rejeitados",
        "em_tramitacao",
        "outro_resultado_oficial",
        "autorias_conjuntas",
    ):
        out[chave] = (out.get(chave) or 0) + (bb.get(chave) or 0)
    out["por_categoria"] = _mesclar_por_categoria(
        out.get("por_categoria") or {}, bb.get("por_categoria") or {}
    )
    lista = list(out.get("lista") or [])
    ids = {item.get("id") for item in lista if item.get("id") is not None}
    for item in bb.get("lista") or []:
        iid = item.get("id")
        if iid is not None and iid in ids:
            continue
        lista.append(item)
        if iid is not None:
            ids.add(iid)
    out["lista"] = lista
    return out


def _recomputar_presenca(por_sessao: list[dict], fora: int = 0) -> dict:
    """Soma da legislatura na mesma regra do ano.

    Sessoes fora da janela do mandato nao estao na lista e chegam como
    contagem separada. Qualquer situacao que nao seja presenca, falta ou
    fora conta como licenca: tem rotulo proprio, nunca e falta, mas
    entra no total da taxa.
    """
    presencas = 0
    faltas_j = 0
    faltas_s = 0
    por_afast: dict[str, int] = {}
    for s in por_sessao:
        sit = s.get("situacao") or ""
        if sit == "presente":
            presencas += 1
        elif sit == "falta_com_justificativa":
            faltas_j += 1
        elif sit == "falta_sem_justificativa":
            faltas_s += 1
        elif sit == "fora_do_mandato":
            raise ValueError("sessao fora do mandato na lista de presenca")
        elif sit:
            por_afast[sit] = por_afast.get(sit, 0) + 1
    licenca = sum(por_afast.values())
    fora = int(fora)
    no_mandato = presencas + faltas_j + faltas_s + licenca
    total_sessoes = len(por_sessao) + fora
    taxa = round((presencas / no_mandato) * 100, 2) if no_mandato else 0.0
    pct_faltas = round(((faltas_j + faltas_s) / no_mandato) * 100, 2) if no_mandato else 0.0
    return {
        "sessoes_ordinarias": no_mandato,
        "sessoes_do_ano": total_sessoes,
        "sessoes_fora_do_mandato": fora,
        "sessoes_licenca": licenca,
        "sessoes_por_afastamento": por_afast,
        "presencas": presencas,
        "faltas_com_justificativa": faltas_j,
        "faltas_sem_justificativa": faltas_s,
        "faltas_totais": faltas_j + faltas_s,
        "percentual_faltas": pct_faltas,
        "taxa_presenca": taxa,
        "por_sessao": por_sessao,
    }


def _mesclar_votos(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a or {})
    bb = b or {}
    for chave in CHAVES_CONTAGEM_VOTO:
        out[chave] = (out.get(chave) or 0) + (bb.get(chave) or 0)
    for chave in ("primeiro_turno_registros", "turno_nao_identificado_registros"):
        out[chave] = (out.get(chave) or 0) + (bb.get(chave) or 0)
    for chave in ("nao_deliberativo_registros",):
        out[chave] = (out.get(chave) or 0) + (bb.get(chave) or 0)
    if bb.get("rotulos"):
        out["rotulos"] = bb["rotulos"]
    nominais = list(out.get("nominais") or [])
    chaves = {
        (n.get("votacao_id"), n.get("sessao_id"), n.get("materia_id")) for n in nominais
    }
    for n in bb.get("nominais") or []:
        chave = (n.get("votacao_id"), n.get("sessao_id"), n.get("materia_id"))
        if chave in chaves:
            continue
        nominais.append(n)
        chaves.add(chave)
    nominais.sort(key=lambda x: (x.get("data_sessao") or "", x.get("votacao_id") or 0))
    out["nominais"] = nominais
    out["total_registros"] = len(nominais)
    return out


def _mesclar_afastamentos(a: list, b: list) -> list:
    out = list(a or [])
    vistos = {
        (
            x.get("tipo"),
            x.get("data_inicio"),
            x.get("data_fim"),
            x.get("rotulo"),
        )
        for x in out
    }
    for item in b or []:
        chave = (item.get("tipo"), item.get("data_inicio"), item.get("data_fim"), item.get("rotulo"))
        if chave in vistos:
            continue
        out.append(item)
        vistos.add(chave)
    return out


def _mesclar_vereador(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    por_sessao = list(out.get("presenca", {}).get("por_sessao") or [])
    ids_sess = {s.get("sessao_id") for s in por_sessao}
    for s in (extra.get("presenca") or {}).get("por_sessao") or []:
        if s.get("sessao_id") in ids_sess:
            continue
        por_sessao.append(s)
        ids_sess.add(s.get("sessao_id"))
    por_sessao.sort(key=lambda x: (x.get("data_sessao") or "", x.get("sessao_id") or 0))
    fora = (out.get("presenca", {}).get("sessoes_fora_do_mandato") or 0) + (
        (extra.get("presenca") or {}).get("sessoes_fora_do_mandato") or 0
    )
    out["presenca"] = _recomputar_presenca(por_sessao, fora)
    out["votos"] = _mesclar_votos(out.get("votos") or {}, extra.get("votos") or {})
    out["projetos_lei"] = _mesclar_projetos_lei_vereador(
        out.get("projetos_lei") or {}, extra.get("projetos_lei") or {}
    )
    out["afastamentos"] = _mesclar_afastamentos(
        out.get("afastamentos") or [], extra.get("afastamentos") or []
    )
    anos = sorted(set((out.get("anos_com_mandato") or []) + (extra.get("anos_com_mandato") or [])))
    out["anos_com_mandato"] = anos
    for campo in ("data_inicio_mandato", "data_fim_mandato"):
        va = out.get(campo)
        vb = extra.get(campo)
        if va and vb:
            if campo == "data_inicio_mandato":
                out[campo] = min(va, vb)
            else:
                out[campo] = max(va, vb)
        elif vb and not va:
            out[campo] = vb
    if extra.get("nota_factual") and not out.get("nota_factual"):
        out["nota_factual"] = extra["nota_factual"]
    return out


def _mesclar_projetos_lei_raiz(listas: list[list]) -> list[dict]:
    por_id: dict[int, dict] = {}
    for lista in listas:
        for p in lista:
            pid = p.get("id")
            if pid is None:
                continue
            por_id[int(pid)] = p

    return list(por_id.values())



def _parse_coleta_em(meta: dict) -> datetime:
    raw = (meta or {}).get("dado_coletado_em") or ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=TZ)


def mesclar_atuacao_legislatura(dados_por_ano: list[dict], anos: list[int], cfg: dict) -> dict:
    if not dados_por_ano:
        raise ValueError("sem dados para mesclar")
    base_meta = copy.deepcopy(dados_por_ano[-1]["meta"])
    base_meta["anos_recorte"] = anos
    base_meta.pop("ano", None)
    base_meta["escopo"] = SUFIXO_LEGISLATURA
    base_meta["gerado_por"] = "dados/tratados/gerar_dados_tela.py"
    lacuna_por_ano: dict[str, dict] = {}
    for d in dados_por_ano:
        ano = d["meta"].get("ano")
        lac = d["meta"].get("lacuna_sessoes_ordinarias")
        if ano is not None and lac:
            lacuna_por_ano[str(int(ano))] = copy.deepcopy(lac)
    base_meta.pop("lacuna_sessoes_ordinarias", None)
    if lacuna_por_ano:
        base_meta["lacuna_sessoes_ordinarias_por_ano"] = lacuna_por_ano

    for chave in CHAVES_META_SOMA:
        base_meta[chave] = sum((d["meta"].get(chave) or 0) for d in dados_por_ano)

    contagem = {ch: 0 for ch in CHAVES_CONTAGEM_VOTO}
    for d in dados_por_ano:
        parcial = (d["meta"].get("contagem_estados") or {})
        for ch in CHAVES_CONTAGEM_VOTO:
            contagem[ch] += parcial.get(ch) or 0
    base_meta["contagem_estados"] = contagem

    coletas = [_parse_coleta_em(d["meta"]) for d in dados_por_ano]
    mais_recente = max(coletas)
    base_meta["dado_coletado_em"] = mais_recente.isoformat()
    base_meta["n_vereadores"] = len(
        {
            v["id_sapl"]
            for d in dados_por_ano
            for v in d.get("vereadores") or []
        }
    )

    sessoes = _ordenar_sessoes([s for d in dados_por_ano for s in (d.get("sessoes") or [])])
    projetos = _mesclar_projetos_lei_raiz([d.get("projetos_lei") or [] for d in dados_por_ano])

    por_id: dict[int, dict] = {}
    ordem: list[int] = []
    for d in dados_por_ano:
        for v in d.get("vereadores") or []:
            vid = int(v["id_sapl"])
            if vid not in por_id:
                por_id[vid] = copy.deepcopy(v)
                ordem.append(vid)
            else:
                por_id[vid] = _mesclar_vereador(por_id[vid], v)


    try:
        with open(RAIZ / "dados" / "tratados" / "afastamentos_manuais.json", "r", encoding="utf-8") as f:
            manuais = json.load(f)
            motivos = manuais.get("motivos_fora_do_mandato") or []
            for m in motivos:
                vid_sapl = m.get("parlamentar_id_sapl")
                if vid_sapl in por_id:
                    if "motivos_fora_do_mandato" not in por_id[vid_sapl]:
                        por_id[vid_sapl]["motivos_fora_do_mandato"] = []
                    por_id[vid_sapl]["motivos_fora_do_mandato"].append(m)
    except Exception as e:
        pass

    vereadores = [por_id[i] for i in ordem]

    return {
        "meta": base_meta,
        "sessoes": sessoes,
        "projetos_lei": projetos,
        "vereadores": vereadores,
    }


def gerar_legislatura(cfg: dict) -> None:
    anos = anos_recorte(cfg)
    dados = []
    for ano in anos:
        path = RAIZ / "dados" / "tratados" / f"atuacao_vereadores_{ano}.json"
        dados.append(json.loads(path.read_text(encoding="utf-8")))
    consolidado = mesclar_atuacao_legislatura(dados, anos, cfg)
    out = RAIZ / "dados" / "tratados"
    dest = out / f"atuacao_vereadores_{SUFIXO_LEGISLATURA}.json"
    dest.write_bytes(
        (json.dumps(consolidado, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )

    temas = carregar_temas()
    bruto = pll_votados_no_ano(consolidado)
    sessao, mes, todo = periodos(bruto, consolidado.get("sessoes") or [], cfg, temas)
    gravar_camara(SUFIXO_LEGISLATURA, sessao, mes, todo, todo, out)
    print(
        f"Legislatura {anos}: sessao={len(sessao)} mes={len(mes)} todo={len(todo)} PLL, "
        f"{len(consolidado['vereadores'])} vereadores"
    )


def main():
    cfg = carregar_config()
    for ano in anos_recorte(cfg):
        gerar_ano(ano, cfg)
    gerar_legislatura(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
