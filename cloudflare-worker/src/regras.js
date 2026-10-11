// Logica pura da votacao popular. Sem D1, sem rede, sem relogio real.
//
// Tudo que varia por cidade ou por aprovacao (limites, siglas, contorno,
// dias de rodada) chega por parametro, a partir de src/dados_cidade.js
// (gerado de config_cidade.json). Nenhum numero, cidade, codigo IBGE ou
// endereco fixo aqui.
//
// Convenções de GeoJSON: posicao e [lon, lat], em graus decimais.

export const METROS_POR_GRAU_LAT = 111320.0;

export const VALORES_VOTO = ["util", "inutil"];

// Mensagens em pt-BR, sem dado pessoal, sem segredo, sem coordenada.
export const MENSAGENS_ERRO = {
  pedido_invalido: "Pedido invalido. Recarregue a pagina e tente de novo.",
  gps_negado: "Ative a localizacao do aparelho para participar.",
  precisao_ruim: "Sinal de localizacao fraco. Tente de novo em local aberto.",
  fora_do_municipio:
    "Voce parece estar fora do municipio. A consulta vale para quem esta no municipio.",
  captcha_invalido: "Verificacao anti robo falhou. Tente de novo.",
  corpo_grande: "Pedido grande demais. Tente de novo.",
  ja_votou: "Este aparelho ja votou nesta rodada.",
  teto_endereco: "Muitos votos nesta conexao para esta rodada.",
  limite_pedidos: "Muitos pedidos. Aguarde e tente de novo.",
  rodada_fechada: "Esta rodada ja fechou.",
  rodada_sem_materias: "Esta rodada nao tem materias para votar.",
  respostas_incompletas: "Responda todas as materias da rodada.",
  materia_invalida: "Materia fora desta rodada.",
  valor_invalido: "Resposta invalida. Use Util ou Inutil.",
  autorizacao_invalida:
    "Autorizacao invalida ou vencida. Refaca a verificacao.",
  autorizacao_reutilizada: "Autorizacao ja usada. Refaca a verificacao.",
  erro_interno: "Servidor indisponivel. Tente de novo em instantes.",
};

// Chaves que nunca podem aparecer na rodada que o Worker aceita.
// Mesma regra de scripts/verificar_regras.py: autor, partido, vereador.
const PARTES_PROIBIDAS_RODADA = ["autor", "partido", "vereador"];

// ---------------------------------------------------------------------------
// Base64url e HMAC (WebCrypto, presente no Worker e no Node 18 ou mais novo)
// ---------------------------------------------------------------------------

export function bytesParaBase64url(bytes) {
  const bin = Array.from(bytes, (b) => String.fromCharCode(b)).join("");
  let b64;
  if (typeof btoa === "function") {
    b64 = btoa(bin);
  } else {
    b64 = Buffer.from(bin, "binary").toString("base64");
  }
  return b64.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function base64urlParaBytes(texto) {
  const b64 = String(texto || "")
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const resto = b64.length % 4;
  const completo = resto === 0 ? b64 : b64 + "=".repeat(4 - resto);
  let bin;
  if (typeof atob === "function") {
    bin = atob(completo);
  } else {
    bin = Buffer.from(completo, "base64").toString("binary");
  }
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) {
    bytes[i] = bin.charCodeAt(i);
  }
  return bytes;
}

function textoParaBytes(texto) {
  return new TextEncoder().encode(String(texto));
}

// HMAC SHA-256 com o segredo da cidade. Rotulos da ESPEC secao 3.
export function rotuloAparelho(rodadaId, aparelhoId) {
  return `aparelho|${rodadaId}|${aparelhoId}`;
}

export function rotuloEndereco(rodadaId, endereco) {
  return `endereco|${rodadaId}|${endereco}`;
}

export function rotuloTaxa(rota, endereco) {
  return `taxa|${rota}|${endereco}`;
}

