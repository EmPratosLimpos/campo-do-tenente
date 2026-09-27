# Processo de Desenvolvimento, Governança, Segurança e Publicação
## Projeto: Em Pratos Limpos (Campo Largo - PR)

| Campo | Valor |
| :--- | :--- |
| Documento | Política Oficial de Governança, Desenvolvimento, Segurança e Publicação |
| Versão | 1.0 (documento definitivo) |
| Data de vigência | 16 de setembro de 2026 |
| Repositório | `empratoslimposcl/em-pratos-limpos` |
| Ambiente de produção | `https://empratoslimpos.pages.dev` |
| Branch de produção | `main` (protegida) |
| Branch de integração | `desenvolvimento` |
| Classificação | Público (o projeto é cívico e auditável por qualquer cidadão) |
| Aprovador único | Mantenedor e Gatekeeper do projeto |
| Ciclo de revisão | Semestral, ou imediato após incidente de segurança ou mudança estrutural |

---

## 0. Propósito, Escopo e Princípios Reitores

### 0.1 Propósito

O projeto "Em Pratos Limpos" é um portal cívico de transparência que consolida, organiza e apresenta a atuação parlamentar dos 15 vereadores oficiais da Câmara Municipal de Campo Largo, Paraná. Diferente de um software comercial, o produto aqui entregue é **confiança pública**. Um dado errado, uma contagem inflada ou uma sessão faltante não gera apenas um bug: gera desinformação cívica e destrói a credibilidade do projeto perante a comunidade.

Este documento estabelece, em caráter normativo e obrigatório, o processo completo que vai da escrita da primeira linha de código até a homologação do dado publicado ao vivo.

### 0.2 Escopo

Aplica-se integralmente a:

- `index.html`: aplicação SPA estática, com Content Security Policy estrita e camada de sanitização `esc()`.
- `coletor/`: scripts Python de coleta determinística contra o sistema SAPL da Câmara, com rate-limiting de 2.5 segundos.
- `coletor/gerar_hash_integridade.py`: gerador do arquivo `atuacao_vereadores_2026.json.sha256`.
- `coletor/testes_sanidade.py` e `tests/test_sanidade_dados.py`: suíte de sanidade de dados.
- `.github/workflows/atualizacao_semanal.yml`: esteira de automação semanal, backup e abertura de Pull Request.
- Toda documentação, dataset e artefato versionado no repositório.

### 0.3 Princípios reitores

| Princípio | Significado prático |
| :--- | :--- |
| Verdade verificável | Nenhum número aparece na tela sem origem rastreável no SAPL e sem hash de integridade correspondente. |
| Determinismo | A mesma coleta, sobre a mesma base, produz o mesmo resultado. Nada de aleatoriedade, nada de estimativa. |
| Menor privilégio | Cada token, cada workflow e cada permissão recebem o mínimo necessário e nada além disso. |
| Ambiente segregado | Produção nunca é laboratório. Experimentação vive e morre fora da `main`. |
| Zero Secrets | Segredo em repositório público é segredo vazado, sem exceções e sem atenuantes. |
| OPSEC por padrão | Nenhum dado pessoal do mantenedor, nenhum caminho de máquina local, nenhum nome de usuário do sistema operacional entra no repositório. |
| Reversibilidade | Toda publicação precisa ter um caminho de volta ensaiado e documentado. |

### 0.4 Papéis e responsabilidades (matriz RACI)

| Atividade | Mantenedor | Agente de IA / Assistente | Automação (GitHub Actions) | Comunidade |
| :--- | :---: | :---: | :---: | :---: |
| Definir escopo e prioridade | R, A | C | I | C |
| Implementar código em `feature/*` | A | R | I | C |
| Executar testes de sanidade locais | A | R | I | I |
| Executar coleta semanal | A | I | R | I |
| Abrir Pull Request para `main` | A | R | R | C |
| Revisar e aprovar merge | **R, A** | C | I | I |
| Publicar em produção | A | I | R | I |
| Homologar pós-deploy | R, A | C | I | C |
| Acionar rollback | **R, A** | C | I | I |
| Reportar erro de dado público | I | I | I | R |

Legenda: R (Responsável pela execução), A (Autoridade que aprova), C (Consultado), I (Informado).

**Regra de autoridade:** a aprovação de merge para `main` é indelegável e exclusiva do mantenedor. Nenhum agente automatizado, nenhum bot e nenhum colaborador externo possui essa prerrogativa.

---

## 1. AMBIENTE DE DESENVOLVIMENTO E SETUP LOCAL

### 1.1 Segregação de ambientes

O projeto opera com dois ambientes formalmente distintos e um ambiente efêmero de trabalho.

| Ambiente | Branch | Natureza | Público | Pode quebrar? |
| :--- | :--- | :--- | :--- | :--- |
| Produção | `main` | Estável, publicada via GitHub Pages | Cidadãos, imprensa, vereadores | **Nunca** |
| Integração / Staging | `desenvolvimento` | Testes locais, integração de features, validação de dados | Apenas mantenedor e colaboradores | Tolerado, desde que corrigido antes do PR |
| Trabalho | `feature/*`, `hotfix/*`, `atualizacao-dados/*` | Efêmero, descartável | Autor da branch | Sim, é para isso que existe |

A branch `desenvolvimento` funciona como staging local isolado. Ela não possui deploy público, não alimenta o GitHub Pages e não é indexada por buscadores. Esse isolamento é deliberado: permite testar coletas, layouts e filtros com liberdade total, sem qualquer risco de exposição de dados parciais ou incorretos ao público.

### 1.2 Pré-requisitos da estação de trabalho

| Item | Versão mínima | Verificação |
| :--- | :--- | :--- |
| Python | 3.11 | `python --version` |
| Git | 2.40 | `git --version` |
| Navegador baseado em Chromium ou Firefox | Atual | DevTools obrigatório para inspeção de CSP |
| Editor com suporte a EditorConfig e UTF-8 | Atual | Conferir encoding do arquivo salvo |

Todas as dependências Python são fixadas (pinned) por versão exata no arquivo de requisitos, garantindo builds reprodutíveis. Instalação em ambiente virtual isolado é obrigatória:

```bash
python -m venv .venv
# Linux ou macOS
source .venv/bin/activate
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install --require-hashes -r coletor/requirements.txt
```

O diretório `.venv/` está no `.gitignore` e nunca deve ser versionado.

### 1.3 Clonagem e posicionamento correto

```bash
git clone https://github.com/empratoslimposcl/em-pratos-limpos.git
cd em-pratos-limpos
git checkout desenvolvimento
git pull --rebase origin desenvolvimento
```

Nota de OPSEC: os caminhos absolutos da máquina local do mantenedor jamais devem aparecer em documentação, commits, logs ou issues. Use sempre referências relativas ao repositório ou placeholders genéricos do tipo `<diretorio-de-trabalho>`.

### 1.4 Execução local do portal

