from pathlib import Path
from pypdf import PdfReader

src = Path(r'C:\Users\ADMIN\Projects\pipe_product_agent\data\raw\Product_Price_List.pdf')
out = Path(r'C:\Users\ADMIN\Projects\pipe_product_agent\data\processed\pdf_pages_dump.txt')
out.parent.mkdir(parents=True, exist_ok=True)
reader = PdfReader(str(src))
with out.open('w', encoding='utf-8', errors='replace') as f:
    f.write(f'pages={len(reader.pages)}\n')
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ''
        f.write(f'--- PAGE {i} ---\n')
        f.write(text)
        f.write('\n\n')
print(f'dumped {len(reader.pages)} pages to {out}')
