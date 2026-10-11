import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DatabaseSync } from "node:sqlite";
import handler, { CHAVE_TETO } from "../src/index.js";
import { DADOS_CIDADE } from "../src/dados_cidade.js";
import { hmacHex, rotuloAparelho, rotuloEndereco } from "../src/regras.js";

// ---------------------------------------------------------------------------
// SQLite real (node:sqlite, mesmo motor do D1) com o schema.sql de verdade.
// Adaptador minimo com a interface do D1: prepare/bind/first/all/run e
// batch em transacao BEGIN/COMMIT com ROLLBACK em erro.
// ---------------------------------------------------------------------------

class DeclaracaoReal {
  constructor(banco, sql) {
    this.banco = banco;
    this.sql = sql;
    this.params = [];
  }
  bind(...params) {
    this.params = params;
    return this;
  }
  async first() {
    const linha = this.banco.prepare(this.sql).get(...this.params);
    return linha === undefined ? null : { ...linha };
  }
  async all() {
    return {
      results: this.banco.prepare(this.sql).all(...this.params).map((r) => ({ ...r })),
    };
  }
  async run() {
    const info = this.banco.prepare(this.sql).run(...this.params);
    return { success: true, meta: { changes: Number(info.changes) } };
  }
}

class D1Real {
  constructor() {
    this.banco = new DatabaseSync(":memory:");
    const schema = readFileSync(new URL("../schema.sql", import.meta.url), "utf-8");
    this.banco.exec(schema);
  }
  prepare(sql) {
    return new DeclaracaoReal(this.banco, sql);
  }
  async batch(declaracoes) {
    this.banco.exec("BEGIN");
    const saidas = [];
    try {
      for (const d of declaracoes) {
        saidas.push(await d.run());
      }
    } catch (e) {
      this.banco.exec("ROLLBACK");
      throw e;
    }
    this.banco.exec("COMMIT");
    return saidas;
  }
  async contar(tabela, onde, ...params) {
    const linha = await this.prepare(
      `SELECT COUNT(*) AS total FROM ${tabela} WHERE ${onde}`,
    ).bind(...params).first();
    return linha ? linha.total : 0;
  }
  async somarTotais(rodadaId) {
    const resto = await this.prepare(
      "SELECT total_util, total_inutil FROM vp_totais WHERE rodada_id = ?",
    ).bind(rodadaId).all();
    let soma = 0;
    for (const linha of resto.results || []) {
      soma += linha.total_util + linha.total_inutil;
    }
    return soma;
  }
}

// ---------------------------------------------------------------------------
// Apoio aos testes (mesmo desenho do handler.test.js, com banco real)
// ---------------------------------------------------------------------------

const REAL_FETCH = global.fetch;
const REAL_NOW = Date.now;
const SEGREDO_HMAC = "segredo-falso-hmac-gerado-neste-teste-99";
const IP_BASE = "203.0.113.";
const LAT_DENTRO = -25.9778;
const LON_DENTRO = -49.6564;

function rodadaFalsa(id) {
  const sigla = DADOS_CIDADE.siglas_elegiveis[0];
  return {
    rodada_id: `sessao:${id}`,
    sessao_id: id,
    data_sessao: "2026-10-06",
    status: "aberta",
    materias: [
      { id: id * 10 + 1, sigla, numero: "1", ano: "2026", ementa: "Ementa falsa um.", link_sapl: "https://exemplo.falso/materia/1", ordem_pauta: 1 },
      { id: id * 10 + 2, sigla, numero: "2", ano: "2026", ementa: "Ementa falsa dois.", link_sapl: "https://exemplo.falso/materia/2", ordem_pauta: 2 },
    ],
  };
}

const MS_BASE = Date.parse("2026-10-20T12:00:00Z");

function montarMundoReal({ ambiente = "teste", rodada = rodadaFalsa(900) } = {}) {
  const db = new D1Real();
  const rede = {
    turnstile: { success: true, hostname: "site.falso", action: "votacao" },
    rodada,
  };
  global.fetch = async (url, opts) => {
    void opts;
    const texto = String(url);
    if (texto.includes("siteverify")) {
      return { ok: true, json: async () => rede.turnstile };
    }
    if (texto === "https://site.falso/dados/tratados/votacao_rodada.json") {
      if (rede.rodada === null) {
        throw new Error("rede falsa fora do ar");
      }
      return { ok: true, json: async () => rede.rodada };
    }
    throw new Error(`fetch falso: url inesperada ${texto}`);
  };
  const env = {
    DB: db,
    SITE_ORIGEM: "https://site.falso",
    RODADA_URL: "https://site.falso/dados/tratados/votacao_rodada.json",
    TURNSTILE_SITE_KEY: "site-falsa",
    RODADA_ID_LOCAL: "",
    AMBIENTE: ambiente,
    TURNSTILE_SECRET_KEY: "segredo-falso-turnstile-xyz",
    HMAC_SECRET: SEGREDO_HMAC,
    MODO_TESTE_SECRETO: "modo-falso-abc123",
  };
  return { db, env, rede };
}