A SPA é 100% estática e não requer backend. A execução local deve sempre passar por um servidor HTTP, nunca pelo protocolo `file://`, porque o esquema `file://` altera o comportamento de origem e impede a validação fiel da Content Security Policy e dos carregamentos de dados.

```bash
# A partir da raiz do repositório
python -m http.server 8000
```

Acesse `http://localhost:8000/index.html`.

| Erro comum | Causa provável | Correção |
| :--- | :--- | :--- |
| Página abre mas sem dados | Aberta via `file://` | Usar `python -m http.server 8000` |
| Porta 8000 ocupada | Outro servidor ativo | `python -m http.server 8080` e ajustar a URL |
| CSP bloqueando recurso | Recurso externo introduzido indevidamente | Remover o recurso externo, não afrouxar a CSP |
| Dados desatualizados na tela | Cache do navegador | Recarregar com cache desabilitado (Ctrl + Shift + R) |

### 1.5 Execução local do coletor

```bash
python coletor/coletor.py
python coletor/testes_sanidade.py
python coletor/gerar_hash_integridade.py
python -m pytest tests/test_sanidade_dados.py -v
```

Regras invioláveis de coleta local:

1. O rate-limiting de 2.5 segundos entre requisições ao SAPL **nunca** pode ser reduzido, removido, paralelizado ou contornado. O SAPL é infraestrutura pública custeada pelo contribuinte. Sobrecarregá-lo é, na prática, um ataque de negação de serviço contra um órgão público, além de ser antiético e juridicamente arriscado.
2. Coletas de teste repetitivas devem usar cache local ou fixtures em `tests/`, e não novas rodadas contra o servidor real.
3. O coletor é determinístico: qualquer não determinismo observado (ordenação instável, timestamp embutido no payload de dados, uso de estrutura sem ordem garantida) é tratado como defeito de severidade alta.

### 1.6 Checklist obrigatório de testes na interface

Este checklist deve ser executado integralmente antes de qualquer Pull Request que toque `index.html`. Nenhum item pode ser marcado por presunção: cada linha exige verificação visual.

#### 1.6.1 Temas

- [ ] Tema claro renderiza com contraste adequado em todos os cards, tabelas e rótulos.
- [ ] Tema escuro renderiza sem texto invisível, sem fundo branco residual e sem ícone ilegível.
- [ ] Alternância entre temas é instantânea e não provoca recarregamento nem perda de estado dos filtros.
- [ ] A preferência de tema persiste após recarregar a página.
- [ ] O tema respeita a preferência do sistema operacional no primeiro acesso.

#### 1.6.2 Responsividade

- [ ] Desktop 1920x1080: layout completo, sem barra de rolagem horizontal.
- [ ] Desktop 1366x768: sem sobreposição de elementos, sem corte de texto.
- [ ] Tablet 768px: tabelas se adaptam ou se tornam roláveis de forma controlada.
- [ ] Mobile 390px: navegação utilizável com uma mão, alvos de toque com no mínimo 44px.
- [ ] Mobile 320px (limite inferior): nenhum estouro de container, nenhum texto truncado sem reticências.
- [ ] Orientação paisagem em mobile não quebra cabeçalhos fixos.

#### 1.6.3 Filtros e interatividade

- [ ] Filtro por vereador retorna exatamente os registros do parlamentar selecionado.
- [ ] Filtro por tipo de proposição (PLL e demais) apresenta contagens coerentes com o dataset.
- [ ] Filtro por período (mês e ano) oculta corretamente os painéis não selecionados.
- [ ] Combinação de múltiplos filtros produz interseção correta, não união.
- [ ] Limpar filtros restaura o estado inicial completo.
- [ ] Busca textual não quebra com acentuação, cedilha, caixa alta ou caixa baixa.
- [ ] Busca com string vazia não zera a listagem indevidamente.
- [ ] Nenhum filtro produz estado de tela vazia sem mensagem explicativa ao usuário.

#### 1.6.4 Integridade visível dos dados

- [ ] A contagem de vereadores exibida é exatamente 15.
- [ ] O total de sessões exibido é maior ou igual a 26.
- [ ] O total de PLLs exibido é maior ou igual a 100.
- [ ] Nenhum campo exibe `undefined`, `null`, `NaN` ou string vazia não tratada.
- [ ] Datas aparecem no formato brasileiro (DD/MM/AAAA).
- [ ] Nomes de parlamentares aparecem com grafia oficial, sem abreviação inventada.

#### 1.6.5 Segurança e console

- [ ] Console do navegador sem erros de JavaScript.
- [ ] Console do navegador sem violações de CSP registradas.
- [ ] Aba Network sem requisições para domínios de terceiros não previstos.
- [ ] Nenhum vazamento de caminho local, nome de usuário ou e-mail em `console.log`.
- [ ] Nenhum `console.log` de depuração remanescente no código enviado.

#### 1.6.6 Acessibilidade mínima

- [ ] Navegação completa por teclado (Tab e Shift + Tab) com foco visível.
- [ ] Imagens e ícones informativos possuem texto alternativo.
- [ ] Hierarquia de cabeçalhos coerente, sem saltos de nível.
- [ ] Contraste de texto normal com razão mínima de 4.5:1 em ambos os temas.

### 1.7 Regra de ouro

> **Nunca, em nenhuma hipótese, codifique diretamente na branch `main`.**

A `main` é a fotografia do que os cidadãos de Campo Largo estão vendo neste exato momento. Ela recebe código apenas por merge de Pull Request aprovado. Não recebe commit direto, não recebe "correção rápida", não recebe push forçado.

| Prática proibida na `main` | Consequência |
| :--- | :--- |
| `git commit` direto | Revert imediato e registro de não conformidade |
| `git push --force` | Proibição absoluta, risco de perda irreversível de histórico |
| Merge sem aprovação do mantenedor | Revert imediato |
| Merge com teste de sanidade falhando | Revert imediato e abertura de incidente |
| Edição de arquivo pela interface web do GitHub | Proibida, pois contorna a suíte de testes local |

---

## 2. REGRAS DE SEGURANÇA DA INFORMAÇÃO E APPSEC

### 2.1 Modelo de ameaças resumido

| Ativo | Ameaça | Vetor | Controle aplicado |
| :--- | :--- | :--- | :--- |
| Navegador do cidadão | Cross Site Scripting | Dado malicioso vindo do SAPL renderizado como HTML | `esc()` + CSP estrita |
| Credibilidade do dado | Adulteração silenciosa do JSON | Commit indevido ou corrupção em trânsito | SHA-256 publicado + testes de sanidade |
| Infraestrutura pública | Sobrecarga do SAPL | Coleta sem rate-limiting | Delay fixo de 2.5s, coleta semanal |
| Repositório | Vazamento de segredo | Token ou chave commitado | Política Zero Secrets + `.gitignore` + varredura |
| Privacidade do mantenedor | Exposição de identidade e ambiente | Log, path local, e-mail em commit | Regras de OPSEC da seção 2.4 |
| Produção | Publicação de build quebrado | Merge sem gate de qualidade | Gatekeeping da seção 4 |
| Cadeia de dependências | Pacote comprometido | Dependência não fixada | Versões fixadas com hash |

