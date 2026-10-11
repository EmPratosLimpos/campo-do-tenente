// Handler fino da votacao popular: D1, relogio, rede e cabecalhos.
//
// A logica pura (HMAC, autorizacao, ponto no poligono, validadores,
// percentuais, limites) esta em src/regras.js e e testada sem rede.
// Os dados da cidade (limites, siglas, contorno) vêm de src/dados_cidade.js,
// gerado de config_cidade.json. Nenhum numero, cidade, codigo IBGE ou
// endereco fixo aqui.
//
// Variaveis publicas (wrangler.toml): SITE_ORIGEM, RODADA_URL,
// TURNSTILE_SITE_KEY, RODADA_ID_LOCAL (reservada, ignorada pelo Worker),
// AMBIENTE ("teste" ou "producao").
// Segredos (so no cofre, nunca em arquivo): TURNSTILE_SECRET_KEY,
// HMAC_SECRET, MODO_TESTE_SECRETO.

import {
  MENSAGENS_ERRO,
  conferirAutorizacao,
  corpoLimiteExcedido,
  decidirLocalizacao,
  emitirAutorizacao,
  formatarMateriaResultado,
  hmacHex,
  janelaIndice,
  modoTestePularGps,
  rotuloAparelho,
  rotuloEndereco,
  rotuloTaxa,
  tentarDepoisS,
  validarFormaRodada,
  validarPedidoVerificar,
  validarRespostas,
} from "./regras.js";
import { DADOS_CIDADE } from "./dados_cidade.js";

const CABECALHO_MODO_TESTE = "X-Modo-Teste";
const URL_VERIFICAR_TURNSTILE =
  "https://challenges.cloudflare.com/turnstile/v0/siteverify";
// Unico lugar do codigo com o texto da chave do teto. O schema.sql repete o
// mesmo texto no trigger; ha teste que falha se os dois divergirem.
export const CHAVE_TETO = "teto_votos_por_endereco_por_rodada";
// A rotina agendada so apaga autorizacao vencida ha mais que esta margem,
// para nao apagar o jti de um voto que ainda esta em andamento.
const MARGEM_RETENCAO_AUTORIZACAO_S = 3600;
// Teto de corpo dos POST, antes de ler e interpretar o JSON.
const LIMITE_CORPO_BYTES = 32 * 1024;
// Acao do Turnstile que a tela envia no widget da votacao.
const ACAO_TURNSTILE = "votacao";

function limites() {
  return DADOS_CIDADE.limites;
}

function agoraS() {
  return Math.floor(Date.now() / 1000);
}

function agoraISO() {
  return new Date(agoraS() * 1000).toISOString();
}

// O endereco sai so de CF-Connecting-IP. Nada de X-Forwarded-For.
function enderecoDoPedido(request) {
  const direto = request.headers.get("CF-Connecting-IP") || "";
  return direto.trim();
}

// ---------------------------------------------------------------------------
// Respostas: CORS, seguranca, erros em pt-BR, sem dado pessoal
// ---------------------------------------------------------------------------

function origensPermitidas(env) {
  const lista = [];
  if (env.SITE_ORIGEM) {
    lista.push(env.SITE_ORIGEM);
  }
  if (env.AMBIENTE === "teste") {
    lista.push("http://localhost:8000", "http://127.0.0.1:8000");
  }
  return lista;
}

function origemResposta(request, env) {
  const origin = request.headers.get("Origin") || "";
  const permitidas = origensPermitidas(env);
  if (origin && permitidas.includes(origin)) {
    return origin;
  }
  return permitidas[0] || "";
}

function respostaJSON(request, env, corpo, status, cacheControl) {
  const headers = {
    "Content-Type": "application/json",
    "X-Content-Type-Options": "nosniff",
    "Vary": "Origin",
  };
  const origem = origemResposta(request, env);
  if (origem) {
    headers["Access-Control-Allow-Origin"] = origem;
  }
  headers["Cache-Control"] = cacheControl || "no-store";
  return new Response(JSON.stringify(corpo), { status, headers });
}

