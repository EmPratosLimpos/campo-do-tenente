import { describe, it, before, after } from "node:test";
import assert from "node:assert/strict";
import handler from "../src/index.js";
import { DADOS_CIDADE } from "../src/dados_cidade.js";
import { hmacHex, rotuloAparelho, rotuloEndereco } from "../src/regras.js";

// ---------------------------------------------------------------------------
// D1 falso em memoria: prepare/bind/first/all/run e batch tudo ou nada,
// com semantica real de PRIMARY KEY e dos triggers do teto e do uso unico.
// ---------------------------------------------------------------------------

class DeclaracaoFalsa {
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
    return this.banco._first(this.sql, this.params);
  }
  async all() {
    return { results: this.banco._all(this.sql, this.params) };
  }
  async run() {
    return this.banco._run(this.sql, this.params);
  }
}

class D1Falso {
  constructor() {
    this.zerar();
    this.falharNoLote = 0;
  }
  zerar() {
    this.rodadas = new Map();
    this.materias = new Map();
    this.totais = new Map();
    this.participacoes = new Map();
    this.votos = new Map();
    this.autorizacoes = new Map();
    this.taxa = new Map();
    this.config = new Map();
  }
  prepare(sql) {
    return new DeclaracaoFalsa(this, sql);
  }
  _copiaTabela(mapa) {
    return new Map([...mapa.entries()].map(([chave, linha]) => [chave, { ...linha }]));
  }
  async batch(declaracoes) {
    const copia = {
      rodadas: this._copiaTabela(this.rodadas),
      materias: this._copiaTabela(this.materias),
      totais: this._copiaTabela(this.totais),
      participacoes: this._copiaTabela(this.participacoes),
      votos: this._copiaTabela(this.votos),
      autorizacoes: this._copiaTabela(this.autorizacoes),
      taxa: new Map(this.taxa),
      config: new Map(this.config),
    };
    const atual = {
      rodadas: this.rodadas,
      materias: this.materias,
      totais: this.totais,
      participacoes: this.participacoes,
      votos: this.votos,
      autorizacoes: this.autorizacoes,
      taxa: this.taxa,
      config: this.config,
    };
    Object.assign(this, copia);
    const saidas = [];
    try {
      let n = 0;
      for (const d of declaracoes) {
        n += 1;
        if (this.falharNoLote > 0 && n === this.falharNoLote) {
          throw new Error("falha simulada no meio do batch");
        }
        saidas.push(await d.run());
      }
    } catch (e) {
      Object.assign(this, atual);
      throw e;
    }
    return saidas;
  }
  _norm(sql) {
    return String(sql).replace(/\s+/g, " ").trim();
  }
  _first(sql, p) {
    const linhas = this._all(sql, p);
    return linhas.length > 0 ? linhas[0] : null;
  }
  _all(sql, p) {
    const s = this._norm(sql);
    if (s.startsWith("SELECT") && s.includes("FROM vp_rodadas WHERE rodada_id = ?")) {
      const linha = this.rodadas.get(p[0]);
      return linha ? [{ ...linha }] : [];
    }
    if (s.startsWith("SELECT") && s.includes("FROM vp_rodadas WHERE status = 'aberta'")) {
      return [...this.rodadas.values()]
        .filter((r) => r.status === "aberta")
        .sort((a, b) => (a.criada_em < b.criada_em ? 1 : -1))
        .slice(0, 1)
        .map((r) => ({ ...r }));
    }
    if (s.startsWith("SELECT") && s.includes("FROM vp_rodadas WHERE status = 'fechada'")) {
      return [...this.rodadas.values()]
        .filter((r) => r.status === "fechada" && r.fechada_em !== null && r.fechada_em < p[0])
        .map((r) => ({ rodada_id: r.rodada_id }));
    }
    if (s.startsWith("SELECT") && s.includes("FROM vp_rodadas ORDER BY")) {
      return [...this.rodadas.values()]
        .sort((a, b) => (a.criada_em < b.criada_em ? 1 : -1))
        .map((r) => ({ rodada_id: r.rodada_id, status: r.status }));
    }
    if (s.startsWith("SELECT") && s.includes("FROM vp_materias WHERE rodada_id = ?")) {
      return [...this.materias.values()]
        .filter((m) => m.rodada_id === p[0])
        .sort((a, b) => a.ordem_pauta - b.ordem_pauta || a.materia_id - b.materia_id)
        .map((m) => ({ ...m }));
    }
    if (s.startsWith("SELECT") && s.includes("FROM vp_participacoes WHERE rodada_id = ? AND aparelho_hash = ?")) {
      const linha = this.participacoes.get(`${p[0]}|${p[1]}`);
      return linha ? [{ rodada_id: linha.rodada_id }] : [];
    }
    if (s.startsWith("SELECT COUNT(*) AS total FROM vp_participacoes")) {
      let n = 0;
      for (const linha of this.participacoes.values()) {
        if (linha.rodada_id === p[0] && linha.endereco_hash === p[1]) n += 1;
      }
      return [{ total: n }];
    }
    if (s.startsWith("SELECT") && s.includes("FROM vp_totais WHERE rodada_id = ?")) {
      return [...this.totais.values()]
        .filter((t) => t.rodada_id === p[0])
        .map((t) => ({ ...t }));
    }
    if (s.startsWith("SELECT contagem FROM vp_taxa")) {
      const linha = this.taxa.get(`${p[0]}|${p[1]}`);
      return linha ? [{ contagem: linha }] : [];
    }
    if (s.startsWith("SELECT valor FROM vp_config")) {
      const valor = this.config.get(p[0]);
      return valor === undefined ? [] : [{ valor }];
    }
    throw new Error(`D1 falso: SELECT nao suportado: ${s}`);
  }
  _run(sql, p) {
    const s = this._norm(sql);
    if (s.startsWith("UPDATE vp_rodadas SET status = 'fechada', fechada_em = ? WHERE status = 'aberta' AND rodada_id != ?")) {
      let n = 0;
      for (const linha of this.rodadas.values()) {
        if (linha.status === "aberta" && linha.rodada_id !== p[1]) {
          linha.status = "fechada";
          linha.fechada_em = p[0];
          n += 1;
        }
      }
      return this._ok(n);
    }
    if (s.startsWith("UPDATE vp_rodadas SET status = 'fechada', fechada_em = ? WHERE rodada_id = ?")) {
      const linha = this.rodadas.get(p[1]);
      if (!linha) return this._ok(0);
      linha.status = "fechada";
      linha.fechada_em = p[0];
      return this._ok(1);
    }
    if (s.startsWith("INSERT OR IGNORE INTO vp_rodadas")) {
      if (this.rodadas.has(p[0])) return this._ok(0);
      this.rodadas.set(p[0], {
        rodada_id: p[0], sessao_id: p[1], data_sessao: p[2],
        status: "aberta", criada_em: p[3], fechada_em: null,
      });
      return this._ok(1);
    }
    if (s.startsWith("INSERT OR IGNORE INTO vp_materias")) {
      const chave = `${p[0]}|${p[1]}`;
      if (this.materias.has(chave)) return this._ok(0);
      this.materias.set(chave, {
        rodada_id: p[0], materia_id: p[1], sigla: p[2], numero: p[3],
        ano: p[4], ordem_pauta: p[5], ementa: p[6], link_sapl: p[7],
      });
      return this._ok(1);
    }
    if (s.startsWith("INSERT OR IGNORE INTO vp_totais")) {
      const chave = `${p[0]}|${p[1]}`;
      if (this.totais.has(chave)) return this._ok(0);
      this.totais.set(chave, { rodada_id: p[0], materia_id: p[1], total_util: 0, total_inutil: 0 });
      return this._ok(1);
    }
    if (s.startsWith("INSERT INTO vp_participacoes")) {
      const chave = `${p[0]}|${p[1]}`;
      if (this.participacoes.has(chave)) {
        throw new Error("UNIQUE constraint failed: vp_participacoes.rodada_id, vp_participacoes.aparelho_hash");
      }
      const tetoTexto = this.config.get("teto_votos_por_endereco_por_rodada");
      if (tetoTexto !== undefined) {
        let n = 0;
        for (const linha of this.participacoes.values()) {
          if (linha.rodada_id === p[0] && linha.endereco_hash === p[2]) n += 1;
        }
        if (n >= Number(tetoTexto)) {
          throw new Error("teto_endereco");
        }
      }
      this.participacoes.set(chave, {
        rodada_id: p[0], aparelho_hash: p[1], endereco_hash: p[2], criada_em: p[3],
      });
      return this._ok(1);
    }
    if (s.startsWith("INSERT INTO vp_votos")) {
      const chave = `${p[0]}|${p[2]}|${p[1]}`;
      if (this.votos.has(chave)) {
        throw new Error("UNIQUE constraint failed: vp_votos.rodada_id, vp_votos.aparelho_hash, vp_votos.materia_id");
      }
      this.votos.set(chave, {
        rodada_id: p[0], materia_id: p[1], aparelho_hash: p[2], valor: p[3],
      });
      return this._ok(1);
    }
    if (s.startsWith("UPDATE vp_totais SET total_util = total_util + ?")) {
      const chave = `${p[2]}|${p[3]}`;
      const linha = this.totais.get(chave);
      if (!linha) return this._ok(0);
      linha.total_util += p[0];
      linha.total_inutil += p[1];
      return this._ok(1);
    }
    if (s.startsWith("INSERT INTO vp_autorizacoes")) {
      if (this.autorizacoes.has(p[0])) {
        throw new Error("UNIQUE constraint failed: vp_autorizacoes.jti");
      }
      this.autorizacoes.set(p[0], {
        jti: p[0], rodada_id: p[1], aparelho_hash: p[2], expira_em: p[3], usada: 0,
      });
      return this._ok(1);
    }
    if (s.startsWith("UPDATE vp_autorizacoes SET usada = 1 WHERE jti = ?")) {
      const linha = this.autorizacoes.get(p[0]);
      if (!linha) return this._ok(0);
      if (linha.usada !== 0) {
        throw new Error("autorizacao_reutilizada");
      }
      linha.usada = 1;
      return this._ok(1);
    }
    if (s.startsWith("INSERT INTO vp_taxa") && s.includes("ON CONFLICT")) {
      const chave = `${p[0]}|${p[1]}`;
      this.taxa.set(chave, (this.taxa.get(chave) || 0) + 1);
      return this._ok(1);
    }
    if (s.startsWith("INSERT INTO vp_config") && s.includes("ON CONFLICT")) {
      this.config.set(p[0], p[1]);
      return this._ok(1);
    }
    if (s.startsWith("DELETE FROM vp_participacoes WHERE rodada_id = ?")) {
      let n = 0;
      for (const chave of [...this.participacoes.keys()]) {
        if (this.participacoes.get(chave).rodada_id === p[0]) {
          this.participacoes.delete(chave);
          n += 1;
        }
      }
      return this._ok(n);
    }
    if (s.startsWith("DELETE FROM vp_votos WHERE rodada_id = ?")) {
      let n = 0;
      for (const chave of [...this.votos.keys()]) {
        if (this.votos.get(chave).rodada_id === p[0]) {
          this.votos.delete(chave);
          n += 1;
        }
      }
      return this._ok(n);
    }
    if (s.startsWith("DELETE FROM vp_autorizacoes WHERE rodada_id = ?")) {
      let n = 0;
      for (const [chave, linha] of [...this.autorizacoes.entries()]) {
        if (linha.rodada_id === p[0]) {
          this.autorizacoes.delete(chave);
          n += 1;
        }
      }
      return this._ok(n);
    }
    if (s.startsWith("DELETE FROM vp_autorizacoes WHERE expira_em <= ?")) {
      let n = 0;
      for (const [chave, linha] of [...this.autorizacoes.entries()]) {
        if (linha.expira_em <= p[0]) {
          this.autorizacoes.delete(chave);
          n += 1;
        }
      }
      return this._ok(n);
    }
    if (s.startsWith("DELETE FROM vp_taxa WHERE janela_minuto < ?")) {
      let n = 0;
      for (const [chave, linha] of [...this.taxa.entries()]) {
        void linha;
        const janela = Number(chave.split("|").pop());
        if (janela < p[0]) {
          this.taxa.delete(chave);
          n += 1;
        }
      }
      return this._ok(n);
    }
    throw new Error(`D1 falso: escrita nao suportada: ${s}`);
  }
  _ok(changes) {
    return { success: true, meta: { changes } };
  }
}