### 2.2 Content Security Policy estrita

O `index.html` declara uma CSP restritiva por design. As diretivas de bloqueio total já implantadas são:

| Diretiva | Valor | Objetivo de defesa |
| :--- | :--- | :--- |
| `frame-src` | `'none'` | Impede incorporação de iframes maliciosos ou de terceiros |
| `child-src` | `'none'` | Bloqueia contextos de navegação filhos e workers legados |
| `worker-src` | `'none'` | Elimina a superfície de Web Workers e Service Workers |

Diretrizes complementares obrigatórias para toda alteração:

1. `default-src` deve permanecer o mais restritivo possível, servindo como rede de segurança para diretivas não declaradas.
2. `object-src 'none'` e `base-uri 'none'` devem ser mantidos para eliminar injeção de plugin e sequestro de URL base.
3. `frame-ancestors 'none'` protege contra clickjacking.
4. `form-action 'none'` impede exfiltração via submissão forjada, já que o portal não possui formulários de envio.
5. Recursos externos (CDN de fonte, biblioteca hospedada fora, analytics de terceiros) são **proibidos**. Toda dependência visual deve ser local e versionada.

#### Regra de não afrouxamento

> Se uma funcionalidade nova exige relaxar a CSP, a funcionalidade está errada, não a política.

| Tentativa de afrouxamento | Decisão |
| :--- | :--- |
| `script-src 'unsafe-inline'` | Recusado. Externalize o script. |
| `script-src 'unsafe-eval'` | Recusado sem exceção. |
| Liberar domínio de CDN | Recusado. Traga o ativo para o repositório. |
| Liberar `frame-src` para vídeo incorporado | Recusado. Use link externo com `rel="noopener noreferrer"`. |
| Adicionar analytics de terceiros | Recusado. Fere CSP, privacidade do cidadão e neutralidade cívica. |

### 2.3 Sanitização de saída com `esc()`

O dado que alimenta o portal vem de um sistema externo (SAPL) sobre o qual o projeto não exerce controle editorial. Portanto, todo dado é tratado como não confiável por padrão.

Regras de aplicação:

1. **Toda** interpolação de dado externo em HTML passa obrigatoriamente por `esc()`. Sem exceções para campos "que são sempre numéricos" ou "que nunca vêm com caractere especial": essa presunção é exatamente o que produz XSS.
2. `esc()` neutraliza os caracteres estruturais de HTML (`<`, `>`, `&`, `"`, `'`) e remove sequências de escape ANSI, que podem ser usadas para forjar saída de terminal, ofuscar conteúdo em logs e enganar o operador durante a auditoria.
3. Uso de `innerHTML` com conteúdo dinâmico é **proibido**. Prefira `textContent` ou construção de nós via `createElement`.
4. `eval()`, `new Function()`, `setTimeout` com string e `document.write()` são proibidos.
5. Atributos gerados dinamicamente (`href`, `src`, `title`, `data-*`) exigem escape específico de contexto de atributo, com aspas sempre presentes.
6. URLs dinâmicas devem ser validadas por esquema, aceitando apenas `https:`, e rejeitando `javascript:`, `data:` e `vbscript:`.

#### Checklist de revisão AppSec de front-end

- [ ] Todo campo textual renderizado passa por `esc()`.
- [ ] Nenhuma ocorrência nova de `innerHTML` com variável.
- [ ] Nenhuma ocorrência de `eval`, `new Function`, `document.write`.
- [ ] Nenhum atributo de evento inline (`onclick`, `onerror`) no HTML.
- [ ] Nenhum link externo sem `rel="noopener noreferrer"`.
- [ ] Nenhuma diretiva de CSP foi enfraquecida no diff.
- [ ] Teste com payload de XSS em fixture local resultou em texto literal na tela, nunca em execução.

Payloads de verificação recomendados em fixture local (nunca em ambiente público):

```
<script>alert(1)</script>
"><img src=x onerror=alert(1)>
javascript:alert(1)
\u001b[31mtexto forjado\u001b[0m
```

Resultado esperado: os quatro renderizam como texto visível e inerte.

### 2.4 Política de Zero Secrets, privacidade e OPSEC

#### 2.4.1 Zero Secrets

O repositório é público. Logo, qualquer segredo commitado deve ser considerado comprometido no instante do push, mesmo que removido segundos depois, porque o objeto permanece no histórico, em forks, em caches e em espelhos automatizados.

| Regra | Detalhamento |
| :--- | :--- |
| Proibição total | Nenhum token, senha, chave de API, certificado privado ou cookie de sessão no repositório |
| Uso de GitHub Secrets | Toda credencial de automação vive exclusivamente em GitHub Secrets |
| Escopo mínimo | `GITHUB_TOKEN` com apenas as permissões necessárias ao job; sem `write` desnecessário |
| Ausência de log de segredo | Workflows nunca ecoam variáveis sensíveis, nem em modo de depuração |
| Rotação | Qualquer credencial suspeita é revogada primeiro e investigada depois |

Procedimento de resposta a vazamento de segredo (ordem obrigatória):

1. **Revogar** imediatamente a credencial no provedor de origem. Esta é a primeira ação, sempre.
2. Gerar nova credencial e registrá-la em GitHub Secrets.
3. Remover a ocorrência do histórico e forçar a limpeza de referências.
4. Registrar o incidente em documento interno, com data, escopo e impacto.
5. Adicionar padrão de detecção ao `.gitignore` e à varredura pré-commit para impedir reincidência.

#### 2.4.2 Conteúdo obrigatório do `.gitignore`

```gitignore
# Ambientes e dependências
.venv/
venv/
env/
__pycache__/
*.py[cod]
node_modules/

# Segredos e configuração local
.env
.env.*
*.key
*.pem
*.p12
*.pfx
credentials.json
secrets.json
config.local.*
token.txt

# Artefatos locais e temporários
*.log
*.tmp
*.bak
*.swp
cache/
.cache/
backups/local/
*.tar.gz

# Metadados de sistema operacional e IDE
.DS_Store
Thumbs.db
desktop.ini
.idea/
.vscode/
*.code-workspace

# Saídas de teste
.pytest_cache/
.coverage
htmlcov/
```

#### 2.4.3 Privacidade e OPSEC

Esta subseção tem caráter estrito e prevalece sobre conveniência de depuração.

É **terminantemente proibido** versionar, logar, comentar em código, incluir em mensagem de commit, em issue, em Pull Request ou em documentação:

| Categoria proibida | Exemplos do que nunca pode aparecer | Alternativa correta |
| :--- | :--- | :--- |
| E-mails pessoais | Endereço pessoal do mantenedor ou de colaboradores | E-mail institucional do projeto ou `noreply` do GitHub |
| Nome de usuário local | Nome de conta do sistema operacional | Placeholder genérico |
| Caminhos absolutos | Qualquer caminho iniciado por `C:\Users\...` ou `/home/<usuario>/...` | Caminho relativo à raiz do repositório |
| Identificadores de máquina | Hostname, endereço MAC, IP residencial | Omitir integralmente |
| Dados pessoais de terceiros | Telefone, endereço, documento de qualquer cidadão ou parlamentar | Apenas dados públicos e oficiais de atuação parlamentar |
| Prints de tela não higienizados | Captura exibindo barra de caminho, abas pessoais, notificações | Recortar ou reproduzir o erro em ambiente limpo |

Configuração obrigatória de identidade Git no repositório, para evitar vazamento de e-mail pessoal em commits:

```bash
git config user.name "empratoslimposcl"
git config user.email "<id>+empratoslimposcl@users.noreply.github.com"
```

Regra sobre dados de parlamentares: o portal trata exclusivamente de **atuação pública de agente público no exercício do mandato**, o que é informação de interesse coletivo e de publicidade obrigatória. O projeto não coleta, não infere e não publica dado de vida privada, dado sensível na acepção da LGPD, nem dado de terceiros não investidos de mandato.

#### 2.4.4 Higienização de logs

- Mensagens de erro do coletor devem referenciar identificadores lógicos (código da proposição, número da sessão), nunca caminhos de disco.
- Stack traces publicados em issue devem ter os caminhos substituídos por `<path>` antes do envio.
- Sequências ANSI em logs capturados devem ser removidas antes de qualquer colagem em texto público, exatamente pelo mesmo motivo técnico que justifica sua remoção em `esc()`.

### 2.5 Integridade de dados e auditoria cívica

A integridade é o coração do valor público do projeto. O arquivo `coletor/gerar_hash_integridade.py` produz `atuacao_vereadores_2026.json.sha256`, permitindo que qualquer cidadão, jornalista ou pesquisador verifique de forma independente que o dataset consultado é exatamente aquele publicado pelo projeto, sem intermediação e sem necessidade de confiar no mantenedor.

| Aspecto | Definição |
| :--- | :--- |
| Algoritmo | SHA-256 |
| Arquivo protegido | `atuacao_vereadores_2026.json` |
| Arquivo de hash | `atuacao_vereadores_2026.json.sha256` |
| Momento de geração | Após toda coleta e antes de todo commit do dataset |
| Verificação | Obrigatória no CI e recomendada ao público |

Comandos de verificação independente pelo cidadão:

```bash
# Linux ou macOS
sha256sum -c atuacao_vereadores_2026.json.sha256

# Windows PowerShell
Get-FileHash .\atuacao_vereadores_2026.json -Algorithm SHA256
```

Regras de integridade:

1. Commit que altera o JSON sem atualizar o `.sha256` correspondente é **bloqueado** na revisão.
2. Commit que altera o `.sha256` sem alteração correspondente no JSON é tratado como **indício de adulteração** e exige investigação formal antes de qualquer merge.
3. Divergência de hash detectada em produção é **incidente de severidade crítica**, com acionamento imediato do protocolo de contingência da seção 5.
4. O hash publicado é o compromisso público do projeto. Alterá-lo silenciosamente para "fazer passar" uma verificação é violação grave de governança.

### 2.6 Segurança da cadeia de suprimentos

| Controle | Implementação |
| :--- | :--- |
| Dependências fixadas | Versão exata e hash no arquivo de requisitos |
| Superfície mínima | Nenhuma biblioteca JavaScript de terceiros em produção |
| Actions de terceiros | Referenciadas por SHA de commit, nunca por tag móvel |
| Permissões de workflow | Declaração explícita de `permissions` no topo do workflow, com escopo mínimo |
| Atualização de dependência | Só entra por `feature/*` com suíte de sanidade completa executada |

---

## 3. REGRAS DE CRIAÇÃO DE BRANCHES E POLÍTICA DE BACKUP

### 3.1 Estratégia de branches

| Branch | Origem | Destino do merge | Tempo de vida | Proteção |
| :--- | :--- | :--- | :--- | :--- |
| `main` | Permanente | Não aplicável | Permanente | Máxima: sem push direto, sem force push, PR aprovado obrigatório |
| `desenvolvimento` | `main` | `main` via PR | Permanente | Alta: sem force push, testes obrigatórios |
| `feature/*` | `desenvolvimento` | `desenvolvimento` | Efêmera, até 14 dias | Padrão |
| `hotfix/*` | `main` | `main` e retro-merge em `desenvolvimento` | Efêmera, horas | Padrão, com revisão acelerada |
| `atualizacao-dados/*` | `main` | `main` via PR automatizado | Efêmera, um ciclo semanal | Padrão, gerada pela esteira |

#### 3.1.1 Convenção de nomenclatura

| Padrão | Exemplo | Uso |
| :--- | :--- | :--- |
| `feature/<escopo>-<descricao-curta>` | `feature/filtros-por-comissao` | Nova funcionalidade ou melhoria |
| `hotfix/<severidade>-<descricao>` | `hotfix/critico-contagem-sessoes` | Correção urgente em produção |
| `atualizacao-dados/<ano>-<semana>` | `atualizacao-dados/2026-s38` | Ciclo semanal do coletor |
| `docs/<assunto>` | `docs/politica-governanca` | Alteração exclusivamente documental |
| `chore/<assunto>` | `chore/pin-dependencias` | Manutenção sem efeito funcional |

Regras de nomenclatura: apenas minúsculas, hífen como separador, sem acentos, sem caracteres especiais, sem nome de pessoa, sem identificador de máquina local.

#### 3.1.2 Fluxo padrão de uma feature

```bash
git checkout desenvolvimento
git pull --rebase origin desenvolvimento
git checkout -b feature/filtros-por-comissao

# ciclo de trabalho, testes locais e checklists da seção 1.6

python coletor/testes_sanidade.py
python -m pytest tests/test_sanidade_dados.py -v

git add <arquivos-especificos>
git commit -m "Adiciona filtro por comissao com sanitizacao esc() na renderizacao"
git push -u origin feature/filtros-por-comissao
```

Nunca use `git add .` sem inspecionar previamente o resultado de `git status`. Essa é a origem mais comum de vazamento acidental de arquivo local, artefato temporário ou credencial.

#### 3.1.3 Fluxo de hotfix

Hotfix nasce da `main`, porque a `desenvolvimento` pode conter trabalho ainda não homologado que não deve subir junto com a correção urgente.

```bash
git checkout main
git pull --rebase origin main
git checkout -b hotfix/critico-contagem-sessoes
# correção mínima e cirúrgica, escopo estritamente limitado ao defeito
python coletor/testes_sanidade.py
python -m pytest tests/test_sanidade_dados.py -v
git push -u origin hotfix/critico-contagem-sessoes
```