function erroCodigo(request, env, codigo, status) {
  return respostaJSON(
    request,
    env,
    { codigo, erro: MENSAGENS_ERRO[codigo] || MENSAGENS_ERRO.erro_interno },
    status,
    "no-store",
  );
}

function erroLimite(request, env, tentarDepois) {
  const corpo = corpoLimiteExcedido(tentarDepois);
  const resp = respostaJSON(request, env, corpo, 429, "no-store");
  resp.headers.set("Retry-After", String(tentarDepois));
  return resp;
}

function erroInterno(request, env) {
  return erroCodigo(request, env, "erro_interno", 500);
}

// Nunca registra segredo, endereco, coordenada ou aparelho.
function logLinha(fase, detalhe) {
  console.log(`[votacao] ${fase} ${detalhe}`);
}

// Erro interno no log: so rota, codigo interno curto e classe do erro.
// Nunca mensagem completa, pilha, IP, endereco, aparelho, hash, coordenada,
// jti, token ou segredo.
function logErro(rota, codigo, erro) {
  const tipo = erro && erro.name ? String(erro.name) : "desconhecido";
  console.error(`[votacao] erro rota=${rota} codigo=${codigo} tipo=${tipo}`);
}

// ---------------------------------------------------------------------------
// Limite de pedidos por HMAC do endereco
// ---------------------------------------------------------------------------

async function checarLimite(DB, segredo, endereco, rota, maxPedidos, janelaSegs, agora) {
  const chave = await hmacHex(segredo, rotuloTaxa(rota, endereco));
  const janela = janelaIndice(agora, janelaSegs);
  await DB.prepare(
    "INSERT INTO vp_taxa (endereco_hash, janela_minuto, contagem) VALUES (?, ?, 1) ON CONFLICT (endereco_hash, janela_minuto) DO UPDATE SET contagem = contagem + 1",
  )
    .bind(chave, janela)
    .run();
  const linha = await DB.prepare(
    "SELECT contagem FROM vp_taxa WHERE endereco_hash = ? AND janela_minuto = ?",
  )
    .bind(chave, janela)
    .first();
  if (linha && linha.contagem > maxPedidos) {
    return { bloqueado: true, tentarDepois: tentarDepoisS(agora, janelaSegs) };
  }
  return { bloqueado: false };
}

async function checarLimiteGeral(request, env, endereco, agora) {
  const lim = limites();
  return checarLimite(
    env.DB,
    env.HMAC_SECRET,
    endereco,
    "geral",
    lim.limite_geral_pedidos,
    lim.limite_geral_janela_s,
    agora,
  );
}

async function checarLimiteVotar(request, env, endereco, agora) {
  const lim = limites();
  return checarLimite(
    env.DB,
    env.HMAC_SECRET,
    endereco,
    "votar",
    lim.limite_votar_pedidos,
    lim.limite_votar_janela_s,
    agora,
  );
}

// ---------------------------------------------------------------------------
// Rodada: busca o JSON publico, registra no D1, nunca inventa rodada
// ---------------------------------------------------------------------------

function fechaAteS(dataSessao) {
  const base = Date.parse(`${dataSessao}T00:00:00Z`);
  if (!Number.isFinite(base)) {
    return null;
  }
  return Math.floor(base / 1000) + DADOS_CIDADE.dias_maximos_rodada * 86400;
}

async function buscarRodadaPublica(env) {
  if (!env.RODADA_URL) {
    return null;
  }
  try {
    const resp = await fetch(env.RODADA_URL, { cf: { cacheTtl: 60 } });
    if (!resp || !resp.ok) {
      return null;
    }
    const obj = await resp.json();
    const conf = validarFormaRodada(obj, DADOS_CIDADE.siglas_elegiveis);
    if (!conf.ok) {
      return null;
    }
    return obj;
  } catch (e) {
    logErro("rodada", "rodada_busca", e);
    return null;
  }
}

async function lerRodadaAbertaD1(DB) {
  const linha = await DB.prepare(
    "SELECT rodada_id, sessao_id, data_sessao, status, criada_em, fechada_em FROM vp_rodadas WHERE status = 'aberta' ORDER BY criada_em DESC LIMIT 1",
  ).first();
  return linha || null;
}