export async function hmacHex(segredo, mensagem) {
  const chave = await crypto.subtle.importKey(
    "raw",
    textoParaBytes(segredo),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const assinatura = await crypto.subtle.sign(
    "HMAC",
    chave,
    textoParaBytes(mensagem),
  );
  return Array.from(new Uint8Array(assinatura), (b) =>
    b.toString(16).padStart(2, "0"),
  ).join("");
}

async function assinarPayload(segredo, payloadB64) {
  const chave = await crypto.subtle.importKey(
    "raw",
    textoParaBytes(segredo),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const assinatura = await crypto.subtle.sign(
    "HMAC",
    chave,
    textoParaBytes(payloadB64),
  );
  return bytesParaBase64url(new Uint8Array(assinatura));
}

// Comparacao que nao para no primeiro byte diferente.
function comparacaoFixa(a, b) {
  const xa = String(a || "");
  const xb = String(b || "");
  if (xa.length !== xb.length || xa.length === 0) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < xa.length; i += 1) {
    diff |= xa.charCodeAt(i) ^ xb.charCodeAt(i);
  }
  return diff === 0;
}

// ---------------------------------------------------------------------------
// Autorizacao de uso unico: <base64url(payload)>.<base64url(assinatura)>
// ---------------------------------------------------------------------------

export async function emitirAutorizacao({
  segredo,
  rodadaId,
  aparelhoHash,
  dentro,
  agoraS,
  validadeMin,
  jti,
}) {
  const payload = {
    v: 1,
    jti,
    rodada: rodadaId,
    h_aparelho: aparelhoHash,
    dentro: dentro ? 1 : 0,
    iat: agoraS,
    exp: agoraS + validadeMin * 60,
  };
  const payloadB64 = bytesParaBase64url(
    textoParaBytes(JSON.stringify(payload)),
  );
  const assinaturaB64 = await assinarPayload(segredo, payloadB64);
  return `${payloadB64}.${assinaturaB64}`;
}

// Confere forma, assinatura e validade. Nao toca no banco.
export async function conferirAutorizacao(token, segredo, agoraS) {
  const partes = String(token || "").split(".");
  if (partes.length !== 2 || !partes[0] || !partes[1]) {
    return { ok: false, codigo: "autorizacao_invalida" };
  }
  const esperado = await assinarPayload(segredo, partes[0]);
  if (!comparacaoFixa(esperado, partes[1])) {
    return { ok: false, codigo: "autorizacao_invalida" };
  }
  let payload;
  try {
    const texto = new TextDecoder().decode(base64urlParaBytes(partes[0]));
    payload = JSON.parse(texto);
  } catch {
    return { ok: false, codigo: "autorizacao_invalida" };
  }
  if (
    !payload ||
    payload.v !== 1 ||
    typeof payload.jti !== "string" ||
    !payload.jti ||
    typeof payload.rodada !== "string" ||
    !payload.rodada ||
    typeof payload.h_aparelho !== "string" ||
    !payload.h_aparelho ||
    typeof payload.iat !== "number" ||
    typeof payload.exp !== "number"
  ) {
    return { ok: false, codigo: "autorizacao_invalida" };
  }
  if (payload.exp <= agoraS) {
    return { ok: false, codigo: "autorizacao_invalida" };
  }
  return { ok: true, payload };
}

// ---------------------------------------------------------------------------
// Forma da rodada vinda de RODADA_URL
// ---------------------------------------------------------------------------

function temChaveProibida(valor) {
  if (Array.isArray(valor)) {
    return valor.some(temChaveProibida);
  }
  if (valor && typeof valor === "object") {
    return Object.entries(valor).some(
      ([chave, item]) =>
        PARTES_PROIBIDAS_RODADA.some((parte) =>
          String(chave).toLowerCase().includes(parte),
        ) || temChaveProibida(item),
    );
  }
  return false;
}

export function validarFormaRodada(obj, siglasElegiveis) {
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) {
    return { ok: false, motivo: "forma" };
  }
  if (typeof obj.rodada_id !== "string" || !obj.rodada_id) {
    return { ok: false, motivo: "forma" };
  }
  if (typeof obj.sessao_id !== "number" || !Number.isInteger(obj.sessao_id)) {
    return { ok: false, motivo: "forma" };
  }
  if (typeof obj.data_sessao !== "string" || !obj.data_sessao) {
    return { ok: false, motivo: "forma" };
  }
  if (!["aberta", "sem_materias_elegiveis"].includes(obj.status)) {
    return { ok: false, motivo: "forma" };
  }
  if (!Array.isArray(obj.materias)) {
    return { ok: false, motivo: "forma" };
  }
  if (temChaveProibida(obj)) {
    return { ok: false, motivo: "autor" };
  }
  const elegiveis = new Set(siglasElegiveis || []);
  for (const materia of obj.materias) {
    if (!materia || typeof materia !== "object") {
      return { ok: false, motivo: "forma" };
    }
    if (typeof materia.id !== "number" || !Number.isInteger(materia.id)) {
      return { ok: false, motivo: "forma" };
    }
    if (!elegiveis.has(materia.sigla)) {
      return { ok: false, motivo: "sigla" };
    }
  }
  if (obj.status === "sem_materias_elegiveis" && obj.materias.length !== 0) {
    return { ok: false, motivo: "forma" };
  }
  return { ok: true };
}