function pedido(rota, { metodo = "GET", corpo = null, corpoTexto = null, ip = `${IP_BASE}7`, origin = "https://site.falso", extras = {} } = {}) {
  const headers = {
    "Content-Type": "application/json",
    "CF-Connecting-IP": ip,
    Origin: origin,
    ...extras,
  };
  const body = corpoTexto !== null ? corpoTexto : corpo === null ? undefined : JSON.stringify(corpo);
  return new Request(`https://worker.falso${rota}`, {
    metodo,
    method: metodo,
    headers,
    body,
  });
}

async function corpoJSON(resp) {
  return resp.json();
}

async function verificarEVotar(mundo, { aparelho, ip, lat = LAT_DENTRO, lon = LON_DENTRO, precisao = 20, valores = ["util", "inutil"] }) {
  const { env } = mundo;
  const r1 = await handler.fetch(
    pedido("/api/verificar", {
      metodo: "POST",
      corpo: { turnstile_token: "token-falso", aparelho_id: aparelho, lat, lon, precisao_m: precisao },
      ip,
    }),
    env,
    {},
  );
  const j1 = await corpoJSON(r1);
  assert.equal(r1.status, 200, JSON.stringify(j1));
  const materias = mundo.rede.rodada.materias;
  const r2 = await handler.fetch(
    pedido("/api/votar", {
      metodo: "POST",
      corpo: {
        autorizacao: j1.autorizacao,
        aparelho_id: aparelho,
        respostas: materias.map((m, i) => ({ materia_id: m.id, valor: valores[i % valores.length] })),
      },
      ip,
    }),
    env,
    {},
  );
  const j2 = await corpoJSON(r2);
  return { verificar: j1, votarStatus: r2.status, votar: j2 };
}