async function lerMateriasD1(DB, rodadaId) {
  const resto = await DB.prepare(
    "SELECT materia_id, sigla, numero, ano, ordem_pauta, ementa, link_sapl FROM vp_materias WHERE rodada_id = ? ORDER BY ordem_pauta ASC, materia_id ASC",
  )
    .bind(rodadaId)
    .all();
  return (resto.results || []).map((m) => ({
    id: m.materia_id,
    sigla: m.sigla,
    numero: m.numero,
    ano: m.ano,
    ordem_pauta: m.ordem_pauta,
    ementa: m.ementa,
    link_sapl: m.link_sapl,
  }));
}

async function fecharRodadaD1(DB, rodadaId, agoraIso) {
  await DB.prepare(
    "UPDATE vp_rodadas SET status = 'fechada', fechada_em = ? WHERE rodada_id = ?",
  )
    .bind(agoraIso, rodadaId)
    .run();
}

// Devolve a declaracao que grava o teto atual em vp_config. Ela e a primeira
// instrucao do proprio batch do voto, para o trigger do teto ler dentro da
// mesma transacao. A chave vai como parametro, a partir de CHAVE_TETO.
function declaracaoConfigTeto(DB) {
  return DB.prepare(
    "INSERT INTO vp_config (chave, valor) VALUES (?, ?) ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
  ).bind(CHAVE_TETO, String(limites().teto_votos_por_endereco_por_rodada));
}

// Devolve { estado: "aberta", rodada } ou { estado: "fechada" | "sem_materias", rodadaId }.
async function sincronizarRodada(env, agora) {
  const agoraIso = new Date(agora * 1000).toISOString();
  const publica = await buscarRodadaPublica(env);

  if (publica && publica.status === "sem_materias_elegiveis") {
    return { estado: "sem_materias", rodadaId: publica.rodada_id };
  }

  if (publica && publica.status === "aberta") {
    const existente = await env.DB.prepare(
      "SELECT rodada_id, sessao_id, data_sessao, status, criada_em, fechada_em FROM vp_rodadas WHERE rodada_id = ?",
    )
      .bind(publica.rodada_id)
      .first();
    if (!existente) {
      const lote = [
        env.DB.prepare(
          "UPDATE vp_rodadas SET status = 'fechada', fechada_em = ? WHERE status = 'aberta' AND rodada_id != ?",
        ).bind(agoraIso, publica.rodada_id),
        env.DB.prepare(
          "INSERT OR IGNORE INTO vp_rodadas (rodada_id, sessao_id, data_sessao, status, criada_em, fechada_em) VALUES (?, ?, ?, 'aberta', ?, NULL)",
        ).bind(
          publica.rodada_id,
          publica.sessao_id,
          publica.data_sessao,
          agoraIso,
        ),
      ];
      for (const materia of publica.materias) {
        lote.push(
          env.DB.prepare(
            "INSERT OR IGNORE INTO vp_materias (rodada_id, materia_id, sigla, numero, ano, ordem_pauta, ementa, link_sapl) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
          ).bind(
            publica.rodada_id,
            materia.id,
            materia.sigla,
            String(materia.numero ?? ""),
            String(materia.ano ?? ""),
            materia.ordem_pauta ?? materia.id,
            materia.ementa ?? "",
            materia.link_sapl ?? "",
          ),
        );
        lote.push(
          env.DB.prepare(
            "INSERT OR IGNORE INTO vp_totais (rodada_id, materia_id, total_util, total_inutil) VALUES (?, ?, 0, 0)",
          ).bind(publica.rodada_id, materia.id),
        );
      }
      await env.DB.batch(lote);
    }
    // Rodada que ja esta com status diferente de aberta no D1 nunca volta a
    // ser servida como aberta, mesmo que o arquivo publico (ou o cache dele)
    // ainda diga aberta.
    if (existente && existente.status !== "aberta") {
      return { estado: "fechada", rodadaId: publica.rodada_id };
    }
    const limiteIdade = fechaAteS(publica.data_sessao);
    if (limiteIdade !== null && agora > limiteIdade) {
      await fecharRodadaD1(env.DB, publica.rodada_id, agoraIso);
      return { estado: "fechada", rodadaId: publica.rodada_id };
    }
    const materias = await lerMateriasD1(env.DB, publica.rodada_id);
    return {
      estado: "aberta",
      rodada: {
        rodada_id: publica.rodada_id,
        sessao_id: publica.sessao_id,
        data_sessao: publica.data_sessao,
        status: "aberta",
        materias,
      },
    };
  }

  // Arquivo fora do ar ou invalido: usa a ultima do D1 se ainda aberta.
  const aberta = await lerRodadaAbertaD1(env.DB);
  if (!aberta) {
    return { estado: "fechada", rodadaId: null };
  }
  const limiteIdade = fechaAteS(aberta.data_sessao);
  if (limiteIdade !== null && agora > limiteIdade) {
    await fecharRodadaD1(env.DB, aberta.rodada_id, agoraIso);
    return { estado: "fechada", rodadaId: aberta.rodada_id };
  }
  const materias = await lerMateriasD1(env.DB, aberta.rodada_id);
  return {
    estado: "aberta",
    rodada: {
      rodada_id: aberta.rodada_id,
      sessao_id: aberta.sessao_id,
      data_sessao: aberta.data_sessao,
      status: "aberta",
      materias,
    },
  };
}

