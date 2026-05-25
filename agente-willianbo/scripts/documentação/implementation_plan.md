# Plano de Implementação - Correção de Navegadores Duplos e Telas Vazias no e-CAC

Este plano descreve as correções para evitar a abertura concorrente de múltiplos navegadores (Google Chrome e Microsoft Edge) e solucionar as falhas de carregamento de páginas deslogadas ou em branco (sem botões de download) no portal do e-CAC.

---

## 1. Análise do Problema (Causa Raiz)

1. **Abertura Concorrente de Navegadores**:
   - O robô tenta iniciar o Google Chrome nativo (`channel="chrome"`) usando perfil persistente em `temp/chrome_profile_chrome`.
   - Se uma execução anterior travou ou foi encerrada abruptamente, processos do Chrome podem continuar órfãos em segundo plano no Windows, mantendo bloqueado o arquivo `SingletonLock` do perfil.
   - Ao tentar abrir o Chrome, o Playwright falha devido a esse bloqueio. O script captura a falha e entra em um fluxo de fallback tentando iniciar o Microsoft Edge (`channel="msedge"` em `temp/chrome_profile_msedge`).
   - O usuário acaba visualizando o Chrome (travado em background ou aberto pelo usuário) e o Edge (fallback ativo da automação) simultaneamente.

2. **Telas Vazias e Sem Botões no e-CAC**:
   - Quando o robô cai no fallback do Edge, a sessão e os cookies salvos originalmente no `state.json` (que pertencem ao Chrome) são injetados em um navegador diferente, ou o Edge não consegue interagir corretamente com o diálogo de certificados digitais do Windows (que costuma estar focado ou respondendo ao Chrome).
   - O e-CAC carrega deslogado ou cai em telas de erro vazias que não possuem os botões operacionais e relatórios.

---

## 2. Proposta de Solução

### A. Limpeza Cirúrgica de Processos Órfãos
* Implementar a função `limpar_processos_automatizados_antigos()` no script `executar.py`.
* Essa função usará comandos do PowerShell executados via `subprocess` para encerrar todos os processos do Chrome/Edge que contenham a linha de comando contendo a pasta do perfil da nossa automação (`chrome_profile_`). 
* **Por que isso é seguro?** Não afeta o Chrome/Edge de uso pessoal do usuário, pois encerra exclusivamente os processos vinculados às pastas de perfil da automação.
* Remover fisicamente os arquivos `SingletonLock` remanescentes nas pastas de perfil para destravar a inicialização.

### B. Fixação do Navegador (Sem Fallbacks Mistos)
* Leremos do `config.json` a chave `"browser"` (com padrão `"chrome"`).
* As funções `realizar_login_manual()` e `iniciar_navegador()` tentarão iniciar **exclusivamente** o navegador configurado.
* Se a inicialização falhar (ex: por bloqueio persistente), o script fará uma nova limpeza de processos e tentará novamente. Caso a falha persista, o erro será exibido de forma explícita, evitando abrir navegadores concorrentes silenciosamente que corrompam o estado da sessão.

---

## 3. Modificações Propostas

### 1. Automação do e-CAC (`executar.py`)

#### [MODIFY] [executar.py](file:///c:/Users/jejco/Desktop/Escavador%20de%20Pendencias/executar.py)

* **Adicionar a função de limpeza de processos órfãos:**
  ```python
  def limpar_processos_automatizados_antigos():
      log("Iniciando limpeza preventiva de processos órfãos da automação...", "SYSTEM")
      import subprocess
      # Filtro no PowerShell para matar apenas processos do Chrome/Edge que rodam a partir de nossos perfis automatizados
      cmd = (
          'powershell -NoProfile -Command "'
          'Get-CimInstance Win32_Process -Filter \\"Name = \'chrome.exe\' or Name = \'msedge.exe\' or Name = \'chromedriver.exe\' or Name = \'msedgedriver.exe\'\\" '
          '| Where-Object { $_.CommandLine -like \'*chrome_profile_*\' } '
          '| ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"'
      )
      try:
          subprocess.run(cmd, shell=True, capture_output=True, text=True)
          log("Processos órfãos anteriores finalizados com sucesso.", "SUCCESS")
      except Exception as e:
          log(f"Aviso ao finalizar processos antigos: {e}", "WARNING")

      # Apagar arquivos SingletonLock para destravar o perfil
      for folder in ["chrome_profile_chrome", "chrome_profile_msedge", "chrome_profile"]:
          lock_path = os.path.join("temp", folder, "SingletonLock")
          if os.path.exists(lock_path):
              try:
                  os.remove(lock_path)
                  log(f"Arquivo de lock removido: {lock_path}", "SUCCESS")
              except Exception as e:
                  pass
  ```

* **Chamar a limpeza no início da execução:**
  - Chamar `limpar_processos_automatizados_antigos()` na primeira linha da função `main()`.
  - Chamar `limpar_processos_automatizados_antigos()` no início da função `iniciar_navegador()` sempre que o navegador for reiniciado devido a falhas durante a varredura.

* **Refatorar `realizar_login_manual(config)`:**
  - Ler a configuração do navegador: `browser_choice = config.get("browser", "chrome").lower()`.
  - Se for `"chrome"`, instanciar apenas com `channel="chrome"` e perfil `temp/chrome_profile_chrome`.
  - Se for `"msedge"`, instanciar apenas com `channel="msedge"` e perfil `temp/chrome_profile_msedge`.
  - Em caso de falha ao inicializar, tentar realizar a limpeza de processos órfãos e tentar de novo uma vez. Se falhar novamente, lançar erro claro de ambiente.

* **Refatorar `iniciar_navegador()` dentro de `main()`:**
  - Seguir a mesma regra estrita do navegador configurado.
  - Eliminar fallbacks para outros navegadores que misturem perfis de sessão e causem instabilidade no e-CAC.

---

## 4. Plano de Verificação

### Testes Manuais
1. **Verificação de Limpeza de Processos**:
   - Iniciar o robô, interrompê-lo manualmente no meio da execução e rodar novamente.
   - Validar via console se os processos do ciclo anterior foram encerrados e se apenas uma janela do navegador Google Chrome é aberta na nova execução.
2. **Consistência da Sessão**:
   - Concluir o login no Chrome e rodar a varredura dos clientes.
   - Verificar se as páginas do e-CAC carregam corretamente com todas as informações e botões de baixar relatório/certidão ativos, sem retornar telas vazias ou deslogadas.
