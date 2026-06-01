import os
import pypdf

def extract_pdf_info():
    pdf_path = r"C:\Users\jejco\Downloads\RelatórioSituaçãoFiscal-16624954000105-20260601.pdf"
    output_txt = r"c:\Users\jejco\Desktop\Escavador de Pendencias\scratch\pdf_content_temp.txt"
    
    if not os.path.exists(pdf_path):
        print(f"Error: File not found at {pdf_path}")
        return
        
    try:
        reader = pypdf.PdfReader(pdf_path)
        content = []
        for i, page in enumerate(reader.pages):
            content.append(f"=== PAGE {i+1} ===")
            content.append(page.extract_text() or "")
            
        with open(output_txt, "w", encoding="utf-8") as f:
            f.write("\n".join(content))
            
        print("Success! Extracted content written to scratch/pdf_content_temp.txt")
    except Exception as e:
        print(f"Error extracting PDF: {e}")

if __name__ == "__main__":
    extract_pdf_info()