// ---------------------------------------------------------------------------
// Turnstile no servidor
// ---------------------------------------------------------------------------

// Hosts aceitos na resposta do siteverify: o host de SITE_ORIGEM e, so no
// ambiente de teste, localhost e 127.0.0.1.
function hostsTurnstileEsperados(env) {
  const lista = [];
  try {
    if (env.SITE_ORIGEM) {
      lista.push(new URL(env.SITE_ORIGEM).hostname);
    }
  } catch {
    // SITE_ORIGEM invalida: nenhum host passa.
  }
  if (env.AMBIENTE === "teste") {
    lista.push("localhost", "127.0.0.1");
  }
  return lista;
}

async function verificarTurnstile(token, segredo, endereco, env) {
  if (!token || !segredo) {
    return false;
  }
  try {
    const resp = await fetch(URL_VERIFICAR_TURNSTILE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        secret: segredo,
        response: token,
        remoteip: endereco,
      }),
    });
    const json = await resp.json();
    if (!(json && json.success)) {
      return false;
    }
    if (
      typeof json.hostname !== "string" ||
      !hostsTurnstileEsperados(env).includes(json.hostname)
    ) {
      return false;
    }
    if (json.action !== undefined && json.action !== ACAO_TURNSTILE) {
      return false;
    }
    return true;
  } catch (e) {
    logErro("verificar", "turnstile_rede", e);
    return false;
  }
}

// Recusa cedo, antes de ler o corpo: Content-Length anunciado acima do teto.
function corpoAnunciadoGrande(request) {
  const anunciado = Number(request.headers.get("Content-Length"));
  return Number.isFinite(anunciado) && anunciado > LIMITE_CORPO_BYTES;
}

// Le o corpo como texto, recusa acima do teto e interpreta o JSON.
async function lerCorpoJSON(request) {
  const texto = await request.text();
  if (texto.length > LIMITE_CORPO_BYTES) {
    return { grande: true };
  }
  try {
    return { corpo: JSON.parse(texto) };
  } catch {
    return { invalido: true };
  }
}

// ---------------------------------------------------------------------------
// Rotas
// ---------------------------------------------------------------------------

async function rotaRodada(request, env) {
  const agora = agoraS();
  const endereco = enderecoDoPedido(request);
  if (!endereco) {
    return erroCodigo(request, env, "pedido_invalido", 400);
  }
  try {
    const geral = await checarLimiteGeral(request, env, endereco, agora);
    if (geral.bloqueado) {
      return erroLimite(request, env, geral.tentarDepois);
    }
    const sinc = await sincronizarRodada(env, agora);
    if (sinc.estado !== "aberta") {
      const status =
        sinc.estado === "sem_materias" ? "sem_materias_elegiveis" : "fechada";
      return respostaJSON(
        request,
        env,
        { rodada_id: sinc.rodadaId || null, status, materias: [] },
        200,
        "no-store",
      );
    }
    logLinha("rodada", `aberta ${sinc.rodada.rodada_id}`);
    return respostaJSON(request, env, sinc.rodada, 200, "no-store");
  } catch (e) {
    logErro("rodada", "rodada_erro", e);
    return erroInterno(request, env);
  }
}