// ---------------------------------------------------------------------------
// Ponto no poligono e distancia a divisa (plano local equiretangular)
// ---------------------------------------------------------------------------

function paraPlano(lon, lat, lon0, lat0) {
  const kx = METROS_POR_GRAU_LAT * Math.cos((lat0 * Math.PI) / 180);
  return [(lon - lon0) * kx, (lat - lat0) * METROS_POR_GRAU_LAT];
}

function distPontoSegmento(px, py, ax, ay, bx, by) {
  const dx = bx - ax;
  const dy = by - ay;
  if (dx === 0 && dy === 0) {
    return Math.hypot(px - ax, py - ay);
  }
  let t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy);
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

export function pontoNoAnel(lon, lat, anel) {
  let dentro = false;
  const n = anel ? anel.length : 0;
  if (n < 3) {
    return false;
  }
  for (let i = 0; i < n; i += 1) {
    const [x1, y1] = anel[i];
    const [x2, y2] = anel[(i + 1) % n];
    if (distPontoSegmento(lon, lat, x1, y1, x2, y2) === 0) {
      return true;
    }
    if (y1 > lat !== y2 > lat) {
      const xinters = ((x2 - x1) * (lat - y1)) / (y2 - y1) + x1;
      if (lon < xinters) {
        dentro = !dentro;
      }
    }
  }
  return dentro;
}

export function pontoNoPoligono(lon, lat, aneis) {
  if (!aneis || aneis.length === 0) {
    return false;
  }
  if (!pontoNoAnel(lon, lat, aneis[0])) {
    return false;
  }
  for (let i = 1; i < aneis.length; i += 1) {
    if (pontoNoAnel(lon, lat, aneis[i])) {
      return false;
    }
  }
  return true;
}

export function geometriaContem(lon, lat, geometria) {
  const tipo = geometria ? geometria.type : "";
  const coords = (geometria && geometria.coordinates) || [];
  if (tipo === "Polygon") {
    return pontoNoPoligono(lon, lat, coords);
  }
  if (tipo === "MultiPolygon") {
    return coords.some((poly) => pontoNoPoligono(lon, lat, poly));
  }
  return false;
}

export function dentroDoContorno(lon, lat, contorno) {
  if (!contorno || typeof contorno !== "object") {
    return false;
  }
  if (contorno.type === "FeatureCollection") {
    return (contorno.features || []).some(
      (f) => f && geometriaContem(lon, lat, f.geometry || {}),
    );
  }
  if (contorno.type === "Feature") {
    return geometriaContem(lon, lat, contorno.geometry || {});
  }
  return geometriaContem(lon, lat, contorno);
}

function aneisDaGeometria(geometria) {
  if (!geometria) {
    return [];
  }
  if (geometria.type === "Polygon") {
    return geometria.coordinates || [];
  }
  if (geometria.type === "MultiPolygon") {
    return (geometria.coordinates || []).flat();
  }
  return [];
}

function aneisDoContorno(contorno) {
  if (!contorno || typeof contorno !== "object") {
    return [];
  }
  if (contorno.type === "FeatureCollection") {
    return (contorno.features || []).flatMap((f) =>
      aneisDaGeometria((f || {}).geometry || {}),
    );
  }
  if (contorno.type === "Feature") {
    return aneisDaGeometria(contorno.geometry || {});
  }
  return aneisDaGeometria(contorno);
}

// Menor distancia em metros do ponto a divisa. Mesma projecao local do
// script dados/territorio/simplificar_contorno.py.
export function distanciaAoContornoM(lon, lat, contorno) {
  const aneis = aneisDoContorno(contorno);
  let menor = Infinity;
  for (const anel of aneis) {
    for (let i = 0; i < anel.length; i += 1) {
      const [ax, ay] = anel[i];
      const [bx, by] = anel[(i + 1) % anel.length];
      const lon0 = (ax + bx) / 2;
      const lat0 = (ay + by) / 2;
      const [px, py] = paraPlano(lon, lat, lon0, lat0);
      const [qx, qy] = paraPlano(ax, ay, lon0, lat0);
      const [rx, ry] = paraPlano(bx, by, lon0, lat0);
      const d = distPontoSegmento(px, py, qx, qy, rx, ry);
      if (d < menor) {
        menor = d;
      }
    }
  }
  return menor;
}