// ---------------------------------------------------------------------------
// Apoio aos testes
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

function montarMundo({ ambiente = "teste", rodada = rodadaFalsa(900) } = {}) {
  const db = new D1Falso();
  const rede = { turnstile: true, rodada };
  global.fetch = async (url, opts) => {
    void opts;
    const texto = String(url);
    if (texto.includes("siteverify")) {
      return { ok: true, json: async () => ({ success: rede.turnstile }) };
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

function pedido(rota, { metodo = "GET", corpo = null, ip = `${IP_BASE}7`, origin = "https://site.falso", extras = {} } = {}) {
  const headers = {
    "Content-Type": "application/json",
    "CF-Connecting-IP": ip,
    Origin: origin,
    ...extras,
  };
  return new Request(`https://worker.falso${rota}`, {
    metodo,
    method: metodo,
    headers,
    body: corpo === null ? undefined : JSON.stringify(corpo),
  });
}

async function corpoJSON(resp) {
  return resp.json();
}

async function verificarEVotar(mundo, { aparelho, ip, lat = LAT_DENTRO, lon = LON_DENTRO, precisao = 20, valores = ["util", "inutil"], extras = {} }) {
  const { env } = mundo;
  const r1 = await handler.fetch(
    pedido("/api/verificar", {
      metodo: "POST",
      corpo: { turnstile_token: "token-falso", aparelho_id: aparelho, lat, lon, precisao_m: precisao },
      ip,
      extras,
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

function semChaveDeAutor(valor, caminho = "raiz", achadas = []) {
  if (Array.isArray(valor)) {
    valor.forEach((item, i) => semChaveDeAutor(item, `${caminho}[${i}]`, achadas));
  } else if (valor && typeof valor === "object") {
    for (const [chave, item] of Object.entries(valor)) {
      const baixa = chave.toLowerCase();
      if (baixa.includes("autor") || baixa.includes("partido") || baixa.includes("vereador")) {
        achadas.push(`${caminho}.${chave}`);
      }
      semChaveDeAutor(item, `${caminho}.${chave}`, achadas);
    }
  }
  return achadas;
}

before(() => {
  Date.now = () => MS_BASE;
});

after(() => {
  Date.now = REAL_NOW;
  global.fetch = REAL_FETCH;
});

// ---------------------------------------------------------------------------
// Voto valido, repeticao e simultaneidade
// ---------------------------------------------------------------------------

describe("voto valido e repeticao", () => {
  it("voto valido grava e aparece sem autor na rodada", async () => {
    const mundo = montarMundo();
    const r = await handler.fetch(pedido("/api/rodada"), mundo.env, {});
    assert.equal(r.status, 200);
    const rodada = await corpoJSON(r);
    assert.equal(rodada.status, "aberta");
    assert.equal(rodada.materias.length, 2);
    assert.deepEqual(semChaveDeAutor(rodada), []);

    const fluxo = await verificarEVotar(mundo, { aparelho: "ap-valido-1", ip: `${IP_BASE}11` });
    assert.equal(fluxo.votarStatus, 200);
    assert.equal(fluxo.votar.ok, true);
    assert.equal(mundo.db.participacoes.size, 1);
  });

  it("mesmo aparelho de novo recebe ja_votou", async () => {
    const mundo = montarMundo();
    await verificarEVotar(mundo, { aparelho: "ap-repete-1", ip: `${IP_BASE}12` });
    const r = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-repete-1", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
        ip: `${IP_BASE}12`,
      }),
      mundo.env,
      {},
    );
    assert.equal(r.status, 409);
    assert.equal((await corpoJSON(r)).codigo, "ja_votou");
  });

  it("dois votos simultaneos do mesmo aparelho: so um grava", async () => {
    const mundo = montarMundo();
    const tokens = [];
    for (let i = 0; i < 2; i += 1) {
      const r = await handler.fetch(
        pedido("/api/verificar", {
          metodo: "POST",
          corpo: { turnstile_token: "t", aparelho_id: "ap-sim-1", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
          ip: `${IP_BASE}13`,
        }),
        mundo.env,
        {},
      );
      tokens.push((await corpoJSON(r)).autorizacao);
    }
    const materias = mundo.rede.rodada.materias.map((m) => ({ materia_id: m.id, valor: "util" }));
    const [a, b] = await Promise.all(
      tokens.map((autorizacao) =>
        handler.fetch(
          pedido("/api/votar", {
            metodo: "POST",
            corpo: { autorizacao, aparelho_id: "ap-sim-1", respostas: materias },
            ip: `${IP_BASE}13`,
          }),
          mundo.env,
          {},
        ),
      ),
    );
    const estados = [a.status, b.status].sort();
    assert.deepEqual(estados, [200, 409]);
    let total = 0;
    for (const linha of mundo.db.totais.values()) {
      total += linha.total_util + linha.total_inutil;
    }
    assert.equal(total, 2);
    assert.equal(mundo.db.participacoes.size, 1);
  });
});

// ---------------------------------------------------------------------------
// Teto por endereco, inclusive simultaneo
// ---------------------------------------------------------------------------

describe("teto por endereco", () => {
  async function encher(mundo, n, ip) {
    const rodadaId = mundo.rede.rodada.rodada_id;
    const teto = DADOS_CIDADE.limites.teto_votos_por_endereco_por_rodada;
    mundo.db.config.set("teto_votos_por_endereco_por_rodada", String(teto));
    const enderecoHash = await hmacHex(SEGREDO_HMAC, rotuloEndereco(rodadaId, ip));
    for (let i = 0; i < n; i += 1) {
      const aparelhoHash = await hmacHex(SEGREDO_HMAC, rotuloAparelho(rodadaId, `ap-teto-${i}`));
      mundo.db.participacoes.set(`${rodadaId}|${aparelhoHash}`, {
        rodada_id: rodadaId, aparelho_hash: aparelhoHash, endereco_hash: enderecoHash, criada_em: "2026-10-20T00:00:00.000Z",
      });
    }
  }

  it("o voto 30 passa e o 31 e recusado", async () => {
    const mundo = montarMundo();
    const teto = DADOS_CIDADE.limites.teto_votos_por_endereco_por_rodada;
    assert.equal(teto, 30);
    const ip = `${IP_BASE}21`;
    await encher(mundo, teto - 1, ip);
    const ok = await verificarEVotar(mundo, { aparelho: "ap-teto-30", ip });
    assert.equal(ok.votarStatus, 200);
    const r = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-teto-31", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
        ip,
      }),
      mundo.env,
      {},
    );
    assert.equal(r.status, 409);
    assert.equal((await corpoJSON(r)).codigo, "teto_endereco");
  });

  it("dois simultaneos no limite: um passa, o outro recebe teto", async () => {
    const mundo = montarMundo();
    const teto = DADOS_CIDADE.limites.teto_votos_por_endereco_por_rodada;
    const ip = `${IP_BASE}22`;
    await encher(mundo, teto - 1, ip);
    const [a, b] = await Promise.all([
      verificarEVotar(mundo, { aparelho: "ap-teto-a", ip }),
      verificarEVotar(mundo, { aparelho: "ap-teto-b", ip }),
    ]);
    const estados = [a.votarStatus, b.votarStatus].sort();
    assert.deepEqual(estados, [200, 409]);
    const perdedor = a.votarStatus === 409 ? a.votar : b.votar;
    assert.equal(perdedor.codigo, "teto_endereco");
    let n = 0;
    for (const linha of mundo.db.participacoes.values()) {
      if (linha.rodada_id === mundo.rede.rodada.rodada_id) n += 1;
    }
    assert.equal(n, teto);
  });
});

// ---------------------------------------------------------------------------
// Autorizacao: reuso, vencida, outro aparelho, outra rodada, adulterada
// ---------------------------------------------------------------------------

describe("autorizacao", () => {
  it("reaproveitada recebe autorizacao_reutilizada", async () => {
    const mundo = montarMundo();
    const fluxo = await verificarEVotar(mundo, { aparelho: "ap-reuso-1", ip: `${IP_BASE}31` });
    assert.equal(fluxo.votarStatus, 200);
    const materias = mundo.rede.rodada.materias.map((m) => ({ materia_id: m.id, valor: "util" }));
    const r = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpo: { autorizacao: fluxo.verificar.autorizacao, aparelho_id: "ap-reuso-1", respostas: materias },
        ip: `${IP_BASE}31`,
      }),
      mundo.env,
      {},
    );
    assert.equal(r.status, 409);
    assert.equal((await corpoJSON(r)).codigo, "autorizacao_reutilizada");
  });

  it("vencida, de outro aparelho, de outra rodada e adulterada sao invalidas", async () => {
    const { emitirAutorizacao, conferirAutorizacao } = await import("../src/regras.js");
    void conferirAutorizacao;
    const mundo = montarMundo();
    const materias = mundo.rede.rodada.materias.map((m) => ({ materia_id: m.id, valor: "util" }));
    const agora = Math.floor(MS_BASE / 1000);

    const vencida = await emitirAutorizacao({
      segredo: SEGREDO_HMAC,
      rodadaId: "sessao:900",
      aparelhoHash: "hash-falso",
      dentro: true,
      agoraS: agora - 1200,
      validadeMin: 10,
      jti: "jti-vencida",
    });
    const r1 = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpo: { autorizacao: vencida, aparelho_id: "ap-x", respostas: materias },
        ip: `${IP_BASE}32`,
      }),
      mundo.env,
      {},
    );
    assert.equal(r1.status, 400);
    assert.equal((await corpoJSON(r1)).codigo, "autorizacao_invalida");

    const fluxo = await verificarEVotar(mundo, { aparelho: "ap-dono-1", ip: `${IP_BASE}33` });
    assert.equal(fluxo.votarStatus, 200);
    const fluxo2 = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-outro-1", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
        ip: `${IP_BASE}34`,
      }),
      mundo.env,
      {},
    );
    const tokenOutro = (await corpoJSON(fluxo2)).autorizacao;
    const r2 = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpo: { autorizacao: tokenOutro, aparelho_id: "ap-trocado-1", respostas: materias },
        ip: `${IP_BASE}34`,
      }),
      mundo.env,
      {},
    );
    assert.equal(r2.status, 400);
    assert.equal((await corpoJSON(r2)).codigo, "autorizacao_invalida");

    const outraRodada = await emitirAutorizacao({
      segredo: SEGREDO_HMAC,
      rodadaId: "sessao:999",
      aparelhoHash: await hmacHex(SEGREDO_HMAC, rotuloAparelho("sessao:999", "ap-x")),
      dentro: true,
      agoraS: agora,
      validadeMin: 10,
      jti: "jti-outra",
    });
    const r3 = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpo: { autorizacao: outraRodada, aparelho_id: "ap-x", respostas: materias },
        ip: `${IP_BASE}35`,
      }),
      mundo.env,
      {},
    );
    assert.equal(r3.status, 400);
    assert.equal((await corpoJSON(r3)).codigo, "autorizacao_invalida");

    const [payload] = fluxo.verificar.autorizacao.split(".");
    const r4 = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpo: { autorizacao: `${payload}.adulterada`, aparelho_id: "ap-dono-1", respostas: materias },
        ip: `${IP_BASE}33`,
      }),
      mundo.env,
      {},
    );
    assert.equal(r4.status, 400);
    assert.equal((await corpoJSON(r4)).codigo, "autorizacao_invalida");
  });
});

