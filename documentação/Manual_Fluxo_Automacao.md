# 🤖 Fluxo de Automação do Sistema — Escavador de Pendências e-CAC

> **Nível Arquiteto de Software Contábil Sênior — Metodologia Agente WillianBO**
> Este manual técnico detalha o ciclo de vida completo da execução do **Escavador de Pendências**, mapeando sua lógica de decisão inteligente, redundâncias contra falhas e a consolidação do Painel de Controle Excel para a **J&J Contabilidade**.

---

## 📌 Visão Geral do Sistema
O **Escavador de Pendências** é uma solução de RPA (Robotic Process Automation) de alto nível construída em **Python** utilizando **Playwright** como motor de automação web. Ele foi projetado para contornar de forma resiliente as instabilidades do portal e-CAC da Receita Federal, gerenciar outorgas de procurações, tratar notificações bloqueantes e extrair a real situação fiscal (emitindo **CND** em PDF se a empresa estiver regular, ou baixando o **Relatório de Pendências** se houver débitos).

---

## 🗺️ Mapa Visual do Fluxo de Execução

```mermaid
graph TD
    A([Início da Execução]) --> B[Carregar config.json e clientes.csv]
    B --> C{Existe state.json válido?}
    
    %% Mapeamento de Login
    C -- NÃO / --login --> D[Modo Interativo - Abrir Chrome]
    D --> E[Aguardar Login do Usuário no e-CAC]
    E --> F[Thread paralela: press_enter via Windows API]
    F --> G[Salvar cookies e estado de sessão em state.json]
    G --> H[Fechar Chrome e reiniciar em background]
    
    C -- SIM --> I[Modo Autônomo - Carregar state.json]
    H --> I
    
    %% Início do Loop de Clientes
    I --> J[Iniciar Loop de Clientes Ativos]
    J --> K{Cliente está Ativo?}
    
    K -- NÃO --> L[Ignorar e Pular Cliente]
    K -- SIM --> M{Consultado com sucesso hoje?}
    
    M -- SIM --> N[Pular Cliente - Já Processado]
    M -- NÃO --> O[Iniciar Rotina do Cliente - Status: Pendente]
    
    %% Tratamento de Overlays e Caixa Postal
    O --> P[Remover Modais/Overlays do DOM]
    P --> Q{Existe Caixa Postal bloqueante?}
    Q -- SIM --> R[Ir para Caixa Postal, salvar Alerta TXT/JSON e retornar]
    Q -- NÃO --> S[Verificar Perfil Ativo no Cabeçalho]
    R --> S
    
    %% Troca de Perfil
    S --> T{CNPJ do Cliente = CNPJ Ativo?}
    T -- SIM --> V[Ignorar Mudança de Perfil]
    T -- NÃO --> U[Alterar Perfil de Acesso no e-CAC]
    U --> W{CNPJ Alvo = Procurador?}
    W -- SIM --> X[Clicar em Perfil: Titular]
    W -- NÃO --> Y[Preencher CNPJ e clicar em Alterar]
    X --> Z[Validar CNPJ no Cabeçalho]
    Y --> Z
    
    %% Acesso à Situação Fiscal e Bypass
    V --> AA[Navegar para Certidões e Situação Fiscal]
    Z --> AA
    AA --> AB[Clicar em Consulta Pendências - Situação Fiscal]
    AB --> AC[Abrir Nova Aba servicos.receitafederal.gov.br]
    AC --> AD{Exige reautenticação Gov.br?}
    AD -- SIM --> AE[Clicar em Entrar com Gov.br - Bypass Automático]
    AD -- NÃO --> AF[Aguardar Carregamento dos Dados Fiscais]
    AE --> AF
    
    %% Decisão Contábil
    AF --> AG{Status na Tela = 'Sem pendência'?}
    
    %% Fluxo Regular (CND)
    AG -- SIM --> AH[Localizar Botão Baixar Certidão]
    AH --> AI{Botão CND Localizado?}
    AI -- SIM --> AJ[Baixar CND Oficial em PDF]
    AI -- NÃO --> AK[Fallback: Emitir CND via Menu Tradicional e-CAC]
    AJ --> AM[Salvar Status: Sucesso - Certidão Baixada]
    AK --> AM
    
    %% Fluxo com Débitos (Relatório)
    AG -- NÃO --> AL[Localizar e Clicar em Baixar/Gerar Relatório]
    AL --> AN[Baixar Relatório Fiscal em PDF]
    AN --> AO[Salvar Status: Sucesso - Relatório Baixado]
    
    %% Finalização do Loop
    AM --> AP[Retornar para Home do e-CAC]
    AO --> AP
    AP --> AQ{Mais Clientes?}
    
    AQ -- SIM --> J
    AQ -- NÃO --> AR[Gerar Painel de Controle Excel Consolidado]
    AR --> AS[Gravar Cópia no Desktop do Usuário]
    AS --> AT([Fim da Rotina])
    
    %% Tratamento de Erros (Auto-Healing)
    O -.->|Falha Crítica / Procuração Inválida| AU[Capturar Screenshot da Tela erro_execucao.png]
    AU -.-> AV[Salvar Status: Erro e Detalhes]
    AV -.-> AP
```

