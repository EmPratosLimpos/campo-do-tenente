-- Esquema D1 da votacao popular. Tabelas exclusivas desta cidade, prefixo vp_.
--
-- Nenhum numero de limite fixo aqui: o teto por endereco fica em vp_config,
-- gravado pelo Worker a partir de src/dados_cidade.js (gerado do config),
-- para o trigger do teto ler dentro da mesma transacao.
--
-- Colunas ementa e link_sapl em vp_materias: extensao aditiva a ESPEC secao 3
-- para GET /api/rodada sair do D1, a mesma fonte que valida o voto.
-- Coluna expira_em em vp_autorizacoes e INTEGER com segundos desde a epoca.

CREATE TABLE vp_rodadas (
  rodada_id TEXT PRIMARY KEY,
  sessao_id INTEGER UNIQUE NOT NULL,
  data_sessao TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'aberta',
  criada_em TEXT NOT NULL,
  fechada_em TEXT
);

CREATE TABLE vp_materias (
  rodada_id TEXT NOT NULL REFERENCES vp_rodadas(rodada_id),
  materia_id INTEGER NOT NULL,
  sigla TEXT NOT NULL,
  numero TEXT NOT NULL,
  ano TEXT NOT NULL,
  ordem_pauta INTEGER NOT NULL,
  ementa TEXT NOT NULL DEFAULT '',
  link_sapl TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (rodada_id, materia_id)
);

CREATE TABLE vp_totais (
  rodada_id TEXT NOT NULL,
  materia_id INTEGER NOT NULL,
  total_util INTEGER NOT NULL DEFAULT 0,
  total_inutil INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (rodada_id, materia_id)
);

CREATE TABLE vp_participacoes (
  rodada_id TEXT NOT NULL,
  aparelho_hash TEXT NOT NULL,
  endereco_hash TEXT NOT NULL,
  criada_em TEXT NOT NULL,
  PRIMARY KEY (rodada_id, aparelho_hash)
);

CREATE TABLE vp_votos (
  rodada_id TEXT NOT NULL,
  materia_id INTEGER NOT NULL,
  aparelho_hash TEXT NOT NULL,
  valor TEXT NOT NULL CHECK (valor IN ('util', 'inutil')),
  PRIMARY KEY (rodada_id, aparelho_hash, materia_id)
);

CREATE TABLE vp_autorizacoes (
  jti TEXT PRIMARY KEY,
  rodada_id TEXT NOT NULL,
  aparelho_hash TEXT NOT NULL,
  expira_em INTEGER NOT NULL,
  usada INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE vp_taxa (
  endereco_hash TEXT NOT NULL,
  janela_minuto INTEGER NOT NULL,
  contagem INTEGER NOT NULL,
  PRIMARY KEY (endereco_hash, janela_minuto)
);

-- Config gravado pelo Worker. O trigger do teto le daqui dentro do batch,
-- entao dois votos simultaneos do mesmo endereco nao passam do teto.
CREATE TABLE vp_config (
  chave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);

CREATE INDEX idx_vp_part_endereco ON vp_participacoes (rodada_id, endereco_hash);
CREATE INDEX idx_vp_votos_materia ON vp_votos (rodada_id, materia_id);

-- Teto por endereco atomico: aborta o INSERT (e com ele o batch inteiro)
-- quando a contagem do endereco na rodada ja atingiu o teto.
CREATE TRIGGER trg_vp_teto_endereco
BEFORE INSERT ON vp_participacoes
WHEN (
  (SELECT COUNT(*) FROM vp_participacoes
    WHERE rodada_id = NEW.rodada_id
      AND endereco_hash = NEW.endereco_hash)
  >=
  (SELECT CAST(valor AS INTEGER) FROM vp_config
    WHERE chave = 'teto_votos_por_endereco_por_rodada')
)
BEGIN
  SELECT RAISE(ABORT, 'teto_endereco');
END;

-- Uso unico da autorizacao: o segundo UPDATE no mesmo jti aborta o batch.
CREATE TRIGGER trg_vp_autorizacao_uso_unico
BEFORE UPDATE OF usada ON vp_autorizacoes
WHEN OLD.usada <> 0
BEGIN
  SELECT RAISE(ABORT, 'autorizacao_reutilizada');
END;