Após o merge aprovado em `main`, é **obrigatório** o retro-merge em `desenvolvimento`, sob pena de a correção ser silenciosamente desfeita no próximo ciclo de integração.

#### 3.1.4 Padrão de mensagem de commit

Formato: `<Verbo no presente> <objeto direto> <complemento de contexto>`.

| Boa mensagem | Má mensagem |
| :--- | :--- |
| `Corrige contagem de PLLs duplicados na agregacao por vereador` | `fix` |
| `Reforca CSP com form-action none e base-uri none` | `ajustes` |
| `Atualiza dataset da semana 38 com hash SHA-256 regenerado` | `update dados` |

Regras: sem emoji, sem dado pessoal, sem caminho local, sem referência a ferramenta interna do ambiente do mantenedor. Commits atômicos: uma mudança lógica por commit.

### 3.2 Política de backup

A política de backup opera em três camadas independentes, de forma que a falha de uma camada não comprometa a capacidade de restauração.

| Camada | Mecanismo | Retenção | Responsável | Cobertura |
| :--- | :--- | :--- | :--- | :--- |
| 1. Artefato de esteira | `tar.gz` gerado por `.github/workflows/atualizacao_semanal.yml` | **90 dias** | GitHub Actions | Dataset e saídas da coleta semanal |
| 2. Marco semântico | Tags Git anotadas | Permanente | Mantenedor | Estado completo do código e dados em cada release |
| 3. Backup local pré-mudança | Cópia manual fora da árvore de trabalho | Até confirmação de estabilidade | Mantenedor | Proteção contra mudança estrutural destrutiva |

#### 3.2.1 Camada 1: artefatos da esteira

O workflow semanal gera um pacote `tar.gz` com o estado dos dados coletados, publicado como artefato do GitHub Actions com **90 dias de retenção**. Isso garante janela ampla para reconstruir qualquer dataset de até aproximadamente treze ciclos semanais anteriores, mesmo em cenário de corrupção não detectada de imediato.

Regras:

- O artefato nunca contém segredo, log bruto com caminho local ou arquivo de ambiente.
- O nome do artefato segue o padrão `backup-dados-<ano>-s<semana>`.
- A retenção de 90 dias não pode ser reduzida sem aprovação formal do mantenedor registrada no Pull Request.

#### 3.2.2 Camada 2: tags semânticas

O versionamento adota Semantic Versioning adaptado ao contexto cívico:

| Componente | Incrementa quando |
| :--- | :--- |
| MAJOR | Mudança estrutural no schema do dataset ou reescrita da SPA que quebre compatibilidade |
| MINOR | Nova funcionalidade, novo filtro, nova visualização, nova fonte de dado |
| PATCH | Correção de bug, ajuste de layout, correção pontual de dado |

```bash
git checkout main
git pull --rebase origin main
git tag -a v1.4.0 -m "Adiciona filtro por comissao e regenera hash de integridade"
git push origin v1.4.0
```

Toda publicação em produção deve ter uma tag correspondente. Sem tag, não há ponto de retorno nomeado para rollback, e o rollback deixa de ser uma operação de rotina para virar uma arqueologia de histórico sob pressão.

#### 3.2.3 Camada 3: backup local pré-mudança estrutural

Obrigatório **antes** de qualquer uma das seguintes operações:

- Alteração de schema do `atuacao_vereadores_2026.json`.
- Refatoração ampla do `index.html`.
- Reescrita da lógica de agregação do coletor.
- Alteração dos pisos mínimos dos testes de sanidade.
- Mudança no workflow de automação.

```bash
# Executar fora da árvore do repositório, em diretorio nao versionado
tar -czf backup-pre-<descricao>-<AAAAMMDD>.tar.gz em-pratos-limpos/
```

O arquivo resultante nunca deve ser commitado (`*.tar.gz` está no `.gitignore`).

#### 3.2.4 Teste de restauração

Backup não testado não é backup, é esperança. Trimestralmente, o mantenedor deve executar e registrar:

- [ ] Download de um artefato `tar.gz` da esteira.
- [ ] Extração em diretório limpo e isolado.
- [ ] Verificação do SHA-256 do dataset extraído.
- [ ] Execução de `coletor/testes_sanidade.py` sobre o dataset restaurado.
- [ ] Checkout de uma tag anterior e verificação de que a SPA sobe localmente sem erro.
- [ ] Registro da data e do resultado do teste.

---

## 4. PROCESSO DE REVISÃO E APROVAÇÃO (GATEKEEPING DE QUALIDADE)

### 4.1 Filosofia do gate

O gate existe porque o custo de um erro em produção neste projeto não é técnico, é cívico. Um número inflado de proposições beneficia indevidamente um parlamentar. Um número reduzido prejudica indevidamente outro. Ambos os casos convertem uma ferramenta de transparência em instrumento de desinformação. Por isso o gate é rígido, explícito e não negociável sob pressão de prazo.

### 4.2 Critérios obrigatórios de aprovação

Nenhum Pull Request para `main` pode ser aprovado sem que **todos** os critérios abaixo estejam satisfeitos e verificados.

| # | Critério | Verificação | Bloqueante |
| :---: | :--- | :--- | :---: |
| 1 | `coletor/testes_sanidade.py` com 100% de sucesso | Execução local e no CI | Sim |
| 2 | `tests/test_sanidade_dados.py` com 100% de sucesso | `pytest -v` local e no CI | Sim |
| 3 | Exatamente 15 vereadores oficiais no dataset | Asserção automatizada | Sim |
| 4 | Sessões maior ou igual a 26 | Asserção automatizada de piso | Sim |
| 5 | PLLs maior ou igual a 100 | Asserção automatizada de piso | Sim |
| 6 | Hash SHA-256 regenerado e coerente com o JSON | Verificação do `.sha256` | Sim |
| 7 | CSP não enfraquecida no diff | Revisão manual do diff de `index.html` | Sim |
| 8 | Toda renderização de dado externo com `esc()` | Revisão manual | Sim |
| 9 | Zero segredos e zero dados pessoais no diff | Varredura e revisão manual | Sim |
| 10 | Rate-limiting de 2.5s íntegro no coletor | Revisão manual do diff de `coletor/` | Sim |
| 11 | Checklist de interface da seção 1.6 concluído | Declaração no PR com evidência | Sim |
| 12 | Determinismo da coleta preservado | Duas execuções produzem saída idêntica | Sim |
| 13 | Ausência de `console.log` de depuração | Revisão do diff | Sim |
| 14 | Mensagens de commit conformes | Revisão do histórico do PR | Não, mas exige correção |

### 4.3 Semântica dos pisos mínimos

Os valores de sanidade são **pisos**, expressos com o operador maior ou igual (`>=`), e não igualdades. Essa escolha é deliberada e deve ser preservada.

