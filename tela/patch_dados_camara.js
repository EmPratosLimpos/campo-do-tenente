
  function ultimaSessaoOrdinaria() {
    var sessoes = (estado.dados && estado.dados.sessoes) || [];
    if (!sessoes.length) return null;
    return sessoes.reduce(function (melhor, s) {
      if (!melhor) return s;
      return (s.data || "") >= (melhor.data || "") ? s : melhor;
    }, null);
  }

  function dataUltimaSessaoFmt() {
    var s = ultimaSessaoOrdinaria();
    DATA_ULTIMA_SESSAO = s && s.data ? formatarData(s.data) : "";
    return DATA_ULTIMA_SESSAO;
  }

  function dataColetaCurta() {
    var meta = estado.dados && estado.dados.meta;
    if (!meta || !meta.dado_coletado_em) return "";
    return formatarData(String(meta.dado_coletado_em).split("T")[0]);
  }

  function dataColetaExibicao() {
    var meta = estado.dados && estado.dados.meta;
    if (!meta || !meta.dado_coletado_em) return "";
    return formatarDataHora(meta.dado_coletado_em);
  }

  function rotuloOrdinaria(sessao) {
    if (!sessao) return "";
    if (sessao.numero != null) return sessao.numero + "\u00aa Ordin\u00e1ria";
    return "Sess\u00e3o ordin\u00e1ria";
  }

  function svgCardMeta() {
    return '<svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 18l6-6-6-6"></path></svg>';
  }

  function atualizarRodapesColeta() {
    var data = dataColetaExibicao();
    var fonte = rotuloSaplCamara();
    var us = ultimaSessaoOrdinaria();
    var linkSessao = us && us.link_sapl ? urlSegura(us.link_sapl) : "";
    document.querySelectorAll(".rodape-coleta").forEach(function (footer) {
      var painel = footer.closest(".painel-camara-interno");
      var comLink = painel && painel.id === "painel-periodo-sessao" && linkSessao;
      var html = "<p>Dado coletado em <strong>" + esc(data) + "</strong>. Fonte: ";
      if (comLink) {
        html += '<a href="' + esc(linkSessao) + '" target="_blank" rel="noopener noreferrer">' + esc(fonte) + "</a>";
      } else {
        html += esc(fonte);
      }
      html += ".</p>";
      footer.innerHTML = html;
    });
    var imp = document.getElementById("data-coleta-impressao");
    if (imp) imp.textContent = dataColetaCurta();
  }

  function atualizarCabecalhoUltimaSessao() {
    var s = ultimaSessaoOrdinaria();
    var titulo = document.getElementById("link-titulo-ultima-sessao");
    var metaData = document.getElementById("texto-meta-data-votacoes-sessao");
    var metaLink = document.getElementById("link-meta-data-votacoes-sessao");
    if (!s) {
      if (titulo) titulo.hidden = true;
      return;
    }
    var href = urlSegura(s.link_sapl) || "#";
    if (titulo) {
      titulo.textContent = rotuloOrdinaria(s);
      titulo.href = href;
      titulo.hidden = false;
    }
    if (metaData) metaData.textContent = formatarData(s.data);
    if (metaLink) metaLink.href = href;
  }

  function atualizarPresencaUltimaSessao() {
    var s = ultimaSessaoOrdinaria();
    var meta = estado.dados && estado.dados.meta;
    var banca = meta && meta.n_vereadores != null ? meta.n_vereadores : 0;
    var textoBanca = document.getElementById("texto-meta-presenca-sessao");
    var linkMeta = document.getElementById("link-meta-presenca-sessao");
    var elPresentes = document.querySelector("#card-presenca-sessao .capsula-verde .capsula-valor");
    var elFaltas = document.querySelector("#card-presenca-sessao .capsula-neutro .capsula-valor");
    if (!s) return;
    var faltas = (s.n_faltas_com_justificativa || 0) + (s.n_faltas_sem_justificativa || 0);
    var rotuloBanca = banca === 1 ? "1 parlamentar" : banca + " parlamentares";
    if (textoBanca) textoBanca.textContent = rotuloBanca;
    if (linkMeta) linkMeta.href = urlSegura(s.link_sapl) || "#";
    if (elPresentes) elPresentes.textContent = String(s.n_presentes != null ? s.n_presentes : 0);
    if (elFaltas) elFaltas.textContent = String(faltas);
  }

  function atualizarTiposMes() {
    var container = document.getElementById("tipos-mes-barras");
    if (!container) return;
    var lista = MATERIAS_CAMARA.mes || [];
    var total = lista.length;
    if (total === 0) {
      container.innerHTML = "";
      return;
    }
    container.innerHTML =
      '<div class="barra-tema"><span class="nome">Projeto de Lei do Legislativo</span>' +
      '<div class="trilho"><div class="preenchido" style="width:100%;background:var(--barra-pl)"></div></div>' +
      '<span class="qtd">' + esc(total) + "</span></div>";
  }

  function atualizarPainelTodo() {
    var meta = estado.dados && estado.dados.meta;
    var lista = MATERIAS_CAMARA.todo || [];
    var total = lista.length;
    var nSessoes = meta && meta.n_sessoes_ordinarias != null ? meta.n_sessoes_ordinarias : 0;
    var ano = ANO_ATUAL;
    var titulo = document.getElementById("titulo-periodo-todo");
    if (titulo) titulo.textContent = "Ano de " + ano;
    var metaEl = document.getElementById("meta-periodo-todo");
    if (metaEl) {
      metaEl.textContent = nSessoes + " sess\u00f5es ordin\u00e1rias, " + total + " PLLs votados.";
    }
    var legTipos = document.getElementById("legenda-tipos-todo");
    if (legTipos) {
      legTipos.textContent =
        "Projetos de Lei do Legislativo (PLL) votados em sess\u00f5es ordin\u00e1rias de " + ano + ".";
    }
    var barraTipos = document.getElementById("barra-tipos-todo");
    if (barraTipos) {
      if (total === 0) {
        barraTipos.innerHTML = "";
      } else {
        barraTipos.innerHTML =
          '<div class="barra-tema"><span class="nome">Projeto de Lei do Legislativo</span>' +
          '<div class="trilho"><div class="preenchido" style="width:100%;background:var(--barra-pl)"></div></div>' +
          '<span class="qtd">' + esc(total) + "</span></div>";
      }
    }
    var unanimes = lista.filter(function (m) { return m.resultado === "unanimidade"; }).length;
    var maioria = total - unanimes;
    var legRes = document.getElementById("legenda-resultado-todo");
    if (legRes) {
      legRes.textContent =
        "Resultado dos " + total + " PLLs votados em sess\u00f5es ordin\u00e1rias de " + ano + ".";
    }
    var barraRes = document.getElementById("barra-resultado-todo");
    if (barraRes && total > 0) {
      var pctUni = (unanimes / total) * 100;
      var pctMai = (maioria / total) * 100;
      barraRes.setAttribute(
        "aria-label",
        unanimes + " unanimidade, " + maioria + " maioria absoluta, 0 rejeitado"
      );
      barraRes.innerHTML =
        '<div class="segmento segmento-unanimidade" style="width:' + pctUni.toFixed(1) + '%"></div>' +
        (maioria > 0
          ? '<div class="segmento segmento-maioria" style="width:' + pctMai.toFixed(1) + '%"></div>'
          : "");
    } else if (barraRes) {
      barraRes.innerHTML = "";
      barraRes.removeAttribute("aria-label");
    }
    var cartoes = document.getElementById("cartoes-resultado-todo");
    if (cartoes && total > 0) {
      var pctUniCard = ((unanimes / total) * 100).toFixed(0);
      var pctMaiCard = ((maioria / total) * 100).toFixed(0);
      cartoes.innerHTML =
        '<div class="status-cartao status-cartao-unanimidade"><span class="indicador" style="background:var(--barra-unanimidade)"></span>' +
        '<span class="num">' + esc(unanimes) + '</span><span class="pct">' + esc(pctUniCard) + '%</span><span class="rot">Unanimidade</span></div>' +
        '<div class="status-cartao status-cartao-maioria"><span class="indicador" style="background:var(--barra-maioria)"></span>' +
        '<span class="num">' + esc(maioria) + '</span><span class="pct">' + esc(pctMaiCard) + '%</span><span class="rot">Maioria</span></div>' +
        '<div class="status-cartao status-cartao-rejeitado"><span class="indicador" style="background:var(--graf-rejeitado)"></span>' +
        '<span class="num">0</span><span class="pct">0%</span><span class="rot">Rejeitadas</span></div>';
    } else if (cartoes) {
      cartoes.innerHTML = "";
    }
    var nota = document.getElementById("nota-resultado-todo");
    if (nota) {
      nota.textContent =
        "Total: " + total + " PLLs votados em sess\u00f5es ordin\u00e1rias de " + ano + ".";
    }
    var btnShare = document.querySelector("#painel-periodo-todo .btn-compartilhar-icone");
    if (btnShare) btnShare.setAttribute("aria-label", "Compartilhar vota\u00e7\u00f5es de " + ano);
  }

  function nomeMesAnteriorUltimaSessao() {
    var sessoes = (estado.dados && estado.dados.sessoes) || [];
    var datas = sessoes.map(function (s) { return s.data; }).filter(Boolean).sort();
    var ultimaData = datas[datas.length - 1];
    if (!ultimaData) return "";
    var partes = ultimaData.split("-");
    var y = parseInt(partes[0], 10);
    var mo = parseInt(partes[1], 10);
    mo -= 1;
    if (mo < 1) { mo = 12; y -= 1; }
    var meses = ["Janeiro", "Fevereiro", "Mar\u00e7o", "Abril", "Maio", "Junho",
      "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
    return meses[mo - 1] + " de " + y;
  }

  function atualizarInterfaceCamara() {
    dataUltimaSessaoFmt();
    atualizarCabecalhoUltimaSessao();
    atualizarPresencaUltimaSessao();
    atualizarRodapesColeta();
    atualizarPainelMes();
    atualizarTiposMes();
    atualizarPainelTodo();
    atualizarCardVotacoes();
    atualizarVotacoesMes();
    ["sessao", "mes", "todo"].forEach(function (p) {
      renderTemasDistribuicao(p);
      renderBlocoVotadoPeriodo(p);
    });
  }