// ---------------------------------------------------------------------------
// Respostas invalidas e GPS
// ---------------------------------------------------------------------------

describe("respostas e GPS", () => {
  it("materia fora da rodada, resposta faltando e valor invalido", async () => {
    const mundo = montarMundo();
    const r = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-resp-1", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
        ip: `${IP_BASE}41`,
      }),
      mundo.env,
      {},
    );
    const token = (await corpoJSON(r)).autorizacao;
    const [m1, m2] = mundo.rede.rodada.materias;
    const casos = [
      { respostas: [{ materia_id: m1.id, valor: "util" }, { materia_id: 999999, valor: "util" }], codigo: "materia_invalida" },
      { respostas: [{ materia_id: m1.id, valor: "util" }], codigo: "respostas_incompletas" },
      { respostas: [{ materia_id: m1.id, valor: "talvez" }, { materia_id: m2.id, valor: "util" }], codigo: "valor_invalido" },
    ];
    for (const caso of casos) {
      const rv = await handler.fetch(
        pedido("/api/votar", {
          metodo: "POST",
          corpo: { autorizacao: token, aparelho_id: "ap-resp-1", respostas: caso.respostas },
          ip: `${IP_BASE}41`,
        }),
        mundo.env,
        {},
      );
      assert.equal(rv.status, 400, JSON.stringify(await rv.clone().json()));
      assert.equal((await corpoJSON(rv)).codigo, caso.codigo);
    }
  });

  it("fora a 30 km recusa, precisao ruim recusa, Turnstile invalido recusa", async () => {
    const mundo = montarMundo();
    const base = { turnstile_token: "t", aparelho_id: "ap-gps-1", precisao_m: 10 };
    const fora = await handler.fetch(
      pedido("/api/verificar", { metodo: "POST", corpo: { ...base, lat: -25.6277, lon: -49.6564 }, ip: `${IP_BASE}42` }),
      mundo.env,
      {},
    );
    assert.equal(fora.status, 400);
    assert.equal((await corpoJSON(fora)).codigo, "fora_do_municipio");

    const ruim = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { ...base, aparelho_id: "ap-gps-2", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: DADOS_CIDADE.limites.precisao_gps_max_m + 1 },
        ip: `${IP_BASE}43`,
      }),
      mundo.env,
      {},
    );
    assert.equal(ruim.status, 400);
    assert.equal((await corpoJSON(ruim)).codigo, "precisao_ruim");

    mundo.rede.turnstile = false;
    const captcha = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { ...base, aparelho_id: "ap-gps-3", lat: LAT_DENTRO, lon: LON_DENTRO },
        ip: `${IP_BASE}44`,
      }),
      mundo.env,
      {},
    );
    assert.equal(captcha.status, 400);
    assert.equal((await corpoJSON(captcha)).codigo, "captcha_invalido");
  });

  it("faixa da margem aceita, alem da margem recusa", async () => {
    const mundo = montarMundo();
    const contorno = DADOS_CIDADE.contorno;
    const margem = DADOS_CIDADE.limites.margem_divisa_m;
    const aneis = contorno.type === "Polygon" ? contorno.coordinates : contorno.coordinates.flat();
    const anel = aneis[0];
    const { dentroDoContorno, distanciaAoContornoM } = await import("../src/regras.js");
    let caso = null;
    for (const [vlon, vlat] of anel) {
      const kx = 111320.0 * Math.cos((vlat * Math.PI) / 180);
      for (const [dlon, dlat] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
        const perto = [vlon + (dlon * margem * 0.5) / kx, vlat + (dlat * margem * 0.5) / 111320.0];
        const longe = [vlon + (dlon * margem * 5) / kx, vlat + (dlat * margem * 5) / 111320.0];
        if (!dentroDoContorno(perto[0], perto[1], contorno) && !dentroDoContorno(longe[0], longe[1], contorno) && distanciaAoContornoM(longe[0], longe[1], contorno) > margem) {
          caso = { perto, longe };
          break;
        }
      }
      if (caso) break;
    }
    assert.ok(caso);
    const rPerto = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-margem-1", lat: caso.perto[1], lon: caso.perto[0], precisao_m: 10 },
        ip: `${IP_BASE}45`,
      }),
      mundo.env,
      {},
    );
    assert.equal(rPerto.status, 200);
    const rLonge = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-margem-2", lat: caso.longe[1], lon: caso.longe[0], precisao_m: 10 },
        ip: `${IP_BASE}46`,
      }),
      mundo.env,
      {},
    );
    assert.equal(rLonge.status, 400);
    assert.equal((await corpoJSON(rLonge)).codigo, "fora_do_municipio");
  });
});

