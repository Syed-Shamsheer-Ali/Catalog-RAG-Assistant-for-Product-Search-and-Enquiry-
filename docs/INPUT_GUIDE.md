# Input guide

Add products using one or more input methods, then review the editable item rows before creating an estimate. Inputs are processed locally. Catalog rates are looked up from the configured processed catalog; do not enter a price as a product requirement.

## Text

Use one product per line or separate products with semicolons. Include the item description, size, specifications, quantity, and unit where available. A part number removes most catalog ambiguity.

```text
10 Elbow 45 degree, 1/2 inch, CPVC
2 CPVC pipe, 1/2 inch, SDR 11, 3 m length
1 Reducer Tee, 1/2 x 1/2 x 3/4 inch
1.5 size of 10 Ball Valve - Handle
```

Size and quantity can appear before or after the product name. For example, `1.5 size of 10 Ball Valve - Handle` is read as size 1.5, quantity 10, and product **Ball Valve - Handle**.

This can also be written as separate clauses, for example:

```text
Need 10 Elbow 45 degree, 1/2 inch; 2 CPVC pipe, 1/2 inch, SDR 11, 3 m length
```

For pipe variants, say **3 m length** or **5 m length** when known. Those are separate sellable SKUs with separate part numbers and prices in this catalog. If a pipe request only includes its diameter, the app will show the class/length candidates for review.

## Bill images and PDFs

Upload PNG, JPG, JPEG, BMP, WEBP images, or text-based PDFs. Positioned OCR reads bill table columns as separate fields, including item name, quantity, and source-document rate. Image preprocessing enlarges and improves contrast before local OCR. Each extracted row keeps its original OCR text and confidence so uncertain fields can be reviewed. Scanned/image-only PDFs may require a readable source image if the PDF has no embedded text. OCR is local; install/cache the EasyOCR models before offline use.

Rows are added to the editable item table even if the product does not exist in the catalog. The document's rate is shown as a reference only; estimate prices still come from the local product price list.

## Voice

Record the request and select Auto detect, English, Hindi, or Telugu. Speak one item at a time, with a short pause or a phrase such as “then” between items. State the quantity before the product and read out dimensions, grade/class, and length clearly. For example:

```text
Ten Elbow 45 degree, half inch. Then two CPVC pipe, half inch, SDR eleven, three meter length.
```

Voice transcription requires a local Whisper model configured before offline use. Review the transcript-derived rows before submitting.

## CSV and Excel

Each spreadsheet data row becomes one product row. Put column headers in the first row. The importer recognizes these header aliases (case insensitive):

| Field | Accepted headers |
|---|---|
| Item name | `Product`, `Product Name`, `Item`, `Item Name`, `Description` |
| Product kind | `Product Kind`, `Kind`, `Type` |
| Category | `Category`, `Product Category` |
| Size | `Size`, `Size Inch`, `Diameter` |
| Specifications | `Specifications`, `Specification`, `Specs` |
| Material | `Material` |
| Class/system | `System`, `Class`, `Schedule` |
| Quantity | `Quantity`, `Qty`, `Required Quantity` |
| Unit | `Unit`, `UOM`, `Unit of Measure` |
| Part number | `Part Number`, `Part No`, `SKU`, `Product Code` |
| Notes | `Notes`, `Requirement` |

Example CSV:

```csv
Item Name,Size,Specifications,Quantity,Unit,Part Number
Elbow 45 degree,1/2,CPVC,10,piece,70000560
CPVC pipe,1/2,SDR 11; 3 m length,2,length,70000247
Reducer Tee,1/2 x 1/2 x 3/4,CPVC,1,piece,70000462
```

Supported spreadsheet formats are CSV, XLSX, and XLSM. Leave unknown fields blank. Do not add a price column; pricing is resolved from the local catalog. Enter one sellable SKU per row. Do not combine different pipe lengths or part numbers in one row.

## Units and catalog matching

Catalog units are per piece or per pipe length. The supported requirement units include piece/each/nos, meter (`m`), and length/stick. A 3 m or 5 m pipe price is the price for one catalog length, not a per-meter quote. If the requested unit conflicts with the SKU's price basis, the line remains flagged.

Matching tries an exact part number first, then size, item-name, section heading, HSN code, variant, and specification attributes. In chat, numeric part numbers found in the catalog are looked up directly before LLM extraction, so asking “What is part number 70000462?” retrieves the exact catalog SKU and its details. Catalog headings and HSN codes are stored on each SKU and included in the semantic index. A strong, clearly separated attribute match can resolve automatically. The editable item name is never replaced by a merely similar catalog result. Each row shows **Matched**, **Needs Review**, or **Not Found**; candidate details are suggestions only. Correct the editable name, size, specifications, or part number when needed. An unavailable match never receives an invented price.

## Box and quantity entry

The product grid shows **Quantity per Box** from the local catalog when available. Enter **Number of Boxes** to calculate total pieces from that package capacity. Leave boxes blank to enter a loose piece quantity, meters, or count of fixed pipe lengths in **Total Quantity**. The application does not assume that every product is sold in boxes. Unit prices state their basis, such as `/ piece`, `/ box`, `/ m`, or `/ 3 m length`; totals use that basis. Pipe SKUs sold by a fixed length are priced per catalog length and should use a length count, not boxes.

## Before creating an estimate

1. Confirm each item name, size/specification, quantity, and unit.
2. Review catalog match status and candidate details; correct item fields when needed.
3. Check the local rate and line total against the intended SKU.
4. Confirm intentional duplicate rows or delete accidental duplicates.
5. Review the estimate total and select the confirmation checkbox.

The app blocks final submission when a product has no valid quantity, an unsupported or mismatched unit, an unresolved ambiguous match, or no local catalog price.