// Decide dentro ou fora. Ponto dentro da margem PARA FORA conta como dentro.
// Nunca devolve a coordenada, so o resultado.
export function decidirLocalizacao({
  lat,
  lon,
  precisaoM,
  contorno,
  precisaoMaxM,
  margemM,
}) {
  if (typeof precisaoM !== "number" || precisaoM > precisaoMaxM) {
    return { dentro: false, codigo: "precisao_ruim" };
  }
  if (dentroDoContorno(lon, lat, contorno)) {
    return { dentro: true };
  }
  const distancia = distanciaAoContornoM(lon, lat, contorno);
  if (distancia <= margemM) {
    return { dentro: true };
  }
  return { dentro: false, codigo: "fora_do_municipio" };
}

// ---------------------------------------------------------------------------
// Validadores de pedido
// ---------------------------------------------------------------------------

export function validarPedidoVerificar({ aparelhoId, lat, lon, precisaoM }) {
  if (typeof aparelhoId !== "string" || !aparelhoId.trim()) {
    return "pedido_invalido";
  }
  if (
    aparelhoId.length > 200 ||
    typeof lat !== "number" ||
    typeof lon !== "number" ||
    !Number.isFinite(lat) ||
    !Number.isFinite(lon)
  ) {
    if (
      typeof lat !== "number" ||
      typeof lon !== "number" ||
      !Number.isFinite(lat) ||
      !Number.isFinite(lon)
    ) {
      return "gps_negado";
    }
    return "pedido_invalido";
  }
  if (typeof precisaoM !== "number" || !Number.isFinite(precisaoM)) {
    return "gps_negado";
  }
  return null;
}

// Materias exatamente as da rodada: todas, uma por materia, sem extra.
export function validarRespostas(respostas, materias) {
  const idsRodada = (materias || []).map((m) => m.id);
  if (!Array.isArray(respostas) || respostas.length === 0) {
    return "respostas_incompletas";
  }
  const vistos = new Set();
  for (const resposta of respostas) {
    if (!resposta || typeof resposta !== "object") {
      return "materia_invalida";
    }
    if (!idsRodada.includes(resposta.materia_id)) {
      return "materia_invalida";
    }
    if (vistos.has(resposta.materia_id)) {
      return "materia_invalida";
    }
    vistos.add(resposta.materia_id);
    if (!VALORES_VOTO.includes(resposta.valor)) {
      return "valor_invalido";
    }
  }
  if (vistos.size !== idsRodada.length) {
    return "respostas_incompletas";
  }
  return null;
}

// ---------------------------------------------------------------------------
// Resultados: percentual so com minimo de respostas
// ---------------------------------------------------------------------------

export function formatarMateriaResultado({ materiaId, util, inutil, minimo }) {
  const total = util + inutil;
  if (total < minimo) {
    return {
      materia_id: materiaId,
      respostas: `menos de ${minimo}`,
      percentual_util: null,
      percentual_inutil: null,
    };
  }
  // Acima do minimo, com as contagens exatas por lado. O segundo percentual
  // e o complemento do primeiro, para os dois somarem sempre 100.
  const percentualUtil = Math.round((util / total) * 100);
  return {
    materia_id: materiaId,
    respostas: total,
    total_util: util,
    total_inutil: inutil,
    percentual_util: percentualUtil,
    percentual_inutil: 100 - percentualUtil,
  };
}

// ---------------------------------------------------------------------------
// Limite de pedidos e modo de teste
// ---------------------------------------------------------------------------

export function janelaIndice(agoraS, janelaS) {
  return Math.floor(agoraS / janelaS);
}

export function tentarDepoisS(agoraS, janelaS) {
  return (janelaIndice(agoraS, janelaS) + 1) * janelaS - agoraS;
}

export function corpoLimiteExcedido(tentarDepois) {
  return {
    codigo: "limite_pedidos",
    erro: MENSAGENS_ERRO.limite_pedidos,
    tentar_depois_s: tentarDepois,
  };
}

// Pular o GPS so vale com AMBIENTE igual a teste E cabecalho igual ao
// segredo. Na producao e sempre falso, mesmo com segredo presente.
export function modoTestePularGps({ ambiente, cabecalhoValor, segredo }) {
  if (ambiente !== "teste") {
    return false;
  }
  if (!segredo || !cabecalhoValor) {
    return false;
  }
  return comparacaoFixa(cabecalhoValor, segredo);
}