// ---------------------------------------------------------------------------
// Limites de pedidos, batch atomico, rodada e resultados
// ---------------------------------------------------------------------------

describe("limites, batch, rodada e resultados", () => {
  it("429 com Retry-After na regra geral e na regra do votar", async () => {
    const mundo = montarMundo();
    const geral = DADOS_CIDADE.limites.limite_geral_pedidos;
    let ultima = null;
    for (let i = 0; i < geral + 1; i += 1) {
      ultima = await handler.fetch(pedido("/api/rodada", { ip: `${IP_BASE}51` }), mundo.env, {});
    }
    assert.equal(ultima.status, 429);
    assert.ok(ultima.headers.get("Retry-After"));
    const corpo = await corpoJSON(ultima);
    assert.equal(corpo.codigo, "limite_pedidos");
    assert.ok(corpo.tentar_depois_s > 0);

    const votarMax = DADOS_CIDADE.limites.limite_votar_pedidos;
    let ultimoVoto = null;
    for (let i = 0; i < votarMax + 1; i += 1) {
      ultimoVoto = await handler.fetch(
        pedido("/api/votar", { metodo: "POST", corpo: { aparelho_id: "x" }, ip: `${IP_BASE}52` }),
        mundo.env,
        {},
      );
    }
    assert.equal(ultimoVoto.status, 429);
    assert.ok(ultimoVoto.headers.get("Retry-After"));
    assert.equal((await corpoJSON(ultimoVoto)).codigo, "limite_pedidos");
  });

  it("falha no meio do batch nao deixa nada gravado", async () => {
    const mundo = montarMundo();
    const r = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-falha-1", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 10 },
        ip: `${IP_BASE}61`,
      }),
      mundo.env,
      {},
    );
    const token = (await corpoJSON(r)).autorizacao;
    const materias = mundo.rede.rodada.materias.map((m) => ({ materia_id: m.id, valor: "util" }));
    mundo.db.falharNoLote = 3;
    const rv = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpo: { autorizacao: token, aparelho_id: "ap-falha-1", respostas: materias },
        ip: `${IP_BASE}61`,
      }),
      mundo.env,
      {},
    );
    assert.equal(rv.status, 500);
    assert.equal(mundo.db.participacoes.size, 0);
    assert.equal(mundo.db.votos.size, 0);
    for (const linha of mundo.db.totais.values()) {
      assert.equal(linha.total_util + linha.total_inutil, 0);
    }
    mundo.db.falharNoLote = 0;
    const r2 = await handler.fetch(
      pedido("/api/votar", {
        metodo: "POST",
        corpo: { autorizacao: token, aparelho_id: "ap-falha-1", respostas: materias },
        ip: `${IP_BASE}61`,
      }),
      mundo.env,
      {},
    );
    assert.equal(r2.status, 200);
  });

  it("troca de rodada fecha a anterior e rodada vencida fecha por idade", async () => {
    const mundo = montarMundo({ rodada: rodadaFalsa(900) });
    const ok = await verificarEVotar(mundo, { aparelho: "ap-troca-1", ip: `${IP_BASE}71` });
    assert.equal(ok.votarStatus, 200);
    mundo.rede.rodada = rodadaFalsa(901);
    const r = await handler.fetch(pedido("/api/rodada"), mundo.env, {});
    const rodada = await corpoJSON(r);
    assert.equal(rodada.rodada_id, "sessao:901");
    assert.equal(mundo.db.rodadas.get("sessao:900").status, "fechada");
    assert.ok(mundo.db.rodadas.get("sessao:900").fechada_em);

    Date.now = () => Date.parse("2026-12-06T12:00:00Z");
    try {
      const rv = await handler.fetch(pedido("/api/rodada"), mundo.env, {});
      const fechada = await corpoJSON(rv);
      assert.equal(fechada.status, "fechada");
      assert.equal(mundo.db.rodadas.get("sessao:901").status, "fechada");
    } finally {
      Date.now = () => MS_BASE;
    }
  });

  it("rodada sem materias responde sem rodada aberta", async () => {
    const mundo = montarMundo({
      rodada: { rodada_id: "sessao:902", sessao_id: 902, data_sessao: "2026-10-06", status: "sem_materias_elegiveis", materias: [] },
    });
    const r = await handler.fetch(pedido("/api/rodada"), mundo.env, {});
    const corpo = await corpoJSON(r);
    assert.equal(r.status, 200);
    assert.equal(corpo.status, "sem_materias_elegiveis");
    assert.deepEqual(corpo.materias, []);
  });

  it("resultados escondem abaixo do minimo e mostram no minimo ou acima", async () => {
    const mundo = montarMundo();
    const minimo = DADOS_CIDADE.limites.minimo_respostas_por_materia;
    await verificarEVotar(mundo, { aparelho: "ap-res-1", ip: `${IP_BASE}81` });
    const r1 = await handler.fetch(pedido("/api/resultados", { ip: `${IP_BASE}82` }), mundo.env, {});
    const j1 = await corpoJSON(r1);
    assert.equal(r1.status, 200);
    assert.equal(j1.rodadas.length, 1);
    for (const m of j1.rodadas[0].materias) {
      assert.equal(m.respostas, `menos de ${minimo}`);
      assert.equal(m.percentual_util, null);
    }
    for (let i = 2; i <= minimo; i += 1) {
      const fluxo = await verificarEVotar(mundo, {
        aparelho: `ap-res-${i}`,
        ip: `${IP_BASE}${80 + i}`,
        valores: i % 2 === 0 ? ["util", "util"] : ["inutil", "inutil"],
      });
      assert.equal(fluxo.votarStatus, 200, JSON.stringify(fluxo.votar));
    }
    const r2 = await handler.fetch(pedido("/api/resultados", { ip: `${IP_BASE}99` }), mundo.env, {});
    const j2 = await corpoJSON(r2);
    const mats = j2.rodadas[0].materias;
    for (const m of mats) {
      assert.equal(m.respostas, minimo);
      assert.ok(Number.isInteger(m.percentual_util));
      assert.equal(m.percentual_util + m.percentual_inutil, 100);
    }
  });

  it("arquivo fora do ar usa o D1 e nunca inventa rodada", async () => {
    const mundo = montarMundo();
    await verificarEVotar(mundo, { aparelho: "ap-queda-1", ip: `${IP_BASE}91` });
    mundo.rede.rodada = null;
    const r = await handler.fetch(pedido("/api/rodada"), mundo.env, {});
    const corpo = await corpoJSON(r);
    assert.equal(corpo.status, "aberta");
    assert.equal(corpo.rodada_id, "sessao:900");

    const mundo2 = montarMundo();
    mundo2.rede.rodada = null;
    const r2 = await handler.fetch(pedido("/api/rodada"), mundo2.env, {});
    const corpo2 = await corpoJSON(r2);
    assert.equal(corpo2.status, "fechada");
    assert.deepEqual(corpo2.materias, []);
  });
});

