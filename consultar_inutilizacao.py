# entrar nesse endereço: https://www.nfe.fazenda.gov.br/portal/principal.aspx

# clicar em consultar inutilização : <a href="consulta.aspx?tipoConsulta=inutilizacao&amp;tipoConteudo=nDmpH/MjKrg=">Consultar Inutilização</a>

# marcar checkbox : checkbox sou humano
# preenchear cnpj do cliente: ctl00$ContentPlaceHolder1$txtCNPJInutilizacao
# clicar em consultar: ctl00$ContentPlaceHolder1$btnConsultar

# verificar se não existe :Link que permite reduzir o tamanho da fonte Link que permite aumentar o tamanho da fonte
from tempfile import template
from pypdf.generic._appearance_stream import TextAlignment
Não existe registro para os dados informados.

Consultar Inutilização
CNPJ: XXXXXXXXXXXXXX
Razão Social: XXXXXXXXXXXXXXXXXXXXXXXXXXXX

Data/Hora da Consulta: XXXXXXXXXXXXXX


# clicar em nova consulta: ctl00$ContentPlaceHolder1$btnVoltar

# preencher os campos:
- cnpj do cliente
- clicar em sou humano
- clicar em consultar

#copiar a chave de acesso se aparecer na tela  

#com a chave copiada volta pra pagina inicial
# na pagina inicial clicar em consultar nfe: <a href="consultaRecaptcha.aspx?tipoConsulta=resumo&amp;tipoConteudo=7PhJ+gAVw2g=">Consultar NF-e</a>

#colar chave de acesso nfe: ctl00$ContentPlaceHolder1$txtChaveAcessoResumo
# clicar sou humano: checkbox
# cicar continuar: ctl00$ContentPlaceHolder1$btnConsultarHCaptcha
# ao abrir nova pagina clicar em dowload do documento e guardar em pasta "documentos de consulta inutilização"

# gerar o excel com resumos de cnpj e nome do cliente e chave de acesso, baixado ou nao baixado xml   