| Métrica | Piso | Razão do piso |
| :--- | :---: | :--- |
| Vereadores oficiais | Exatamente 15 | A composição da Câmara é fixa. Qualquer desvio indica erro de coleta ou duplicação. |
| Sessões | 26 ou mais | A base cresce naturalmente a cada nova sessão realizada. O piso detecta perda de dado, não limita crescimento. |
| PLLs | 100 ou mais | Mesma lógica: protege contra coleta truncada sem travar a evolução legítima da base. |

Interpretação das falhas:

| Sintoma | Diagnóstico provável | Ação |
| :--- | :--- | :--- |
| Valor abaixo do piso | Coleta truncada, falha de rede, mudança de layout do SAPL | **Bloquear merge.** Investigar o coletor. |
| Vereadores diferente de 15 | Duplicação, parsing incorreto de nome, registro órfão | **Bloquear merge.** Corrigir a normalização. |
| Salto anômalo para cima | Possível duplicação de registros | **Bloquear merge.** Auditar unicidade de identificadores. |
| Hash divergente | Dataset alterado fora do fluxo | **Bloquear merge.** Tratar como incidente de integridade. |

Elevação de piso: à medida que a base cresce de forma estável, o mantenedor pode elevar os pisos para aumentar a sensibilidade de detecção. Essa alteração é sempre feita por Pull Request explícito, jamais embutida em um PR de outra natureza.

### 4.4 Fluxo de aprovação

```
feature/* ou atualizacao-dados/*
        |
        v
[Autoverificação do autor: checklists das seções 1.6 e 2.3]
        |
        v
[Pull Request para main, com descrição completa e evidências]
        |
        v
[CI: testes de sanidade + verificação de hash + varredura de segredos]
        |
        +---> Falhou? --> PR bloqueado. Correção na própria branch. Reenvio.
        |
        v
[Revisão humana detalhada por parte do mantenedor]
        |
        +---> Reprovado? --> Comentários no PR. Autor corrige. Nova rodada completa.
        |
        v
[APROVAÇÃO EXCLUSIVA DO MANTENEDOR]
        |
        v
[Merge em main]
        |
        v
[Deploy automático no GitHub Pages]
        |
        v
[Homologação pós-deploy da seção 5.3]
```

### 4.5 Modelo obrigatório de descrição do Pull Request

```markdown
## Objetivo
Descrição clara do que muda e por que muda.

## Tipo de alteração
- [ ] Nova funcionalidade (feature)
- [ ] Correção de defeito (hotfix)
- [ ] Atualização semanal de dados
- [ ] Documentação
- [ ] Manutenção sem efeito funcional

## Evidência de testes de sanidade
- [ ] coletor/testes_sanidade.py: 100% de sucesso
- [ ] tests/test_sanidade_dados.py: 100% de sucesso
- Vereadores encontrados: ___ (esperado: exatamente 15)
- Sessões encontradas: ___ (piso: 26)
- PLLs encontradas: ___ (piso: 100)

## Integridade
- [ ] atuacao_vereadores_2026.json.sha256 regenerado
- [ ] Hash conferido localmente

## Segurança (AppSec)
- [ ] CSP não foi enfraquecida
- [ ] Todo dado externo renderizado passa por esc()
- [ ] Sem innerHTML, eval, new Function ou document.write
- [ ] Rate-limiting de 2.5s preservado no coletor
- [ ] Sem segredos, e-mails pessoais, nomes de usuário local ou caminhos absolutos

## Checklist de interface
- [ ] Tema claro e tema escuro validados
- [ ] Mobile (320px e 390px) e desktop (1366px e 1920px) validados
- [ ] Filtros validados individualmente e combinados
- [ ] Console sem erro e sem violação de CSP

## Rollback
Tag de retorno em caso de falha: v_._._
```

### 4.6 Critérios de reprovação sumária

O Pull Request é reprovado sem necessidade de análise adicional quando:

| Condição | Justificativa |
| :--- | :--- |
| Qualquer teste de sanidade falhando | Dado não confiável não vai ao público |
| Piso mínimo violado | Indica perda de dado |
| CSP enfraquecida | Regressão de segurança inaceitável |
| Segredo ou dado pessoal no diff | Violação da política Zero Secrets e de OPSEC |
| Rate-limiting alterado para menos de 2.5s | Risco ético e operacional contra infraestrutura pública |
| Ausência de hash atualizado | Quebra da cadeia de auditoria cívica |
| Commit direto na `main` no histórico | Violação da regra de ouro |
| PR sem descrição preenchida | Impede revisão responsável |

### 4.7 Autoridade de aprovação

> **Somente o mantenedor aprova merges para `main`.**

Esta regra é absoluta e não comporta exceção por urgência, por horário, por feriado ou por simplicidade aparente da mudança. Não existe "aprovação automática", não existe "auto-merge", não existe aprovação por agente de IA. A automação pode preparar, testar, empacotar e propor. A decisão de publicar em nome da transparência pública de Campo Largo é humana, nominal e rastreável.

### 4.7.1 Proibições explícitas para agentes de IA

Nenhum agente de IA (Claude, Cursor, Grok, DeepSeek, Copilot, ou qualquer outro) pode executar as ações abaixo sem aprovação expressa e registrada do mantenedor:

| Ação | Exigência |
| :--- | :--- |
| Merge de PR para `main` | Aprovação expressa do mantenedor no PR |
| Aprovação de PR próprio | Proibido. Nenhum agente aprova seu próprio PR |
| Deploy para produção | Aprovação expressa do mantenedor |
| Criação, edição ou exclusão de secrets | Aprovação expressa do mantenedor |
| Rollback | Aprovação expressa do mantenedor |
| Push forçado | Proibido em qualquer circunstância |

**Classificação de violação:** Qualquer ação acima sem aprovação registrada é classificada como **violação de governança** (não como "urgência"). A resposta é revert imediato + registro do incidente.

**Prevenção:** Todo PR aberto por agente de IA deve conter, na descrição, a confirmação de que a aprovação do mantenedor foi solicitada antes de abrir o PR.

---

## 5. PROCESSO DE PUBLICAÇÃO E DEPLOY EM PRODUÇÃO

### 5.1 Arquitetura de publicação

| Elemento | Definição |
| :--- | :--- |
| Hospedagem | GitHub Pages |
| Fonte | Branch `main` |
| Gatilho | Merge de Pull Request aprovado |
| URL de produção | `https://empratoslimpos.pages.dev` |
| Natureza | Site estático, sem backend, sem banco de dados, sem sessão de usuário |
| Tempo típico de propagação | 1 a 5 minutos |

A ausência de backend é uma decisão arquitetural de segurança: sem servidor de aplicação, não há injeção de SQL, não há desserialização insegura, não há gestão de sessão vulnerável e não há superfície de execução remota. A superfície de ataque residual concentra-se no navegador do visitante, e é exatamente essa superfície que a CSP estrita e o `esc()` endereçam.

### 5.2 Checklist pré-deploy

Executado imediatamente antes do merge autorizado.

