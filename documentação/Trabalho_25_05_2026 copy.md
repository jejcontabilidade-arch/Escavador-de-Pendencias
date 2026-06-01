# Diário de Trabalho - 25/05/2026 (Metodologia WillianBO)

Este documento registra as implementações, melhorias de arquitetura, correções de bugs de infraestrutura/integração e validações efetuadas no sistema **Escavador de Pendências e-CAC & Nota Fiscal XML** no dia de hoje.

---

## 📅 Backlog do Dia (Tarefas)

- [x] Migração de nomenclatura e reestruturação para **Nota Fiscal XML** (anterior Inutilização/Manifestação) em todo o ecossistema (backend, automação, web e WhatsApp).
- [x] Adicionar botões **"Parar Processo"** independentes para e-CAC e Nota Fiscal XML no painel web.
- [x] Investigar e corrigir inicialização involuntária do robô via mensagens do WhatsApp.
- [x] Habilitar exibição visual das automações na tela do servidor (Chrome visível) mesmo quando o servidor Flask roda oculto em background.
- [x] Configurar um intervalo/delay de **5 segundos** em cada loop de execução de cliente para fins de acompanhamento visual.
- [x] Validar a compilação e estabilidade de todo o projeto.

---

## 🏗️ Planejamento & Arquitetura

### Integração do WhatsApp e Robôs
A comunicação é intermediada por um gateway local em Node.js (`whatsapp_gateway/gateway.js`) que usa o `whatsapp-web.js` para escutar mensagens. As mensagens válidas vindas de contatos cadastrados em `autorizados.csv` são enviadas via webhook para o backend Flask (`app.py`), o qual interpreta as mensagens com NLP (GPT-4o-mini ou heurística local em `agente_escavador.py`) e dispara os robôs `executar.py` (e-CAC) ou `consultar_nota_fiscal_xml.py` (XML) em subprocessos assíncronos.

### Arquitetura de Visibilidade de Processo no Windows
O painel web Flask é normalmente executado sem console através de um VBScript invisível (`Iniciar_Escavador_Silencioso.vbs`) para que não incomode o usuário com terminais persistentes. Contudo, no Windows, subprocessos filhos herdam por padrão a flag de ocultação de janela do processo pai. Para permitir que o Chrome controlado pelo Playwright abra de forma visível (`headless: false`), planejou-se o uso da flag `creationflags=subprocess.CREATE_NEW_CONSOLE` na chamada de `subprocess.Popen` em Python, isolando o processo console do robô e restaurando seu estado visível normal.

---

## 🛠️ Implementação Detalhada

### 1. Migração para Nota Fiscal XML e Botões de Parada
* Criou-se o script [consultar_nota_fiscal_xml.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/consultar_nota_fiscal_xml.py) unificando a consulta pública no portal da NF-e. Os resultados consolidados são gravados em `C:\Users\jejco\Desktop\nota_fiscal_xml.xlsx`.
* O painel web em [index.html](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/templates/index.html) foi atualizado com botões de interrupção forçada vermelhos ("Parar Processo"). Estes botões chamam endpoints de parada que usam comandos de SO (`taskkill` filtrando por perfil do navegador) para limpar com segurança os navegadores órfãos e arquivos de trava como `SingletonLock`.

### 2. Visibilidade da Janela do Chrome via CREATE_NEW_CONSOLE
No arquivo [app.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/app.py), configuramos a execução dos subprocessos em consoles visíveis separados:
```python
creationflags = 0
if os.name == 'nt':
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 1  # SW_SHOWNORMAL (Força a janela a aparecer)
    creationflags = subprocess.CREATE_NEW_CONSOLE  # Cria console visível independente
```
Isso foi aplicado nos quatro métodos de spawning de processos dentro do backend (no painel gráfico e nas callbacks do WhatsApp).

### 3. Atraso de 5 Segundos por Cliente
* Em [executar.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/executar.py), alterou-se a linha 2200 de `time.sleep(60)` para `time.sleep(5)`.
* Em [consultar_nota_fiscal_xml.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/consultar_nota_fiscal_xml.py), adicionou-se `time.sleep(5)` no fechamento de cada loop de cliente.
* Isso concede exatamente 5 segundos de navegador aberto no portal ao final de cada execução individual, permitindo leitura visual dos status antes da transição.

---

## 🚨 Gestão de Incidentes (Troubleshooting)

### Incidente: Automação inicia sozinha sem cliques ou comandos
* **Problema:** A automação e-CAC ou XML iniciava de maneira involuntária durante conversas comuns do operador com terceiros.
* **Causa Raiz:** O webhook do WhatsApp recebia notificações para todas as mensagens, incluindo mensagens enviadas do próprio celular do operador (`fromMe = true`) e de chats em grupos (`isGroup = true`). Adicionalmente, a heurística de análise de comandos apenas buscava a presença da string `"iniciar"`, de modo que frases como *"Como posso iniciar?"* iniciavam o robô imediatamente.
* **Solução Definitiva:**
  * Modificou-se o início da função [processar_mensagem_recebida](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/agente_escavador.py#L411) para ignorar webhooks onde `fromMe` ou `isGroup` fossem booleanos ou strings avaliando para verdadeiro.
  * Aprimorou-se a heurística em [interpretar_mensagem_heuristica](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/agente_escavador.py#L356) exigindo que verbos de ação como `"iniciar"` ou `"rodar"` estejam pareados a termos operacionais (como `"varredura"`, `"ecac"`, `"xml"`, `"notas"`) para justificar o disparo.

---

## 🔬 Validação e QA (Works)

### Testes de Compilação
Todos os módulos foram submetidos a testes de compilação sem apresentar qualquer erro de sintaxe:
1. `python -m py_compile app.py` -> **SUCESSO**
2. `python -m py_compile agente_escavador.py` -> **SUCESSO**
3. `python -m py_compile executar.py` -> **SUCESSO**
4. `python -m py_compile consultar_nota_fiscal_xml.py` -> **SUCESSO**

### Testes Manuais de Execução e Visibilidade
* Disparou-se a automação pelo painel web e confirmou-se que a janela de console do robô e o navegador Google Chrome (visível) abriram em primeiro plano no desktop do Windows.
* Validou-se que o navegador permanece 5 segundos parado exibindo o portal antes de passar para o cliente seguinte da lista.
* Enviou-se mensagens contendo a palavra "iniciar" em grupos e conversas informais, certificando que o robô não ativa mais por engano. Ao enviar a mensagem *"iniciar varredura"*, o robô decola de imediato.

---

## 🔒 Checklist de Segurança e Escalabilidade

- [x] Variáveis sensíveis e chaves de API carregadas via `config_private.json` e isoladas do repositório público.
- [x] Filtro contra loop de mensagens ativado (bloqueando `fromMe` no webhook).
- [x] Separação estrita dos perfis de navegação do Chrome (`chrome_profile_chrome` e `chrome_profile_nota_fiscal_xml`) possibilitando execução simultânea sem colisões ou erros de lock de perfil de usuário.
- [x] Sanitização de arquivos de travamento (`SingletonLock`) na interrupção forçada dos robôs.
