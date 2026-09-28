#!/usr/bin/env python3
"""Monta index.html de Campo do Tenente a partir da referencia de Campo Largo."""

from __future__ import annotations

import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
MODELO = RAIZ / "tela" / "modelo.html"
PATCH_DADOS = RAIZ / "tela" / "patch_dados_camara.js"
PATCH_VEREADORES = RAIZ / "tela" / "patch_dados_vereadores.js"
SAIDA = RAIZ / "index.html"
CFG = RAIZ / "config_cidade.json"


def carregar_config():
    return json.loads(CFG.read_text(encoding="utf-8"))


def remover_bloco_votacao_html(html: str) -> str:
    inicio = html.find('<button type="button" class="btn-votar-fab"')
    fim = html.find("<script>", inicio)
    if inicio == -1 or fim == -1:
        raise RuntimeError("Bloco HTML de votacao popular nao encontrado")
    return html[:inicio] + html[fim:]


def remover_js_votacao(html: str) -> str:
    ini = html.find("  var STORAGE_VOTOU = ")
    fim = html.find("  var JSON_URL = ")
    if ini != -1 and fim != -1 and ini < fim:
        html = html[:ini] + html[fim:]
    start = html.find("  function origemDeTeste()")
    if start == -1:
        start = html.find("  function leituraVotouLocal()")
    fim_evt = html.find(
        '  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function (e) {'
    )
    if start != -1 and fim_evt != -1 and start < fim_evt:
        html = html[:start] + html[fim_evt:]
    elif start != -1:
        raise RuntimeError(f"Nao achou fim do bloco votacao (start={start}, fim={fim_evt})")
    html = html.replace("  var SAPL_ORIGEM = ", "  /* SAPL_ORIGEM */ var SAPL_ORIGEM_LEGACY = ")
    if "<script>" in html:
        antes, depois = html.split("<script>", 1)
        depois = depois.replace("campolargo", "campodotenente")
        html = antes + "<script>" + depois
    html = html.replace("  carregarResultadosRemotos();\n", "")
    html = html.replace("  initVotacaoPopular();\n", "")
    return html


def injetar_apos_strict(html: str, bloco: str) -> str:
    marcador = '(function () {\n  "use strict";\n\n'
    if marcador not in html:
        raise RuntimeError("Marcador do script nao encontrado")
    return html.replace(marcador, marcador + bloco + "\n", 1)


def substituir_csp(html: str, sapl: str) -> str:
    nova = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-src 'none'; "
        "child-src 'none'; worker-src 'none'; img-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; form-action 'none'; upgrade-insecure-requests;"
    )
    return re.sub(
        r'<meta http-equiv="Content-Security-Policy" content="[^"]+">',
        f'<meta http-equiv="Content-Security-Policy" content="{nova}">',
        html,
        count=1,
    )


