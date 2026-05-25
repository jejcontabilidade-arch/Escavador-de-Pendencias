# Checklist de Implementação - Agente Escavador Inteligente

- [x] **Componente: Gerenciador de Túnel SSH (tunnel_manager.py)**
  - [x] Implementar execução em background do túnel SSH via `localhost.run`.
  - [x] Implementar parser para obter a URL HTTPS gerada dinamicamente.
  - [x] Implementar registro automático do webhook na Z-API.
- [x] **Componente: Inteligência de Comandos (agente_escavador.py)**
  - [x] Implementar interpretador NLP com OpenAI GPT-4o-mini usando a chave de API cadastrada.
  - [x] Integrar com comandos operacionais (iniciar, status, ok, inadimplentes, certidão).
  - [x] Implementar envio de arquivos físicos (PDF/Excel) via API da Z-API.
- [x] **Componente: Webhook no Backend Flask (app.py)**
  - [x] Expor a rota `/api/webhook/whatsapp` (POST).
  - [x] Processar mensagens de forma assíncrona com Threads para responder rápido ao webhook.
  - [x] Validar e restringir o acesso apenas ao número autorizado.
- [ ] **Componente: Notificações de Execução (executar.py)**
  - [ ] Adicionar disparos de notificações no WhatsApp durante as etapas chaves da varredura.
- [ ] **Validação e QA**
  - [ ] Criar script de teste local de fluxo de webhook `testar_agente.py`.
  - [ ] Validar funcionamento do túnel e do bot em ambiente real.