---

## 🛠️ Detalhamento Técnico do Fluxo de Automação

### 1. Inicialização e Carga Parametrizada
*   **`load_config()`**: Carrega as diretrizes do arquivo `config.json` (como o modo de visualização `headless`, tempo limite de conexões e caminhos de saída).
*   **`load_clients()`**: Lê a lista `clientes.csv`. Possui **Parser de Auto-Healing** que detecta codificação do Windows (`utf-8-sig` para tolerar arquivos gerados pelo Microsoft Excel) e mapeia os cabeçalhos das colunas de forma inteligente (independente de maiúsculas/minúsculas, espaços extras ou variações como `Documento` / `CNPJ` / `Razão Social`).
*   **Detecção de Certificado do Procurador**: Varre o diretório em busca de arquivos `.pfx`, extraindo o CNPJ do Procurador pelo nome do arquivo via Expressões Regulares (`re.search(r"\d{14}", filename)`). Isso é essencial para saber quando o robô deve atuar como "Titular" ou "Procurador".

### 2. Gestão Inteligente de Sessão (`state.json`)
*   **Aproveitamento de Cookies**: O portal do e-CAC possui sessões curtas, mas que duram algum tempo. O robô sempre busca o arquivo `state.json` (que armazena os cookies e local storage). Se ele existir, o robô pula o login inicial e vai **diretamente para a varredura em segundo plano (Modo Autônomo)**, economizando tempo.
*   **Login Interativo com Confirmação Nativa (`press_enter`)**: 
    Se o arquivo `state.json` não existir ou a sessão expirar, o robô inicia no **Modo Interativo** (abrindo o Chrome visível). Como o diálogo de seleção de Certificado Digital é uma janela nativa do Windows (blindada contra automações web normais), o robô inicia uma **thread em background** que aguarda o momento exato e envia a instrução **ENTER** diretamente para o sistema operacional (`ctypes.windll.user32.keybd_event`), simulando o clique humano. 
    Uma vez feito o login, a sessão ativa é gravada no `state.json` para as próximas execuções.

### 3. Transição Resiliente de Perfis (Profile Swapping)
Para consultar cada cliente, o robô precisa alterar o perfil ativo no e-CAC de forma dinâmica:
1.  **Limpeza Preventiva (`fechar_modais_e_overlays`)**: Antes de clicar em qualquer botão, o robô remove ativamente do DOM quaisquer elementos jQuery UI, tutoriais de novidades ou modais flutuantes que possam bloquear ou interceptar fisicamente os cliques do mouse.
2.  **Bypass de Caixa Postal Bloqueante**: O e-CAC costuma bloquear o acesso a serviços fiscais exibindo uma tela de aviso que obriga a leitura de mensagens da Caixa Postal. O robô detecta esse modal, clica em "Ir para a Caixa Postal", localiza a mensagem de alerta ou não lida, extrai seu assunto e corpo completo salvando-os em `ALERTA_CAIXA_POSTAL.txt` e `.json` dentro da pasta do cliente, e reestabelece a rota retornando à página inicial sem travar a rotina.
3.  **Troca de Representação**:
    *   **Retorno ao Escritório (Titular)**: Se o cliente da vez for o próprio procurador, o robô clica no botão dedicado `[ Titular ]`.
    *   **Representação de Clientes (Procurador de PJ)**: Se for uma empresa representada, clica em "Alterar perfil de acesso", localiza o campo de CNPJ do procurador por XPath resiliente ancorado à label de texto, preenche o CNPJ e submete.
    *   **Validação de Segurança**: O robô monitora o cabeçalho por até 10 segundos. Se o e-CAC rejeitar a alteração (procuração revogada, inativa ou expirada), o erro é capturado, um **screenshot de erro** (`erro_execucao.png`) é gerado na pasta do cliente e o robô pula para o próximo sem interromper a execução do lote.

