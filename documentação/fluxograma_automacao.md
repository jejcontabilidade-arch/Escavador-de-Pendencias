# 🗺️ Fluxograma de Execução do Escavador de Pendências e-CAC

> **Nível Arquiteto de Software Contábil Sênior — Metodologia Agente WillianBO**

Este documento detalha o desenho exato do fluxo lógico de execução da automação, detalhando as tomadas de decisões inteligentes para seleção de perfil, auto-bypass de login Gov.br, e o motor de download dinâmico (CND vs Relatório).

---

```text
===================================================================================================
                    ESCAVADOR DE PENDÊNCIAS E-CAC — FLUXOGRAMA DE EXECUÇÃO
===================================================================================================

                        _________________________________________________
                        |         INÍCIO DA EXECUÇÃO (executar.py)       |
			_________________________________________________
                                                 ▼
                        ___________________________________________________
                        |    1. Carrega configurações do config.json     |
                        |    2. Carrega lista ativa do clientes.csv      |
                        ─_________________________________________________─
                                                 │
                                                 ▼
                                     /───────────────────────\
                                    <   Existe o state.json   > ──── (Verifica sessão ativa)
                                     \───────────────────────/
                                      /                     \
                               [NÃO] /                       \ [SIM]
                                    /                         \
                                   ▼                           ▼
                     _________________________       ________________________
                     |     MODO INTERATIVO    |     |      MODO AUTÔNOMO     |
                     |  - Abre Chrome Visível |     |  - Roda em Headless    |
                     |  - Executa login manual|     |  - Restaura cookies    |
                     |  - Grava cookies/sessão|     |    de sessão ativa     |
                     _________________________       ________________________
                                 │                              │
                                 └──────────────┬───────────────┘
                                                │
                                                ▼
                                    _________________________   
                                    |     INICIA O LOOP DE   |
                                    |     CLIENTES ATIVOS    |
                                    _________________________   
                                                │
                               ┌────────────────┴────────────────┐
                               ▼                                 ▼
                        [Cliente Ativo]                   [Cliente Inativo]
                         (ativo=True)                      (ativo=False)
                               │                                 │
                               ▼                                 ▼
                     _________________________          _________________________   
                     |  Lê CNPJ no cabeçalho  |         |     PULA CLIENTE       |
                     |  da página do e-CAC    |         |   (Ignora da rotina)   |
                     _________________________           _________________________       ─
                               │
                               ▼
                        /──────────────────────────────────────────────\
                       <   CNPJ do Cliente = CNPJ ativo no cabeçalho?   >
                        \──────────────────────────────────────────────/
                          /                                          \
                   [NÃO] /                                            \ [SIM]
                        ▼                                              ▼
          _|___________________________________              __________________________   
          |      MUDANÇA DE PERFIL (Alterar)   |             |  PULA A MUDANÇA        |
          |  1. Clica em "Alterar perfil..."   |             |  (CNPJ do cliente já é |
          |  2. Se destino = Procurador PJ:    |             |   o perfil que está    |
          |     - Insere CNPJ e clica Alterar  |             |   ativo no e-CAC)      |
          |  3. Se destino = Titular original: |              _________________________   
          |     - Clica no botão [ Titular ]   |                         │
          |  4. Valida CNPJ no cabeçalho       |                         │
            ___________________________________                          │
                         │                                               │
                         └──────────────────────┬────────────────────────┘
                                                │
                                                ▼
                                     _________________________   
                                    |     Navega no e-CAC:   |
                                    |  "Certidões e Situação"|
                                    |  -> "Consulta Pendência"|
                                      _________________________   
                                                │
                                                ▼
                                    _||||||||||||||||||||||||_
                                    |   Abre a aba fiscal    |
                                    |   (servicos.receita)   |
                                    ─||||||||||||||||||||||||─
                                                │
                                                ▼
                                     /───────────────────────\
                                    <   Exige login Gov.br?   > ─── (Segurança do domínio)
                                     \───────────────────────/
                                      /                     \
                               [SIM] /                       \ [NÃO]
                                    /                         \
                                   ▼                           ▼
                      ───────────────────────        ───────────────────────
                     |  BYPASS AUTOMÁTICO GOV |     | Carrega tela fiscal    |
                     |  - Clica "Entrar GovBR"|     | de forma direta        |
                     |  - Sincroniza sessão   |      ─────────────────────────
                       ───────────────────────                  │
                                 │                              │
                                 └──────────────┬───────────────┘
                                                │
                                                ▼
                                    __________________________
                                    | Lê corpo de texto (DOM)|
                                    |  da página de Consulta |
                                      ───────────────────────
                                                │
                                                ▼
                               /───────────────────────────────────\
                              <  Status da tela = "Sem pendência"?  >
                               \───────────────────────────────────/
                                /                                 \
                         [SIM] /                                   \ [NÃO]
                              /                                     \
                             ▼                                       ▼
                 ───────────────────────                 ───────────────────────
               |  CLIENTE REGULAR (CND) |              |  CLIENTE COM DÉBITOS   |
               |  - Localiza botão:     |              |  - Localiza botão:     |
               |   [ Baixar Certidão ]  |              |   [ Baixar Relatório ] |
               |  - Clica e baixa o PDF |              |  - Clica e baixa o PDF |
               |  - Salva em PDF CND    |              |  - Salva em PDF Relat  |
                ───────────────────────                 ───────────────────────                                       		  
                  (Se falhar, faz                                  │
                   fallback via menu                               │
                   tradicional e-CAC)                              │
                           │                                       │
                           └───────────────────┬───────────────────┘
                                               │
                                               ▼
                                   ─────────────────────────
                                   |  1. Fecha aba fiscal   |
                                   |  2. Salva status.json  |
                                   |     do cliente na pasta|
                                   ─────────────────────────
                                               │
                                               ▼
                                     /───────────────────\
                                    <   Mais clientes?    >
                                     \───────────────────/
                                      /                 \
                               [SIM] /                   \ [NÃO]
                                    /                     \
                                   ▼                       ▼
                         [ REINICIA O LOOP ]       __________________________
                                                   | Grava Relatório Final  |
                                                   | Consolidado da Rotina  |
                                                   |   - Clientes Sucesso   |
                                                   |   - Clientes Falhas    |
                                                   __________________________
                                                               │
                                                               ▼
                                                        [ FIM DO ROBÔ ]
===================================================================================================
```

---

## 🧭 Legenda e Guia Técnico das Linhas de Execução 

* **`load_config()` & `load_clients()`**: Engrenagens iniciais de inteligência. Configuram os tempos limite (`timeout`), pastas de destino e a lista de CNPJs de clientes.
* **Decisão de Sessão (`Existe state.json?`)**: O robô é inteligente para pular o login interativo. Se já houver um login ativo registrado de hoje, ele inicia em background direto para a varredura.
* **Módulo de Mudança de Perfil (`alterar`)**: Detecta se o perfil correto está ativo. Se for preciso alterar, abre o modal e gerencia a transição. Se for para voltar para o próprio escritório, reverte para `Titular` instantaneamente.
* **Auto-Bypass de Segurança**: Intercepta a transição entre domínios da Receita Federal. Caso o domínio secundário de pendências perca a sessão, o robô clica no botão do Gov.br e se reautentica em frações de segundos.
* **Motor Contábil de Decisão**: A inteligência que economiza seu tempo. O robô sabe que se a empresa está limpa, ela merece a CND oficial (Certidão Negativa). Se a empresa tem dívidas, ela precisa do Relatório Fiscal detalhado para fins de regularização. Ambos são baixados diretamente da tela de pendências de forma dinâmica.
