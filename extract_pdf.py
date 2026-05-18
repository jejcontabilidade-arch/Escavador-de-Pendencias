import os
import sys

def main():
    pdf_path = r"C:\Users\jejco\Desktop\Escavador de Pendencias\Relação de Férias Geral.pdf"
    output_path = r"C:\Users\jejco\Desktop\Escavador de Pendencias\pdf_content.txt"
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at {pdf_path}")
        sys.exit(1)
        
    try:
        import pypdf
    except ImportError:
        print("pypdf is not installed. Installing it now...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pypdf"])
        import pypdf
        
    print(f"Reading PDF from: {pdf_path}")
    reader = pypdf.PdfReader(pdf_path)
    text_content = []
    
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        text_content.append(f"--- PAGE {i + 1} ---")
        text_content.append(text)
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text_content))
        
    print(f"Successfully extracted text to: {output_path}")

if __name__ == "__main__":
    main()