// ---------------------------------------------------------------------------
// Retencao, modo de teste e privacidade
// ---------------------------------------------------------------------------

describe("retencao, modo de teste e privacidade", () => {
  it("retencao apaga so identificadores velhos e mantem totais", async () => {
    const mundo = montarMundo();
    const { db, env } = mundo;
    const agora = Math.floor(MS_BASE / 1000);
    db.rodadas.set("sessao:800", {
      rodada_id: "sessao:800", sessao_id: 800, data_sessao: "2020-01-01",
      status: "fechada", criada_em: "2020-01-02T00:00:00.000Z", fechada_em: "2020-02-01T00:00:00.000Z",
    });
    db.rodadas.set("sessao:900", {
      rodada_id: "sessao:900", sessao_id: 900, data_sessao: "2026-10-06",
      status: "aberta", criada_em: "2026-10-20T00:00:00.000Z", fechada_em: null,
    });
    db.participacoes.set("sessao:800|h1", { rodada_id: "sessao:800", aparelho_hash: "h1", endereco_hash: "e1", criada_em: "x" });
    db.participacoes.set("sessao:900|h2", { rodada_id: "sessao:900", aparelho_hash: "h2", endereco_hash: "e2", criada_em: "x" });
    db.votos.set("sessao:800|h1|1", { rodada_id: "sessao:800", materia_id: 1, aparelho_hash: "h1", valor: "util" });
    db.votos.set("sessao:900|h2|2", { rodada_id: "sessao:900", materia_id: 2, aparelho_hash: "h2", valor: "util" });
    db.autorizacoes.set("jti-velha", { jti: "jti-velha", rodada_id: "sessao:800", aparelho_hash: "h1", expira_em: 1, usada: 1 });
    db.autorizacoes.set("jti-vencida", { jti: "jti-vencida", rodada_id: "sessao:900", aparelho_hash: "h2", expira_em: agora - 10, usada: 0 });
    db.autorizacoes.set("jti-boa", { jti: "jti-boa", rodada_id: "sessao:900", aparelho_hash: "h2", expira_em: agora + 600, usada: 0 });
    db.totais.set("sessao:800|1", { rodada_id: "sessao:800", materia_id: 1, total_util: 5, total_inutil: 1 });
    db.totais.set("sessao:900|2", { rodada_id: "sessao:900", materia_id: 2, total_util: 2, total_inutil: 0 });
    db.taxa.set("hashvelho|1", 30);
    db.taxa.set("hashnovo|999999999", 2);

    await handler.scheduled({}, env, {});
    assert.equal(db.participacoes.has("sessao:800|h1"), false);
    assert.equal(db.votos.has("sessao:800|h1|1"), false);
    assert.equal(db.autorizacoes.has("jti-velha"), false);
    assert.equal(db.participacoes.has("sessao:900|h2"), true);
    assert.equal(db.votos.has("sessao:900|h2|2"), true);
    assert.equal(db.autorizacoes.has("jti-vencida"), false);
    assert.equal(db.autorizacoes.has("jti-boa"), true);
    assert.equal(db.totais.get("sessao:800|1").total_util, 5);
    assert.equal(db.taxa.has("hashvelho|1"), false);
    assert.equal(db.taxa.has("hashnovo|999999999"), true);
  });

  it("modo de teste pula o GPS so em ambiente de teste", async () => {
    const prod = montarMundo({ ambiente: "producao" });
    const rProd = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-mt-1" },
        ip: `${IP_BASE}101`,
        extras: { "X-Modo-Teste": "modo-falso-abc123" },
      }),
      prod.env,
      {},
    );
    assert.equal(rProd.status, 400);
    assert.equal((await corpoJSON(rProd)).codigo, "gps_negado");

    const teste = montarMundo({ ambiente: "teste" });
    const rTeste = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-mt-1" },
        ip: `${IP_BASE}102`,
        extras: { "X-Modo-Teste": "modo-falso-abc123" },
      }),
      teste.env,
      {},
    );
    assert.equal(rTeste.status, 200);

    const testeErrado = montarMundo({ ambiente: "teste" });
    const rErrado = await handler.fetch(
      pedido("/api/verificar", {
        metodo: "POST",
        corpo: { turnstile_token: "t", aparelho_id: "ap-mt-1" },
        ip: `${IP_BASE}103`,
        extras: { "X-Modo-Teste": "segredo-errado" },
      }),
      testeErrado.env,
      {},
    );
    assert.equal(rErrado.status, 400);
  });

  it("CORS e cabecalhos de seguranca", async () => {
    const mundo = montarMundo();
    const opt = await handler.fetch(
      new Request("https://worker.falso/api/votar", {
        method: "OPTIONS",
        headers: { Origin: "https://site.falso" },
      }),
      mundo.env,
      {},
    );
    assert.equal(opt.status, 204);
    assert.equal(opt.headers.get("Access-Control-Allow-Origin"), "https://site.falso");

    const local = await handler.fetch(pedido("/api/rodada", { origin: "http://localhost:8000" }), mundo.env, {});
    assert.equal(local.headers.get("Access-Control-Allow-Origin"), "http://localhost:8000");
    assert.equal(local.headers.get("X-Content-Type-Options"), "nosniff");

    const prod = montarMundo({ ambiente: "producao" });
    const negado = await handler.fetch(pedido("/api/rodada", { origin: "http://localhost:8000" }), prod.env, {});
    assert.equal(negado.headers.get("Access-Control-Allow-Origin"), "https://site.falso");
  });

  it("nenhuma resposta ou log contem IP, coordenada, aparelho ou segredo", async () => {
    const mundo = montarMundo();
    const linhas = [];
    const realLog = console.log;
    const realErr = console.error;
    console.log = (...args) => linhas.push(args.join(" "));
    console.error = (...args) => linhas.push(args.join(" "));
    const ipMarcado = "203.0.113.199";
    try {
      const corpos = [];
      const r1 = await handler.fetch(
        pedido("/api/verificar", {
          metodo: "POST",
          corpo: { turnstile_token: "t", aparelho_id: "aparelho-marcado-xyz", lat: LAT_DENTRO, lon: LON_DENTRO, precisao_m: 12 },
          ip: ipMarcado,
        }),
        mundo.env,
        {},
      );
      corpos.push(await r1.text());
      const token = JSON.parse(corpos[0]).autorizacao;
      const materias = mundo.rede.rodada.materias.map((m) => ({ materia_id: m.id, valor: "util" }));
      const r2 = await handler.fetch(
        pedido("/api/votar", {
          metodo: "POST",
          corpo: { autorizacao: token, aparelho_id: "aparelho-marcado-xyz", respostas: materias },
          ip: ipMarcado,
        }),
        mundo.env,
        {},
      );
      corpos.push(await r2.text());
      const r3 = await handler.fetch(pedido("/api/rodada", { ip: ipMarcado }), mundo.env, {});
      corpos.push(await r3.text());
      const r4 = await handler.fetch(pedido("/api/resultados", { ip: ipMarcado }), mundo.env, {});
      corpos.push(await r4.text());
      const proibidos = [ipMarcado, String(LAT_DENTRO), String(LON_DENTRO), "aparelho-marcado-xyz", SEGREDO_HMAC, "segredo-falso-turnstile", "modo-falso-abc123"];
      for (const texto of [...corpos, ...linhas]) {
        for (const segredo of proibidos) {
          assert.ok(!texto.includes(segredo), `vazamento em: ${texto.slice(0, 120)}`);
        }
      }
    } finally {
      console.log = realLog;
      console.error = realErr;
    }
  });
});