async function soVerificar(mundo, { aparelho, ip }) {
  const r = await handler.fetch(
    pedido("/api/verificar", {
      metodo: "POST",
      corpo: { turnstile_token: "token-falso", aparelho_id: aparelho, lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
      ip,
    }),
    mundo.env,
    {},
  );
  return { status: r.status, corpo: await corpoJSON(r) };
}

async function soVotar(mundo, { token, aparelho, ip }) {
  const materias = mundo.rede.rodada.materias.map((m) => ({ materia_id: m.id, valor: "util" }));
  const r = await handler.fetch(
    pedido("/api/votar", {
      metodo: "POST",
      corpo: { autorizacao: token, aparelho_id: aparelho, respostas: materias },
      ip,
    }),
    mundo.env,
    {},
  );
  return { status: r.status, corpo: await corpoJSON(r) };
}

before(() => {
  Date.now = () => MS_BASE;
});

after(() => {
  Date.now = REAL_NOW;
  global.fetch = REAL_FETCH;
});

// ---------------------------------------------------------------------------
// Chave do teto: um lugar so no codigo, igual ao schema
// ---------------------------------------------------------------------------

describe("chave do teto", () => {
  it("texto no schema.sql igual a constante CHAVE_TETO", () => {
    const schema = readFileSync(new URL("../schema.sql", import.meta.url), "utf-8");
    assert.ok(CHAVE_TETO, "CHAVE_TETO nao exportada por src/index.js");
    assert.ok(
      schema.includes(`chave = '${CHAVE_TETO}'`),
      "schema.sql com chave diferente de CHAVE_TETO",
    );
  });
});

// ---------------------------------------------------------------------------
// Voto valido e autorizacao invalida dentro da transacao (A1)
// ---------------------------------------------------------------------------

describe("voto no SQLite real", () => {
  it("voto valido grava participacao, votos e totais", async () => {
    const mundo = montarMundoReal();
    const fluxo = await verificarEVotar(mundo, { aparelho: "ap-real-1", ip: `${IP_BASE}11` });
    assert.equal(fluxo.votarStatus, 200);
    const rodadaId = mundo.rede.rodada.rodada_id;
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", rodadaId), 1);
    assert.equal(await mundo.db.contar("vp_votos", "rodada_id = ?", rodadaId), 2);
    assert.equal(await mundo.db.somarTotais(rodadaId), 2);
  });

  it("jti inexistente: 400 e ZERO linhas gravadas", async () => {
    const mundo = montarMundoReal();
    const { env } = mundo;
    const rodadaId = mundo.rede.rodada.rodada_id;
    const v = await soVerificar(mundo, { aparelho: "ap-real-2", ip: `${IP_BASE}12` });
    assert.equal(v.status, 200);
    const antes = await mundo.db.somarTotais(rodadaId);
    const linha = await env.DB.prepare(
      "SELECT jti FROM vp_autorizacoes WHERE rodada_id = ?",
    ).bind(rodadaId).first();
    assert.ok(linha && linha.jti, "jti nao gravado na verificacao");
    await env.DB.prepare("DELETE FROM vp_autorizacoes WHERE jti = ?").bind(linha.jti).run();
    const r = await soVotar(mundo, { token: v.corpo.autorizacao, aparelho: "ap-real-2", ip: `${IP_BASE}12` });
    assert.equal(r.status, 400);
    assert.equal(r.corpo.codigo, "autorizacao_invalida");
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", rodadaId), 0);
    assert.equal(await mundo.db.contar("vp_votos", "rodada_id = ?", rodadaId), 0);
    assert.equal(await mundo.db.somarTotais(rodadaId), antes);
  });

  it("autorizacao reutilizada: 409 e nada somado a mais", async () => {
    const mundo = montarMundoReal();
    const rodadaId = mundo.rede.rodada.rodada_id;
    const fluxo = await verificarEVotar(mundo, { aparelho: "ap-real-3", ip: `${IP_BASE}13` });
    assert.equal(fluxo.votarStatus, 200);
    const antes = await mundo.db.somarTotais(rodadaId);
    assert.equal(antes, 2);
    const r = await soVotar(mundo, { token: fluxo.verificar.autorizacao, aparelho: "ap-real-3", ip: `${IP_BASE}13` });
    assert.equal(r.status, 409);
    assert.equal(r.corpo.codigo, "autorizacao_reutilizada");
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", rodadaId), 1);
    assert.equal(await mundo.db.contar("vp_votos", "rodada_id = ?", rodadaId), 2);
    assert.equal(await mundo.db.somarTotais(rodadaId), antes);
  });

  it("mesmo aparelho duas vezes: ja_votou e nada duplicado", async () => {
    const mundo = montarMundoReal();
    const rodadaId = mundo.rede.rodada.rodada_id;
    const fluxo = await verificarEVotar(mundo, { aparelho: "ap-real-4", ip: `${IP_BASE}14` });
    assert.equal(fluxo.votarStatus, 200);
    const r = await soVerificar(mundo, { aparelho: "ap-real-4", ip: `${IP_BASE}14` });
    assert.equal(r.status, 409);
    assert.equal(r.corpo.codigo, "ja_votou");
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", rodadaId), 1);
  });
});

// ---------------------------------------------------------------------------
// Teto por endereco no SQLite real, com falha fechada (M1)
// ---------------------------------------------------------------------------

describe("teto no SQLite real", () => {
  it("ate o teto passa, o seguinte e recusado pelo trigger", async () => {
    const mundo = montarMundoReal();
    const { env } = mundo;
    const rodadaId = mundo.rede.rodada.rodada_id;
    const teto = DADOS_CIDADE.limites.teto_votos_por_endereco_por_rodada;
    const ip = `${IP_BASE}21`;
    const agora = Math.floor(MS_BASE / 1000);
    const enderecoHash = await hmacHex(SEGREDO_HMAC, rotuloEndereco(rodadaId, ip));
    await env.DB.prepare(
      "INSERT INTO vp_config (chave, valor) VALUES (?, ?) ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
    ).bind(CHAVE_TETO, String(teto)).run();
    for (let i = 0; i < teto - 1; i += 1) {
      const aparelhoHash = await hmacHex(SEGREDO_HMAC, rotuloAparelho(rodadaId, `ap-teto-${i}`));
      await env.DB.prepare(
        "INSERT INTO vp_autorizacoes (jti, rodada_id, aparelho_hash, expira_em, usada) VALUES (?, ?, ?, ?, 1)",
      ).bind(`jti-falso-teto-${i}`, rodadaId, aparelhoHash, agora + 600).run();
      await env.DB.prepare(
        "INSERT INTO vp_participacoes (rodada_id, aparelho_hash, endereco_hash, criada_em, jti) VALUES (?, ?, ?, ?, ?)",
      ).bind(rodadaId, aparelhoHash, enderecoHash, "2026-10-20T00:00:00.000Z", `jti-falso-teto-${i}`).run();
    }
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", rodadaId), teto - 1);
    const a = await soVerificar(mundo, { aparelho: "ap-teto-a", ip });
    assert.equal(a.status, 200);
    const b = await soVerificar(mundo, { aparelho: "ap-teto-b", ip });
    assert.equal(b.status, 200);
    const ra = await soVotar(mundo, { token: a.corpo.autorizacao, aparelho: "ap-teto-a", ip });
    assert.equal(ra.status, 200);
    const rb = await soVotar(mundo, { token: b.corpo.autorizacao, aparelho: "ap-teto-b", ip });
    assert.equal(rb.status, 409);
    assert.equal(rb.corpo.codigo, "teto_endereco");
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", rodadaId), teto);
    const c = await soVerificar(mundo, { aparelho: "ap-teto-31", ip });
    assert.equal(c.status, 409);
    assert.equal(c.corpo.codigo, "teto_endereco");
  });

  it("sem a linha do teto em vp_config, insercao direta e recusada", async () => {
    const mundo = montarMundoReal();
    const { env } = mundo;
    await env.DB.prepare(
      "INSERT INTO vp_autorizacoes (jti, rodada_id, aparelho_hash, expira_em, usada) VALUES (?, ?, ?, ?, 1)",
    ).bind("jti-falso-teto", "sessao:900", "h-falso", Math.floor(MS_BASE / 1000) + 600).run();
    await assert.rejects(
      env.DB.prepare(
        "INSERT INTO vp_participacoes (rodada_id, aparelho_hash, endereco_hash, criada_em, jti) VALUES (?, ?, ?, ?, ?)",
      ).bind("sessao:900", "h-falso", "e-falso", "2026-10-20T00:00:00.000Z", "jti-falso-teto").run(),
      /teto_endereco/,
    );
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", "sessao:900"), 0);
  });
});

// ---------------------------------------------------------------------------
// Turnstile, corpo grande, rodada fechada e totais no SQLite real
// ---------------------------------------------------------------------------

describe("turnstile e corpo no SQLite real", () => {
  it("hostname errado ou acao errada viram captcha_invalido", async () => {
    for (const resposta of [
      { success: true, hostname: "site-errado.falso", action: "votacao" },
      { success: true, hostname: "site.falso", action: "outra-acao" },
    ]) {
      const mundo = montarMundoReal();
      mundo.rede.turnstile = resposta;
      const r = await soVerificar(mundo, { aparelho: "ap-cap-1", ip: `${IP_BASE}111` });
      assert.equal(r.status, 400, JSON.stringify(resposta));
      assert.equal(r.corpo.codigo, "captcha_invalido");
    }
  });

  it("corpo acima de 32 KB e recusado com 413 corpo_grande", async () => {
    const mundo = montarMundoReal();
    const anunciado = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpoTexto: "{}",
        ip: `${IP_BASE}121`,
        extras: { "Content-Length": String(100 * 1024) },
      }),
      mundo.env,
      {},
    );
    assert.equal(anunciado.status, 413);
    assert.equal((await anunciado.json()).codigo, "corpo_grande");

    const lido = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: `ap-${"x".repeat(40000)}`, lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
        ip: `${IP_BASE}122`,
      }),
      mundo.env,
      {},
    );
    assert.equal(lido.status, 413);
    assert.equal((await lido.json()).codigo, "corpo_grande");
  });
});

