import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  MENSAGENS_ERRO,
  base64urlParaBytes,
  bytesParaBase64url,
  conferirAutorizacao,
  decidirLocalizacao,
  distanciaAoContornoM,
  dentroDoContorno,
  emitirAutorizacao,
  formatarMateriaResultado,
  corpoLimiteExcedido,
  geometriaContem,
  hmacHex,
  janelaIndice,
  tentarDepoisS,
  modoTestePularGps,
  pontoNoAnel,
  pontoNoPoligono,
  rotuloAparelho,
  rotuloEndereco,
  validarFormaRodada,
  validarPedidoVerificar,
  validarRespostas,
} from "../src/regras.js";
import { DADOS_CIDADE } from "../src/dados_cidade.js";

const SEGREDO_FALSO = "segredo-falso-gerado-neste-teste-0123456789";
const AGORA = 1790000000;

function rodadaFalsa(materias) {
  return {
    rodada_id: "sessao:900",
    sessao_id: 900,
    data_sessao: "2026-09-29",
    status: "aberta",
    materias:
      materias ||
      (DADOS_CIDADE.siglas_elegiveis.length > 0
        ? [
            { id: 1, sigla: DADOS_CIDADE.siglas_elegiveis[0] },
            { id: 2, sigla: DADOS_CIDADE.siglas_elegiveis[0] },
          ]
        : []),
  };
}

describe("base64url e HMAC", () => {
  it("faz ida e volta sem perda", () => {
    const bytes = new Uint8Array([0, 1, 2, 250, 255, 72, 101, 108, 111]);
    assert.deepEqual(base64urlParaBytes(bytesParaBase64url(bytes)), bytes);
  });

  it("HMAC e deterministico e muda com segredo ou mensagem", async () => {
    const a = await hmacHex(SEGREDO_FALSO, rotuloAparelho("sessao:1", "abc"));
    const b = await hmacHex(SEGREDO_FALSO, rotuloAparelho("sessao:1", "abc"));
    const c = await hmacHex(SEGREDO_FALSO, rotuloAparelho("sessao:1", "abd"));
    const d = await hmacHex("outro-segredo-falso", rotuloAparelho("sessao:1", "abc"));
    assert.equal(a, b);
    assert.notEqual(a, c);
    assert.notEqual(a, d);
    assert.match(a, /^[0-9a-f]{64}$/);
  });

  it("rotulos de aparelho e endereco sao diferentes", async () => {
    const a = await hmacHex(SEGREDO_FALSO, rotuloAparelho("sessao:1", "x"));
    const b = await hmacHex(SEGREDO_FALSO, rotuloEndereco("sessao:1", "x"));
    assert.notEqual(a, b);
  });
});

describe("autorizacao de uso unico", () => {
  it("emite e confere um token valido", async () => {
    const token = await emitirAutorizacao({
      segredo: SEGREDO_FALSO,
      rodadaId: "sessao:900",
      aparelhoHash: "hash-falso",
      dentro: true,
      agoraS: AGORA,
      validadeMin: DADOS_CIDADE.limites.validade_autorizacao_min,
      jti: "jti-falso-1",
    });
    const conf = await conferirAutorizacao(token, SEGREDO_FALSO, AGORA + 60);
    assert.equal(conf.ok, true);
    assert.equal(conf.payload.rodada, "sessao:900");
    assert.equal(conf.payload.h_aparelho, "hash-falso");
  });

  it("recusa assinatura adulterada", async () => {
    const token = await emitirAutorizacao({
      segredo: SEGREDO_FALSO,
      rodadaId: "sessao:900",
      aparelhoHash: "hash-falso",
      dentro: true,
      agoraS: AGORA,
      validadeMin: 10,
      jti: "jti-falso-2",
    });
    const [payload] = token.split(".");
    const conf = await conferirAutorizacao(
      `${payload}.assinatura-adulterada`,
      SEGREDO_FALSO,
      AGORA,
    );
    assert.equal(conf.ok, false);
    assert.equal(conf.codigo, "autorizacao_invalida");
  });

  it("recusa token vencido e segredo errado", async () => {
    const token = await emitirAutorizacao({
      segredo: SEGREDO_FALSO,
      rodadaId: "sessao:900",
      aparelhoHash: "hash-falso",
      dentro: true,
      agoraS: AGORA,
      validadeMin: 10,
      jti: "jti-falso-3",
    });
    const vencido = await conferirAutorizacao(token, SEGREDO_FALSO, AGORA + 601);
    assert.equal(vencido.ok, false);
    const segredoErrado = await conferirAutorizacao(token, "segredo-errado-falso", AGORA);
    assert.equal(segredoErrado.ok, false);
  });

  it("recusa formato quebrado", async () => {
    for (const token of ["", "sem-ponto", "a.b.c", "!!!.???"]) {
      const conf = await conferirAutorizacao(token, SEGREDO_FALSO, AGORA);
      assert.equal(conf.ok, false);
    }
  });
});

