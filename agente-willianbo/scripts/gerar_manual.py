import os
import re

def remove_emojis(text):
    emoji_pattern = re.compile(
        r'[\U00010000-\U0010ffff]'
        r'|[\u2600-\u27FF]'
        r'|[\u2300-\u23FF]'
        r'|[\u25A0-\u25FF]'
        r'|[\u2190-\u21FF]'
        r'|[\u2000-\u206F]'
        r'|[\u2900-\u297F]'
        r'|[\u2B00-\u2BFF]',
        flags=re.UNICODE
    )
    text = emoji_pattern.sub(r'', text)
    text = re.sub(r'```[a-zA-Z]*\n[\s\S]*?```', r'\n*[Bloco de código omitido para fluidez da leitura arquitetural]*\n', text)
    text = re.sub(r'> \[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]', r'', text)
    return text

def gerar_arvore(dir_path, ignore_list, prefix=""):
    tree_str = ""
    try:
        items = sorted(os.listdir(dir_path))
    except PermissionError:
        return ""
        
    items = [i for i in items if i not in ignore_list and not i.startswith('.')]
    
    for index, item in enumerate(items):
        path = os.path.join(dir_path, item)
        is_last = (index == len(items) - 1)
        connector = "└── " if is_last else "├── "
        tree_str += f"{prefix}{connector}{item}\n"
        if os.path.isdir(path):
            extension = "    " if is_last else "│   "
            tree_str += gerar_arvore(path, ignore_list, prefix + extension)
    return tree_str

# 1. Define a pasta raiz como o diretório atual onde o script está sendo executado
root_dir = os.getcwd()

# 2. Extrai o nome do projeto dinamicamente a partir da pasta raiz
nome_pasta = os.path.basename(root_dir)
nome_projeto_base = nome_pasta.replace('_', ' ').replace('-', ' ').strip()

# Tratar para não duplicar a palavra "Sistema" no título do manual
if nome_projeto_base.lower().startswith("sistema"):
    nome_projeto = nome_projeto_base.title()
    nome_exibicao = nome_projeto_base.title()
else:
    nome_projeto = nome_projeto_base.title()
    nome_exibicao = f"Sistema {nome_projeto_base.title()}"

print(f"Iniciando documentação para o projeto: {nome_projeto} na raiz: {root_dir}")

# Pastas a serem ignoradas
pastas_ignoradas = ['node_modules', '.git', '__pycache__', '.wwebjs_auth', '.wwebjs_cache', 'dist', 'build', 'venv', 'env']

# 3. Gera a árvore do projeto
print("Mapeando estrutura do sistema...")
arvore_estrutura = gerar_arvore(root_dir, pastas_ignoradas)