describe("rodada fechada no SQLite real", () => {
  it("D1 fechada com arquivo aberto: verificar e votar recusam", async () => {
    const mundo = montarMundoReal();
    const { env } = mundo;
    const fluxo = await verificarEVotar(mundo, { aparelho: "ap-fecha-1", ip: `${IP_BASE}131` });
    assert.equal(fluxo.votarStatus, 200);
    const rodadaId = mundo.rede.rodada.rodada_id;
    await env.DB.prepare(
      "UPDATE vp_rodadas SET status = 'fechada', fechada_em = ? WHERE rodada_id = ?",
    ).bind("2026-10-20T00:00:00.000Z", rodadaId).run();
    const r = await handler.fetch(pedido("/api/rodada", { ip: `${IP_BASE}132` }), env, {});
    assert.equal((await r.json()).status, "fechada");
    const v = await soVerificar(mundo, { aparelho: "ap-fecha-2", ip: `${IP_BASE}133` });
    assert.equal(v.status, 400);
    assert.equal(v.corpo.codigo, "rodada_fechada");
  });
});

describe("resultados no SQLite real", () => {
  it("1 util e 199 inutil: totais exatos e percentuais que somam 100", async () => {
    const mundo = montarMundoReal();
    const { env } = mundo;
    const rodadaId = mundo.rede.rodada.rodada_id;
    const r0 = await handler.fetch(pedido("/api/rodada", { ip: `${IP_BASE}141` }), env, {});
    assert.equal(r0.status, 200);
    const [m1, m2] = mundo.rede.rodada.materias;
    await env.DB.prepare(
      "UPDATE vp_totais SET total_util = ?, total_inutil = ? WHERE rodada_id = ? AND materia_id = ?",
    ).bind(1, 199, rodadaId, m1.id).run();
    await env.DB.prepare(
      "UPDATE vp_totais SET total_util = ?, total_inutil = ? WHERE rodada_id = ? AND materia_id = ?",
    ).bind(150, 50, rodadaId, m2.id).run();
    const r = await handler.fetch(pedido("/api/resultados", { ip: `${IP_BASE}142` }), env, {});
    const corpo = await r.json();
    assert.equal(r.status, 200);
    const primeira = corpo.rodadas[0].materias.find((m) => m.materia_id === m1.id);
    assert.equal(primeira.respostas, 200);
    assert.equal(primeira.total_util, 1);
    assert.equal(primeira.total_inutil, 199);
    assert.equal(primeira.percentual_util, 1);
    assert.equal(primeira.percentual_inutil, 99);
  });
});

