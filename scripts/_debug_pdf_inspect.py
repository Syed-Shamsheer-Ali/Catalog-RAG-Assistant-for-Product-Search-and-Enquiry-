from pathlib import Path
from pypdf import PdfReader

path = Path(r"C:\Users\ADMIN\Projects\pipe_product_agent\data\raw\Product_Price_List.pdf")
reader = PdfReader(str(path))
print(f"pages={len(reader.pages)}")
for i, p in enumerate(reader.pages[:6], 1):
    text = (p.extract_text() or "")[:3000]
    print(f"--- PAGE {i} ---")
    print(text)
    print()