describe("forma da rodada", () => {
  it("aceita rodada bem formada", () => {
    assert.equal(
      validarFormaRodada(rodadaFalsa(), DADOS_CIDADE.siglas_elegiveis).ok,
      true,
    );
  });

  it("recusa chave de autor, partido ou vereador", () => {
    const rodada = rodadaFalsa();
    rodada.materias[0].autor_nome = "alguem";
    assert.equal(
      validarFormaRodada(rodada, DADOS_CIDADE.siglas_elegiveis).ok,
      false,
    );
  });

  it("recusa sigla fora das elegiveis", () => {
    const rodada = rodadaFalsa([{ id: 1, sigla: "ATA" }]);
    assert.equal(
      validarFormaRodada(rodada, DADOS_CIDADE.siglas_elegiveis).ok,
      false,
    );
  });

  it("sem_materias_elegiveis exige lista vazia", () => {
    const vazia = {
      rodada_id: "sessao:901",
      sessao_id: 901,
      data_sessao: "2026-09-29",
      status: "sem_materias_elegiveis",
      materias: [],
    };
    assert.equal(
      validarFormaRodada(vazia, DADOS_CIDADE.siglas_elegiveis).ok,
      true,
    );
    const cheia = { ...vazia, materias: [{ id: 1, sigla: "IND" }] };
    assert.equal(
      validarFormaRodada(cheia, DADOS_CIDADE.siglas_elegiveis).ok,
      false,
    );
  });
});

