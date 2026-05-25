# Walkthrough - Implementação do Agente Escavador Inteligente (WhatsApp Z-API)

Nesta entrega, implementamos o **Agente Escavador Inteligente** no ecossistema da **J&J Contabilidade**, permitindo o controle completo da automação e-CAC por comandos diretos via WhatsApp, com respostas em linguagem natural e entrega de arquivos.

---

## O que foi desenvolvido

### 1. Túnel SSH Automático Zero-Setup ([tunnel_manager.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/tunnel_manager.py))
* Desenvolvemos um orquestrador que roda em uma thread paralela do Flask e abre um túnel SSH seguro e persistente via `localhost.run`.
* Esse túnel expõe a porta local `5000` na internet sob um domínio dinâmico do tipo `.lhr.life`.
* O script extrai a URL gerada e registra o webhook automaticamente na Z-API chamando o endpoint `/update-webhook-received`.

### 2. Cérebro do Agente Escavador ([agente_escavador.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/agente_escavador.py))
* Criamos o cérebro NLP integrado com a OpenAI API (`gpt-4o-mini`) que interpreta mensagens em linguagem natural do usuário autorizado.
* Caso ocorra qualquer indisponibilidade da OpenAI, o agente possui uma camada de fallback heurística resiliente.
* Criamos funções para ler o status em tempo real da automação e gerar resumos textuais elegantes de progresso, sucessos e falhas.
* Implementamos um localizador inteligente de arquivos que busca PDFs de certidões/relatórios de um cliente específico nas pastas de relatórios, codifica em Base64 e os envia no chat como anexo via Z-API.

### 3. Endpoint Webhook Assíncrono ([app.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/app.py))
* Adicionamos a rota `/api/webhook/whatsapp` que recebe as mensagens.
* O processamento das intenções é delegado a uma thread assíncrona, respondendo status `200 OK` instantaneamente à Z-API para evitar reenvios.
* Configuramos uma barreira de segurança que valida e responde estritamente às mensagens vindas do número autorizado (`whatsapp_number` em `config_private.json`).

### 4. Notificações do Robô durante o Processamento ([executar.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/executar.py))
* Injetamos disparos de mensagens WhatsApp em pontos chaves da execução do robô:
  * Ao iniciar a consulta de uma empresa específica.
  * Ao concluir com sucesso (informando o status).
  * Ao falhar (informando o erro detalhado da tela).

### 5. Procedimento de Intervenção Manual e Captura de URL ([executar.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/executar.py))
* **Mapeamento de Impasses e Captchas:** Adicionamos a detecção de URL (`page.url`) em tempo real em todas as situações de impasse em que a automação aguarda a ação do usuário (como resolução de Captchas ou telas de certificado bloqueadas).
* **Alertas no WhatsApp com Link:** O robô envia o link exato da página atual no e-CAC/Gov.br diretamente ao celular cadastrado do usuário via WhatsApp, permitindo que a intervenção seja ágil e precisa.
* **Logs e Rastreamento:** Os erros finais de execução e as URLs correspondentes às falhas de consulta são salvos na pasta de logs e exibidos no painel para facilitar auditoria.

---

## O que foi testado

Desenvolvemos o script de testes de homologação local [testar_agente.py](file:///C:/Users/jejco/.gemini/antigravity-ide/brain/8f3b44a9-056e-4e67-a332-c75f355b7cd3/scratch/testar_agente.py) para validar as rotinas de busca heurística de intenções e a varredura e-CAC de arquivos. 

### Resultados obtidos:
```text
=== TESTANDO INTERPRETADOR HEURÍSTICO ===
[OK] 'Iniciar varredura' -> 'iniciar_varredura'
[OK] 'Como está a execução do robô?' -> 'obter_status'
[OK] 'Parar processo imediatamente' -> 'interromper_varredura'
[OK] 'Manda a certidão da Tome & Lopes' -> 'baixar_documento'
[OK] 'Quais deram erro?' -> 'listar_clientes_pendentes_erro'
[OK] 'Lista de empresas ok' -> 'listar_clientes_ok'
[OK] 'Oi, bom dia!' -> 'conversa_casual'
Resultado: 7/7 testes heurísticos bem-sucedidos.

=== TESTANDO BUSCA DE DOCUMENTOS (MOCK) ===
Buscando termo 'Tome'...
[SUCESSO] Pasta encontrada -> '26470042000180_TOME _ LOPES RESTAURANTE E LANCHONETE LTDA'
Arquivos na pasta: ['CertidaoRegularidadeFiscal-26470042000180-20260521.pdf', 'status.json']
```
Comprovamos que o bot consegue resolver os nomes curtos e associá-los perfeitamente às certidões fiscais e-CAC.

### 3. Validação em Ambiente Real e Correção de Túnel (IPv6 vs IPv4)
* **Incidente Corrigido:** Durante a homologação em tempo real, as mensagens do WhatsApp do usuário não atingiam o Flask local. Diagnosticamos que o encaminhamento do túnel SSH para `localhost:5000` resolvia para IPv6 (`::1`), enquanto o Flask escutava em IPv4 (`127.0.0.1`). Ajustamos o encaminhamento do túnel no [tunnel_manager.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/tunnel_manager.py) para utilizar `-R 80:127.0.0.1:5000`.
* **Resultado Real:** O fluxo de webhook passou a operar 100% livre. Ao receber a mensagem `"como está a varredura?"` vinda do usuário autorizado pelo WhatsApp, a requisição percorreu o túnel dinâmico e o bot respondeu em tempo real com o status atualizado do robô diretamente no chat de WhatsApp do procurador.
