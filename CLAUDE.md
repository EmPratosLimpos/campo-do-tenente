# Claude Code CLI Guidelines (CLAUDE.md)
## Projeto: Em Pratos Limpos (Campo Largo - PR)

Este arquivo é lido automaticamente pela CLI do Claude Code (`claude`) ao iniciar qualquer sessão neste repositório.

A norma técnica soberana de governança do projeto é:
`PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md`

---

## Regras Obrigatórias de Comportamento

1. **Restrição de Pontuação com o Mantenedor:**
   * ESTRITAMENTE SEM TRAVESSAO: Nunca use caracteres de travessao (em dash ou en dash) ou hifen como pontuacao em respostas, relatorios ou commits. Use virgulas, dois pontos, pontos finais, parenteses ou hifens simples de listas ("- ").
2. **Estimativas de Tempo:**
   * Sempre forneça estimativas realistas em minutos para qualquer tarefa ou execução.
3. **Decisão e Autoridade:**
   * O mantenedor é o aprovador exclusivo. Não execute merges em `main` ou publicações sem a aprovação prévia e expressa dele.
4. **Segregação de Branches:**
   * Trabalhe SEMPRE na branch `desenvolvimento` (ou em branches `feature/*`).
   * NUNCA faça commits diretos na branch `main`.
   * NUNCA execute `git push --force`.
5. **OPSEC e Sigilo:**
   * Nunca exiba ou registre em arquivos do Git e-mails pessoais, nomes locais de usuários ou caminhos absolutos locais de diretórios.
   * Política de Zero Secrets.

---

## Comandos Comuns de Desenvolvimento

* **Servidor local de visualização:**
  `python -m http.server 8000` (acesse `http://localhost:8000/index.html`)
* **Executar suíte de sanidade de dados:**
  `python coletor/testes_sanidade.py`
  `python -m unittest tests/test_sanidade_dados.py`
* **Atualizar hash de integridade:**
  `python coletor/gerar_hash_integridade.py`
* **Rate-limiting do SAPL:**
  Manter obrigatoriamente pausa de 2.5s entre requisições em `coletor/baixar_voto_presenca_ordinarias_2026.py`.

---

## Padrões de Código e Segurança (AppSec)

* **SPA Estática:** O `index.html` não possui dependências de compilação/build complexas.
* **CSP:** Manter diretivas restritas (`frame-src 'none'`, `child-src 'none'`, `worker-src 'none'`).
* **Sanitização XSS:** Todo texto externo vindo de JSON ou API deve passar obrigatoriamente pela função `esc()`, que também remove sequências ANSI.
* **Imparcialidade:** Nenhum juízo de valor, nota política ou ranking partidário.