describe("ponto no poligono", () => {
  const quadrado = [
    [0, 0],
    [4, 0],
    [4, 4],
    [0, 4],
    [0, 0],
  ];
  const buraco = [
    [1, 1],
    [3, 1],
    [3, 3],
    [1, 3],
    [1, 1],
  ];

  it("dentro, fora e borda", () => {
    assert.equal(pontoNoAnel(2, 2, quadrado), true);
    assert.equal(pontoNoAnel(5, 5, quadrado), false);
    assert.equal(pontoNoAnel(0, 2, quadrado), true);
  });

  it("buraco nao conta como dentro", () => {
    assert.equal(pontoNoPoligono(0.5, 0.5, [quadrado, buraco]), true);
    assert.equal(pontoNoPoligono(2, 2, [quadrado, buraco]), false);
  });

  it("multipoligono acha os dois lados", () => {
    const geo = {
      type: "MultiPolygon",
      coordinates: [
        [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        [[[10, 10], [11, 10], [11, 11], [10, 11], [10, 10]]],
      ],
    };
    assert.equal(geometriaContem(0.5, 0.5, geo), true);
    assert.equal(geometriaContem(10.5, 10.5, geo), true);
    assert.equal(geometriaContem(5, 5, geo), false);
  });

  it("contorno real: dentro e fora a 30 km", () => {
    const contorno = DADOS_CIDADE.contorno;
    assert.equal(dentroDoContorno(-49.6564, -25.9778, contorno), true);
    assert.equal(dentroDoContorno(-49.6564, -25.6277, contorno), false);
  });

  it("faixa da margem aceita, alem da margem recusa", () => {
    const contorno = DADOS_CIDADE.contorno;
    const margem = DADOS_CIDADE.limites.margem_divisa_m;
    const aneis =
      contorno.type === "Polygon"
        ? contorno.coordinates
        : contorno.coordinates.flat();
    const anel = aneis[0];
    let caso = null;
    const direcoes = [
      [1, 0],
      [-1, 0],
      [0, 1],
      [0, -1],
    ];
    for (const [vlon, vlat] of anel) {
      for (const [dlon, dlat] of direcoes) {
        const kx =
          111320.0 * Math.cos((vlat * Math.PI) / 180);
        const perto = [vlon + (dlon * margem * 0.5) / kx, vlat + (dlat * margem * 0.5) / 111320.0];
        const longe = [vlon + (dlon * margem * 5) / kx, vlat + (dlat * margem * 5) / 111320.0];
        if (
          !dentroDoContorno(perto[0], perto[1], contorno) &&
          !dentroDoContorno(longe[0], longe[1], contorno) &&
          distanciaAoContornoM(longe[0], longe[1], contorno) > margem
        ) {
          caso = { perto, longe };
          break;
        }
      }
      if (caso) break;
    }
    assert.ok(caso, "contorno real nao deu ponto fora perto da divisa");
    const base = {
      precisaoM: 10,
      contorno,
      precisaoMaxM: DADOS_CIDADE.limites.precisao_gps_max_m,
      margemM: margem,
    };
    const aceito = decidirLocalizacao({
      ...base,
      lat: caso.perto[1],
      lon: caso.perto[0],
    });
    assert.equal(aceito.dentro, true);
    const recusado = decidirLocalizacao({
      ...base,
      lat: caso.longe[1],
      lon: caso.longe[0],
    });
    assert.equal(recusado.dentro, false);
    assert.equal(recusado.codigo, "fora_do_municipio");
  });

  it("precisao ruim recusa mesmo dentro", () => {
    const r = decidirLocalizacao({
      lat: -25.9778,
      lon: -49.6564,
      precisaoM: DADOS_CIDADE.limites.precisao_gps_max_m + 1,
      contorno: DADOS_CIDADE.contorno,
      precisaoMaxM: DADOS_CIDADE.limites.precisao_gps_max_m,
      margemM: DADOS_CIDADE.limites.margem_divisa_m,
    });
    assert.equal(r.dentro, false);
    assert.equal(r.codigo, "precisao_ruim");
  });
});

describe("validadores de pedido", () => {
  it("verificar: aparelho ausente e pedido invalido", () => {
    assert.equal(
      validarPedidoVerificar({ aparelhoId: "", lat: 1, lon: 1, precisaoM: 10 }),
      "pedido_invalido",
    );
  });

  it("verificar: sem GPS e gps negado", () => {
    assert.equal(
      validarPedidoVerificar({ aparelhoId: "a", lat: null, lon: 1, precisaoM: 10 }),
      "gps_negado",
    );
    assert.equal(
      validarPedidoVerificar({ aparelhoId: "a", lat: 1, lon: 1, precisaoM: null }),
      "gps_negado",
    );
  });

  it("verificar: pedido bom passa", () => {
    assert.equal(
      validarPedidoVerificar({ aparelhoId: "a", lat: 1, lon: 1, precisaoM: 10 }),
      null,
    );
  });

  it("respostas: exige todas, uma por materia, so util ou inutil", () => {
    const materias = [{ id: 11 }, { id: 22 }];
    const boas = [
      { materia_id: 11, valor: "util" },
      { materia_id: 22, valor: "inutil" },
    ];
    assert.equal(validarRespostas(boas, materias), null);
    assert.equal(
      validarRespostas([{ materia_id: 11, valor: "util" }], materias),
      "respostas_incompletas",
    );
    assert.equal(
      validarRespostas([...boas, { materia_id: 99, valor: "util" }], materias),
      "materia_invalida",
    );
    assert.equal(
      validarRespostas(
        [
          { materia_id: 11, valor: "util" },
          { materia_id: 11, valor: "inutil" },
        ],
        materias,
      ),
      "materia_invalida",
    );
    assert.equal(
      validarRespostas(
        [
          { materia_id: 11, valor: "talvez" },
          { materia_id: 22, valor: "util" },
        ],
        materias,
      ),
      "valor_invalido",
    );
  });
});

describe("resultados e limites", () => {
  it("esconde numero exato abaixo do minimo", () => {
    const minimo = DADOS_CIDADE.limites.minimo_respostas_por_materia;
    const oculto = formatarMateriaResultado({
      materiaId: 5,
      util: 3,
      inutil: 1,
      minimo,
    });
    assert.equal(oculto.respostas, `menos de ${minimo}`);
    assert.equal(oculto.percentual_util, null);
    assert.equal(oculto.percentual_inutil, null);
  });

  it("mostra percentual inteiro no minimo ou acima", () => {
    const minimo = DADOS_CIDADE.limites.minimo_respostas_por_materia;
    const visivel = formatarMateriaResultado({
      materiaId: 5,
      util: 7,
      inutil: 3,
      minimo,
    });
    assert.equal(visivel.respostas, 10);
    assert.equal(visivel.percentual_util, 70);
    assert.equal(visivel.percentual_inutil, 30);
  });

  it("janela de limite e conta regressiva", () => {
    assert.equal(janelaIndice(125, 60), 2);
    assert.equal(tentarDepoisS(125, 60), 55);
    const corpo = corpoLimiteExcedido(55);
    assert.equal(corpo.codigo, "limite_pedidos");
    assert.equal(corpo.tentar_depois_s, 55);
  });

  it("modo de teste so pula GPS em ambiente de teste com segredo", () => {
    const segredo = "segredo-falso-de-modo-teste";
    assert.equal(
      modoTestePularGps({ ambiente: "teste", cabecalhoValor: segredo, segredo }),
      true,
    );
    assert.equal(
      modoTestePularGps({ ambiente: "producao", cabecalhoValor: segredo, segredo }),
      false,
    );
    assert.equal(
      modoTestePularGps({ ambiente: "teste", cabecalhoValor: "errado", segredo }),
      false,
    );
    assert.equal(
      modoTestePularGps({ ambiente: "teste", cabecalhoValor: "", segredo }),
      false,
    );
  });

  it("mensagens sem travessao e sem segredo", () => {
    for (const texto of Object.values(MENSAGENS_ERRO)) {
      assert.ok(!texto.includes("—") && !texto.includes("–"), texto);
    }
  });
});