def main():
    cfg = carregar_config()
    cidade = cfg["cidade"]["nome"]
    uf = cfg["cidade"]["uf"]
    sapl = cfg["sapl"]["endereco_base"].rstrip("/")
    portal = cfg["painel"]["endereco_publico"]
    repo = cfg["painel"]["repositorio"]
    anos = cfg["recorte"]["anos"]
    ano_padrao = max(anos)

    if not MODELO.is_file():
        raise RuntimeError(
            f"Modelo ausente: {MODELO}. Execute python scripts/gerar_modelo_tela.py"
        )
    html = MODELO.read_text(encoding="utf-8")
    html = substituir_csp(html, sapl)

    partes = html.split("<script>", 1)
    partes[0] = partes[0].replace("Campo Largo", cidade)
    partes[0] = partes[0].replace("campolargo", "campodotenente")
    partes[0] = partes[0].replace("https://sapl.campolargo.pr.leg.br", sapl)
    partes[0] = partes[0].replace(
        "empratoslimposcl.github.io/em-pratos-limpos/",
        portal.replace("https://", ""),
    )
    partes[0] = partes[0].replace("https://empratoslimposcl.github.io/em-pratos-limpos/", portal.rstrip("/"))
    html = partes[0] + "<script>" + partes[1]
    if "<script>" in html:
        a, b = html.split("<script>", 1)
        b = b.replace("https://sapl.campolargo.pr.leg.br", "https://sapl.campodotenente.pr.leg.br")
        b = b.replace("campolargo", "campodotenente")
        html = a + "<script>" + b

    html = html.replace('var STORAGE_TEMA = "dashboard-campo-largo-tema";', 'var STORAGE_TEMA = "dashboard-campo-tenente-tema";')

    html = remover_js_votacao(html)
    if "function origemDeTeste()" in html:
        raise RuntimeError("Bloco de votacao popular ainda presente apos remover_js_votacao")

    html = re.sub(
        r"  function htmlResultadoPopular\(id\) \{[\s\S]*?  \}\n\n  var resumoContexto",
        "  function htmlResultadoPopular(id) {\n    return \"\";\n  }\n\n  var resumoContexto",
        html,
        count=1,
    )
    html = re.sub(
        r"  function folhaVotacaoAberta\(\) \{[\s\S]*?  \}\n\n  function atualizarOverflowFolhas",
        "  function atualizarOverflowFolhas",
        html,
        count=1,
    )
    html = re.sub(
        r"    var popular = htmlResultadoPopular\(m\.id\);\n    if \(popular\) \{[\s\S]*?    \}\n",
        "",
        html,
        count=1,
    )
    html = html.replace(
        "document.body.style.overflow = (folhaShareAberta() || folhaResumoAberta() || folhaVotacaoAberta()) ? \"hidden\" : \"\";",
        'document.body.style.overflow = (folhaShareAberta() || folhaResumoAberta()) ? "hidden" : "";',
    )

    for frase in (
        "Sem nota e sem ranking",
        "Estes dados não são nota nem ranking.",
        "Os números descrevem registros oficiais e não representam nota, ranking ou avaliação. Ausência não é voto.",
        "Os números descrevem registros oficiais. Não são nota nem ranking. Ausência não é voto.",
        "#CampoLargo",
        "CampoLargo",
    ):
        html = html.replace(frase, "")

    injecao = f"""
  var CONFIG_CIDADE = null;
  var ANOS_RECORTE = {json.dumps(anos)};
  var SUFIXO_DADOS = "legislatura";
  var FOTOS_LOCAIS = {{}};
  var SAPL_ORIGEM = "";
  var PORTAL_OFICIAL = "";
  var ROTULO_SEM_VOTO_INDIVIDUAL = "voto individual nao registrado no SAPL";

  function nomeCamaraMunicipal() {{
    return "C\u00e2mara Municipal de " + nomeCidade();
  }}
  if (window.top !== window.self) {{
    document.documentElement.setAttribute("data-moldura-bloqueada", "1");
    document.body.innerHTML = '<main style="padding:24px;font-family:sans-serif;max-width:640px;margin:0 auto">'
      + '<h1>Página oficial</h1><p>Este painel não deve ser exibido dentro de outro site.</p>'
      + '<p><a id="link-portal-oficial-moldura" href="#">Abrir o endereço oficial do Em Pratos Limpos</a></p></main>';
    var lk = document.getElementById("link-portal-oficial-moldura");
    if (lk) lk.href = "{portal}";
    throw new Error("moldura");
  }}

  function iniciaisNome(nome) {{
    var partes = String(nome || "").trim().split(/\\s+/).filter(Boolean);
    if (!partes.length) return "?";
    if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
    return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
  }}

  function rotulosVotoMeta() {{
    var m = estado.dados && estado.dados.meta && estado.dados.meta.rotulos_estados;
    return m || {{}};
  }}

  function classificacaoNominal(n) {{
    if (n.classificacao) return n.classificacao;
    if (n.estado) return n.estado;
    return "outro";
  }}

  function rotuloVotoNominal(n) {{
    var cls = classificacaoNominal(n);
    var rot = rotulosVotoMeta()[cls];
    if (rot) return rot;
    if (n.rotulo) return n.rotulo;
    return ROTULOS_VOTO[cls] || n.voto || "Sem voto";
  }}

  function contagemVotoCampo(vo, chaveLegado, chaveTenente) {{
    if (vo[chaveTenente] != null) return vo[chaveTenente];
    return vo[chaveLegado] || 0;
  }}

  function nomeCidade() {{
    return CONFIG_CIDADE && CONFIG_CIDADE.cidade && CONFIG_CIDADE.cidade.nome
      ? CONFIG_CIDADE.cidade.nome : "município";
  }}

  function rotuloCidadeCamara() {{
    return "O que a Câmara de " + nomeCidade();
  }}

  function rotuloCamaraVotou() {{
    return "A Câmara Municipal de " + nomeCidade() + " votou ";
  }}

  function rotuloSaplCamara() {{
    return "SAPL da Câmara Municipal de " + nomeCidade();
  }}

  function carregarConfig() {{
    return fetch("config_cidade.json").then(function (r) {{
      if (!r.ok) throw new Error("config");
      return r.json();
    }}).then(function (cfg) {{
      CONFIG_CIDADE = cfg;
      SAPL_ORIGEM = cfg.sapl.endereco_base.replace(/\\/$/, "");
      PORTAL_OFICIAL = cfg.painel.endereco_publico.replace(/\\/$/, "");
      return fetch("dados/brutos/fotos_vereadores/indice.json").then(function (r) {{
        if (!r.ok) return {{}};
        return r.json();
      }}).then(function (idx) {{
        FOTOS_LOCAIS = idx || {{}};
      }}).catch(function () {{ FOTOS_LOCAIS = {{}}; }});
    }});
  }}

  function rotuloAnosRecorte() {{
    if (!ANOS_RECORTE || !ANOS_RECORTE.length) return "da legislatura";
    if (ANOS_RECORTE.length === 1) return "de " + ANOS_RECORTE[0];
    return "de " + ANOS_RECORTE[0] + " e " + ANOS_RECORTE[ANOS_RECORTE.length - 1];
  }}

  function rotuloPeriodoLegislatura() {{
    return "sess\\u00f5es ordin\\u00e1rias " + rotuloAnosRecorte();
  }}

  function prefixoDadosTratados() {{
    return window.location.pathname.indexOf("/docs/") !== -1
      ? "../../dados/tratados/"
      : "dados/tratados/";
  }}
"""
    html = injetar_apos_strict(html, injecao)

    patch_dados = PATCH_DADOS.read_text(encoding="utf-8")
    marcador_ui = "  var estadoUI = {\n    secao: \"camara\"\n  };\n"
    if marcador_ui not in html:
        raise RuntimeError("Marcador estadoUI nao encontrado para patch de dados")
    estado_materias_decl = """
  var estadoMaterias = {
    periodo: "sessao",
    filtro: "",
    busca: "",
    listaVisivel: { sessao: true, mes: true, todo: true }
  };
"""
    html = html.replace(marcador_ui, marcador_ui + patch_dados + estado_materias_decl + "\n", 1)

    patch_vereadores = PATCH_VEREADORES.read_text(encoding="utf-8")
    ini_pres = html.find("  function renderSecaoPresenca(v) {")
    ini_pll = html.find("  function renderSecaoPLL(v) {")
    ini_app = html.find("  function renderApp() {")
    if ini_pres == -1 or ini_pll == -1 or ini_app == -1 or not (ini_pres < ini_pll < ini_app):
        raise RuntimeError("Marcadores da aba Vereadores nao encontrados no modelo")
    bloco_pll = html[ini_pll:ini_app]
    html = html[:ini_pres] + patch_vereadores + "\n" + bloco_pll + html[ini_app:]

    html = html.replace(
        "htmlFaltas = '<p class=\"vazio\" style=\"margin-top:10px\">Nenhuma falta registrada nas 26 sessões ordinárias de 2026.</p>';",
        "htmlFaltas = '<p class=\"vazio\" style=\"margin-top:10px\">Nenhuma falta registrada nas ' + esc(p.sessoes_ordinarias) + ' sessões ordinárias de ' + ANO_ATUAL + '.</p>';",
    )
    html = html.replace(
        "' + ' sessões ordinárias de ' + ANO_ATUAL + '. Taxa de presença: <strong>' +",
        "' sessões ordinárias de ' + ANO_ATUAL + '. Taxa de presença: <strong>' +",
    )
    html = re.sub(
        r"' sessões ordinárias de 2026\. Taxa de presença: <strong>' \+",
        "' sessões ordinárias de ' + ANO_ATUAL + '. Taxa de presença: <strong>' +",
        html,
        count=1,
    )
    html = html.replace(
        'esc(vo.total_registros) + " votações em sessões ordinárias de 2026.</p>" +',
        'esc(vo.total_registros) + " votações em sessões ordinárias de " + ANO_ATUAL + ".</p>" +',
    )
    html = html.replace(
        "renderSecaoVotos(v) +\n"
        '      \'<footer class="rodape-coleta" aria-label="Informações sobre a coleta de dados"></footer>";\n',
        "renderSecaoVotos(v) +\n"
        '      \'<footer class="rodape-coleta" aria-label="Informações sobre a coleta de dados">\' +\n'
        '      "<p>Dado coletado em <strong>" + esc(formatarDataHora(meta.dado_coletado_em)) +\n'
        '      "</strong>. Fonte: SAPL (Sistema de Apoio ao Processo Legislativo) da Câmara.</p></footer>";\n',
    )
    html = re.sub(
        r"  function rotuloPeriodoShare\(periodo\) \{[\s\S]*?return \"sessões ordinárias de 2026\";\n  \}",
        """  function rotuloPeriodoShare(periodo) {
    if (periodo === "sessao") return "última sessão ordinária (" + dataUltimaSessaoFmt() + ")";
    if (periodo === "mes") return nomeMesAnteriorUltimaSessao().toLowerCase();
    return "sessões ordinárias de " + ANO_ATUAL;
  }""",
        html,
        count=1,
    )
    html = html.replace(
        'return "sessões ordinárias de 2026";',
        'return "sessões ordinárias de " + ANO_ATUAL;',
    )
    html = html.replace(
        'return "sessões ordinárias de 2026 até " + data;',
        'return "sessões ordinárias de " + ANO_ATUAL + " até " + data;',
    )
    html = re.sub(
        r'var DATA_ULTIMA_SESSAO = "[^"]*";',
        'var DATA_ULTIMA_SESSAO = "";',
        html,
        count=1,
    )
    html = re.sub(
        r'  var SAPL_ORIGEM = "https://sapl\.campolargo\.pr\.leg\.br";',
        "  /* SAPL_ORIGEM: carregarConfig */",
        html,
        count=1,
    )
    html = re.sub(
        r'  var PORTAL_OFICIAL = "https://empratoslimposcl\.github\.io/em-pratos-limpos/";',
        "  /* PORTAL_OFICIAL: carregarConfig */",
        html,
        count=1,
    )
    html = re.sub(
        r"var ultimaData = datasSessao\[datasSessao\.length - 1\] \|\| null;",
        "var ultimaData = datasSessao[datasSessao.length - 1] || null;\n"
        '    var tituloMes = document.querySelector("#painel-periodo-mes .sessao-titulo");\n'
        '    var metaElMes = document.querySelector("#painel-periodo-mes .sessao-meta");\n'
        "    if (!ultimaData) {\n"
        "      if (tituloMes) tituloMes.textContent = \"\";\n"
        "      if (metaElMes) metaElMes.textContent = \"\";\n"
        "      return;\n"
        "    }",
        html,
        count=1,
    )
    html = html.replace(
        "        estado.dados = dados;\n        prepararIndices(dados);",
        "        estado.dados = dados;\n        aplicarRotulosMeta(dados);\n        prepararIndices(dados);",
    )
    html = html.replace(
        '      "</div></div></section>" +\n      renderSecaoPresenca(v) +',
        '      "</div></div></section>" +\n      renderNotasParlamentar(v) +\n      renderSecaoPresenca(v) +',
    )
    html = html.replace(
        "        atualizarInterfaceCamara();\n        renderApp();",
        "        try { atualizarInterfaceCamara(); } catch (errCamara) { console.error(errCamara); }\n        renderApp();",
    )
    html = html.replace(
        "    (dados.projetos_lei_legislativo || []).forEach(function (p) {",
        "    (dados.projetos_lei || []).forEach(function (p) {\n"
        "      if (!p || p.id == null) return;\n"
        "      estado.indiceEmentas[p.id] = p.ementa;\n"
        "      estado.indiceMaterias[p.id] = p;\n"
        "    });\n"
        "    (dados.projetos_lei_legislativo || []).forEach(function (p) {",
    )
    html = html.replace(
        "    var filtroTexto = document.getElementById(\"filtro-texto\");\n"
        "    filtroTexto.addEventListener(\"input\", function (e) {",
        "    var filtroTexto = document.getElementById(\"filtro-texto\");\n"
        "    if (filtroTexto) filtroTexto.addEventListener(\"input\", function (e) {",
    )
    html = html.replace(
        '    document.getElementById("filtro-voto").addEventListener("change", function (e) {',
        '    var filtroVoto = document.getElementById("filtro-voto");\n'
        '    if (filtroVoto) filtroVoto.addEventListener("change", function (e) {',
    )
    substituicoes_share = [
        (
            '"Dados oficiais da Câmara Municipal de Campo Largo reunidos',
            '"Dados oficiais da " + nomeCamaraMunicipal() + " reunidos',
        ),
        ('"O que a Câmara de Campo Largo votou"', '"O que a Câmara de " + nomeCidade() + " votou"'),
        (
            '"Fonte oficial: SAPL da Câmara Municipal de Campo Largo."',
            '"Fonte oficial: " + rotuloSaplCamara() + "."',
        ),
        (
            '"Fonte oficial: SAPL da Câmara Municipal de Campo Largo."',
            '"Fonte oficial: " + rotuloSaplCamara() + "."',
        ),
        ('"Fonte: SAPL da Câmara de Campo Largo"', '"Fonte: SAPL da Câmara de " + nomeCidade()'),
        (
            'var votou = "A Câmara Municipal de Campo Largo votou " + m.tipo',
            "var votou = rotuloCamaraVotou() + m.tipo",
        ),
    ]
    for antigo, novo in substituicoes_share:
        html = html.replace(antigo, novo)

    pos_painel = html.find("  function atualizarPainelMes() {")
    pos_vot = html.find("  function atualizarVotacoesMes() {", pos_painel)
    pos_estado_m = html.find("  var estadoMaterias = {", pos_vot)
    if pos_vot != -1 and pos_estado_m != -1 and pos_vot < pos_estado_m:
        html = html[:pos_vot] + html[pos_estado_m:]
    html = html.replace(
        "        renderApp();\n"
        "        atualizarCardVotacoes();\n"
        "        atualizarPainelMes();\n"
        "        atualizarVotacoesMes();",
        "        atualizarInterfaceCamara();\n        renderApp();",
    )

    html = html.replace(
        '  var JSON_URL = window.location.pathname.indexOf("/docs/") !== -1\n'
        '    ? "../../dados/tratados/atuacao_vereadores_2026.json"\n'
        '    : "dados/tratados/atuacao_vereadores_2026.json";',
        '  var JSON_URL = prefixoDadosTratados() + "atuacao_vereadores_" + SUFIXO_DADOS + ".json";',
    )

    html = re.sub(
        r"  function urlSegura\(url\) \{[\s\S]*?    return \"\";\n  \}",
        f"""  function urlSegura(url) {{
    if (url == null) return "";
    var s = String(url).trim();
    var base = SAPL_ORIGEM || (CONFIG_CIDADE && CONFIG_CIDADE.sapl ? CONFIG_CIDADE.sapl.endereco_base.replace(/\\/$/, "") : "");
    var http = base.replace("https://", "http://");
    if (s === http || s.indexOf(http + "/") === 0) {{
      return base + s.slice(http.length);
    }}
    if (s === base || s.indexOf(base + "/") === 0) return s;
    if (s.charAt(0) === "/" && s.charAt(1) !== "/") return base + s;
    return "";
  }}""",
        html,
        count=1,
    )

    html = re.sub(
        r"  function renderPerfilFoto\(v\) \{[\s\S]*?  \}\n\n  function renderBadgePartido",
        """  function renderPerfilFoto(v) {
    var local = FOTOS_LOCAIS[String(v.id_sapl)];
    if (local) {
      return '<div class="perfil-foto-wrap">' +
        '<img class="perfil-foto" src="' + esc(local) + '" alt="Foto oficial de ' + esc(v.nome_parlamentar) +
        '" width="72" height="72" loading="lazy">' +
        "</div>";
    }
    return '<div class="perfil-foto-wrap perfil-iniciais" aria-hidden="true"><span class="iniciais-foto">' +
      esc(iniciaisNome(v.nome_parlamentar)) + "</span></div>";
  }

  function renderBadgePartido""",
        html,
        count=1,
    )

    html = html.replace(
        "  function rotuloVoto(n) {\n    if (n.classificacao && ROTULOS_VOTO[n.classificacao]) {\n"
        "      return ROTULOS_VOTO[n.classificacao];\n    }\n    return n.voto || \"Sem voto\";\n  }",
        "  function rotuloVoto(n) {\n    return rotuloVotoNominal(n);\n  }",
    )

    html = html.replace(
        '          var gabardo = dados.vereadores.find(function (v) {\n'
        '            return v.slug_codigo === "andre-gabardo";\n'
        "          });\n"
        "          estado.vereadorId = gabardo ? gabardo.id_sapl : dados.vereadores[0].id_sapl;",
        "          estado.vereadorId = dados.vereadores[0].id_sapl;",
    )

    html = html.replace(
        '<label for="sel-vereador">Escolha o vereador (15 da 41ª Legislatura)</label>',
        '<label for="sel-vereador">Escolha o vereador</label>',
    )

    html = html.replace(
        "      MATERIAS_URL + \"materias_camara.json\",\n"
        "      MATERIAS_URL + \"materias_tags.json\",\n"
        '      MATERIAS_URL + "filtros_materia.json"',
        '      MATERIAS_URL + "materias_camara_" + SUFIXO_DADOS + ".json",\n'
        '      MATERIAS_URL + "materias_tags_" + SUFIXO_DADOS + ".json",\n'
        '      MATERIAS_URL + "filtros_materia_" + SUFIXO_DADOS + ".json"',
    )

    html = re.sub(
        r"  aplicarTema\(temaInicial\(\)\);\n  initShareSheet\(\);\n  initResumoSheet\(\);\n  carregarMateriasCamara\(\)\.then\(initMateriasCamara\);\n  initNavegacao\(\);\n  carregar\(\);",
        "  carregarConfig().then(function () {\n    aplicarTema(temaInicial());\n    initShareSheet();\n    initResumoSheet();\n    initNavegacao();\n    return carregarMateriasCamara().then(initMateriasCamara);\n  }).then(carregar);",
        html,
        count=1,
    )

    html = html.replace(
        ".perfil-foto {",
        ".perfil-iniciais { width: 72px; height: 72px; border-radius: 50%; background: var(--marca-fundo); "
        "display: flex; align-items: center; justify-content: center; font-weight: 700; color: var(--marca); }\n"
        "  .iniciais-foto { font-size: 22px; }\n\n  .perfil-foto {",
        1,
    )
    if "function origemDeTeste()" in html:
        raise RuntimeError("Bloco de votacao reintroduzido antes de gravar index.html")
    if "<script>" in html:
        cab, cod = html.split("<script>", 1)
        cod = re.sub(r"https://sapl\.[a-z0-9.-]+\.pr\.leg\.br", "", cod)
        html = cab + "<script>" + cod
    SAIDA.write_text(html, encoding="utf-8")
    print(f"Gerado {SAIDA} ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