async function rotaVerificar(request, env) {
  const agora = agoraS();
  const endereco = enderecoDoPedido(request);
  if (!endereco) {
    return erroCodigo(request, env, "pedido_invalido", 400);
  }
  try {
    const geral = await checarLimiteGeral(request, env, endereco, agora);
    if (geral.bloqueado) {
      return erroLimite(request, env, geral.tentarDepois);
    }

    if (corpoAnunciadoGrande(request)) {
      return erroCodigo(request, env, "corpo_grande", 413);
    }
    let corpo;
    try {
      const lido = await lerCorpoJSON(request);
      if (lido.grande) {
        return erroCodigo(request, env, "corpo_grande", 413);
      }
      if (lido.invalido) {
        return erroCodigo(request, env, "pedido_invalido", 400);
      }
      corpo = lido.corpo;
    } catch {
      return erroCodigo(request, env, "pedido_invalido", 400);
    }
    const aparelhoId = corpo ? corpo.aparelho_id : "";

    const pularGps = modoTestePularGps({
      ambiente: env.AMBIENTE,
      cabecalhoValor: request.headers.get(CABECALHO_MODO_TESTE) || "",
      segredo: env.MODO_TESTE_SECRETO || "",
    });

    if (pularGps) {
      if (typeof aparelhoId !== "string" || !aparelhoId.trim()) {
        return erroCodigo(request, env, "pedido_invalido", 400);
      }
    } else {
      const invalido = validarPedidoVerificar({
        aparelhoId,
        lat: corpo ? corpo.lat : null,
        lon: corpo ? corpo.lon : null,
        precisaoM: corpo ? corpo.precisao_m : null,
      });
      if (invalido) {
        return erroCodigo(request, env, invalido, 400);
      }
    }

    const captchaOk = await verificarTurnstile(
      corpo ? corpo.turnstile_token : "",
      env.TURNSTILE_SECRET_KEY,
      endereco,
      env,
    );
    if (!captchaOk) {
      return erroCodigo(request, env, "captcha_invalido", 400);
    }

    let dentro = false;
    if (!pularGps) {
      const decisao = decidirLocalizacao({
        lat: corpo.lat,
        lon: corpo.lon,
        precisaoM: corpo.precisao_m,
        contorno: DADOS_CIDADE.contorno,
        precisaoMaxM: limites().precisao_gps_max_m,
        margemM: limites().margem_divisa_m,
      });
      if (!decisao.dentro) {
        return erroCodigo(request, env, decisao.codigo, 400);
      }
      dentro = true;
    } else {
      dentro = true;
    }

    const sinc = await sincronizarRodada(env, agora);
    if (sinc.estado !== "aberta") {
      const codigo =
        sinc.estado === "sem_materias" ? "rodada_sem_materias" : "rodada_fechada";
      return erroCodigo(request, env, codigo, 400);
    }
    const rodadaId = sinc.rodada.rodada_id;

    const aparelhoHash = await hmacHex(
      env.HMAC_SECRET,
      rotuloAparelho(rodadaId, aparelhoId),
    );
    const enderecoHash = await hmacHex(
      env.HMAC_SECRET,
      rotuloEndereco(rodadaId, endereco),
    );

    const votou = await env.DB.prepare(
      "SELECT rodada_id FROM vp_participacoes WHERE rodada_id = ? AND aparelho_hash = ? LIMIT 1",
    )
      .bind(rodadaId, aparelhoHash)
      .first();
    if (votou) {
      return erroCodigo(request, env, "ja_votou", 409);
    }

    const contagem = await env.DB.prepare(
      "SELECT COUNT(*) AS total FROM vp_participacoes WHERE rodada_id = ? AND endereco_hash = ?",
    )
      .bind(rodadaId, enderecoHash)
      .first();
    if (
      contagem &&
      contagem.total >= limites().teto_votos_por_endereco_por_rodada
    ) {
      return erroCodigo(request, env, "teto_endereco", 409);
    }

    const jti = crypto.randomUUID();
    const token = await emitirAutorizacao({
      segredo: env.HMAC_SECRET,
      rodadaId,
      aparelhoHash,
      dentro,
      agoraS: agora,
      validadeMin: limites().validade_autorizacao_min,
      jti,
    });
    await env.DB.prepare(
      "INSERT INTO vp_autorizacoes (jti, rodada_id, aparelho_hash, expira_em, usada) VALUES (?, ?, ?, ?, 0)",
    )
      .bind(jti, rodadaId, aparelhoHash, agora + limites().validade_autorizacao_min * 60)
      .run();

    logLinha("verificar", `autorizacao emitida rodada=${rodadaId}`);
    return respostaJSON(
      request,
      env,
      {
        ok: true,
        rodada_id: rodadaId,
        autorizacao: token,
        dentro_do_municipio: dentro,
        ja_votou: false,
      },
      200,
      "no-store",
    );
  } catch (e) {
    logErro("verificar", "verificar_erro", e);
    return erroInterno(request, env);
  }
}

