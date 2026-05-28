PASTA DE CERTIFICADOS INTERNA DO ESCAVADOR
========================================

Se você deseja executar o robô localmente usando certificados copiados manualmente,
siga as instruções abaixo:

1. Copie o arquivo "Controle_Certificados.xlsx" para esta pasta (certificados/).
2. Crie uma subpasta chamada "CONDOMINIO" ou coloque os certificados PFX diretamente aqui dentro.
3. Certifique-se de que os nomes dos arquivos PFX contenham o CNPJ do condomínio correspondente.
4. Caso a senha do certificado não seja a padrão (123456), coloque a palavra "senha" seguida da senha real no nome do arquivo PFX. Exemplo:
   "12345678901234_condominio_teste_senha_minhasenha123.pfx"

O robô irá priorizar a rede (\\\\Srvjej\\...) e a pasta de contingência (C:\\Certificados_Escavador), mas caso ambas não estejam disponíveis, ele usará esta pasta local automaticamente!
