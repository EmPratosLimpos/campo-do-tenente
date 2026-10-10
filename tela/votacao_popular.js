/* Votacao popular: usa o markup #votacao-overlay do index.html */
(function (global) {
  "use strict";

  var deps = {};
  var rodada = null;
  var resultados = null;
  var autorizacao = "";
  var materias = [];
  var respostas = {};
  var indiceCartao = 0;
  var turnstileToken = "";
  var widgetTurnstileId = null;
  var minimoRespostas = 10;
  var workerBase = "";
  var turnstileKey = "";

  var STORAGE_APARELHO = "epl_vp_aparelho_id";
  var STORAGE_VOTO_PREFIX = "epl_vp_votou:";
  var AVISO_CONSULTA =
    "Consulta informal, n\u00e3o \u00e9 pesquisa nem plebiscito.";

  function cfg() {
    return deps.getConfig ? deps.getConfig() : null;
  }

  function esc(t) {
    return deps.esc ? deps.esc(t) : String(t == null ? "" : t);
  }

  function urlSegura(u) {
    return deps.urlSegura ? deps.urlSegura(u) : "";
  }

  function formatarData(d) {
    return deps.formatarData ? deps.formatarData(d) : String(d || "");
  }

  function captureEvento(nome) {
    if (deps.captureEvento) deps.captureEvento(nome, {});
  }

  function blocoCfg() {
    var c = cfg();
    return (c && c.votacao_popular) || {};
  }

  function workerUrl() {
    return String(blocoCfg().worker_url || "").replace(/\/$/, "");
  }

  function ativo() {
    return !!workerUrl();
  }

  function el(id) {
    return document.getElementById(id);
  }

  function aparelhoId() {
    try {
      var id = localStorage.getItem(STORAGE_APARELHO);
      if (id && /^[0-9a-f-]{36}$/i.test(id)) return id;
      id = global.crypto && crypto.randomUUID ? crypto.randomUUID() : "";
      if (!id) return "";
      localStorage.setItem(STORAGE_APARELHO, id);
      return id;
    } catch (e) {
      return "";
    }
  }

  function marcouVotoLocal(rodadaId) {
    if (!rodadaId) return false;
    try {
      return localStorage.getItem(STORAGE_VOTO_PREFIX + rodadaId) === "1";
    } catch (e) {
      return false;
    }
  }

  function marcarVotoLocal(rodadaId) {
    try {
      localStorage.setItem(STORAGE_VOTO_PREFIX + rodadaId, "1");
    } catch (e) { /* ignore */ }
  }

  function podeVerResultados() {
    if (!rodada) return false;
    if (marcouVotoLocal(rodada.rodada_id)) return true;
    var st = rodada.status || "";
    return st === "fechada" || st === "sem_materias_elegiveis";
  }

  function apiUrl(path) {
    return workerBase.replace(/\/$/, "") + path;
  }

  function fetchJson(url, opts) {
    return fetch(url, opts).then(function (r) {
      return r.text().then(function (txt) {
        var corpo = null;
        try {
          corpo = txt ? JSON.parse(txt) : null;
        } catch (e) {
          corpo = null;
        }
        return { ok: r.ok, status: r.status, headers: r.headers, corpo: corpo };
      });
    });
  }

  function cidadeNome() {
    var c = cfg();
    return (c && c.cidade && c.cidade.nome) || "o munic\u00edpio";
  }

  function mensagemRede() {
    return "Sem conex\u00e3o ou servidor fora. Tente de novo em instantes.";
  }

  function mensagemCodigo(codigo, corpo) {
    var mapa = {
      gps_negado: "Ative a localiza\u00e7\u00e3o do aparelho para participar.",
      fora_do_municipio:
        "Voc\u00ea parece estar fora de " +
        cidadeNome() +
        ". A consulta vale para quem est\u00e1 no munic\u00edpio.",
      precisao_ruim:
        "Sinal de localiza\u00e7\u00e3o fraco. Tente de novo em local aberto.",
      captcha_invalido: "Verifica\u00e7\u00e3o anti rob\u00f4 falhou. Tente de novo.",
      ja_votou: "Este aparelho j\u00e1 votou nesta rodada.",
      teto_endereco: "Muitos votos nesta conex\u00e3o para esta rodada.",
      limite_pedidos: "Muitos pedidos. Aguarde e tente de novo.",
      rodada_fechada: "Esta rodada j\u00e1 fechou.",
      autorizacao_invalida:
        "Autoriza\u00e7\u00e3o inv\u00e1lida ou vencida. Refa\u00e7a a verifica\u00e7\u00e3o.",
      autorizacao_reutilizada:
        "Autoriza\u00e7\u00e3o j\u00e1 usada. Refa\u00e7a a verifica\u00e7\u00e3o.",
      erro_interno: "Servidor indispon\u00edvel. Tente de novo em instantes.",
    };
    if (codigo && mapa[codigo]) return mapa[codigo];
    if (corpo && corpo.erro) return String(corpo.erro);
    return mensagemRede();
  }

  function mostrarErro(msg) {
    var node = el("votacao-erro-msg");
    var btnFechar = el("votacao-btn-fechar-erro");
    if (!node) return;
    if (!msg) {
      node.hidden = true;
      node.textContent = "";
      if (btnFechar) btnFechar.hidden = true;
      return;
    }
    node.hidden = false;
    node.textContent = msg;
    if (btnFechar) btnFechar.hidden = false;
  }

  function tratarHttp(resp) {
    if (resp.status === 429) {
      var seg =
        (resp.corpo && resp.corpo.tentar_depois_s) ||
        parseInt(resp.headers.get("Retry-After") || "30", 10);
      mostrarErro(
        "Muitos pedidos. Aguarde " + seg + " segundos e tente de novo."
      );
      return true;
    }
    if (!resp.ok) {
      var cod = resp.corpo && resp.corpo.codigo;
      mostrarErro(mensagemCodigo(cod, resp.corpo));
      return true;
    }
    return false;
  }

  function atualizarEntrada() {
    var fab = el("btn-votar-fab");
    var msg = el("votacao-ja-votou-msg");
    if (!fab || !msg) return;
    if (!ativo() || !rodada) {
      fab.hidden = true;
      msg.hidden = true;
      return;
    }
    var aberta =
      rodada.status === "aberta" &&
      rodada.materias &&
      rodada.materias.length > 0;
    if (marcouVotoLocal(rodada.rodada_id)) {
      fab.hidden = true;
      if (aberta) {
        msg.hidden = false;
        msg.textContent = "Voc\u00ea j\u00e1 votou nesta rodada.";
      } else {
        msg.hidden = true;
      }
      return;
    }
    if (!aberta) {
      fab.hidden = true;
      msg.hidden = true;
      return;
    }
    msg.hidden = true;
    fab.hidden = false;
  }

  function metaResultado() {
    if (!rodada) return "";
    var partes = [];
    if (rodada.data_sessao) {
      partes.push(
        "Rodada da sess\u00e3o de " + formatarData(rodada.data_sessao)
      );
    }
    if (resultados && resultados.atualizado_em) {
      partes.push(
        "Atualizado em " +
          formatarData(String(resultados.atualizado_em).split("T")[0])
      );
    }
    return partes.join(". ") + (partes.length ? "." : "");
  }

  function htmlBarra(u, i) {
    return (
      '<div class="vp-barra-resultado" role="img" aria-label="' +
      esc(u + "% \u00fatil, " + i + "% in\u00fatil") +
      '"><span class="vp-barra-seg" style="width:' +
      esc(String(u)) +
      '%"></span><span class="vp-barra-seg vp-barra-seg-b" style="width:' +
      esc(String(i)) +
      '%"></span></div>'
    );
  }

  function htmlResultadoMateria(materiaId) {
    if (!podeVerResultados() || !resultados) return "";
    var lista = resultados.materias || [];
    var achado = null;
    for (var i = 0; i < lista.length; i++) {
      if (String(lista[i].materia_id) === String(materiaId)) {
        achado = lista[i];
        break;
      }
    }
    if (!achado) return "";
    var corpo;
    if (achado.percentual_util == null) {
      var menos =
        typeof achado.respostas === "string"
          ? achado.respostas
          : "menos de " + minimoRespostas;
      corpo =
        '<p class="votacao-resultado-linha apoio">' + esc(menos) + "</p>";
    } else {
      corpo =
        '<p class="votacao-resultado-linha">' +
        esc(String(achado.percentual_util)) +
        "% \u00fatil \u00b7 " +
        esc(String(achado.percentual_inutil)) +
        "% in\u00fatil</p>" +
        htmlBarra(achado.percentual_util, achado.percentual_inutil);
    }
    var total =
      typeof achado.respostas === "number"
        ? achado.respostas + " respostas"
        : "";
    return (
      '<div class="votacao-resultado-materia" data-vp-materia="' +
      esc(String(materiaId)) +
      '"><p class="votacao-aviso">' +
      esc(AVISO_CONSULTA) +
      "</p>" +
      corpo +
      (total ? '<p class="apoio">' + esc(total) + "</p>" : "") +
      '<p class="apoio">' +
      esc(metaResultado()) +
      "</p></div>"
    );
  }

  function htmlParaMateria(id) {
    return htmlResultadoMateria(id);
  }

  function blocoResultadoMateria(id) {
    return htmlResultadoMateria(id);
  }

  function htmlConsolidadoVereador(v) {
    if (!v || !podeVerResultados() || !resultados || !deps.proposicoesAutor) {
      return "";
    }
    var itens = deps.proposicoesAutor(v.id_sapl) || [];
    var idsRodada = {};
    (rodada.materias || []).forEach(function (m) {
      idsRodada[m.id] = true;
    });
    var util = 0;
    var inutil = 0;
    itens.forEach(function (item) {
      var mid = item.materia_id || item.id;
      if (!idsRodada[mid]) return;
      var achado = null;
      (resultados.materias || []).forEach(function (r) {
        if (String(r.materia_id) === String(mid)) achado = r;
      });
      if (!achado || achado.percentual_util == null) return;
      var tot =
        typeof achado.respostas === "number"
          ? achado.respostas
          : parseInt(String(achado.respostas), 10) || 0;
      if (!tot) return;
      util += Math.round((achado.percentual_util / 100) * tot);
      inutil += Math.round((achado.percentual_inutil / 100) * tot);
    });
    var soma = util + inutil;
    if (!soma) return "";
    var pu = Math.round((util / soma) * 100);
    var pi = Math.round((inutil / soma) * 100);
    return (
      '<article class="cartao ac-cartao votacao-consolidado" aria-labelledby="tit-vp-cons">' +
      '<h2 class="t2" id="tit-vp-cons">Consulta informal na rodada atual</h2>' +
      '<p class="votacao-aviso">' +
      esc(AVISO_CONSULTA) +
      "</p>" +
      '<p class="resumo">Nas mat\u00e9rias desta rodada em que este vereador \u00e9 autor: <strong>' +
      esc(String(pu)) +
      "%</strong> \u00fatil e <strong>" +
      esc(String(pi)) +
      "%</strong> in\u00fatil.</p>" +
      htmlBarra(pu, pi) +
      '<p class="apoio">' +
      esc(metaResultado()) +
      "</p></article>"
    );
  }

  function abrirModal() {
    var ov = el("votacao-overlay");
    if (!ov) return;
    ov.classList.add("ativo");
    ov.setAttribute("aria-hidden", "false");
    document.body.classList.add("folha-aberta");
    mostrarErro("");
    irPasso("termos");
    captureEvento("votacao_iniciada");
  }

  function fecharModal() {
    var ov = el("votacao-overlay");
    if (!ov) return;
    ov.classList.remove("ativo");
    ov.setAttribute("aria-hidden", "true");
    document.body.classList.remove("folha-aberta");
    limparTurnstile();
    mostrarErro("");
  }

  function irPasso(nome) {
    var mapa = {
      termos: "votacao-passo-termos",
      cartoes: "votacao-passo-cartoes",
      resumo: "votacao-passo-resumo",
      fim: "votacao-passo-fim",
    };
    Object.keys(mapa).forEach(function (k) {
      var node = el(mapa[k]);
      if (node) node.hidden = k !== nome;
    });
    if (nome === "termos") renderTurnstile();
    if (nome === "cartoes") renderCartao();
    if (nome === "resumo") renderResumo();
    if (nome === "fim") renderFim();
  }

  function limparTurnstile() {
    turnstileToken = "";
    var box = el("votacao-turnstile");
    if (box) box.innerHTML = "";
    widgetTurnstileId = null;
  }

  function scriptTurnstile() {
    return new Promise(function (resolve, reject) {
      if (global.turnstile) {
        resolve();
        return;
      }
      var s = document.createElement("script");
      s.async = true;
      s.src =
        "https://" +
        "challenges" +
        "." +
        "cloudflare" +
        ".com/turnstile/v0/api.js?render=explicit";
      s.onload = function () {
        resolve();
      };
      s.onerror = function () {
        reject(new Error("turnstile"));
      };
      document.head.appendChild(s);
    });
  }

  function renderTurnstile() {
    limparTurnstile();
    if (!turnstileKey) return;
    scriptTurnstile()
      .then(function () {
        var box = el("votacao-turnstile");
        if (!box || !global.turnstile) return;
        widgetTurnstileId = turnstile.render(box, {
          sitekey: turnstileKey,
          callback: function (token) {
            turnstileToken = token;
          },
          "expired-callback": function () {
            turnstileToken = "";
          },
        });
      })
      .catch(function () { /* ok em teste */ });
  }

  function tituloMateria(m) {
    return (
      esc(m.sigla || "") +
      " " +
      esc(m.numero || "") +
      "/" +
      esc(m.ano || "")
    );
  }

  function renderCartao() {
    var host = el("votacao-cartao-palco");
    var prog = el("votacao-progresso");
    if (!host || !materias.length) return;
    var m = materias[indiceCartao];
    if (prog) {
      prog.textContent = indiceCartao + 1 + " de " + materias.length;
    }
    var link = urlSegura(m.link_sapl);
    var linkHtml = link
      ? '<a class="fonte" href="' +
        esc(link) +
        '" target="_blank" rel="noopener noreferrer">Ver no SAPL<svg class="ic" width="16" height="16" aria-hidden="true"><use href="#ic-ver-na-fonte"/></svg></a>'
      : "";
    host.innerHTML =
      '<div class="voto-cartao vp-cartao-materia" tabindex="0">' +
      '<p class="vp-cartao-tipo">' +
      tituloMateria(m) +
      "</p>" +
      '<p class="materia-assunto">' +
      esc(m.ementa || "") +
      "</p>" +
      linkHtml +
      "</div>";
    var cartao = host.querySelector(".vp-cartao-materia");
    if (cartao) configurarArraste(cartao);
  }

  function registrar(valor) {
    var m = materias[indiceCartao];
    if (!m) return;
    respostas[m.id] = valor === "util" ? "util" : "inutil";
    if (indiceCartao < materias.length - 1) {
      indiceCartao += 1;
      renderCartao();
    } else {
      irPasso("resumo");
    }
  }

  function configurarArraste(cartao) {
    var x0 = 0;
    cartao.addEventListener("pointerdown", function (e) {
      x0 = e.clientX;
    });
    cartao.addEventListener("pointerup", function (e) {
      var dx = e.clientX - x0;
      if (Math.abs(dx) < 40) return;
      registrar(dx > 0 ? "util" : "inutil");
    });
  }

  function renderResumo() {
    var lista = el("votacao-resumo-lista");
    if (!lista) return;
    var html = "";
    materias.forEach(function (m, idx) {
      var v = respostas[m.id] === "util" ? "\u00datil" : "\u00cdn\u00fatil";
      html +=
        '<li class="votacao-item"><button type="button" class="votacao-item-texto vp-link-resumo" data-idx="' +
        idx +
        '"><strong>' +
        tituloMateria(m) +
        "</strong><span>" +
        esc(v) +
        "</span></button></li>";
    });
    lista.innerHTML = html;
    lista.querySelectorAll(".vp-link-resumo").forEach(function (btn) {
      btn.addEventListener("click", function () {
        indiceCartao = parseInt(btn.getAttribute("data-idx"), 10) || 0;
        irPasso("cartoes");
      });
    });
  }

  function renderFim() {
    var host = el("votacao-fim-corpo");
    if (!host) return;
    var itens = (resultados && resultados.materias) || [];
    var blocos = itens
      .map(function (r) {
        return (
          "<li>" + htmlResultadoMateria(r.materia_id) + "</li>"
        );
      })
      .join("");
    host.innerHTML =
      '<p class="votacao-aviso">' +
      esc(AVISO_CONSULTA) +
      '</p><ul class="votacao-lista">' +
      blocos +
      '</ul><p class="apoio">' +
      esc(metaResultado()) +
      "</p>";
  }

  function pedirLocalizacao() {
    mostrarErro("");
    if (!turnstileToken && turnstileKey) {
      mostrarErro(
        "Conclua a verifica\u00e7\u00e3o anti rob\u00f4 antes de continuar."
      );
      return;
    }
    if (!navigator.geolocation) {
      mostrarErro(mensagemCodigo("gps_negado", null));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        enviarVerificar(
          pos.coords.latitude,
          pos.coords.longitude,
          pos.coords.accuracy
        );
      },
      function () {
        mostrarErro(mensagemCodigo("gps_negado", null));
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
  }

  function enviarVerificar(lat, lon, precisao) {
    var aid = aparelhoId();
    if (!aid) {
      mostrarErro(mensagemCodigo("pedido_invalido", null));
      return;
    }
    fetchJson(apiUrl("/api/verificar"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        turnstile_token: turnstileToken || "token-teste-falso",
        aparelho_id: aid,
        lat: lat,
        lon: lon,
        precisao_m: precisao,
      }),
    })
      .then(function (resp) {
        if (tratarHttp(resp)) return;
        if (!resp.corpo || !resp.corpo.ok) {
          mostrarErro(mensagemRede());
          return;
        }
        if (resp.corpo.ja_votou) {
          marcarVotoLocal(resp.corpo.rodada_id || rodada.rodada_id);
          fecharModal();
          atualizarEntrada();
          mostrarErro(mensagemCodigo("ja_votou", resp.corpo));
          return;
        }
        autorizacao = resp.corpo.autorizacao || "";
        materias = (rodada.materias || []).slice();
        respostas = {};
        indiceCartao = 0;
        irPasso("cartoes");
      })
      .catch(function () {
        mostrarErro(mensagemRede());
      });
  }

  function enviarVoto() {
    mostrarErro("");
    fetchJson(apiUrl("/api/votar"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        autorizacao: autorizacao,
        aparelho_id: aparelhoId(),
        respostas: materias.map(function (m) {
          return { materia_id: m.id, valor: respostas[m.id] };
        }),
      }),
    })
      .then(function (resp) {
        if (tratarHttp(resp)) return;
        if (!resp.corpo || !resp.corpo.ok) {
          mostrarErro(mensagemRede());
          return;
        }
        marcarVotoLocal(resp.corpo.rodada_id || rodada.rodada_id);
        captureEvento("votacao_enviada");
        return carregarResultados().then(function () {
          irPasso("fim");
          atualizarEntrada();
          if (deps.onResultados) deps.onResultados();
        });
      })
      .catch(function () {
        mostrarErro(mensagemRede());
      });
  }

  function normalizarResultados(corpo) {
    if (!corpo || !corpo.rodadas) return null;
    var rid = rodada && rodada.rodada_id;
    var achada = null;
    for (var i = 0; i < corpo.rodadas.length; i++) {
      if (corpo.rodadas[i].rodada_id === rid) {
        achada = corpo.rodadas[i];
        break;
      }
    }
    if (!achada && corpo.rodadas.length) achada = corpo.rodadas[0];
    if (!achada) return null;
    return {
      materias: achada.materias || [],
      atualizado_em: corpo.atualizado_em,
    };
  }

  function carregarResultados() {
    if (!podeVerResultados()) return Promise.resolve();
    return fetchJson(apiUrl("/api/resultados"))
      .then(function (resp) {
        if (!resp.ok || !resp.corpo) return;
        resultados = normalizarResultados(resp.corpo);
      })
      .catch(function () { /* silencioso */ });
  }

  function carregarRodada() {
    if (!ativo()) {
      atualizarEntrada();
      return Promise.resolve();
    }
    workerBase = workerUrl();
    turnstileKey = String(blocoCfg().turnstile_site_key || "");
    minimoRespostas =
      (blocoCfg().limites && blocoCfg().limites.minimo_respostas_por_materia) ||
      10;
    return fetchJson(apiUrl("/api/rodada"))
      .then(function (resp) {
        if (!resp.ok || !resp.corpo) {
          rodada = null;
          return;
        }
        rodada = resp.corpo;
        return carregarResultados();
      })
      .catch(function () {
        rodada = null;
      })
      .then(function () {
        atualizarEntrada();
        if (deps.onResultados) deps.onResultados();
      });
  }

  function initTeclado() {
    document.addEventListener("keydown", function (e) {
      var ov = el("votacao-overlay");
      if (!ov || !ov.classList.contains("ativo")) return;
      var passo = el("votacao-passo-cartoes");
      if (!passo || passo.hidden) return;
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        registrar("inutil");
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        registrar("util");
      } else if (e.key === "Enter") {
        var a = document.activeElement;
        if (a && a.id === "votacao-btn-util") {
          e.preventDefault();
          registrar("util");
        } else if (a && a.id === "votacao-btn-inutil") {
          e.preventDefault();
          registrar("inutil");
        }
      }
    });
  }

  function ligarUi() {
    var fab = el("btn-votar-fab");
    if (fab) fab.addEventListener("click", abrirModal);
    var fechar = el("votacao-btn-fechar");
    if (fechar) fechar.addEventListener("click", fecharModal);
    var fecharErro = el("votacao-btn-fechar-erro");
    if (fecharErro) {
      fecharErro.addEventListener("click", function () {
        mostrarErro("");
        fecharModal();
      });
    }
    var fecharFim = el("votacao-btn-fechar-fim");
    if (fecharFim) fecharFim.addEventListener("click", fecharModal);
    var geo = el("votacao-btn-localizacao");
    if (geo) geo.addEventListener("click", pedirLocalizacao);
    var env = el("votacao-btn-enviar");
    if (env) env.addEventListener("click", enviarVoto);
    var volt = el("votacao-btn-voltar");
    if (volt) {
      volt.addEventListener("click", function () {
        if (indiceCartao > 0) {
          indiceCartao -= 1;
          irPasso("cartoes");
        }
      });
    }
    var u = el("votacao-btn-util");
    var i = el("votacao-btn-inutil");
    if (u) u.addEventListener("click", function () {
      registrar("util");
    });
    if (i) i.addEventListener("click", function () {
      registrar("inutil");
    });
    var ov = el("votacao-overlay");
    if (ov) {
      ov.addEventListener("click", function (e) {
        if (e.target === ov) fecharModal();
      });
    }
  }

  function init(opcoes) {
    deps = opcoes || {};
    ligarUi();
    initTeclado();
    return carregarRodada();
  }

  global.VotacaoPopular = {
    init: init,
    recarregar: carregarRodada,
    htmlParaMateria: htmlParaMateria,
    blocoResultadoMateria: blocoResultadoMateria,
    htmlConsolidadoVereador: htmlConsolidadoVereador,
    podeVerResultados: podeVerResultados,
    _teste: { mensagemCodigo: mensagemCodigo, htmlConsolidadoVereador: htmlConsolidadoVereador },
  };
})(typeof window !== "undefined" ? window : globalThis);
