-- Esquema D1 da votacao popular. Tabelas exclusivas desta cidade, prefixo vp_.
--
-- Nenhum numero de limite fixo aqui: o teto por endereco fica em vp_config,
-- gravado pelo Worker a partir de src/dados_cidade.js (gerado do config),
-- como primeira instrucao do proprio batch do voto, para o trigger do teto
-- ler dentro da mesma transacao. Sem a linha do teto em vp_config, o trigger
-- falha fechado e recusa a participacao com teto_endereco.
--
-- A coluna jti em vp_participacoes nao e dado pessoal: e o id da autorizacao
-- de uso unico. O trigger da autorizacao confere, dentro da mesma transacao,
-- que existe linha em vp_autorizacoes com o mesmo jti, rodada e aparelho ja
-- marcada como usada. Sem ela, o batch aborta com autorizacao_invalida e
-- nada e gravado.
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
  jti TEXT NOT NULL,
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

-- Teto por endereco atomico e com falha fechada: aborta o INSERT (e com ele
-- o batch inteiro) quando a contagem do endereco na rodada ja atingiu o teto.
-- Sem a linha do teto em vp_config, o COALESCE vira 0 e qualquer contagem
-- (ate zero) aborta com teto_endereco. A chave aqui tem de ser igual a
-- constante CHAVE_TETO em src/index.js; ha teste que falha se divergir.
CREATE TRIGGER trg_vp_teto_endereco
BEFORE INSERT ON vp_participacoes
WHEN (
  (SELECT COUNT(*) FROM vp_participacoes
    WHERE rodada_id = NEW.rodada_id
      AND endereco_hash = NEW.endereco_hash)
  >=
  COALESCE(
    (SELECT CAST(valor AS INTEGER) FROM vp_config
      WHERE chave = 'teto_votos_por_endereco_por_rodada'),
    0
  )
)
BEGIN
  SELECT RAISE(ABORT, 'teto_endereco');
END;

-- Autorizacao valida dentro da mesma transacao: aborta o INSERT (e com ele
-- o batch inteiro) quando nao existe linha em vp_autorizacoes com o mesmo
-- jti, rodada e aparelho ja marcada como usada. O UPDATE que marca usada = 1
-- e a primeira escrita util do batch, entao um jti inexistente, ainda nao
-- marcado ou de outra rodada ou aparelho aborta aqui com autorizacao_invalida
-- antes de qualquer participacao, voto ou total ser gravado.
CREATE TRIGGER trg_vp_participacao_autorizacao
BEFORE INSERT ON vp_participacoes
WHEN (
  NOT EXISTS (
    SELECT 1 FROM vp_autorizacoes
    WHERE jti = NEW.jti
      AND rodada_id = NEW.rodada_id
      AND aparelho_hash = NEW.aparelho_hash
      AND usada <> 0
  )
)
BEGIN
  SELECT RAISE(ABORT, 'autorizacao_invalida');
END;

-- Uso unico da autorizacao: o segundo UPDATE no mesmo jti aborta o batch.
CREATE TRIGGER trg_vp_autorizacao_uso_unico
BEFORE UPDATE OF usada ON vp_autorizacoes
WHEN OLD.usada <> 0
BEGIN
  SELECT RAISE(ABORT, 'autorizacao_reutilizada');
END;
