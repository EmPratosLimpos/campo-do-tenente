
  function aplicarRotulosMeta(dados) {
    var meta = dados && dados.meta;
    if (!meta) return;
    if (meta.rotulos_estados) {
      Object.keys(meta.rotulos_estados).forEach(function (chave) {
        ROTULOS_VOTO[chave] = meta.rotulos_estados[chave];
      });
    }
    if (meta.rotulo_sem_voto_individual) {
      ROTULO_SEM_VOTO_INDIVIDUAL = meta.rotulo_sem_voto_individual;
    }
  }

  function contagemVotoResumo(vo, chave) {
    if (!vo) return 0;
    return vo[chave] != null ? vo[chave] : 0;
  }

  function cardsResumoVotos(vo) {
    var rot = (vo && vo.rotulos) || {};
    var defs = [
      ["sim", rot.sim || "Sim"],
      ["nao", rot.nao || "N\u00e3o"],
      ["abstencao", rot.abstencao || "Absten\u00e7\u00e3o"],
      ["nao_votou", rot.nao_votou || "N\u00e3o votou"],
      ["presidente_que_nao_votou", rot.presidente_que_nao_votou || "Presidente que n\u00e3o votou"],
      ["ausente_com_justificativa", rot.ausente_com_justificativa || "Ausente com justificativa"],
      ["ausente_sem_justificativa", rot.ausente_sem_justificativa || "Ausente sem justificativa"],
      ["fora_do_mandato", rot.fora_do_mandato || "Fora do mandato naquela data"],
      [
        "presente_sem_voto_individual_registrado",
        rot.presente_sem_voto_individual_registrado || "Presente sem voto individual registrado"
      ],
      ["licenca_tratamento_saude", rot.licenca_tratamento_saude || "Licen\u00e7a para tratamento de sa\u00fade"]
    ];
    return defs.map(function (par) {
      return { num: contagemVotoResumo(vo, par[0]), rot: par[1], id: par[0] };
    });
  }

  function textoNotaFactual(nota) {
    if (!nota) return "";
    if (typeof nota === "string") return nota;
    if (typeof nota === "object" && nota.texto) return String(nota.texto);
    return "";
  }

  function linkFonteNotaFactual(fonte) {
    if (!fonte || typeof fonte !== "object") return "";
    if (fonte.link_fonte) return urlSegura(fonte.link_fonte);
    if (fonte.materia_id) return urlSegura(linkMateria(fonte.materia_id));
    return "";
  }

  function renderNotasParlamentar(v) {
    var html = "";
    var nota = v.nota_factual;
    var textoNota = textoNotaFactual(nota);
    if (textoNota) {
      html += '<p class="nota-factual">' + esc(textoNota) + "</p>";
    }
    var fontes = nota && typeof nota === "object" && Array.isArray(nota.fontes) ? nota.fontes : [];
    if (fontes.length) {
      html += '<div class="nota-factual-fontes"><p class="apoio nota-cartao"><strong>Fonte:</strong> ';
      var links = [];
      fontes.forEach(function (f) {
        var rotulo = f.fonte || "Ver fonte";
        var href = linkFonteNotaFactual(f);
        if (href) {
          links.push('<a class="fonte" href="' + esc(href) + '" target="_blank" rel="noopener noreferrer">' + esc(rotulo) + "</a>");
        } else {
          links.push("<span>" + esc(rotulo) + "</span>");
        }
      });
      html += links.join(" ") + "</p></div>";
    }
    var afast = v.afastamentos || [];
    if (afast.length) {
      html += '<div class="faltas-lista"><h3>Afastamentos registrados</h3><ul>';
      afast.forEach(function (a) {
        var rot = a.rotulo || a.tipo || "Afastamento";
        var periodo = "";
        if (a.data_inicio) periodo = formatarData(a.data_inicio);
        if (a.data_fim) periodo += (periodo ? " a " : "") + formatarData(a.data_fim);
        html += "<li><strong>" + esc(rot) + "</strong>";
        if (periodo) html += " (" + esc(periodo) + ")";
        if (a.motivo) html += ". " + esc(a.motivo);
        html += "</li>";
      });
      html += "</ul></div>";
    }
    return html;
  }

  function renderSecaoPresenca(v) {
    var p = v.presenca;
    var rotMeta = rotulosVotoMeta();
    var partes = [
      { valor: p.presencas, cor: "var(--graf-presenca)", rotulo: "Presente" },
      { valor: p.faltas_com_justificativa, cor: "var(--graf-falta-just)", rotulo: "Falta com justificativa" },
      { valor: p.faltas_sem_justificativa, cor: "var(--graf-falta-sem)", rotulo: "Falta sem justificativa" }
    ];
    if (p.sessoes_licenca > 0) {
      partes.push({
        valor: p.sessoes_licenca,
        cor: "var(--graf-falta-just)",
        rotulo: rotMeta.licenca_tratamento_saude || "Licen\u00e7a para tratamento de sa\u00fade"
      });
    }

    function sessoesPorSituacao(situacao) {
      return (p.por_sessao || []).filter(function (s) {
        return s.situacao === situacao;
      });
    }

    var faltasJust = sessoesPorSituacao("falta_com_justificativa");
    var faltasSem = sessoesPorSituacao("falta_sem_justificativa");
    var licencas = sessoesPorSituacao("licenca_tratamento_saude");

    var htmlFaltas = "";
    if (
      p.faltas_com_justificativa > 0 ||
      p.faltas_sem_justificativa > 0 ||
      licencas.length
    ) {
      htmlFaltas += '<div class="faltas-lista">';
      if (p.faltas_com_justificativa > 0) {
        htmlFaltas += "<h3>Faltas com justificativa oficial (" + esc(p.faltas_com_justificativa) + ")</h3><ul>";
        faltasJust.forEach(function (s) {
          htmlFaltas += "<li><strong>Sess\u00e3o " + esc(s.sessao_id) + "</strong>, " +
            esc(formatarData(s.data_sessao)) + ". " +
            linkExt(s.link_sessao, "Ver no SAPL") + "</li>";
        });
        htmlFaltas += "</ul>";
      }
      if (p.faltas_sem_justificativa > 0) {
        htmlFaltas += "<h3>Faltas sem justificativa (" + esc(p.faltas_sem_justificativa) + ")</h3><ul>";
        faltasSem.forEach(function (s) {
          htmlFaltas += "<li><strong>Sess\u00e3o " + esc(s.sessao_id) + "</strong>, " +
            esc(formatarData(s.data_sessao)) + ". " +
            linkExt(s.link_sessao, "Ver no SAPL") + "</li>";
        });
        htmlFaltas += "</ul>";
      }
      if (licencas.length) {
        var rotLic = rotMeta.licenca_tratamento_saude || "Licen\u00e7a para tratamento de sa\u00fade";
        htmlFaltas += "<h3>" + esc(rotLic) + " (" + esc(licencas.length) + ")</h3><ul>";
        licencas.forEach(function (s) {
          htmlFaltas += "<li><strong>Sess\u00e3o " + esc(s.sessao_id) + "</strong>, " +
            esc(formatarData(s.data_sessao)) + ". " +
            esc(s.rotulo_situacao || rotLic) + ". " +
            linkExt(s.link_sessao, "Ver no SAPL") + "</li>";
        });
        htmlFaltas += "</ul>";
      }
      htmlFaltas += "</div>";
    } else {
      htmlFaltas =
        '<p class="vazio" style="margin-top:10px">Nenhuma falta registrada nas ' +
        esc(p.sessoes_ordinarias) +
        " sess\u00f5es ordin\u00e1rias de " +
        ANO_ATUAL +
        ".</p>";
    }

    return (
      '<section class="secao" aria-labelledby="tit-presenca">' +
      '<h2 id="tit-presenca">Presen\u00e7a nas sess\u00f5es ordin\u00e1rias</h2>' +
      '<p class="legenda">Total de ' +
      esc(p.sessoes_ordinarias) +
      " sess\u00f5es ordin\u00e1rias de " +
      ANO_ATUAL +
      ' no mandato. Taxa de presen\u00e7a: <strong>' +
      esc(p.taxa_presenca.toFixed(2).replace(".", ",")) +
      "%</strong>. Percentual de faltas: <strong>" +
      esc(p.percentual_faltas.toFixed(2).replace(".", ",")) +
      "%</strong>.</p>" +
      '<div class="grafico-linha">' +
      '<div class="rosca-wrap">' +
      roscaSVG(
        partes,
        120,
        p.taxa_presenca.toFixed(1).replace(".", ",") + "%",
        "presen\u00e7a",
        "Taxa de presen\u00e7a: " + p.taxa_presenca.toFixed(2).replace(".", ",") + "%"
      ) +
      "</div>" +
      '<div class="rosca-legenda"><dl>' +
      partes
        .map(function (pt) {
          return (
            '<dt><span class="indicador" style="background:' +
            pt.cor +
            '"></span>' +
            esc(pt.rotulo) +
            "</dt><dd>" +
            esc(pt.valor) +
            " sess\u00f5es</dd>"
          );
        })
        .join("") +
      "</dl></div></div>" +
      htmlFaltas +
      "</section>"
    );
  }

  function renderSecaoVotos(v) {
    var vo = v.votos;
    var cards = cardsResumoVotos(vo).filter(function (c) {
      return c.num > 0;
    });

    var nominais = vo.nominais || [];
    var filtrados = nominais.filter(function (n) {
      if (estado.filtroClassificacao && classificacaoNominal(n) !== estado.filtroClassificacao) {
        return false;
      }
      if (estado.filtroTexto) {
        var busca = normalizarTexto(estado.filtroTexto);
        var ementa = ementaVotacao(n);
        var tagsBusca = n.materia_id ? tagsMateria(n.materia_id) : null;
        var tipoNumeroBusca = tipoNumeroDoVoto(n);
        var texto =
          (ementa || "") +
          " " +
          (n.materia_id || "") +
          " " +
          n.data_sessao +
          " " +
          (tipoNumeroBusca || "");
        if (tagsBusca) texto += " " + tagsBusca.tag_tipo + " " + tagsBusca.tag_tema;
        if (normalizarTexto(texto).indexOf(busca) === -1) return false;
      }
      return true;
    });

    var totalPag = Math.max(1, Math.ceil(filtrados.length / POR_PAGINA));
    if (estado.pagina > totalPag) estado.pagina = totalPag;
    var inicio = (estado.pagina - 1) * POR_PAGINA;
    var fatia = filtrados.slice(inicio, inicio + POR_PAGINA);

    var opcoesFiltro = Object.keys(ROTULOS_VOTO)
      .map(function (k) {
        var sel = estado.filtroClassificacao === k ? " selected" : "";
        return '<option value="' + esc(k) + '"' + sel + ">" + esc(ROTULOS_VOTO[k]) + "</option>";
      })
      .join("");

    var atalhosVoto = cardsResumoVotos(vo)
      .filter(function (c) {
        return c.num > 0;
      })
      .map(function (c) {
        return { id: c.id, rot: c.rot };
      });

    var itens = fatia
      .map(function (n) {
        var ementa = ementaVotacao(n);
        var textoEmenta = ementa
          ? esc(ementa.length > 180 ? ementa.slice(0, 177) + "..." : ementa)
          : n.materia_id
            ? "Mat\u00e9ria " +
              esc(n.materia_id) +
              " (" +
              linkExt(linkMateria(n.materia_id), "ementa no SAPL") +
              ")"
            : "Mat\u00e9ria n\u00e3o identificada no registro";
        var linkSess =
          estado.linksSessao[n.sessao_id] || SAPL_ORIGEM + "/sessao/" + n.sessao_id;
        var tagsHtml = n.materia_id ? htmlTagsMateria(n.materia_id) : "";
        var tipoNumero = tipoNumeroDoVoto(n);
        return (
          "<li>" +
          '<div class="data-voto">' +
          esc(formatarData(n.data_sessao)) +
          ", sess\u00e3o " +
          esc(n.sessao_id) +
          "</div>" +
          (tipoNumero ? '<div class="materia-titulo">' + esc(tipoNumero) + "</div>" : "") +
          (tagsHtml ? tagsHtml : "") +
          '<span class="voto-selo ' +
          classeVotoSelo(classificacaoNominal(n)) +
          '">' +
          esc(rotuloVotoNominal(n)) +
          "</span>" +
          (n.turno === "1o turno" || n.turno === "2o turno"
            ? ' <span class="tag-turno">' + esc(n.turno) + "</span>"
            : "") +
          "<span>" +
          textoEmenta +
          "</span> " +
          linkExt(linkSess, "Sess\u00e3o no SAPL") +
          "</li>"
        );
      })
      .join("");

    var listaAtiva = listaVotosAtiva();
    var htmlListaVotos = "";
    if (!listaAtiva) {
      htmlListaVotos =
        '<div class="estado-vazio" id="votos-estado-vazio">' +
        "<p>Escolha um tipo de voto ou busque por ementa para ver a lista detalhada.</p>" +
        '<div class="atalhos-voto" role="group" aria-label="Filtrar por tipo de voto">' +
        atalhosVoto
          .map(function (a) {
            return (
              '<button type="button" class="btn-atalho-voto" data-voto="' +
              esc(a.id) +
              '">' +
              esc(a.rot) +
              "</button>"
            );
          })
          .join("") +
        "</div></div>";
    } else {
      htmlListaVotos =
        '<ul class="lista-votos" aria-live="polite">' +
        (itens || '<li class="vazio">Nenhum registro neste filtro.</li>') +
        "</ul>" +
        '<div class="paginacao">' +
        '<button type="button" id="btn-anterior"' +
        (estado.pagina <= 1 ? " disabled" : "") +
        ">Anterior</button>" +
        "<span>P\u00e1gina " +
        estado.pagina +
        " de " +
        totalPag +
        " (" +
        filtrados.length +
        " registros)</span>" +
        '<button type="button" id="btn-proximo"' +
        (estado.pagina >= totalPag ? " disabled" : "") +
        ">Pr\u00f3xima</button>" +
        "</div>" +
        '<button type="button" class="btn-secundario" id="btn-limpar-votos" style="margin-top:12px;width:100%">Limpar filtro e ocultar lista</button>';
    }

    var rotuloSemVoto = ROTULO_SEM_VOTO_INDIVIDUAL || "voto individual nao registrado no SAPL";

    return (
      '<section class="secao" aria-labelledby="tit-votos">' +
      '<h2 id="tit-votos">Hist\u00f3rico de votos nominais</h2>' +
      '<p class="legenda">Voto nominal \u00e9 quando o nome de cada vereador fica registrado publicamente. Total: ' +
      esc(vo.total_registros) +
      " vota\u00e7\u00f5es em sess\u00f5es ordin\u00e1rias de " +
      ANO_ATUAL +
      ". " +
      esc(rotuloSemVoto) +
      ".</p>" +
      '<div class="votos-resumo">' +
      cards
        .map(function (c) {
          return (
            '<div class="voto-card"><div class="num">' +
            esc(c.num) +
            '</div><div class="rot">' +
            esc(c.rot) +
            "</div></div>"
          );
        })
        .join("") +
      "</div>" +
      '<div class="filtros-votos">' +
      '<label for="filtro-texto">Buscar por ementa ou n\u00famero da mat\u00e9ria</label>' +
      '<input type="search" id="filtro-texto" value="' +
      esc(estado.filtroTexto) +
      '" placeholder="Digite parte da ementa ou ID">' +
      '<label for="filtro-voto">Filtrar por tipo de voto</label>' +
      '<select id="filtro-voto"><option value="">Todos os tipos de voto</option>' +
      opcoesFiltro +
      "</select>" +
      "</div>" +
      htmlListaVotos +
      "</section>"
    );
  }