- [ ] Todos os critérios da seção 4.2 verificados e registrados no PR.
- [ ] Tag semântica definida para o release.
- [ ] Backup local pré-mudança realizado, se a alteração for estrutural.
- [ ] Tag de rollback identificada e anotada na descrição do PR.
- [ ] Nenhum outro deploy em andamento.
- [ ] Janela de publicação adequada, com o mantenedor disponível para homologar.

### 5.3 Checklist de homologação pós-deploy

Obrigatório em **toda** publicação, sem exceção. Deve iniciar em até 10 minutos após a conclusão do deploy.

#### 5.3.1 Disponibilidade

- [ ] A URL de produção retorna HTTP 200.
- [ ] O certificado TLS é válido e a conexão é HTTPS.
- [ ] O arquivo `atuacao_vereadores_2026.json` é servido com HTTP 200.
- [ ] O arquivo `atuacao_vereadores_2026.json.sha256` é servido com HTTP 200.

Verificação objetiva:

```bash
curl -I https://empratoslimpos.pages.dev/
curl -sI https://empratoslimpos.pages.dev/dados/tratados/atuacao_vereadores_2026.json
```

#### 5.3.2 Integridade dos dados ao vivo

- [ ] Download do JSON e do `.sha256` diretamente de produção.
- [ ] Cálculo local do SHA-256 do JSON baixado.
- [ ] Comparação: o hash calculado é **idêntico** ao hash publicado.
- [ ] Contagem ao vivo: exatamente 15 vereadores.
- [ ] Contagem ao vivo: sessões maior ou igual a 26.
- [ ] Contagem ao vivo: PLLs maior ou igual a 100.

```bash
curl -sO https://empratoslimpos.pages.dev/dados/tratados/atuacao_vereadores_2026.json
curl -sO https://empratoslimpos.pages.dev/dados/tratados/atuacao_vereadores_2026.json.sha256
sha256sum -c atuacao_vereadores_2026.json.sha256
```

Resultado esperado: confirmação de correspondência. Qualquer divergência é **incidente crítico** e dispara imediatamente o protocolo da seção 5.4.

#### 5.3.3 Funcional em produção

- [ ] Tema claro e tema escuro funcionando ao vivo.
- [ ] Layout íntegro em dispositivo móvel real, não apenas em emulação.
- [ ] Filtros por vereador, tipo e período operando corretamente.
- [ ] Painéis de mês e ano ocultos quando não selecionados.
- [ ] Console do navegador sem erro de JavaScript.
- [ ] Console do navegador sem violação de CSP.
- [ ] Aba Network sem requisição para domínio de terceiro não previsto.
- [ ] Cabeçalhos de segurança presentes conforme declarado no documento.

#### 5.3.4 Registro

- [ ] Data, hora, versão publicada e resultado da homologação registrados.
- [ ] Tag de release criada e enviada ao repositório remoto.

### 5.4 Protocolo de contingência e rollback

#### 5.4.1 Classificação de severidade

| Severidade | Definição | Prazo de resposta | Ação padrão |
| :--- | :--- | :--- | :--- |
| **S1 Crítica** | Dado incorreto publicado, hash divergente, XSS explorável, site fora do ar | Imediata | Rollback imediato |
| **S2 Alta** | Filtro retornando resultado errado, contagem parcial visível | Até 4 horas | Rollback ou hotfix, conforme análise |
| **S3 Média** | Falha visual relevante, quebra de layout em resolução comum | Até 48 horas | Hotfix no próximo ciclo |
| **S4 Baixa** | Ajuste cosmético, melhoria de texto | Próximo ciclo regular | Feature normal |

Critério de decisão entre rollback e hotfix: se o defeito compromete a **veracidade do dado exibido** ou a **segurança do visitante**, o rollback é imediato e a correção acontece depois, com calma. Nunca se corrige dado incorreto ao vivo sob pressão, porque a pressa é precisamente o que produz o segundo erro.

#### 5.4.2 Procedimento de rollback rápido

**Passo 1. Conter.** Identificar a última tag comprovadamente estável.

```bash
git fetch --tags
git tag --sort=-creatordate | head -n 5
```

**Passo 2. Reverter por revert, nunca por reset.** A `main` é protegida contra reescrita de histórico. O rollback se faz criando um novo commit que desfaz a mudança, preservando a rastreabilidade completa do incidente.

```bash
git checkout main
git pull --rebase origin main
git revert --no-commit <sha-do-merge-problematico> -m 1
git commit -m "Reverte publicacao <versao> por divergencia de integridade em producao"
```

**Passo 3. Validar antes de republicar.** O rollback também passa pelo gate:

```bash
python coletor/testes_sanidade.py
python -m pytest tests/test_sanidade_dados.py -v
sha256sum -c atuacao_vereadores_2026.json.sha256
```

**Passo 4. Publicar o rollback** por Pull Request com aprovação do mantenedor, mantendo a regra de ouro intacta mesmo em emergência. A urgência justifica prioridade de revisão, jamais a supressão da revisão.

**Passo 5. Homologar novamente.** Repetir integralmente o checklist 5.3.

**Passo 6. Registrar o incidente:**

| Campo | Conteúdo |
| :--- | :--- |
| Data e hora da detecção | |
| Severidade | |
| Descrição objetiva do impacto público | |
| Versão afetada e versão restaurada | |
| Causa raiz | |
| Controle que falhou | |
| Controle novo a ser implementado | |
| Teste de sanidade adicionado para impedir reincidência | |

**Passo 7. Fechar o ciclo.** Todo incidente S1 ou S2 deve resultar em pelo menos **um novo teste automatizado** que teria detectado o problema antes da publicação. Sem isso, o incidente não está encerrado, apenas adiado.

#### 5.4.3 Contingência específica: divergência de hash em produção

1. Retirar imediatamente a confiança no dado: registrar publicamente que há verificação em curso, se a divergência for pública.
2. Comparar o JSON de produção com o artefato `tar.gz` de backup do ciclo correspondente.
3. Se o backup for íntegro, restaurar a partir dele e regenerar o hash.
4. Se o backup também divergir, executar coleta completa nova a partir do SAPL, respeitando o rate-limiting de 2.5 segundos, e reconstruir o dataset do zero.
5. Publicar apenas após aprovação humana e homologação completa.

#### 5.4.4 Contingência específica: mudança de layout no SAPL

O SAPL é sistema de terceiro. Alteração em sua estrutura quebra o coletor de forma silenciosa, produzindo coleta vazia ou parcial. A defesa é o piso mínimo: a coleta truncada falha no teste de sanidade e nunca chega à `main`.

Procedimento:

- [ ] Confirmar a falha pelo relatório do teste de sanidade, não pela inspeção visual.
- [ ] Ajustar o parser em branch `feature/*`, com fixture congelada em `tests/`.
- [ ] Validar determinismo com duas execuções consecutivas.
- [ ] Reprocessar e regenerar o hash.
- [ ] Seguir o fluxo normal de Pull Request. **Não** há atalho para produção.

### 5.5 Ciclo semanal automatizado