### 4. Motor de Decisão Contábil (CND vs Relatório)
Ao acessar a página de situação fiscal do cliente no domínio `servicos.receitafederal.gov.br`, o robô executa a rotina crítica:
*   **Bypass de Reautenticação Gov.br**: Se o novo domínio perder a sessão e exibir o botão `[ Entrar com GovBR ]`, o robô clica automaticamente e se reautentica em frações de segundo aproveitando o certificado em cache.
*   **Auto-Representação**: Se o CNPJ no novo portal estiver incorreto, ele gerencia a troca de perfil diretamente no avatar e dropdown do novo portal.
*   **Leitura Contábil**: O robô lê o texto completo da tela fiscal:
    *   **Regular ("não foram encontradas pendências" / "Sem pendência")**: Clica no botão **`[ Baixar Certidão ]`** no rodapé para obter a **CND Oficial em PDF**. Se houver falha de rede/timeout, ele executa um fallback que fecha a aba, volta ao e-CAC tradicional e emite a certidão pelo menu de certidões tradicional.
    *   **Com Débitos**: Clica no botão **`[ Baixar Relatório ]`** no rodapé, colhendo o **Relatório de Situação Fiscal detalhado** contendo todas as pendências federais.
*   **Organização de Arquivos**: Salva os PDFs com nomes padronizados (`CertidaoRegularidadeFiscal-[CNPJ]-[DATA].pdf` ou `RelatorioSituacaoFiscal-[CNPJ]-[DATA].pdf`) organizados sob a pasta `relatorios\<Nome_Cliente_Higienizado>\<Data>\`.

### 5. Consolidação de Resultados no Painel Excel Premium
Ao final de toda a varredura, o robô unifica os status coletados e gera o **Relatório Consolidado de Pendências e-CAC** utilizando a biblioteca `openpyxl`:
*   **Estética Profissional e Sofisticada**: Aplicação da paleta de cores institucional da **J&J Contabilidade**, com bloco de título em Azul Marinho Navy (`#1F4E78`), fontes brancas e cinzas e linhas de grade nativas do Excel ativadas para máxima precisão visual.
*   **Formatação Condicional por Status**:
    *   🟩 **Verde Suave (`#C6EFCE`)**: Empresa regular (CND emitida com sucesso).
    *   🟥 **Vermelho Coral (`#FFC7CE`)**: Empresa com pendências (Relatório detalhado baixado).
    *   🟨 **Amarelo Suave (`#FFF2CC`)**: Falha no processamento (Procuração inativa ou erro).
    *   ⬜ **Cinza Claro (`#F2F2F2`)**: Cliente inativo no CSV (Ignorado na rotina).
*   **Integração de Alertas**: Se um alerta de caixa postal foi capturado hoje, a planilha detalha o assunto e conteúdo na coluna dedicada `Alerta Caixa Postal (e-CAC)`.
*   **Fórmulas Inteligentes**: A barra de totalizadores contábeis utiliza fórmulas nativas (`COUNTA` e `COUNTIF`), permitindo que filtros manuais recalculam automaticamente a situação das empresas.
*   **Duplo Acesso**: A planilha é salva na pasta de relatórios e uma **cópia idêntica com timestamp é inserida diretamente no Desktop (Área de Trabalho)** do usuário, garantindo acessibilidade em um clique.

---

## 🛡️ Mecanismos de Tolerância a Falhas (Auto-Healing)
1.  **Redundância CND**: Emissão dupla (tenta pela página de pendências; se falhar, tenta pelo menu clássico de certidões).
2.  **Screenshots de Auditoria**: Em caso de erros visuais ou falha de sistema, um snapshot de alta qualidade é salvo na pasta diária do cliente sob o nome `erro_execucao.png`.
3.  **Resiliência a Modais**: Remoção forçada de overlays jQuery UI via injeção JavaScript direta no DOM.
4.  **Desacoplamento de Instalação**: O robô roda de forma portátil em contas de usuário padrão sem exigir privilégios de administrador do Windows para editar chaves de registros do sistema.
