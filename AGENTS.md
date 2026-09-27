# Regras Obrigatórias para Agentes de IA (AGENTS.md)
## Projeto: Em Pratos Limpos (Campo Largo - PR)

Este arquivo é de leitura compulsória para qualquer agente autônomo, assistente de IA, LLM ou ferramenta de automação (Antigravity, Cursor, Claude Code, Codex, Aider, Copilot, Grok, DeepSeek, etc.) antes de ler, editar ou executar qualquer arquivo neste repositório.

A norma técnica soberana deste projeto é o documento:
`PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md`

---

## 1. Princípios Operacionais Inegociáveis

1. **Quem Decide:**
   * O mantenedor único, proprietário e gatekeeper final do projeto é quem decide.
   * Nenhuma alteração estrutural, decisão visual, inclusão de dados ou publicação pode ir para produção sem a revisão humana e aprovação explícita do mantenedor.

2. **Estilo de Comunicação com o Mantenedor:**
   * **Estritamente SEM TRAVESSAO:** E terminantemente proibido utilizar caracteres de travessao (em dash ou en dash) ou hifen como pontuacao em qualquer comunicacao, relatorio, commit ou texto direcionado ao mantenedor. Utilize virgulas, dois pontos, pontos finais, parenteses ou hifens simples de listas ("- ").
   * **Estimativas Realistas em Minutos:** Para qualquer tarefa delegada, processo em andamento ou ação futura, forneça sempre uma estimativa realista de tempo em minutos.
   * **Linguagem Acessível:** O mantenedor não é programador. Explicações devem ser em português do Brasil, claras, diretas e sem jargões desnecessários de código.

3. **OPSEC e Privacidade Absoluta:**
   * Proibição expressa de expor e-mails pessoais, nomes de usuários da máquina local, caminhos absolutos de arquivos do sistema operacional ou tokens/chaves privadas em commits, documentações, logs ou mensagens.
   * Política de "Zero Secrets" no Git.

4. **Imparcialidade Cívica e Rigor com Dados:**
   * Zero rankings políticos, juízos de valor, notas, estrelas ou termos comparativos entre vereadores.
   * Todo número na tela deve ter origem oficial rastreável no SAPL da Câmara de Campo Largo (`sapl.campolargo.pr.leg.br`).
   * Ausência não é voto: registrar com precisão presenças, faltas justificadas e faltas não justificadas.
   * Não invente dados: ausência de dado no SAPL deve ser tratada com clareza, nunca preenchida com estimativas ou valores fictícios.

---

## 2. Segregação de Ambientes e Fluxo de Branches

* **Branch `main` (Produção):**
  * Espelho do GitHub Pages público (`https://empratoslimposcl.github.io/em-pratos-limpos/`).
  * **NUNCA** commite diretamente na branch `main`.
  * **NUNCA** faça force push (`git push --force`).
   * Atualizações em `main` só ocorrem via Pull Request formal após validação e aprovação do mantenedor.
* **Branch `desenvolvimento` (Staging e Integração):**
  * Ambiente de trabalho contínuo onde modificações são criadas, testadas e validadas localmente.
* **Branches Temporárias (`feature/*`, `hotfix/*`, `atualizacao-dados/*`):**
  * Devem ser ramificadas a partir de `desenvolvimento`.

---

## 3. Checklist Técnico Obrigatório antes de qualquer PR

Qualquer agente que realize alterações deve validar localmente:

1. **Testes de Sanidade (100% de Aprovação):**
   * `python coletor/testes_sanidade.py`
   * `python -m unittest tests/test_sanidade_dados.py`
   * Pisos mínimos obrigatórios: contagem de sessões ordinárias >= 26, PLLs >= 100, exatamente 15 vereadores cadastrados e registros de votação consistentes.
2. **Integridade Criptográfica:**
   * Executar `python coletor/gerar_hash_integridade.py` sempre que a base consolidada de atuação dos vereadores for alterada.
3. **Segurança Web (AppSec):**
   * Manter Content Security Policy (CSP) estrita no `index.html`.
   * Toda inserção de dados externos no DOM deve passar pela função `esc()`.
   * O `esc()` trata e remove sequências de escape ANSI e caracteres de controle perigosos.
4. **Respeito à Infraestrutura Pública:**
   * O rate-limiting de 2.5 segundos entre requisições ao SAPL no coletor Python **nunca** pode ser reduzido, contornado ou paralelizado.
5. **Execução Local:**
   * Testar sempre via servidor HTTP local (`python -m http.server 8000`), nunca via protocolo `file://`.

---

## Proibições absolutas para agentes de IA

1. NUNCA faça merge em main sem aprovação expressa do mantenedor
2. NUNCA aprove seu próprio PR
3. NUNCA faça deploy para produção sem aprovação do mantenedor
4. NUNCA crie, edite ou exclua secrets sem aprovação do mantenedor
5. NUNCA faça rollback sem aprovação do mantenedor
6. NUNCA ignore o checklist pré-deploy (seção 5.2 do PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md)

Violação de qualquer regra acima é considerada incidente de governança e deve ser revertida imediatamente.

**Classificação:** Violação de governança, não urgência. A urgência justifica prioridade de revisão, jamais a supressão da revisão.