| Etapa | Executor | Saída |
| :--- | :--- | :--- |
| 1. Coleta agendada contra o SAPL, com delay de 2.5s | Workflow `atualizacao_semanal.yml` | Dataset atualizado |
| 2. Execução dos testes de sanidade | Workflow | Aprovação ou falha bloqueante |
| 3. Geração do SHA-256 | `gerar_hash_integridade.py` | `atuacao_vereadores_2026.json.sha256` |
| 4. Empacotamento de backup | Workflow | `tar.gz` com 90 dias de retenção |
| 5. Abertura de Pull Request para `main` | Workflow | PR em `atualizacao-dados/*` |
| 6. Revisão humana | **Mantenedor** | Aprovação ou reprovação |
| 7. Merge e deploy | GitHub Pages | Produção atualizada |
| 8. Homologação pós-deploy | **Mantenedor** | Registro de conformidade |

Princípio central da esteira: **valida antes de publicar e nunca faz push cego na `main`.** A automação tem autonomia para trabalhar, coletar, testar e propor. Não tem autonomia para publicar.

---

## 6. Incidentes de Governança

### 6.1 Classificação

| Tipo | Descrição | Resposta |
| :--- | :--- | :--- |
| Violação de merge | Merge em `main` sem aprovação do mantenedor | Revert imediato + incidente |
| Violação de segredo | Segredo exposto em commit, PR ou documento público | Revogar primeiro, limpar depois, registrar |
| Violação de OPSEC | Dado pessoal do mantenedor exposto | Remover + registrar |

### 6.2 Registro

Todo incidente deve ser registrado em `historico/handoffs/` com:
- Data e hora
- O que aconteceu
- O que foi feito para corrigir
- O que mudou para prevenir reincidência

### 6.3 Prevenção

- As proibições da seção 4.7.1 devem ser replicadas em `AGENTS.md`, `CLAUDE.md` e `GUIA_DO_ORQUESTRADOR.md`
- Checklist pré-PR obrigatório (seção 4.5.1) deve ser verificado antes de todo PR
- Nenhum agente pode ignorar estas regras por "urgência" ou "simplicidade"

---

## 7. Anexos

### 6.1 Checklist consolidado de release

```
PRÉ-DESENVOLVIMENTO
[ ] Branch criada a partir da origem correta (desenvolvimento para feature, main para hotfix)
[ ] Backup local realizado, se mudança estrutural

DESENVOLVIMENTO
[ ] Nenhuma linha escrita diretamente na main
[ ] Commits atômicos e com mensagens conformes
[ ] Nenhum dado pessoal, caminho local ou segredo introduzido

TESTES LOCAIS
[ ] coletor/testes_sanidade.py: 100%
[ ] tests/test_sanidade_dados.py: 100%
[ ] 15 vereadores, sessoes >= 26, PLLs >= 100
[ ] Hash SHA-256 regenerado
[ ] Checklist de interface (temas, responsividade, filtros) concluído
[ ] Console limpo, sem violação de CSP

SEGURANÇA
[ ] CSP intacta ou mais restritiva
[ ] esc() aplicado em toda renderização de dado externo
[ ] Rate-limiting de 2.5s preservado
[ ] .gitignore respeitado

REVISÃO
[ ] Pull Request aberto para main com descrição completa
[ ] CI verde
[ ] Aprovação explícita do mantenedor

PUBLICAÇÃO
[ ] Merge realizado
[ ] Tag semântica criada e enviada
[ ] Deploy concluído no GitHub Pages

HOMOLOGAÇÃO
[ ] HTTP 200 na URL de produção
[ ] Hash de produção confere com o publicado
[ ] Contagens ao vivo dentro dos pisos
[ ] Funcional validado em mobile e desktop reais
[ ] Registro do release arquivado
```

### 6.2 Tabela de decisão rápida

| Situação | Ação correta |
| :--- | :--- |
| Preciso corrigir um typo em produção | `hotfix/*` a partir da `main`, PR, aprovação, merge. Nunca edição direta. |
| O teste de sanidade falhou por pouco | Investigar. O piso existe justamente para isso. Nunca baixar o piso para passar. |
| Uma biblioteca externa resolveria rápido | Avaliar alternativa local. CSP não é negociável. |
| A coleta está lenta demais | Aceitar. O rate-limiting protege infraestrutura pública. |
| O dado do SAPL parece errado na origem | Publicar o dado oficial e registrar a divergência. O projeto reflete a fonte, não a corrige silenciosamente. |
| O mantenedor está indisponível e o dado está desatualizado | Aguardar. Atraso é aceitável, publicação não revisada não é. |
| Preciso depurar com `console.log` | Usar localmente e remover antes do commit. |
| Encontrei um segredo commitado | Revogar primeiro, limpar depois, registrar sempre. |

### 6.3 Glossário

| Termo | Definição |
| :--- | :--- |
| AppSec | Segurança de aplicação, disciplina voltada a prevenir defeitos exploráveis no software |
| CSP | Content Security Policy, política do navegador que restringe origens e comportamentos permitidos |
| Gatekeeping | Controle de passagem que impede a promoção de mudanças que não atendam aos critérios de qualidade |
| PLL | Projeto de Lei do Legislativo |
| Piso mínimo | Valor limite inferior aceitável em teste de sanidade, expresso com maior ou igual |
| Rate-limiting | Limitação deliberada da frequência de requisições a um serviço externo |
| SAPL | Sistema de Apoio ao Processo Legislativo, fonte oficial dos dados |
| SPA | Single Page Application, aplicação de página única |
| XSS | Cross Site Scripting, injeção de script no contexto do navegador da vítima |
| Zero Secrets | Política que proíbe qualquer credencial no repositório |

### 6.4 Declaração final de governança

Este documento é normativo. Exceções não são criadas por conveniência, por urgência ou por hábito: são criadas apenas por decisão expressa e registrada do mantenedor, documentada no Pull Request correspondente, com justificativa, escopo, prazo de validade e controle compensatório.

O compromisso operacional do projeto "Em Pratos Limpos" se resume a quatro afirmações verificáveis:

1. Nenhum número chega ao cidadão sem passar por teste de sanidade com 100% de sucesso.
2. Nenhum dataset é publicado sem hash SHA-256 correspondente e verificável de forma independente.
3. Nenhuma publicação ocorre sem revisão e aprovação humana nominal.
4. Nenhuma funcionalidade justifica o enfraquecimento das defesas de segurança do visitante.

Transparência pública exige, antes de tudo, que a própria ferramenta de transparência seja auditável.

---

Escrevi o documento como texto, conforme solicitado, sem executar nenhuma ferramenta ou comando. Notei que já existe um arquivo `PROCESSO_DESENVOLVIMENTO_E_GOVERNANCA.md` não rastreado na raiz do repositório; se quiser, posso ler o conteúdo atual dele e gravar esta versão (substituindo ou mesclando), mas não fiz nenhuma alteração em disco sem sua confirmação.