// ---------------------------------------------------------------------------
// Falha no meio do lote desfaz tudo, inclusive o uso da autorizacao
// ---------------------------------------------------------------------------

describe("lote atomico no SQLite real", () => {
  it("falha no meio do lote: nada gravado e token segue valido", async () => {
    const mundo = montarMundoReal();
    const { env } = mundo;
    const rodadaId = mundo.rede.rodada.rodada_id;
    const aparelho = "ap-real-5";
    const ip = `${IP_BASE}15`;
    const v = await soVerificar(mundo, { aparelho, ip });
    assert.equal(v.status, 200);
    const linhaJti = await env.DB.prepare(
      "SELECT jti FROM vp_autorizacoes WHERE rodada_id = ?",
    ).bind(rodadaId).first();
    const jti = linhaJti.jti;
    const aparelhoHash = await hmacHex(SEGREDO_HMAC, rotuloAparelho(rodadaId, aparelho));
    const enderecoHash = await hmacHex(SEGREDO_HMAC, rotuloEndereco(rodadaId, ip));
    const materiaId = mundo.rede.rodada.materias[0].id;
    const lote = [
      env.DB.prepare(
        "INSERT INTO vp_config (chave, valor) VALUES (?, ?) ON CONFLICT (chave) DO UPDATE SET valor = excluded.valor",
      ).bind(CHAVE_TETO, "30"),
      env.DB.prepare("UPDATE vp_autorizacoes SET usada = 1 WHERE jti = ?").bind(jti),
      env.DB.prepare(
        "INSERT INTO vp_participacoes (rodada_id, aparelho_hash, endereco_hash, criada_em, jti) VALUES (?, ?, ?, ?, ?)",
      ).bind(rodadaId, aparelhoHash, enderecoHash, "2026-10-20T00:00:00.000Z", jti),
      env.DB.prepare(
        "INSERT INTO vp_votos (rodada_id, materia_id, aparelho_hash, valor) VALUES (?, ?, ?, ?)",
      ).bind(rodadaId, materiaId, aparelhoHash, "valor-falso"),
    ];
    await assert.rejects(env.DB.batch(lote));
    assert.equal(await mundo.db.contar("vp_participacoes", "rodada_id = ?", rodadaId), 0);
    assert.equal(await mundo.db.contar("vp_votos", "rodada_id = ?", rodadaId), 0);
    assert.equal(await mundo.db.somarTotais(rodadaId), 0);
    const aut = await env.DB.prepare("SELECT usada FROM vp_autorizacoes WHERE jti = ?").bind(jti).first();
    assert.equal(aut.usada, 0);
    const r = await soVotar(mundo, { token: v.corpo.autorizacao, aparelho, ip });
    assert.equal(r.status, 200, JSON.stringify(r.corpo));
  });
});
