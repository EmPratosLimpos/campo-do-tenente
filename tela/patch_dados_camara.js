
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

  function contagemPresencaSessao(sessao) {
    if (!sessao) {
      return { presentes: 0, faltas: 0, fora: 0, licenca: 0, banca: 0 };
    }
    var presentes = sessao.n_presentes != null ? sessao.n_presentes : 0;
    var faltas =
      (sessao.n_faltas_com_justificativa || 0) + (sessao.n_faltas_sem_justificativa || 0);
    var fora = sessao.n_fora_do_mandato || 0;
    var licenca = sessao.n_licenca || 0;
    return {
      presentes: presentes,
      faltas: faltas,
      fora: fora,
      licenca: licenca,
      banca: presentes + faltas + fora + licenca
    };
  }

  function capsulaPresenca(classe, rotulo, valor) {
    return (
      '<div class="status-capsula ' +
      classe +
      '"><span class="capsula-rotulo">' +
      esc(rotulo) +
      '</span><span class="capsula-valor">' +
      esc(String(valor)) +
      "</span></div>"
    );
  }

  function contagemResultadosMaterias(lista) {
    var out = { unanimidade: 0, maioria: 0, rejeitado: 0, outro: 0 };
    (lista || []).forEach(function (m) {
      var r = m.resultado || "outro";
      if (r === "unanimidade") out.unanimidade += 1;
      else if (r === "maioria") out.maioria += 1;
      else if (r === "rejeitado") out.rejeitado += 1;
      else if (r === "primeiro_turno" || r === "turno_nao_identificado") return;
      else out.outro += 1;
    });
    return out;
  }

  function atualizarAvisoLacunaSapl() {
    var aviso = document.getElementById("aviso-lacuna-sapl");
    if (!aviso) return;
    var meta = estado.dados && estado.dados.meta;
    var lacuna = meta && meta.lacuna_sessoes_ordinarias;
    var par = aviso.querySelector("p");
    if (!lacuna || !lacuna.aviso || !meta || meta.ano !== ANO_ATUAL) {
      aviso.hidden = true;
      if (par) par.textContent = "";
      return;
    }
    if (par) par.innerHTML = "<strong>Aviso:</strong> " + esc(lacuna.aviso);
    aviso.hidden = false;
  }

  function atualizarPresencaUltimaSessao() {
    var s = ultimaSessaoOrdinaria();
    var meta = estado.dados && estado.dados.meta;
    var rotulos = (meta && meta.rotulos_estados) || {};
    var textoBanca = document.getElementById("texto-meta-presenca-sessao");
    var linkMeta = document.getElementById("link-meta-presenca-sessao");
    var grade = document.querySelector("#card-presenca-sessao .status-grade");
    if (!s) return;
    var c = contagemPresencaSessao(s);
    if (textoBanca) {
      if (c.banca > 0) {
        textoBanca.textContent =
          c.banca === 1 ? "1 parlamentar" : c.banca + " parlamentares";
      } else {
        textoBanca.textContent = "";
      }
    }
    if (linkMeta) linkMeta.href = urlSegura(s.link_sapl) || "#";
    if (grade) {
      var html =
        capsulaPresenca("capsula-verde", "Presentes", c.presentes) +
        capsulaPresenca("capsula-neutro", "Faltas", c.faltas);
      if (c.fora > 0) {
        html += capsulaPresenca(
          "capsula-neutro",
          rotulos.fora_do_mandato || "Fora do mandato naquela data",
          c.fora
        );
      }
      if (c.licenca > 0) {
        html += capsulaPresenca(
          "capsula-neutro",
          rotulos.licenca_tratamento_saude || "Licença",
          c.licenca
        );
      }
      grade.innerHTML = html;
    }
  }

  function ajustarPainelUltimaSessaoSemPll() {
    var lista = MATERIAS_CAMARA.sessao || [];
    if (lista.length > 0) return;
    var bloco = document.getElementById("bloco-votado-sessao");
    if (!bloco) return;
    var us = ultimaSessaoOrdinaria();
    var dataFmt = us && us.data ? formatarData(us.data) : "";
    var texto =
      "Nenhum projeto de lei do legislativo (PLL) foi votado na última sessão ordinária";
    if (dataFmt) texto += " (" + dataFmt + ")";
    texto += ".";
    var vazio = bloco.querySelector(".estado-vazio");
    if (vazio) {
      vazio.innerHTML = "<p>" + esc(texto) + "</p>";
    } else {
      bloco.insertAdjacentHTML(
        "beforeend",
        '<div class="estado-vazio"><p>' + esc(texto) + "</p></div>"
      );
    }
    var temas = document.getElementById("temas-distribuicao-sessao");
    if (temas && !temas.textContent.trim()) {
      temas.innerHTML =
        '<p class="vazio" style="margin:0">' + esc(texto) + "</p>";
    }
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
    var contagem = contagemResultadosMaterias(lista);
    var unanimes = contagem.unanimidade;
    var maioria = contagem.maioria;
    var rejeitadas = contagem.rejeitado;
    var outro = contagem.outro;
    var legRes = document.getElementById("legenda-resultado-todo");
    if (legRes) {
      legRes.textContent =
        "Resultado dos " + total + " PLLs votados em sess\u00f5es ordin\u00e1rias de " + ano + ".";
    }
    var barraRes = document.getElementById("barra-resultado-todo");
    if (barraRes && total > 0) {
      var pctUni = (unanimes / total) * 100;
      var pctMai = (maioria / total) * 100;
      var pctRej = (rejeitadas / total) * 100;
      var pctOut = (outro / total) * 100;
      barraRes.setAttribute(
        "aria-label",
        unanimes +
          " unanimidade, " +
          maioria +
          " maioria, " +
          rejeitadas +
          " rejeitado, " +
          outro +
          " outro"
      );
      var htmlBarra =
        '<div class="segmento segmento-unanimidade" style="width:' + pctUni.toFixed(1) + '%"></div>';
      if (maioria > 0) {
        htmlBarra +=
          '<div class="segmento segmento-maioria" style="width:' + pctMai.toFixed(1) + '%"></div>';
      }
      if (rejeitadas > 0) {
        htmlBarra +=
          '<div class="segmento segmento-rejeitado" style="width:' + pctRej.toFixed(1) + '%"></div>';
      }
      if (outro > 0) {
        htmlBarra +=
          '<div class="segmento segmento-tramitacao" style="width:' + pctOut.toFixed(1) + '%"></div>';
      }
      barraRes.innerHTML = htmlBarra;
    } else if (barraRes) {
      barraRes.innerHTML = "";
      barraRes.removeAttribute("aria-label");
    }
    var cartoes = document.getElementById("cartoes-resultado-todo");
    if (cartoes && total > 0) {
      function cartaoResultado(classe, num, rot) {
        var pctCard = ((num / total) * 100).toFixed(0);
        return (
          '<div class="status-cartao status-cartao-' +
          classe +
          '"><span class="indicador" style="background:var(--barra-' +
          classe +
          ',var(--graf-' +
          classe +
          '))"></span><span class="num">' +
          esc(num) +
          '</span><span class="pct">' +
          esc(pctCard) +
          '%</span><span class="rot">' +
          esc(rot) +
          "</span></div>"
        );
      }
      var htmlCartoes = cartaoResultado("unanimidade", unanimes, "Unanimidade");
      htmlCartoes += cartaoResultado("maioria", maioria, "Maioria");
      htmlCartoes += cartaoResultado("rejeitado", rejeitadas, "Rejeitadas");
      if (outro > 0) {
        htmlCartoes += cartaoResultado("tramitacao", outro, "Outro resultado");
      }
      cartoes.innerHTML = htmlCartoes;
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

  function atualizarVotacoesMes() {
    var container = document.getElementById("votacoes-mes-conteudo");
    if (!container) return;

    var lista = MATERIAS_CAMARA.mes || [];
    var total = lista.length;
    if (total === 0) {
      container.innerHTML = "";
      return;
    }

    var contagem = contagemResultadosMaterias(lista);
    var unanimes = contagem.unanimidade;
    var maioria = contagem.maioria;
    var rejeitadas = contagem.rejeitado;
    var outro = contagem.outro;
    var pctUni = total > 0 ? Math.round((unanimes / total) * 100) : 0;
    var pctMai = total > 0 ? Math.round((maioria / total) * 100) : 0;

    var rotuloTotal = total === 1 ? "1 projeto votado" : total + " projetos votados";

    container.innerHTML =
      '<div class="card-header">' +
      '<div class="card-categoria cat-laranja">' +
      '<div class="card-icone icone-laranja" aria-hidden="true">' +
      '<svg width="14" height="14" fill="currentColor" viewBox="0 0 24 24"><path d="M12 23c6.075 0 11-4.925 11-11 0-4.04-2.18-7.58-5.46-9.52-.39-.23-.88.11-.8.56.57 3.32-.42 6.64-2.74 8.89-2.07-3.04-2.52-6.85-1.2-10.36.17-.46-.3-.9-.73-.69C8.36 2.65 5.5 6.94 5.5 12c0 1.25.21 2.45.59 3.57-1.34-1.2-2.09-2.93-2.09-4.8 0-.48-.56-.76-.92-.44C1.19 12.01 0 14.86 0 18c0 2.76 1.12 5.26 2.93 7.07C4.74 26.88 7.24 28 10 28c.68 0 1.34-.07 1.98-.2-.33-.67-.53-1.42-.53-2.22 0-2.48 2.02-4.5 4.5-4.5h.05c-.39-1.09-.6-2.27-.6-3.5 0-.75.08-1.48.24-2.18-.75.75-1.74 1.28-2.84 1.5-.47.1-.8-.34-.6-.78 1.1-2.4 1.05-5.22-.15-7.58-.23-.46.24-.96.7-.76 2.4 1.03 4.2 3.12 4.7 5.72z"></path></svg></div>' +
      '<span id="tit-votacoes-mes">Vota\u00e7\u00f5es do M\u00eas</span></div>' +
      '<span class="card-meta">' + rotuloTotal + "</span></div>" +
      '<div class="card-corpo">' +
      '<div class="metricas-bloco">' +
      '<div class="metrica-destaque">' +
      '<span class="metrica-numero">' + total + "</span>" +
      '<span class="metrica-rotulo">projetos votados</span></div>' +
      '<div class="metrica-detalhes">' +
      '<div class="item-detalhe">' +
      '<span class="det-rotulo det-rotulo-unanimidade">Unanimidade</span>' +
      '<span class="det-valor">' + unanimes + ' <small style="font-size:11px;font-weight:500">(' + pctUni + "%)</small></span></div>" +
      '<div class="item-detalhe det-separador">' +
      '<span class="det-rotulo det-rotulo-maioria">Por Maioria</span>' +
      '<span class="det-valor">' + maioria + ' <small style="font-size:11px;font-weight:500">(' + pctMai + "%)</small></span></div>" +
      (rejeitadas > 0
        ? '<div class="item-detalhe det-separador"><span class="det-rotulo">Rejeitadas</span><span class="det-valor">' +
          rejeitadas +
          "</span></div>"
        : "") +
      (outro > 0
        ? '<div class="item-detalhe det-separador"><span class="det-rotulo">Outro resultado</span><span class="det-valor">' +
          outro +
          "</span></div>"
        : "") +
      "</div></div>" +
      '<div class="grafico-anel-box" role="img" aria-label="' +
      total +
      " projetos: " +
      unanimes +
      " unanimidade, " +
      maioria +
      " maioria, " +
      rejeitadas +
      " rejeitado, " +
      outro +
      ' outro">' +
      '<svg class="anel-svg" viewBox="0 0 58 58" aria-hidden="true">' +
      '<circle class="anel-fundo" cx="29" cy="29" r="23"></circle>' +
      '<circle class="anel-progresso-unanimidade" cx="29" cy="29" r="23"></circle>' +
      '<circle class="anel-progresso-maioria" cx="29" cy="29" r="23"></circle></svg>' +
      '<span class="anel-porcento">' + pctUni + "%</span></div></div>";

    var circ = 2 * Math.PI * 23;
    var circUni = container.querySelector(".anel-progresso-unanimidade");
    var circMai = container.querySelector(".anel-progresso-maioria");
    if (circUni) {
      circUni.style.strokeDasharray = (pctUni / 100 * circ) + " " + circ;
      circUni.style.strokeDashoffset = "0";
    }
    if (circMai) {
      if (pctMai === 0) {
        circMai.style.display = "none";
      } else {
        circMai.style.display = "";
        circMai.style.strokeDasharray = (pctMai / 100 * circ) + " " + circ;
        circMai.style.strokeDashoffset = -(pctUni / 100 * circ);
      }
    }
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
    atualizarAvisoLacunaSapl();
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
    estadoMaterias.listaVisivel.sessao = true;
    ajustarPainelUltimaSessaoSemPll();
  }