# 4. Procura os arquivos .md recursivamente apenas na pasta 'documentação'
todos_mds = []
doc_dir_path = os.path.join(root_dir, "documentação")
if os.path.exists(doc_dir_path):
    for root, dirs, files in os.walk(doc_dir_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith('.md') and "Manual_Oficial" not in file:
                caminho_completo = os.path.join(root, file)
                caminho_relativo = os.path.relpath(caminho_completo, root_dir).replace('\\', '/')
                todos_mds.append(caminho_relativo)


# Organiza deixando README e documentação geral por primeiro, se existirem
arquivos_finais = sorted(todos_mds, key=lambda x: (
    0 if 'README' in x.upper() else
    1 if 'DOCUMENT' in x.upper() else
    2
))

# 5. Monta o conteúdo consolidado
conteudo_final = f"""
<div style="text-align: center; margin-top: 150px;">
    <h1 style="font-size: 32px; color: #2c3e5e;">Manual Técnico e Documentação de Arquitetura</h1>
    <h2 style="font-size: 24px; color: #34495e;">{nome_exibicao}</h2>
    <br><br><br><br>
    <h3 style="font-size: 18px; color: #7f8c8d;">Autor e Responsável Técnico</h3>
    <p style="font-size: 22px; font-weight: bold; color: #2c3e5e;">Willian Batista Oliveira</p>
    <p style="font-size: 14px; color: #555;">Desenvolvedor Sênior | Engenheiro de Sistemas | Auditor Q&A | Designer de Arquitetura | Engenheiro de Prompt</p>
    <br><br><br><br><br><br><br><br>
    <p style="font-size: 14px; color: #95a5a6;">Documentação Gerada Dinamicamente</p>
</div>

<div style="page-break-after: always;"></div>

# Estrutura e Arquitetura de Diretórios
Abaixo está o mapeamento automatizado de toda a estrutura do sistema `{nome_projeto}`, identificando os diretórios e arquivos que compõem sua arquitetura atual:

```text
{nome_pasta}/
{arvore_estrutura}
```

<div style="page-break-after: always;"></div>
"""

corpo_texto = ""

for arquivo_relativo in arquivos_finais:
    caminho_absoluto = os.path.join(root_dir, arquivo_relativo)
    if os.path.exists(caminho_absoluto):
        print(f"Incluindo documentação: {arquivo_relativo}")
        try:
            with open(caminho_absoluto, 'r', encoding='utf-8') as f:
                texto = f.read()
        except UnicodeDecodeError:
            with open(caminho_absoluto, 'r', encoding='latin-1') as f:
                texto = f.read()
            
        texto_limpo = remove_emojis(texto)
        
        # Ajusta nomenclaturas se necessário
        texto_limpo = texto_limpo.replace('Ronda Virtual', nome_projeto)
        texto_limpo = texto_limpo.replace('Agente JOTA', nome_projeto)
        
        titulo = os.path.basename(arquivo_relativo).replace('.md', '').replace('_', ' ').title()
        
        if not texto_limpo.strip().startswith('# '):
            corpo_texto += f"\n# {titulo}\n\n"
        
        corpo_texto += texto_limpo
        corpo_texto += "\n\n---\n"

conteudo_final += "\n" + corpo_texto

# Salva os arquivos gerados dentro da pasta 'documentação' baseados no nome da pasta raiz
nome_arquivo_safe = nome_pasta.replace(' ', '_').replace('-', '_')
doc_dir = os.path.join(root_dir, "documentação")
os.makedirs(doc_dir, exist_ok=True)

md_output_path = os.path.join(doc_dir, f"Manual_Oficial_{nome_arquivo_safe}.md")
pdf_output_path = os.path.join(doc_dir, f"Manual_Oficial_{nome_arquivo_safe}.pdf")

# Limpeza de arquivos antigos legados obsoletos (Manual_Oficial_Agente_de_Atendimento.*) no root e na pasta documentação
old_files_to_clean = [
    os.path.join(root_dir, "Manual_Oficial_Agente_de_Atendimento.md"),
    os.path.join(root_dir, "Manual_Oficial_Agente_de_Atendimento.pdf"),
    os.path.join(doc_dir, "Manual_Oficial_Agente_de_Atendimento.md"),
    os.path.join(doc_dir, "Manual_Oficial_Agente_de_Atendimento.pdf"),
    # Limpar também as cópias que foram geradas temporariamente na raiz
    os.path.join(root_dir, f"Manual_Oficial_{nome_arquivo_safe}.md"),
    os.path.join(root_dir, f"Manual_Oficial_{nome_arquivo_safe}.pdf")
]

for file_path in old_files_to_clean:
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"Limpo arquivo legado obsoleto: {file_path}")
        except Exception as err:
            print(f"Aviso: Não foi possível remover {os.path.basename(file_path)}: {err}")

with open(md_output_path, "w", encoding="utf-8") as f:
    f.write(conteudo_final)


print(f"Markdown consolidado gerado com sucesso em: {md_output_path}")
print("Iniciando conversão para PDF...")

try:
    from markdown_pdf import MarkdownPdf
    from markdown_pdf import Section

    pdf = MarkdownPdf(toc_level=0)
    pdf.meta["title"] = f"Manual Técnico Oficial - {nome_projeto}"
    pdf.meta["author"] = "Willian Batista Oliveira"

    partes = conteudo_final.split('<div style="page-break-after: always;"></div>')

    for parte in partes:
        if parte.strip():
            parte = parte.replace("<div style='page-break-before: always;'></div>", "")
            section = Section(parte.strip())
            pdf.add_section(section)

    pdf.save(pdf_output_path)
    print(f"PDF Oficial gerado com sucesso em: {pdf_output_path}")
except ImportError:
    print("Aviso: Biblioteca 'markdown-pdf' não encontrada. Apenas o arquivo Markdown foi gerado.")
    print("Para gerar o PDF, instale a biblioteca com: pip install markdown-pdf")
