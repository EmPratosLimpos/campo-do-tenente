/*
 * Em Pratos Limpos: tela do painel.
 *
 * Nada de cidade, endereco, ano, numero de vereadores ou lista de assuntos
 * fica fixo aqui. Tudo vem de config_cidade.json e dos arquivos de
 * dados/tratados. A tela monta o DOM com createElement e textContent; nenhum
 * texto externo vira HTML. Todo texto externo passa por esc().
 */
(function () {
  "use strict";

  var CAMINHO_CONFIG = "config_cidade.json";
  var PASTA_DADOS = "dados/tratados/";
  var CHAVE_TEMA = "epl-tema";
  var POR_PAGINA = 20;
  var NS_SVG = "http://www.w3.org/2000/svg";

  var estado = {
    cfg: null,
    anos: [],
    ano: null,
    aba: "camara",
    dados: {},
    temas: {},
    autoria: {},
    afastamentos: null,
    vereadorSlug: null,
    filtroVotacoes: { tema: "", registro: "", busca: "", limite: POR_PAGINA },
    filtroVotos: { estado: "", limite: POR_PAGINA },
    filtroProjetos: { tipo: "", tema: "", limite: POR_PAGINA }
  };

  /* ---------- Texto seguro ---------- */

  // Remove sequencias ANSI e caracteres de controle. O resultado so e usado
  // como texto (textContent ou atributo), nunca como HTML.
  function esc(texto) {
    if (texto === null || texto === undefined) return "";
    return String(texto)
      .replace(/\u001B\][^\u0007\u001B]*(\u0007|\u001B\\)/g, "")
      .replace(/[\u001B\u009B][[\]()#;?]*(?:\d{1,4}(?:;\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]/g, "")
      .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F-\u009F]/g, "");
  }

  // Os arquivos de dados ainda trazem alguns rotulos sem acento. A correcao e
  // so de exibicao e so troca palavras inteiras conhecidas.
  var ACENTOS = {
    nao: "não", sessao: "sessão", sessoes: "sessões", licenca: "licença",
    saude: "saúde", abstencao: "abstenção", apos: "após", cassacao: "cassação",
    votacao: "votação", votacoes: "votações", materia: "matéria", materias: "matérias",
    noticia: "notícia", camara: "câmara", tramitacao: "tramitação", unanime: "unânime",
    ordinaria: "ordinária", ordinarias: "ordinárias", numeros: "números", ja: "já",
    ate: "até", referencia: "referência", ausencia: "ausência", presidencia: "presidência",
    aprovacao: "aprovação", rejeicao: "rejeição", sancao: "sanção", decisao: "decisão",
    situacao: "situação", periodo: "período", legislacao: "legislação", informacao: "informação"
  };

  function acentuar(texto) {
    var s = esc(texto);
    s = s.replace(/[A-Za-zÀ-ÿ]+/g, function (palavra) {
      var certo = ACENTOS[palavra.toLowerCase()];
      if (!certo) return palavra;
      if (palavra === palavra.toUpperCase() && palavra.length > 1) return certo.toUpperCase();
      if (palavra.charAt(0) === palavra.charAt(0).toUpperCase()) {
        return certo.charAt(0).toUpperCase() + certo.slice(1);
      }
      return certo;
    });
    s = s.replace(/\bde marco de\b/g, "de março de");
    s = s.replace(/\b[Nn] (\d)/g, "nº $1");
    s = s.replace(/\b(\d{4})-(\d{2})-(\d{2})\b/g, "$3/$2/$1");
    return s;
  }

  function maiusculaInicial(texto) {
    var s = acentuar(texto);
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  /* ---------- Enderecos ---------- */

  function origemDe(url) {
    var m = /^https:\/\/([a-z0-9.-]+)(?::\d+)?(?:\/|$)/i.exec(String(url || "").trim());
    return m ? "https://" + m[1].toLowerCase() : "";
  }

  function origemSapl() {
    return origemDe(estado.cfg && estado.cfg.sapl && estado.cfg.sapl.endereco_base);
  }

  // So aceita https do SAPL da cidade do config. http do mesmo SAPL vira https;
  // caminho relativo vira endereco do SAPL. Qualquer outra coisa vira "".
  function urlSegura(url) {
    var base = origemSapl();
    if (!base || url === null || url === undefined) return "";
    var s = esc(url).trim();
    var host = base.slice("https://".length);
    var semEsquema = s.replace(/^https?:\/\//i, "");
    if (/^https?:\/\//i.test(s)) {
      var hostUrl = semEsquema.split(/[/?#]/)[0].toLowerCase();
      if (hostUrl !== host) return "";
      return base + semEsquema.slice(hostUrl.length);
    }
    if (s.charAt(0) === "/" && s.charAt(1) !== "/") return base + s;
    return "";
  }

  // Fonte oficial fora do SAPL (site da Camara), usada so para afastamentos
  // que o SAPL nao registra. Aceita apenas a origem declarada no config.
  function urlFonteOficial(url) {
    var sapl = urlSegura(url);
    if (sapl) return sapl;
    var site = origemDe(estado.cfg && estado.cfg.painel && estado.cfg.painel.site_camara);
    var s = esc(url).trim();
    if (site && origemDe(s) === site && !/[\s"'<>]/.test(s)) return s;
    return "";
  }

  // Enderecos que vem do proprio config (repositorio, painel publico).
  function urlDoConfig(url) {
    var s = esc(url).trim();
    return /^https:\/\/[a-z0-9.-]+\//i.test(s) && !/[\s"'<>]/.test(s) ? s : "";
  }

  /* ---------- DOM ---------- */

  function el(tag, props, filhos) {
    var n = document.createElement(tag);
    if (props) {
      Object.keys(props).forEach(function (k) {
        var v = props[k];
        if (v === null || v === undefined || v === false) return;
        if (k === "classe") n.className = v;
        else if (k === "texto") n.textContent = esc(v);
        else if (k === "ao") Object.keys(v).forEach(function (ev) { n.addEventListener(ev, v[ev]); });
        else n.setAttribute(k, v === true ? "" : esc(v));
      });
    }
    anexar(n, filhos);
    return n;
  }

  function anexar(n, filhos) {
    if (filhos === null || filhos === undefined) return;
    if (!Array.isArray(filhos)) filhos = [filhos];
    filhos.forEach(function (f) {
      if (f === null || f === undefined || f === false) return;
      if (typeof f === "string" || typeof f === "number") n.appendChild(document.createTextNode(esc(f)));
      else n.appendChild(f);
    });
  }

  function svg(caminhos, classe) {
    var s = document.createElementNS(NS_SVG, "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("aria-hidden", "true");
    s.setAttribute("focusable", "false");
    if (classe) s.setAttribute("class", classe);
    caminhos.forEach(function (d) {
      var p = document.createElementNS(NS_SVG, "path");
      p.setAttribute("d", d);
      s.appendChild(p);
    });
    return s;
  }

  function iconeExterno() {
    return svg(["M14 4h6v6", "M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"], "icone-externo");
  }

  // Link externo. Sem endereco seguro, vira texto simples.
  function linkFonte(href, texto, validador, classe) {
    var seguro = (validador || urlSegura)(href);
    if (!seguro) return el("span", { classe: classe || null }, [texto]);
    return el("a", { href: seguro, target: "_blank", rel: "noopener noreferrer", classe: classe || null }, [
      texto, el("span", { classe: "so-leitor", texto: " (abre em nova aba)" }), iconeExterno()
    ]);
  }

  function numeroComFonte(valor, href, rotuloFonte) {
    var seguro = urlSegura(href);
    var n = el("span", { classe: "num", texto: String(valor) });
    if (!seguro) return n;
    return el("a", { href: seguro, target: "_blank", rel: "noopener noreferrer", classe: "num-link" }, [
      n, el("span", { classe: "so-leitor", texto: ", " + rotuloFonte + " (abre em nova aba)" })
    ]);
  }

  function limpar(n) {
    while (n.firstChild) n.removeChild(n.firstChild);
  }

  /* ---------- Datas ---------- */

  var MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro"];

  function data(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(esc(iso));
    return m ? m[3] + "/" + m[2] + "/" + m[1] : "";
  }

  function dataPorExtenso(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/.exec(esc(iso));
    if (!m) return "";
    var s = Number(m[3]) + " de " + MESES[Number(m[2]) - 1] + " de " + m[1];
    if (m[4]) s += ", às " + m[4] + "h" + m[5];
    return s;
  }

  /* ---------- Vocabulario de estados ---------- */

  // Explicacao curta de cada estado. Os rotulos exibidos vem dos dados.
  var EXPLICACOES = {
    sim: "O SAPL registrou o voto Sim deste vereador nesta votação.",
    nao: "O SAPL registrou o voto Não deste vereador nesta votação.",
    abstencao: "O SAPL registrou abstenção: o vereador participou da votação sem votar sim nem não.",
    nao_votou: "O SAPL registrou \"Não votou\" para este vereador. Não é falta e não é voto sim, não ou abstenção.",
    presidente_que_nao_votou: "Quem presidia a sessão, segundo a mesa registrada no SAPL, aparece como \"Não votou\". O painel não presume isso só pelo cargo.",
    ausente_com_justificativa: "Não estava presente e a Câmara registrou justificativa para a falta. Ausência não é voto.",
    ausente_sem_justificativa: "Não estava presente e o SAPL não traz justificativa registrada para a falta. Ausência não é voto.",
    fora_do_mandato: "Nesta data a pessoa não exercia o mandato, pelas datas de início e fim registradas. Não conta como falta nem como voto.",
    presente_sem_voto_individual_registrado: "Estava presente na sessão, mas o SAPL não tem o voto individual dele nesta votação. O painel não completa o voto.",
    licenca_tratamento_saude: "Afastamento por licença para tratamento de saúde, com fonte oficial da Câmara. Não conta como falta.",
    sem_voto_individual: "A Câmara registrou só o total oficial desta votação, sem o voto de cada vereador. Isso não quer dizer votação unânime.",
    presente: "O SAPL registrou a presença do vereador nesta sessão.",
    falta_com_justificativa: "Não estava presente e a Câmara registrou justificativa para a falta.",
    falta_sem_justificativa: "Não estava presente e o SAPL não traz justificativa registrada para esta sessão."
  };

  var ESTADOS_VOTO = ["sim", "nao", "abstencao", "nao_votou", "presidente_que_nao_votou",
    "ausente_com_justificativa", "ausente_sem_justificativa", "licenca_tratamento_saude",
    "fora_do_mandato", "presente_sem_voto_individual_registrado"];

  var ESTADOS_PRESENCA = ["presente", "falta_com_justificativa", "falta_sem_justificativa",
    "licenca_tratamento_saude", "fora_do_mandato"];

  function classeEstado(chave) {
    return "estado estado-" + String(chave).replace(/[^a-z_]/g, "").replace(/_/g, "-");
  }

  function chipEstado(chave, rotulo) {
    var ch = esc(chave);
    return el("button", {
      type: "button",
      classe: classeEstado(ch),
      "data-dica": EXPLICACOES[ch] ? ch : null,
      "aria-expanded": EXPLICACOES[ch] ? "false" : null
    }, [maiusculaInicial(rotulo || ch)]);
  }

  function rotuloEstadoVoto(dados, chave) {
    var r = dados && dados.meta && dados.meta.rotulos_estados;
    return (r && r[chave]) || chave;
  }

  /* ---------- Dica ao tocar ou passar o mouse ---------- */

  var dica = { alvo: null, fixa: false };

  function mostrarDica(alvo, fixa) {
    var caixa = document.getElementById("dica");
    var chave = alvo.getAttribute("data-dica");
    if (!caixa || !EXPLICACOES[chave]) return;
    if (dica.alvo && dica.alvo !== alvo) esconderDica();
    caixa.textContent = EXPLICACOES[chave];
    caixa.hidden = false;
    alvo.setAttribute("aria-describedby", "dica");
    alvo.setAttribute("aria-expanded", "true");
    dica.alvo = alvo;
    dica.fixa = !!fixa;
    var r = alvo.getBoundingClientRect();
    var largura = Math.min(320, document.documentElement.clientWidth - 32);
    caixa.style.maxWidth = largura + "px";
    var esquerda = Math.max(16, Math.min(r.left + window.scrollX, window.scrollX + document.documentElement.clientWidth - largura - 16));
    caixa.style.left = esquerda + "px";
    caixa.style.top = (r.bottom + window.scrollY + 8) + "px";
  }

  function esconderDica() {
    var caixa = document.getElementById("dica");
    if (caixa) caixa.hidden = true;
    if (dica.alvo) {
      dica.alvo.removeAttribute("aria-describedby");
      dica.alvo.setAttribute("aria-expanded", "false");
    }
    dica.alvo = null;
    dica.fixa = false;
  }

  function iniciarDicas() {
    document.addEventListener("click", function (e) {
      var alvo = e.target.closest ? e.target.closest("[data-dica]") : null;
      if (alvo) {
        if (dica.alvo === alvo && dica.fixa) esconderDica();
        else mostrarDica(alvo, true);
        return;
      }
      if (!e.target.closest || !e.target.closest("#dica")) esconderDica();
    });
    document.addEventListener("mouseover", function (e) {
      var alvo = e.target.closest ? e.target.closest("[data-dica]") : null;
      if (alvo && !dica.fixa) mostrarDica(alvo, false);
    });
    document.addEventListener("mouseout", function (e) {
      var alvo = e.target.closest ? e.target.closest("[data-dica]") : null;
      if (alvo && alvo === dica.alvo && !dica.fixa) esconderDica();
    });
    document.addEventListener("focusin", function (e) {
      var alvo = e.target.closest ? e.target.closest("[data-dica]") : null;
      if (alvo) mostrarDica(alvo, false);
      else if (dica.alvo) esconderDica();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && dica.alvo) {
        var alvo = dica.alvo;
        esconderDica();
        alvo.focus();
      }
    });
    window.addEventListener("resize", esconderDica);
  }

  /* ---------- Tema claro e escuro ---------- */

  function temaInicial() {
    try {
      var salvo = window.localStorage.getItem(CHAVE_TEMA);
      if (salvo === "claro" || salvo === "escuro") return salvo;
    } catch (e) { /* armazenamento indisponivel */ }
    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "escuro" : "claro";
  }

  function aplicarTema(tema, salvar) {
    document.documentElement.setAttribute("data-tema", tema);
    var botao = document.getElementById("botao-tema");
    var texto = document.getElementById("botao-tema-texto");
    if (botao) botao.setAttribute("aria-pressed", tema === "escuro" ? "true" : "false");
    if (texto) texto.textContent = "Tema escuro";
    if (salvar) {
      try { window.localStorage.setItem(CHAVE_TEMA, tema); } catch (e) { /* sem armazenamento */ }
    }
  }

  /* ---------- Carga dos arquivos ---------- */

  function lerJson(caminho) {
    return fetch(caminho, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error("Arquivo " + caminho + " respondeu " + r.status);
      return r.json();
    });
  }

  function carregarAno(ano) {
    if (estado.dados[ano]) return Promise.resolve(estado.dados[ano]);
    return lerJson(PASTA_DADOS + "atuacao_vereadores_" + ano + ".json").then(function (d) {
      estado.dados[ano] = d;
      return d;
    });
  }

  function indexarApoio(temas, autoria, afastamentos) {
    (temas && temas.materias || []).forEach(function (m) { estado.temas[m.id] = m; });
    (autoria && autoria.materias || []).forEach(function (m) { estado.autoria[m.materia_id] = m; });
    estado.afastamentos = afastamentos || null;
  }

  /* ---------- Consultas aos dados ---------- */

  function dadosAno() {
    return estado.dados[estado.ano];
  }

  function nomeMateria(id) {
    var a = estado.autoria[id];
    if (a && a.rotulo_sapl) return acentuar(a.rotulo_sapl);
    var t = estado.temas[id];
    if (t) return esc(t.sigla) + " nº " + esc(t.numero) + " de " + esc(t.ano);
    return "Matéria " + esc(id);
  }

  function temaDe(id) {
    var t = estado.temas[id];
    return t && t.tema ? maiusculaInicial(t.tema) : "";
  }

  function ehTemaEspecial(nome) {
    var n = String(nome).toLowerCase();
    return n === "não se aplica" || n.indexOf("sem ementa") === 0;
  }

  function textoAutoria(autoria) {
    var autores = autoria && autoria.autores || [];
    if (!autores.length) return autoria && autoria.rotulo ? acentuar(autoria.rotulo) : "Autoria não registrada no SAPL";
    return autores.map(function (a) {
      var nome = a.nome_parlamentar || a.nome_no_sapl || "Autor sem nome no SAPL";
      return a.cargo_no_sapl ? esc(nome) + " (" + esc(a.cargo_no_sapl) + ")" : esc(nome);
    }).join(", ");
  }

  function vereadorPorId(d, id) {
    return (d.vereadores || []).filter(function (v) { return v.id_sapl === id; })[0] || null;
  }

  function rotuloSessaoCurto(numero, iso) {
    return esc(numero) + "ª sessão ordinária, " + data(iso);
  }

  function linkBuscaSessoes(ano) {
    var tipo = estado.cfg.sapl.id_tipo_sessao_ordinaria;
    return origemSapl() + "/sessao/pesquisar-sessao?data_inicio__year=" + encodeURIComponent(ano) +
      (tipo ? "&tipo=" + encodeURIComponent(tipo) : "");
  }

  function linkBuscaMaterias(ano) {
    return origemSapl() + "/materia/pesquisar-materia?ano=" + encodeURIComponent(ano);
  }

  function contarPorTema(ids) {
    var cont = {};
    ids.forEach(function (id) {
      var t = temaDe(id) || "Sem assunto classificado";
      cont[t] = (cont[t] || 0) + 1;
    });
    return Object.keys(cont).map(function (k) { return { tema: k, n: cont[k] }; }).sort(function (a, b) {
      var ea = ehTemaEspecial(a.tema), eb = ehTemaEspecial(b.tema);
      if (ea !== eb) return ea ? 1 : -1;
      return b.n - a.n || a.tema.localeCompare(b.tema, "pt-BR");
    });
  }

  function temasDisponiveis(ids) {
    return contarPorTema(ids).map(function (x) { return x.tema; });
  }

  /* ---------- Cabecalho, ano e aviso ---------- */

  function montarCabecalhoFixo() {
    var cfg = estado.cfg;
    var cidade = esc(cfg.cidade.nome) + " (" + esc(cfg.cidade.uf) + ")";
    document.getElementById("nome-projeto").textContent = esc(cfg.painel && cfg.painel.nome_projeto || "Em Pratos Limpos");
    document.getElementById("nome-cidade").textContent = "Câmara Municipal de " + cidade;
    document.getElementById("subtitulo").textContent =
      "O que a Câmara votou, quem estava presente em cada sessão e como cada vereador votou, segundo o registro oficial.";

    var opcoes = document.getElementById("seletor-ano-opcoes");
    limpar(opcoes);
    estado.anos.forEach(function (ano) {
      var id = "ano-" + ano;
      var input = el("input", { type: "radio", name: "ano", id: id, value: String(ano) });
      input.checked = ano === estado.ano;
      input.addEventListener("change", function () { if (input.checked) trocarAno(ano); });
      opcoes.appendChild(el("span", { classe: "opcao-ano" }, [input, el("label", { "for": id, texto: String(ano) })]));
    });
    document.getElementById("seletor-ano").disabled = false;
  }

  function atualizarColeta() {
    var d = dadosAno();
    var alvo = document.getElementById("coleta");
    limpar(alvo);
    var quando = d && d.meta && d.meta.dado_coletado_em;
    anexar(alvo, [
      svg(["M12 7v5l3 2", "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z"], "icone-coleta"),
      el("span", null, [
        "Dados coletados em ",
        el("strong", { texto: quando ? dataPorExtenso(quando) : "data não informada no arquivo" }),
        " no ",
        linkFonte(origemSapl() + "/", "SAPL da Câmara"),
        ". O que foi registrado depois disso ainda não aparece aqui."
      ])
    ]);
  }

  function atualizarAvisoAno() {
    var d = dadosAno();
    var caixa = document.getElementById("aviso-ano");
    limpar(caixa);
    var lac = d && d.meta && d.meta.lacuna_sessoes_ordinarias;
    if (!lac || !lac.aviso) { caixa.hidden = true; return; }
    var primeira = lac.primeira_ordinaria_no_sapl;
    anexar(caixa, [
      svg(["M12 9v4", "M12 17h.01", "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"], "icone-aviso"),
      el("div", null, [
        el("p", { classe: "aviso-titulo" }, [acentuar(lac.aviso)]),
        primeira ? el("p", null, [
          "Por isso " + esc(estado.ano) + " começa na ",
          linkFonte(origemSapl() + "/sessao/" + esc(primeira.id), esc(primeira.numero) + "ª sessão ordinária, de " + data(primeira.data_inicio)),
          ". Os totais do ano contam só as sessões que estão no sistema oficial da Câmara."
        ]) : null
      ])
    ]);
    caixa.hidden = false;
  }

  /* ---------- Painel Camara ---------- */

  function linhaResumo(rotulo, valor, href, rotuloFonte, detalhe) {
    return el("div", { classe: "livro-linha" }, [
      el("dt", null, [rotulo, detalhe ? el("span", { classe: "livro-detalhe", texto: detalhe }) : null]),
      el("dd", null, [numeroComFonte(valor, href, rotuloFonte)])
    ]);
  }

  function renderCamara() {
    var d = dadosAno();
    var m = d.meta;
    var painel = document.getElementById("painel-camara");
    limpar(painel);
    var ano = estado.ano;
    var fonteSessoes = linkBuscaSessoes(ano);

    var resumo = el("section", { classe: "bloco bloco-resumo", "aria-labelledby": "tit-resumo" }, [
      el("h2", { id: "tit-resumo", texto: "O ano de " + ano + " em números" }),
      el("p", { classe: "bloco-intro", texto: "Cada número abre a consulta correspondente no SAPL, para conferir na fonte." }),
      el("dl", { classe: "livro" }, [
        linhaResumo("Sessões ordinárias no SAPL", m.n_sessoes_ordinarias, fonteSessoes, "sessões no SAPL"),
        linhaResumo("Votações registradas nessas sessões", m.n_votacoes, fonteSessoes, "sessões no SAPL"),
        linhaResumo("com o voto de cada vereador", m.n_votacoes_com_voto_individual, fonteSessoes, "sessões no SAPL", "votação nominal registrada"),
        linhaResumo("só com o total oficial", m.n_votacoes_sem_voto_individual, fonteSessoes, "sessões no SAPL", "voto individual não registrado no SAPL"),
        linhaResumo("Projetos de lei apresentados", m.n_projetos_lei_legislativo_e_executivo, linkBuscaMaterias(ano), "matérias no SAPL",
          esc(m.n_projetos_lei_legislativo) + " do Legislativo e " + esc(m.n_projetos_lei_executivo) + " do Executivo"),
        linhaResumo("Presenças registradas", m.n_presencas, fonteSessoes, "sessões no SAPL", "somando todos os vereadores"),
        linhaResumo("Faltas com justificativa", m.n_faltas_com_justificativa, fonteSessoes, "sessões no SAPL"),
        linhaResumo("Faltas sem justificativa", m.n_faltas_sem_justificativa, fonteSessoes, "sessões no SAPL"),
        m.n_sessoes_licenca ? linhaResumo("Sessões em licença para tratamento de saúde", m.n_sessoes_licenca, fonteSessoes, "sessões no SAPL", "não contam como falta") : null
      ])
    ]);

    var idsVotados = unicos((d.votacoes || []).map(function (v) { return v.materia_id; }));
    var temas = el("section", { classe: "bloco bloco-temas", "aria-labelledby": "tit-temas" }, [
      el("h2", { id: "tit-temas", texto: "Assuntos das matérias votadas" }),
      el("p", { classe: "bloco-intro", texto: "Assunto principal de cada matéria votada em " + ano + ", lido da ementa oficial. Toque em um assunto para ver as votações dele." }),
      barrasTemas(idsVotados)
    ]);

    var topo = el("div", { classe: "grade-camara" }, [resumo, temas]);
    painel.appendChild(el("h2", { classe: "so-leitor", texto: "Câmara" }));
    painel.appendChild(topo);
    painel.appendChild(blocoVotacoes(d));
    painel.appendChild(blocoSessoes(d));
  }

  function unicos(lista) {
    var visto = {};
    return lista.filter(function (x) {
      if (visto[x]) return false;
      visto[x] = true;
      return true;
    });
  }

  function barrasTemas(ids) {
    var lista = contarPorTema(ids);
    var maior = lista.reduce(function (a, x) { return Math.max(a, x.n); }, 0) || 1;
    var ul = el("ul", { classe: "barras", role: "list" });
    lista.forEach(function (x) {
      var ativo = estado.filtroVotacoes.tema === x.tema;
      var barra = el("span", { classe: "barra-trilho", "aria-hidden": "true" }, [el("span", { classe: "barra-cheia" })]);
      barra.firstChild.style.width = Math.max(2, Math.round(100 * x.n / maior)) + "%";
      var botao = el("button", {
        type: "button",
        classe: "barra-botao" + (ehTemaEspecial(x.tema) ? " barra-especial" : ""),
        "aria-pressed": ativo ? "true" : "false",
        ao: {
          click: function () {
            estado.filtroVotacoes.tema = ativo ? "" : x.tema;
            estado.filtroVotacoes.limite = POR_PAGINA;
            renderCamara();
            var alvo = document.getElementById("tit-votacoes");
            if (alvo && !ativo) alvo.scrollIntoView({ block: "start" });
          }
        }
      }, [
        el("span", { classe: "barra-nome", texto: x.tema }),
        el("span", { classe: "barra-num", texto: x.n + (x.n === 1 ? " matéria" : " matérias") }),
        barra
      ]);
      ul.appendChild(el("li", null, [botao]));
    });
    return ul;
  }

  function campoSelect(id, rotulo, opcoes, valor, aoMudar) {
    var sel = el("select", { id: id });
    opcoes.forEach(function (o) {
      var op = el("option", { value: o.valor, texto: o.texto });
      if (o.valor === valor) op.selected = true;
      sel.appendChild(op);
    });
    sel.addEventListener("change", function () { aoMudar(sel.value); });
    return el("div", { classe: "campo" }, [el("label", { "for": id, texto: rotulo }), sel]);
  }

  function normal(s) {
    return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  function votacoesDoAno(d) {
    var f = estado.filtroVotacoes;
    var todas = (d.votacoes || []).slice().sort(function (a, b) {
      return String(b.data_hora || b.data_sessao).localeCompare(String(a.data_hora || a.data_sessao));
    });
    var filtradas = todas.filter(function (v) {
      var tema = temaDe(v.materia_id) || "Sem assunto classificado";
      if (f.tema && tema !== f.tema) return false;
      if (f.registro === "individual" && !v.voto_individual_registrado) return false;
      if (f.registro === "total" && v.voto_individual_registrado) return false;
      if (f.busca) {
        var alvo = normal(nomeMateria(v.materia_id) + " " + textoAutoria(v.autoria) + " " + tema);
        if (alvo.indexOf(normal(f.busca)) === -1) return false;
      }
      return true;
    });
    return { todas: todas, filtradas: filtradas };
  }

  function blocoVotacoes(d) {
    var f = estado.filtroVotacoes;
    var r = votacoesDoAno(d);
    var todas = r.todas;
    var idsVotados = unicos(todas.map(function (v) { return v.materia_id; }));
    var filtradas = r.filtradas;

    var bloco = el("section", { classe: "bloco", "aria-labelledby": "tit-votacoes" });
    bloco.appendChild(el("h2", { id: "tit-votacoes", texto: "Votações de " + estado.ano }));
    bloco.appendChild(el("p", { classe: "bloco-intro", texto: "Da mais recente para a mais antiga. O resultado e os totais são os registrados pela Câmara." }));

    var busca = el("input", { type: "search", id: "busca-votacoes", value: f.busca, placeholder: "Número, tipo ou autor", autocomplete: "off" });
    busca.addEventListener("input", function () {
      f.busca = busca.value;
      f.limite = POR_PAGINA;
      atualizarListaVotacoes();
    });
    var filtros = el("div", { classe: "filtros" }, [
      el("div", { classe: "campo campo-busca" }, [el("label", { "for": "busca-votacoes", texto: "Buscar matéria" }), busca]),
      campoSelect("filtro-tema", "Assunto", [{ valor: "", texto: "Todos os assuntos" }].concat(
        temasDisponiveis(idsVotados).map(function (t) { return { valor: t, texto: t }; })), f.tema, function (v) {
        f.tema = v; f.limite = POR_PAGINA; renderCamara(); focar("filtro-tema");
      }),
      campoSelect("filtro-registro", "Registro do voto", [
        { valor: "", texto: "Todas as votações" },
        { valor: "individual", texto: "Com o voto de cada vereador" },
        { valor: "total", texto: "Só com o total oficial" }
      ], f.registro, function (v) { f.registro = v; f.limite = POR_PAGINA; atualizarListaVotacoes(); })
    ]);
    bloco.appendChild(filtros);
    var saida = el("div", { id: "lista-votacoes" });
    bloco.appendChild(saida);
    preencherVotacoes(saida, filtradas, todas.length);
    return bloco;
  }

  function focar(id) {
    var n = document.getElementById(id);
    if (n) n.focus();
  }

  function atualizarListaVotacoes() {
    var saida = document.getElementById("lista-votacoes");
    if (!saida) return;
    var r = votacoesDoAno(dadosAno());
    preencherVotacoes(saida, r.filtradas, r.todas.length);
  }

  function preencherVotacoes(saida, lista, total) {
    var f = estado.filtroVotacoes;
    limpar(saida);
    var filtrado = f.tema || f.registro || f.busca;
    saida.appendChild(el("p", { classe: "contagem", role: "status", texto: filtrado
      ? lista.length + " de " + total + " votações com estes filtros."
      : total + " votações." }));
    if (filtrado) {
      saida.appendChild(el("button", { type: "button", classe: "botao-texto", ao: { click: function () {
        f.tema = ""; f.registro = ""; f.busca = ""; f.limite = POR_PAGINA; renderCamara(); focar("busca-votacoes");
      } } }, ["Limpar filtros"]));
    }
    if (!lista.length) {
      saida.appendChild(el("p", { classe: "vazio", texto: "Nenhuma votação encontrada com estes filtros." }));
      return;
    }
    var ol = el("ol", { classe: "lista-registros", role: "list" });
    lista.slice(0, f.limite).forEach(function (v) { ol.appendChild(itemVotacao(v)); });
    saida.appendChild(ol);
    botaoMais(saida, lista.length, f, function () { atualizarListaVotacoes(); });
  }

  function botaoMais(saida, total, filtro, recarregar) {
    if (total <= filtro.limite) return;
    var resta = total - filtro.limite;
    saida.appendChild(el("button", { type: "button", classe: "botao-mais", ao: { click: function () {
      var antes = filtro.limite;
      filtro.limite += POR_PAGINA;
      recarregar();
      var itens = saida.querySelectorAll(".lista-registros > li");
      var alvo = itens[antes] && itens[antes].querySelector("a, button, summary");
      if (alvo) alvo.focus();
    } } }, ["Mostrar mais " + Math.min(POR_PAGINA, resta) + " (faltam " + resta + ")"]));
  }

  function totaisOficiais(t) {
    if (!t) return "totais não registrados no SAPL";
    return "Sim " + esc(t.numero_votos_sim) + ", Não " + esc(t.numero_votos_nao) + ", Abstenção " + esc(t.numero_abstencoes);
  }

  function resultadoTexto(v) {
    if (v.frase_resultado_sapl) return acentuar(v.frase_resultado_sapl);
    if (v.situacao_oficial_sapl) return acentuar(v.situacao_oficial_sapl);
    return "Resultado não registrado no SAPL";
  }

  function classeResultado(v) {
    var s = normal(v.situacao_oficial_sapl || v.resultado_texto_sapl);
    if (s.indexOf("aprovad") === 0) return "resultado resultado-aprovado";
    if (s.indexOf("rejeitad") === 0) return "resultado resultado-rejeitado";
    return "resultado";
  }

  function itemVotacao(v) {
    var tema = temaDe(v.materia_id);
    var li = el("li", { classe: "registro" });
    li.appendChild(el("div", { classe: "registro-topo" }, [
      el("h3", { classe: "registro-titulo" }, [linkFonte(v.link_materia, nomeMateria(v.materia_id))]),
      tema ? el("span", { classe: "etiqueta-tema", texto: tema }) : null
    ]));
    li.appendChild(el("p", { classe: "registro-meta" }, [
      linkFonte(v.link_sessao, rotuloSessaoCurto(v.numero_sessao, v.data_sessao)),
      el("span", { classe: "sep", "aria-hidden": "true", texto: " / " }),
      "Autoria: " + textoAutoria(v.autoria)
    ]));
    li.appendChild(el("p", { classe: "registro-resultado" }, [
      el("span", { classe: classeResultado(v), texto: resultadoTexto(v) }),
      " ",
      el("span", { classe: "totais" }, ["Totais oficiais: ", linkFonte(v.link_materia, totaisOficiais(v.totais_oficiais))])
    ]));
    if (!v.voto_individual_registrado) {
      li.appendChild(el("div", { classe: "registro-votos" }, [
        chipEstado("sem_voto_individual", v.rotulo || (dadosAno().meta.rotulo_sem_voto_individual))
      ]));
    } else {
      var lista = el("ul", { classe: "votos-nominais", role: "list" });
      (v.estados_por_vereador || []).forEach(function (e) {
        lista.appendChild(el("li", null, [
          el("span", { classe: "votante", texto: e.nome_parlamentar }),
          chipEstado(e.estado, e.rotulo)
        ]));
      });
      li.appendChild(el("details", { classe: "registro-detalhe" }, [
        el("summary", null, ["Voto de cada vereador (", resumoEstados(v.estados_por_vereador), ")"]),
        lista
      ]));
    }
    return li;
  }

  function resumoEstados(lista) {
    var cont = {};
    var rotulos = {};
    (lista || []).forEach(function (e) {
      cont[e.estado] = (cont[e.estado] || 0) + 1;
      rotulos[e.estado] = e.rotulo;
    });
    return ESTADOS_VOTO.filter(function (k) { return cont[k]; }).map(function (k) {
      return maiusculaInicial(rotulos[k]) + " " + cont[k];
    }).join(", ");
  }

  function blocoSessoes(d) {
    var bloco = el("section", { classe: "bloco", "aria-labelledby": "tit-sessoes" });
    bloco.appendChild(el("h2", { id: "tit-sessoes", texto: "Sessões ordinárias de " + estado.ano }));
    bloco.appendChild(el("p", { classe: "bloco-intro", texto: "Presença de cada vereador, sessão por sessão. Abra uma sessão para ver os nomes." }));
    var porSessao = {};
    (d.vereadores || []).forEach(function (v) {
      (v.presenca && v.presenca.por_sessao || []).forEach(function (p) {
        (porSessao[p.sessao_id] = porSessao[p.sessao_id] || []).push({ v: v, p: p });
      });
    });
    var ol = el("ol", { classe: "lista-sessoes", role: "list" });
    (d.sessoes || []).slice().sort(function (a, b) { return String(b.data).localeCompare(String(a.data)); }).forEach(function (s) {
      var pres = vereadorPorId(d, s.presidente_id_sapl);
      var partes = [esc(s.n_presentes) + " presentes"];
      var faltas = (s.n_faltas_com_justificativa || 0) + (s.n_faltas_sem_justificativa || 0);
      partes.push(faltas === 1 ? "1 falta" : faltas + " faltas");
      if (s.n_licenca) partes.push(esc(s.n_licenca) + " em licença");
      if (s.n_fora_do_mandato) partes.push(esc(s.n_fora_do_mandato) + " fora do mandato");
      var linhas = el("ul", { classe: "votos-nominais", role: "list" });
      (porSessao[s.id] || []).forEach(function (x) {
        linhas.appendChild(el("li", null, [
          el("span", { classe: "votante", texto: x.v.nome_parlamentar }),
          chipEstado(x.p.situacao, x.p.rotulo_situacao)
        ]));
      });
      ol.appendChild(el("li", null, [el("details", { classe: "sessao" }, [
        el("summary", null, [
          el("span", { classe: "sessao-nome", texto: rotuloSessaoCurto(s.numero, s.data) }),
          el("span", { classe: "sessao-resumo", texto: partes.join(", ") })
        ]),
        el("div", { classe: "sessao-corpo" }, [
          el("p", null, [
            pres ? "Presidiu a sessão: " + esc(pres.nome_parlamentar) + ". " : "",
            esc(s.n_registros_votacao) + (s.n_registros_votacao === 1 ? " votação registrada. " : " votações registradas. "),
            linkFonte(s.link_sapl, "Ver a sessão no SAPL")
          ]),
          linhas
        ])
      ])]));
    });
    bloco.appendChild(ol);
    return bloco;
  }

  /* ---------- Painel Vereadores ---------- */

  function vereadorAtual(d) {
    var lista = d.vereadores || [];
    var v = lista.filter(function (x) { return x.slug_codigo === estado.vereadorSlug; })[0];
    return v || lista[0] || null;
  }

  function renderVereadores() {
    var d = dadosAno();
    var painel = document.getElementById("painel-vereadores");
    limpar(painel);
    var lista = (d.vereadores || []).slice().sort(function (a, b) {
      return String(a.nome_parlamentar).localeCompare(String(b.nome_parlamentar), "pt-BR");
    });
    var v = vereadorAtual(d);
    if (v) estado.vereadorSlug = v.slug_codigo;

    painel.appendChild(el("h2", { classe: "titulo-painel", texto: "Vereadores em " + estado.ano }));
    painel.appendChild(el("p", { classe: "bloco-intro", texto: lista.length + " pessoas exerceram mandato em " + estado.ano + ", segundo o cadastro oficial de mandatos no SAPL. Escolha uma para ver presença, votos e projetos." }));

    var escolha = el("ul", { classe: "escolha-vereador", role: "list", "aria-label": "Escolher vereador" });
    lista.forEach(function (x) {
      var foto = urlSegura(x.foto_url);
      escolha.appendChild(el("li", null, [el("button", {
        type: "button",
        classe: "vereador-botao",
        "aria-pressed": x === v ? "true" : "false",
        ao: { click: function () {
          estado.vereadorSlug = x.slug_codigo;
          estado.filtroVotos = { estado: "", limite: POR_PAGINA };
          gravarEndereco();
          renderVereadores();
          focar("perfil-titulo");
        } }
      }, [
        foto ? el("img", { src: foto, alt: "", width: "36", height: "36", loading: "lazy", decoding: "async" }) : el("span", { classe: "foto-vazia", "aria-hidden": "true" }),
        el("span", { classe: "vereador-botao-nome", texto: x.nome_parlamentar })
      ])]));
    });
    painel.appendChild(escolha);
    if (v) painel.appendChild(perfil(d, v));
  }

  function perfil(d, v) {
    var foto = urlSegura(v.foto_url);
    var art = el("article", { classe: "perfil", "aria-labelledby": "perfil-titulo" });
    var partido = v.partido_sigla ? esc(v.partido_sigla) + (v.partido_nome ? " (" + maiusculaNome(v.partido_nome) + ")" : "") : "Partido não registrado no SAPL";
    art.appendChild(el("header", { classe: "perfil-topo" }, [
      foto ? el("img", { classe: "perfil-foto", src: foto, alt: "Foto oficial de " + esc(v.nome_parlamentar) + " no SAPL", width: "96", height: "96", decoding: "async" }) : null,
      el("div", null, [
        el("h3", { id: "perfil-titulo", tabindex: "-1", texto: v.nome_parlamentar }),
        el("p", { classe: "perfil-dado", texto: "Nome oficial: " + esc(v.nome_oficial) }),
        el("p", { classe: "perfil-dado", texto: "Partido: " + partido }),
        el("p", { classe: "perfil-dado", texto: "Mandato registrado: de " + data(v.data_inicio_mandato) + " a " + data(v.data_fim_mandato) }),
        el("p", { classe: "perfil-dado" }, [linkFonte(v.link_sapl, "Cadastro no SAPL")])
      ])
    ]));
    var notas = notasVereador(v);
    if (notas) art.appendChild(notas);
    art.appendChild(secaoPresenca(v));
    art.appendChild(secaoVotos(d, v));
    art.appendChild(secaoProjetosVereador(v));
    return art;
  }

  function maiusculaNome(s) {
    return esc(s).toLowerCase().replace(/(^|\s)([a-zà-ÿ])/g, function (_m, a, b) { return a + b.toUpperCase(); })
      .replace(/\s(De|Do|Da|Dos|Das|E)\s/g, function (m) { return m.toLowerCase(); });
  }

  // Registros de afastamento e notas que vem dos dados, com a fonte.
  function notasVereador(v) {
    var itens = [];
    (v.afastamentos || []).forEach(function (a) {
      itens.push(el("li", null, [
        chipEstado(a.tipo, a.rotulo),
        el("span", null, [" de " + data(a.data_inicio) + " a " + data(a.data_fim) + ". Fonte: ",
          linkFonte(a.link_fonte, acentuar(a.fonte), urlFonteOficial), "."])
      ]));
    });
    var man = estado.afastamentos;
    (man && man.motivos_fora_do_mandato || []).forEach(function (m) {
      if (m.parlamentar_id_sapl !== v.id_sapl) return;
      var fonte = m.materia_id ? linkFonte(origemSapl() + "/materia/" + esc(m.materia_id), nomeMateria(m.materia_id) + " no SAPL") : null;
      itens.push(el("li", null, [
        chipEstado("fora_do_mandato", "Fora do mandato"),
        el("span", null, [" depois de " + data(m.depois_de) + ". Motivo registrado: " + acentuar(m.motivo) + ".",
          fonte ? " Fonte: " : "", fonte, fonte ? "." : ""])
      ]));
    });
    if (v.nota_factual && v.nota_factual.texto) {
      var fontes = (v.nota_factual.fontes || []).filter(function (f) { return f.link_fonte || f.materia_id; });
      var ul = el("span", null, []);
      fontes.forEach(function (f, i) {
        var href = f.link_fonte || (origemSapl() + "/materia/" + esc(f.materia_id));
        anexar(ul, [i ? "; " : "", linkFonte(href, acentuar(f.fonte), urlFonteOficial)]);
      });
      itens.push(el("li", null, [el("span", null, [maiusculaInicial(v.nota_factual.texto) + ". ",
        fontes.length ? "Fontes: " : "", ul, fontes.length ? "." : ""])]));
    }
    if (!itens.length) return null;
    return el("section", { classe: "notas", "aria-labelledby": "tit-notas" }, [
      el("h4", { id: "tit-notas", texto: "Registro de mandato" }),
      el("ul", { role: "list" }, itens)
    ]);
  }

  function barraEmpilhada(partes, total, rotulo) {
    var trilho = el("div", { classe: "empilhada", role: "img", "aria-label": rotulo });
    partes.forEach(function (p) {
      if (!p.n) return;
      var seg = el("span", { classe: "seg " + classeEstado(p.chave).replace("estado estado-", "seg-") });
      seg.style.width = (100 * p.n / total) + "%";
      trilho.appendChild(seg);
    });
    return trilho;
  }

  function secaoPresenca(v) {
    var p = v.presenca || {};
    var porSit = {};
    var rotulos = {};
    (p.por_sessao || []).forEach(function (s) {
      porSit[s.situacao] = (porSit[s.situacao] || 0) + 1;
      rotulos[s.situacao] = s.rotulo_situacao;
    });
    var total = p.sessoes_do_ano || (p.por_sessao || []).length || 0;
    var chaves = ESTADOS_PRESENCA.concat(Object.keys(porSit).filter(function (k) { return ESTADOS_PRESENCA.indexOf(k) === -1; }));
    var partes = chaves.filter(function (k) { return porSit[k]; }).map(function (k) { return { chave: k, n: porSit[k], rotulo: rotulos[k] }; });
    var descricao = partes.map(function (x) { return x.n + " " + acentuar(x.rotulo).toLowerCase(); }).join(", ");
    var sec = el("section", { classe: "perfil-secao", "aria-labelledby": "tit-presenca" }, [
      el("h4", { id: "tit-presenca", texto: "Presença nas sessões ordinárias" }),
      el("p", { classe: "bloco-intro" }, [
        "Das ",
        numeroComFonte(total, linkBuscaSessoes(estado.ano), "sessões no SAPL"),
        " sessões ordinárias de " + estado.ano + " registradas no SAPL:"
      ]),
      total ? barraEmpilhada(partes, total, "Presença: " + descricao) : null
    ]);
    var dl = el("dl", { classe: "contagens" });
    partes.forEach(function (x) {
      dl.appendChild(el("div", null, [el("dt", null, [chipEstado(x.chave, x.rotulo)]), el("dd", { texto: String(x.n) })]));
    });
    sec.appendChild(dl);
    var lista = el("ul", { classe: "votos-nominais", role: "list" });
    (p.por_sessao || []).slice().sort(function (a, b) { return String(b.data_sessao).localeCompare(String(a.data_sessao)); }).forEach(function (s) {
      lista.appendChild(el("li", null, [
        linkFonte(s.link_sessao, acentuar(s.rotulo).replace(/ da \d+ª Sessão Legislativa da \d+ª Legislatura$/, "") + ", " + data(s.data_sessao), null, "votante"),
        chipEstado(s.situacao, s.rotulo_situacao)
      ]));
    });
    sec.appendChild(el("details", { classe: "registro-detalhe" }, [el("summary", { texto: "Ver sessão por sessão" }), lista]));
    return sec;
  }

  function secaoVotos(d, v) {
    var votos = v.votos || {};
    var nominais = (votos.nominais || []).slice().sort(function (a, b) { return String(b.data_sessao).localeCompare(String(a.data_sessao)); });
    var f = estado.filtroVotos;
    var m = d.meta;
    var sec = el("section", { classe: "perfil-secao", "aria-labelledby": "tit-votos" }, [
      el("h4", { id: "tit-votos", texto: "Votos registrados" }),
      el("p", { classe: "bloco-intro", texto: "Em " + esc(m.n_votacoes_com_voto_individual) + " votações de " + estado.ano +
        " o SAPL registrou o voto de cada vereador. Nas outras " + esc(m.n_votacoes_sem_voto_individual) +
        " há só o total oficial, e o painel não atribui voto a ninguém." })
    ]);
    var partes = ESTADOS_VOTO.filter(function (k) { return votos[k]; }).map(function (k) {
      return { chave: k, n: votos[k], rotulo: (votos.rotulos && votos.rotulos[k]) || rotuloEstadoVoto(d, k) };
    });
    var total = votos.total_registros || 0;
    if (total) {
      sec.appendChild(barraEmpilhada(partes, total, "Votos: " + partes.map(function (x) { return x.n + " " + acentuar(x.rotulo).toLowerCase(); }).join(", ")));
      var dl = el("dl", { classe: "contagens" });
      partes.forEach(function (x) {
        dl.appendChild(el("div", null, [el("dt", null, [chipEstado(x.chave, x.rotulo)]), el("dd", { texto: String(x.n) })]));
      });
      sec.appendChild(dl);
    } else {
      sec.appendChild(el("p", { classe: "vazio", texto: "Nenhum voto individual registrado no SAPL para esta pessoa em " + estado.ano + "." }));
      return sec;
    }
    var opcoes = [{ valor: "", texto: "Todos os registros (" + total + ")" }].concat(partes.map(function (x) {
      return { valor: x.chave, texto: maiusculaInicial(x.rotulo) + " (" + x.n + ")" };
    }));
    sec.appendChild(el("div", { classe: "filtros" }, [campoSelect("filtro-voto", "Mostrar", opcoes, f.estado, function (val) {
      f.estado = val; f.limite = POR_PAGINA; preencher();
    })]));
    var saida = el("div");
    sec.appendChild(saida);
    function preencher() {
      limpar(saida);
      var lista = nominais.filter(function (n) { return !f.estado || n.estado === f.estado; });
      var ol = el("ol", { classe: "lista-registros lista-compacta", role: "list" });
      lista.slice(0, f.limite).forEach(function (n) {
        var tema = temaDe(n.materia_id);
        ol.appendChild(el("li", { classe: "registro registro-compacto" }, [
          el("div", { classe: "registro-topo" }, [
            el("span", { classe: "registro-titulo" }, [linkFonte(n.link_materia, nomeMateria(n.materia_id))]),
            chipEstado(n.estado, n.rotulo)
          ]),
          el("p", { classe: "registro-meta" }, [linkFonte(n.link_sessao, "Sessão de " + data(n.data_sessao)), tema ? el("span", { classe: "sep", "aria-hidden": "true", texto: " / " }) : null, tema || null])
        ]));
      });
      saida.appendChild(ol);
      botaoMais(saida, lista.length, f, preencher);
    }
    preencher();
    return sec;
  }

  function secaoProjetosVereador(v) {
    var pl = v.projetos_lei || {};
    var lista = pl.lista || [];
    var sec = el("section", { classe: "perfil-secao", "aria-labelledby": "tit-pl-vereador" }, [
      el("h4", { id: "tit-pl-vereador", texto: "Projetos de lei com autoria" })
    ]);
    if (!lista.length) {
      sec.appendChild(el("p", { classe: "vazio", texto: "Nenhum projeto de lei com autoria desta pessoa em " + estado.ano + " no SAPL." }));
      return sec;
    }
    sec.appendChild(el("p", { classe: "bloco-intro", texto: lista.length + (lista.length === 1 ? " projeto" : " projetos") + " em " + estado.ano +
      (pl.autorias_conjuntas ? ", " + pl.autorias_conjuntas + " com autoria conjunta" : "") + "." }));
    var ol = el("ol", { classe: "lista-registros", role: "list" });
    lista.forEach(function (p) { ol.appendChild(itemProjeto(p)); });
    sec.appendChild(ol);
    return sec;
  }

  /* ---------- Painel Projetos de lei ---------- */

  function itemProjeto(p) {
    var tema = temaDe(p.id);
    var nome = esc(p.tipo_descricao || p.tipo_sigla) + " nº " + esc(p.numero) + " de " + esc(p.ano);
    var li = el("li", { classe: "registro" });
    li.appendChild(el("div", { classe: "registro-topo" }, [
      el("h3", { classe: "registro-titulo" }, [linkFonte(p.link_sapl, nome)]),
      tema ? el("span", { classe: "etiqueta-tema", texto: tema }) : null
    ]));
    if (p.ementa) li.appendChild(el("p", { classe: "ementa", texto: p.ementa }));
    li.appendChild(el("p", { classe: "registro-meta" }, ["Autoria: " + textoAutoria(p.autoria)]));
    var sit = p.frase_resultado_sapl ? acentuar(p.frase_resultado_sapl) : acentuar(p.situacao || "Situação não registrada");
    li.appendChild(el("p", { classe: "registro-resultado" }, [
      el("span", { classe: classeResultado({ situacao_oficial_sapl: p.situacao }), texto: sit }),
      p.data_sessao && p.sessao_id ? el("span", { classe: "totais" }, [" ", linkFonte(origemSapl() + "/sessao/" + esc(p.sessao_id), "Sessão de " + data(p.data_sessao))]) : null
    ]));
    var extras = [];
    (p.votacoes_ordinarias || []).forEach(function (vo) {
      extras.push(el("li", null, [
        linkFonte(vo.link_sessao, "Votação na sessão de " + data(vo.data_sessao)), ": ",
        vo.resultado_texto_sapl ? acentuar(vo.resultado_texto_sapl).toLowerCase() + ", " : "",
        totaisOficiais(vo.totais_oficiais)
      ]));
    });
    if (extras.length) {
      li.appendChild(el("details", { classe: "registro-detalhe" }, [
        el("summary", { texto: extras.length === 1 ? "1 votação em sessão ordinária" : extras.length + " votações em sessões ordinárias" }),
        el("ul", { classe: "lista-simples", role: "list" }, extras)
      ]));
    }
    if (p.texto_original && urlSegura(p.texto_original)) {
      li.appendChild(el("p", { classe: "registro-meta" }, [linkFonte(p.texto_original, "Texto original (PDF)")]));
    }
    return li;
  }

  function renderProjetos() {
    var d = dadosAno();
    var painel = document.getElementById("painel-projetos");
    limpar(painel);
    var f = estado.filtroProjetos;
    var todos = d.projetos_lei || [];
    var tipos = unicos(todos.map(function (p) { return p.tipo_sigla + "|" + (p.tipo_descricao || p.tipo_sigla); }));
    var filtrados = todos.filter(function (p) {
      if (f.tipo && p.tipo_sigla !== f.tipo) return false;
      if (f.tema && temaDe(p.id) !== f.tema) return false;
      return true;
    }).sort(function (a, b) { return Number(b.numero) - Number(a.numero) || String(a.tipo_sigla).localeCompare(String(b.tipo_sigla)); });

    painel.appendChild(el("h2", { classe: "titulo-painel", texto: "Projetos de lei de " + estado.ano }));
    painel.appendChild(el("p", { classe: "bloco-intro" }, [
      numeroComFonte(todos.length, linkBuscaMaterias(estado.ano), "matérias no SAPL"),
      " projetos de lei apresentados em " + estado.ano + ", do Legislativo e do Executivo, com a situação registrada no SAPL."
    ]));
    painel.appendChild(el("div", { classe: "filtros" }, [
      campoSelect("filtro-tipo", "Origem", [{ valor: "", texto: "Todas" }].concat(tipos.map(function (t) {
        var p = t.split("|");
        return { valor: p[0], texto: p[1] };
      })), f.tipo, function (v) { f.tipo = v; f.limite = POR_PAGINA; renderProjetos(); focar("filtro-tipo"); }),
      campoSelect("filtro-tema-pl", "Assunto", [{ valor: "", texto: "Todos os assuntos" }].concat(
        temasDisponiveis(todos.map(function (p) { return p.id; })).map(function (t) { return { valor: t, texto: t }; })),
        f.tema, function (v) { f.tema = v; f.limite = POR_PAGINA; renderProjetos(); focar("filtro-tema-pl"); })
    ]));
    var saida = el("div");
    painel.appendChild(saida);
    function preencher() {
      limpar(saida);
      saida.appendChild(el("p", { classe: "contagem", role: "status", texto: filtrados.length + " de " + todos.length + " projetos." }));
      if (!filtrados.length) {
        saida.appendChild(el("p", { classe: "vazio", texto: "Nenhum projeto com estes filtros." }));
        return;
      }
      var ol = el("ol", { classe: "lista-registros", role: "list" });
      filtrados.slice(0, f.limite).forEach(function (p) { ol.appendChild(itemProjeto(p)); });
      saida.appendChild(ol);
      botaoMais(saida, filtrados.length, f, preencher);
    }
    preencher();
  }

  /* ---------- Legenda e rodape ---------- */

  function renderLegenda() {
    var d = dadosAno();
    var caixa = document.getElementById("legenda");
    limpar(caixa);
    var rot = d.meta.rotulos_estados || {};
    var dlVoto = el("dl", { classe: "glossario" });
    ESTADOS_VOTO.forEach(function (k) {
      dlVoto.appendChild(el("div", null, [el("dt", null, [chipEstado(k, rot[k] || k)]), el("dd", { texto: EXPLICACOES[k] })]));
    });
    dlVoto.appendChild(el("div", null, [el("dt", null, [chipEstado("sem_voto_individual", d.meta.rotulo_sem_voto_individual)]), el("dd", { texto: EXPLICACOES.sem_voto_individual })]));
    var presencas = {};
    (d.vereadores || []).forEach(function (v) {
      (v.presenca && v.presenca.por_sessao || []).forEach(function (s) { presencas[s.situacao] = s.rotulo_situacao; });
    });
    var dlPres = el("dl", { classe: "glossario" });
    ["presente", "falta_com_justificativa", "falta_sem_justificativa"].forEach(function (k) {
      if (!presencas[k]) return;
      dlPres.appendChild(el("div", null, [el("dt", null, [chipEstado(k, presencas[k])]), el("dd", { texto: EXPLICACOES[k] })]));
    });
    anexar(caixa, [
      el("h2", { id: "legenda-titulo", texto: "Como ler os rótulos" }),
      d.meta.observacao ? el("p", { classe: "regra", texto: acentuar(d.meta.observacao) }) : null,
      el("div", { classe: "glossario-grade" }, [
        el("section", { "aria-labelledby": "tit-leg-voto" }, [el("h3", { id: "tit-leg-voto", texto: "No voto" }), dlVoto]),
        el("section", { "aria-labelledby": "tit-leg-pres" }, [el("h3", { id: "tit-leg-pres", texto: "Na presença" }), dlPres,
          el("p", { classe: "bloco-intro", texto: "Licença para tratamento de saúde e fora do mandato valem também para a presença e não contam como falta." })])
      ])
    ]);
  }

  function renderRodape() {
    var cfg = estado.cfg;
    var d = dadosAno();
    var r = document.getElementById("rodape");
    limpar(r);
    var arquivo = PASTA_DADOS + "atuacao_vereadores_" + estado.ano + ".json";
    var repo = urlDoConfig(cfg.painel && cfg.painel.repositorio);
    anexar(r, [
      el("div", { classe: "rodape-interno" }, [
        el("p", null, ["Fonte de todos os números: ", linkFonte(origemSapl() + "/", "SAPL da Câmara Municipal de " + esc(cfg.cidade.nome)),
          ". Dados coletados em " + dataPorExtenso(d.meta.dado_coletado_em) + "."]),
        el("p", null, ["Conferir o arquivo de " + estado.ano + ": ",
          el("a", { href: arquivo, texto: "dados em JSON" }), " e ",
          el("a", { href: arquivo + ".sha256", texto: "código de conferência SHA-256" }), "."]),
        repo ? el("p", null, ["Encontrou um erro? ", el("a", { href: repo + "/issues", target: "_blank", rel: "noopener noreferrer" }, ["Avise pelo GitHub", el("span", { classe: "so-leitor", texto: " (abre em nova aba)" }), iconeExterno()]),
          ", com o número da sessão ou da matéria e o link do SAPL."]) : null,
        el("p", { texto: "Projeto independente, sem ligação com a Câmara, a Prefeitura, vereador, partido ou candidatura. O painel copia e organiza o registro oficial; não completa nem estima dado que falta." })
      ])
    ]);
  }

  /* ---------- Navegacao ---------- */

  var ABAS = ["camara", "vereadores", "projetos"];

  function ativarAba(aba, focarAba) {
    estado.aba = ABAS.indexOf(aba) === -1 ? "camara" : aba;
    ABAS.forEach(function (a) {
      var botao = document.getElementById("aba-" + a);
      var painel = document.getElementById("painel-" + a);
      var ativa = a === estado.aba;
      botao.setAttribute("aria-selected", ativa ? "true" : "false");
      botao.tabIndex = ativa ? 0 : -1;
      painel.hidden = !ativa;
      if (ativa && focarAba) botao.focus();
    });
    esconderDica();
    gravarEndereco();
  }

  function iniciarAbas() {
    ABAS.forEach(function (a, i) {
      var botao = document.getElementById("aba-" + a);
      botao.addEventListener("click", function () { ativarAba(a, false); });
      botao.addEventListener("keydown", function (e) {
        var alvo = null;
        if (e.key === "ArrowRight") alvo = ABAS[(i + 1) % ABAS.length];
        else if (e.key === "ArrowLeft") alvo = ABAS[(i + ABAS.length - 1) % ABAS.length];
        else if (e.key === "Home") alvo = ABAS[0];
        else if (e.key === "End") alvo = ABAS[ABAS.length - 1];
        if (alvo) { e.preventDefault(); ativarAba(alvo, true); }
      });
    });
  }

  function lerEndereco() {
    var q = {};
    String(window.location.hash || "").replace(/^#/, "").split("&").forEach(function (par) {
      var p = par.split("=");
      if (p[0]) {
        try { q[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || ""); } catch (e) { /* ignora */ }
      }
    });
    return q;
  }

  function gravarEndereco() {
    if (!estado.ano) return;
    var h = "#ano=" + encodeURIComponent(estado.ano) + "&secao=" + encodeURIComponent(estado.aba);
    if (estado.aba === "vereadores" && estado.vereadorSlug) h += "&vereador=" + encodeURIComponent(estado.vereadorSlug);
    if (window.location.hash !== h && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", h);
    }
  }

  function renderTudo() {
    atualizarColeta();
    atualizarAvisoAno();
    renderCamara();
    renderVereadores();
    renderProjetos();
    renderLegenda();
    renderRodape();
  }

  function trocarAno(ano) {
    estado.ano = ano;
    estado.filtroVotacoes = { tema: "", registro: "", busca: "", limite: POR_PAGINA };
    estado.filtroVotos = { estado: "", limite: POR_PAGINA };
    estado.filtroProjetos = { tipo: "", tema: "", limite: POR_PAGINA };
    esconderDica();
    document.getElementById("coleta").textContent = "Carregando " + ano + "…";
    carregarAno(ano).then(function () {
      if (estado.ano !== ano) return;
      renderTudo();
      gravarEndereco();
    }).catch(mostrarErro);
  }

  function mostrarErro(erro) {
    var alvo = document.getElementById("coleta");
    limpar(alvo);
    alvo.className = "coleta erro";
    anexar(alvo, ["Não foi possível ler os arquivos de dados. Recarregue a página. Detalhe técnico: " + esc(erro && erro.message)]);
  }

  /* ---------- Inicio ---------- */

  function iniciar() {
    aplicarTema(temaInicial(), false);
    document.getElementById("botao-tema").addEventListener("click", function () {
      var atual = document.documentElement.getAttribute("data-tema");
      aplicarTema(atual === "escuro" ? "claro" : "escuro", true);
    });
    iniciarDicas();
    iniciarAbas();

    lerJson(CAMINHO_CONFIG).then(function (cfg) {
      estado.cfg = cfg;
      estado.anos = (cfg.recorte && cfg.recorte.anos || []).map(Number).filter(function (a) { return a > 0; });
      if (!estado.anos.length || !origemSapl()) throw new Error("config_cidade.json sem anos ou sem endereço do SAPL");
      var q = lerEndereco();
      var anoPedido = Number(q.ano);
      estado.ano = estado.anos.indexOf(anoPedido) !== -1 ? anoPedido : estado.anos[estado.anos.length - 1];
      if (q.vereador) estado.vereadorSlug = q.vereador;
      montarCabecalhoFixo();
      return Promise.all([
        carregarAno(estado.ano),
        lerJson(PASTA_DADOS + "temas_materias.json").catch(function () { return null; }),
        lerJson(PASTA_DADOS + "autoria_materias.json").catch(function () { return null; }),
        lerJson(PASTA_DADOS + "afastamentos_manuais.json").catch(function () { return null; })
      ]).then(function (r) {
        indexarApoio(r[1], r[2], r[3]);
        renderTudo();
        ativarAba(q.secao || "camara", false);
      });
    }).catch(mostrarErro);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
  else iniciar();
})();