function mapearErroBatch(mensagem) {
  const texto = String((mensagem && mensagem.message) || mensagem || "");
  if (texto.includes("teto_endereco")) {
    return "teto_endereco";
  }
  if (texto.includes("autorizacao_reutilizada")) {
    return "autorizacao_reutilizada";
  }
  if (texto.includes("autorizacao_invalida")) {
    return "autorizacao_invalida";
  }
  if (texto.includes("UNIQUE constraint failed")) {
    return "ja_votou";
  }
  return "erro_interno";
}

async function rotaVotar(request, env) {
  const agora = agoraS();
  const endereco = enderecoDoPedido(request);
  if (!endereco) {
    return erroCodigo(request, env, "pedido_invalido", 400);
  }
  try {
    const geral = await checarLimiteGeral(request, env, endereco, agora);
    if (geral.bloqueado) {
      return erroLimite(request, env, geral.tentarDepois);
    }
    const proprio = await checarLimiteVotar(request, env, endereco, agora);
    if (proprio.bloqueado) {
      return erroLimite(request, env, proprio.tentarDepois);
    }

    if (corpoAnunciadoGrande(request)) {
      return erroCodigo(request, env, "corpo_grande", 413);
    }
    let corpo;
    try {
      const lido = await lerCorpoJSON(request);
      if (lido.grande) {
        return erroCodigo(request, env, "corpo_grande", 413);
      }
      if (lido.invalido) {
        return erroCodigo(request, env, "pedido_invalido", 400);
      }
      corpo = lido.corpo;
    } catch {
      return erroCodigo(request, env, "pedido_invalido", 400);
    }

    const conf = await conferirAutorizacao(
      corpo ? corpo.autorizacao : "",
      env.HMAC_SECRET,
      agora,
    );
    if (!conf.ok) {
      return erroCodigo(request, env, "autorizacao_invalida", 400);
    }

    const sinc = await sincronizarRodada(env, agora);
    if (sinc.estado !== "aberta") {
      return erroCodigo(request, env, "rodada_fechada", 400);
    }
    const rodada = sinc.rodada;
    if (conf.payload.rodada !== rodada.rodada_id) {
      return erroCodigo(request, env, "autorizacao_invalida", 400);
    }

    const aparelhoId = corpo ? corpo.aparelho_id : "";
    if (typeof aparelhoId !== "string" || !aparelhoId) {
      return erroCodigo(request, env, "pedido_invalido", 400);
    }
    const aparelhoHash = await hmacHex(
      env.HMAC_SECRET,
      rotuloAparelho(rodada.rodada_id, aparelhoId),
    );
    if (aparelhoHash !== conf.payload.h_aparelho) {
      return erroCodigo(request, env, "autorizacao_invalida", 400);
    }

    const invalido = validarRespostas(
      corpo ? corpo.respostas : null,
      rodada.materias,
    );
    if (invalido) {
      return erroCodigo(request, env, invalido, 400);
    }

    const enderecoHash = await hmacHex(
      env.HMAC_SECRET,
      rotuloEndereco(rodada.rodada_id, endereco),
    );

    // Batch em uma transacao so, nesta ordem: teto atual, marcar a
    // autorizacao como usada, inserir a participacao com o jti, inserir os
    // votos, somar os totais. O trigger da autorizacao aborta o batch antes
    // de qualquer gravacao quando o jti nao existe, ainda nao foi marcado,
    // venceu e foi apagado, ou e de outra rodada ou aparelho.
    const lote = [
      declaracaoConfigTeto(env.DB),
      env.DB.prepare(
        "UPDATE vp_autorizacoes SET usada = 1 WHERE jti = ?",
      ).bind(conf.payload.jti),
      env.DB.prepare(
        "INSERT INTO vp_participacoes (rodada_id, aparelho_hash, endereco_hash, criada_em, jti) VALUES (?, ?, ?, ?, ?)",
      ).bind(rodada.rodada_id, aparelhoHash, enderecoHash, agoraISO(), conf.payload.jti),
    ];
    for (const resposta of corpo.respostas) {
      lote.push(
        env.DB.prepare(
          "INSERT INTO vp_votos (rodada_id, materia_id, aparelho_hash, valor) VALUES (?, ?, ?, ?)",
        ).bind(rodada.rodada_id, resposta.materia_id, aparelhoHash, resposta.valor),
      );
    }
    for (const resposta of corpo.respostas) {
      lote.push(
        env.DB.prepare(
          "UPDATE vp_totais SET total_util = total_util + ?, total_inutil = total_inutil + ? WHERE rodada_id = ? AND materia_id = ?",
        ).bind(
          resposta.valor === "util" ? 1 : 0,
          resposta.valor === "inutil" ? 1 : 0,
          rodada.rodada_id,
          resposta.materia_id,
        ),
      );
    }

    let resultados;
    try {
      resultados = await env.DB.batch(lote);
    } catch (e) {
      const codigo = mapearErroBatch(e);
      if (codigo === "erro_interno") {
        logErro("votar", "d1_batch", e);
        return erroInterno(request, env);
      }
      const status = codigo === "ja_votou" || codigo === "teto_endereco" || codigo === "autorizacao_reutilizada" ? 409 : 400;
      return erroCodigo(request, env, codigo, status);
    }
    // Defesa extra: a protecao real contra jti invalido e o trigger dentro
    // do batch. Aqui so se confere que o UPDATE da autorizacao (segunda
    // instrucao, depois do upsert do teto) alterou exatamente uma linha.
    if (!resultados || !resultados[1] || resultados[1].meta.changes !== 1) {
      return erroCodigo(request, env, "autorizacao_invalida", 400);
    }

    logLinha("votar", `voto gravado rodada=${rodada.rodada_id}`);
    return respostaJSON(
      request,
      env,
      { ok: true, rodada_id: rodada.rodada_id },
      200,
      "no-store",
    );
  } catch (e) {
    logErro("votar", "votar_erro", e);
    return erroInterno(request, env);
  }
}

