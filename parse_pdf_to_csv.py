import os
import csv
import re
import pypdf

def main():
    pdf_path = r"C:\Users\jejco\Desktop\Escavador de Pendencias\Relação de Férias Geral.pdf"
    csv_path = r"C:\Users\jejco\Desktop\Escavador de Pendencias\clientes.csv"
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF not found at {pdf_path}")
        return
        
    print(f"Parsing PDF: {pdf_path}")
    reader = pypdf.PdfReader(pdf_path)
    
    # Dicionário para armazenar cnpj -> nome (para unicidade)
    extracted_companies = {}
    
    for page_num, page in enumerate(reader.pages):
        text = page.extract_text()
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        company_name = None
        cnpj = None
        
        for idx, line in enumerate(lines):
            # Encontrar o nome da empresa (linha seguinte ao cabeçalho da tabela)
            if "Código Nome Admissão Vcto" in line or "Código Nome Admissão" in line:
                if idx + 1 < len(lines):
                    company_name = lines[idx + 1]
                    
            # Encontrar o CNPJ da empresa
            if "Empresa: CNPJ/CPF:" in line:
                parts = line.split("Empresa: CNPJ/CPF:")
                if len(parts) > 1:
                    raw_cnpj = parts[1].strip()
                    # Manter apenas dígitos
                    cnpj = "".join(filter(str.isdigit, raw_cnpj))
                    
        if company_name and cnpj:
            # Caso o nome venha com alguma sujeira comum de quebra de página
            company_name = company_name.replace("Emissão:", "").strip()
            # Se já existir e o nome atual for maior ou sem abreviação, atualiza
            if cnpj not in extracted_companies or len(company_name) > len(extracted_companies[cnpj]):
                extracted_companies[cnpj] = company_name
                
    print(f"Extracted {len(extracted_companies)} unique companies from PDF:")
    for c, n in extracted_companies.items():
        print(f" - {c}: {n}")
        
    # CNPJs de exemplo a serem apagados (de acordo com a imagem)
    cnpjs_a_excluir = {
        "02241127000128", # CONDOMINIO DO EDIFICIO AERONAUTICA
        "38050811000170", # CONDOMINIO EDIFICIO SOLAR
        "37115714000155", # CONDOMINIO DO EDIFICIO SHCE SUL QUADRA 1505 PROJECAO 03
        "38050753000184", # CONDOMINIO DO BLOCO C DA SQS III
        "01599281000103", # CLIENTE_01599281000103
        "37992979000131", # ANDRADE E BARROS SERVICOS ADMINISTRATIVOS LTDA
        "37993599000111", # CLIENTE_37993599000111
        "02273061000158"  # CONDOMINIO DO BLOCO I DA SQN 204
    }
    
    # Clientes originais a serem mantidos se existirem no CSV original
    # (Mantemos as duas primeiras linhas de clientes legítimos: Tome e Lopes e JEJ)
    legitimate_original_clients = {
        "26470042000180": "TOME E LOPES RESTAURANTE E LANCHONETE LTDA",
        "05443435000124": "JEJ SERVICOS PROFISSIONAIS LTDA"
    }
    
    # Combinar dados legítimos mantendo a ordem e a unicidade
    final_clients = {}
    
    # 1. Adicionar os clientes originais legítimos
    for c, n in legitimate_original_clients.items():
        final_clients[c] = n
        
    # 2. Adicionar os clientes extraídos do PDF (ignorando os de exclusão)
    for c, n in extracted_companies.items():
        if c in cnpjs_a_excluir:
            print(f"Ignorando CNPJ de exemplo: {c} ({n})")
            continue
        final_clients[c] = n
        
    print(f"\nConsolidando {len(final_clients)} clientes legítimos no arquivo CSV...")
    
    # Salvar no arquivo CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["cnpj", "nome", "ativo"])
        for c, n in final_clients.items():
            writer.writerow([c, n, "True"])
            
    print(f"Arquivo CSV atualizado com sucesso em: {csv_path}")

if __name__ == "__main__":
    main()