async function rotaResultados(request, env, url) {
  const agora = agoraS();
  const endereco = enderecoDoPedido(request);
  if (!endereco) {
    return erroCodigo(request, env, "pedido_invalido", 400);
  }
  try {
    const geral = await checarLimiteGeral(request, env, endereco, agora);
    if (geral.bloqueado) {
      return erroLimite(request, env, geral.tentarDepois);
    }

    const temCache = typeof caches !== "undefined" && caches.default;
    const chaveCache = new Request(url.toString(), { method: "GET" });
    if (temCache) {
      const achado = await caches.default.match(chaveCache);
      if (achado) {
        return achado;
      }
    }

    await sincronizarRodada(env, agora);
    const resto = await env.DB.prepare(
      "SELECT rodada_id, status FROM vp_rodadas ORDER BY criada_em DESC",
    ).all();
    const minimo = limites().minimo_respostas_por_materia;
    const rodadas = [];
    for (const linha of resto.results || []) {
      const totais = await env.DB.prepare(
        "SELECT materia_id, total_util, total_inutil FROM vp_totais WHERE rodada_id = ?",
      )
        .bind(linha.rodada_id)
        .all();
      rodadas.push({
        rodada_id: linha.rodada_id,
        status: linha.status,
        materias: (totais.results || [])
          .slice()
          .sort((a, b) => a.materia_id - b.materia_id)
          .map((t) =>
            formatarMateriaResultado({
              materiaId: t.materia_id,
              util: t.total_util,
              inutil: t.total_inutil,
              minimo,
            }),
          ),
      });
    }
    const corpo = {
      atualizado_em: new Date(agora * 1000).toISOString(),
      rodadas,
    };
    const resp = respostaJSON(request, env, corpo, 200, "public, max-age=600");
    if (temCache) {
      await caches.default.put(
        chaveCache,
        resp.clone(),
      );
    }
    return resp;
  } catch (e) {
    logErro("resultados", "resultados_erro", e);
    return erroInterno(request, env);
  }
}

// ---------------------------------------------------------------------------
// Rotina agendada: apaga identificadores velhos, mantem totais
// ---------------------------------------------------------------------------

async function rotinaRetencao(env, agora) {
  const corte = new Date(
    (agora - limites().retencao_identificadores_dias * 86400) * 1000,
  ).toISOString();
  const velhas = await env.DB.prepare(
    "SELECT rodada_id FROM vp_rodadas WHERE status = 'fechada' AND fechada_em IS NOT NULL AND fechada_em < ?",
  )
    .bind(corte)
    .all();
  for (const linha of velhas.results || []) {
    await env.DB.prepare("DELETE FROM vp_participacoes WHERE rodada_id = ?")
      .bind(linha.rodada_id)
      .run();
    await env.DB.prepare("DELETE FROM vp_votos WHERE rodada_id = ?")
      .bind(linha.rodada_id)
      .run();
    await env.DB.prepare("DELETE FROM vp_autorizacoes WHERE rodada_id = ?")
      .bind(linha.rodada_id)
      .run();
  }
  // So apaga autorizacao vencida ha mais que a margem, para nao apagar o
  // jti de um voto que ainda esta em andamento e passar a recusar esse voto.
  await env.DB.prepare("DELETE FROM vp_autorizacoes WHERE expira_em <= ?")
    .bind(agora - MARGEM_RETENCAO_AUTORIZACAO_S)
    .run();
  const janelaAtual = janelaIndice(agora, limites().limite_geral_janela_s);
  await env.DB.prepare("DELETE FROM vp_taxa WHERE janela_minuto < ?")
    .bind(janelaAtual - 2)
    .run();
  return (velhas.results || []).length;
}

// ---------------------------------------------------------------------------
// Entradas do Worker
// ---------------------------------------------------------------------------

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const rota = url.pathname;

    if (request.method === "OPTIONS") {
      const origem = origemResposta(request, env);
      const headers = {
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Modo-Teste",
        "Access-Control-Max-Age": "86400",
        "X-Content-Type-Options": "nosniff",
        "Vary": "Origin",
      };
      if (origem) {
        headers["Access-Control-Allow-Origin"] = origem;
      }
      return new Response(null, { status: 204, headers });
    }

    try {
      if (rota === "/api/rodada" && request.method === "GET") {
        return await rotaRodada(request, env);
      }
      if (rota === "/api/verificar" && request.method === "POST") {
        return await rotaVerificar(request, env);
      }
      if (rota === "/api/votar" && request.method === "POST") {
        return await rotaVotar(request, env);
      }
      if (rota === "/api/resultados" && request.method === "GET") {
        return await rotaResultados(request, env, url);
      }
      return erroCodigo(request, env, "pedido_invalido", 404);
    } catch (e) {
      logErro("roteador", "roteador_erro", e);
      return erroInterno(request, env);
    }
  },

  async scheduled(event, env, ctx) {
    try {
      const total = await rotinaRetencao(env, agoraS());
      logLinha("retencao", `rodadas limpas=${total}`);
    } catch (e) {
      logErro("retencao", "retencao_erro", e);
      logLinha("retencao", "falha na limpeza");
    }
  },
};
