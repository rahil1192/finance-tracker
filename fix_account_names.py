import io
import re
import pdfplumber
from models import get_db, get_pdf_files, get_pdf_content, PDFFile
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image
from PIL import ImageEnhance
from PIL import ImageFilter

def ocr_extract_name_from_top(pdf_content: bytes) -> str:
    try:
        # Convert first page to image
        images = convert_from_bytes(pdf_content, dpi=300, first_page=1, last_page=1)
        if not images:
            return "Unknown"
        image = images[0]
        width, height = image.size
        
        # Crop a smaller region where name typically appears (top 20% instead of 30%)
        crop_box = (0, 0, width, int(height * 0.2))
        top_region = image.crop(crop_box)
        
        # Enhanced preprocessing pipeline
        # 1. Convert to grayscale
        top_region = top_region.convert("L")
        
        # 2. Increase contrast
        enhancer = ImageEnhance.Contrast(top_region)
        top_region = enhancer.enhance(2.0)
        
        # 3. Apply thresholding to create binary image
        top_region = top_region.point(lambda x: 0 if x < 128 else 255, '1')
        
        # 4. Apply slight sharpening
        top_region = top_region.filter(ImageFilter.SHARPEN)
        
        # Run OCR with custom configuration
        custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz "'
        text = pytesseract.image_to_string(top_region, config=custom_config)
        
        print(f"DEBUG: OCR text from top region:\n{text}")
        
        # Enhanced name validation
        for line in text.splitlines():
            line = line.strip()
            # Skip empty lines or lines that are too short
            if not line or len(line) < 5:
                continue
                
            # Check if line matches expected name pattern
            words = line.split()
            if len(words) >= 2:  # At least two words
                # Count alphabetic characters
                alpha_count = sum(c.isalpha() for c in line)
                total_chars = len(line.replace(' ', ''))
                alpha_ratio = alpha_count / total_chars if total_chars > 0 else 0
                
                # Check if line is mostly alphabetic and has reasonable length
                if alpha_ratio > 0.8 and 5 <= len(line) <= 50:
                    # Additional validation: check for common name patterns
                    if any(word[0].isupper() for word in words):  # At least one word starts with capital
                        print(f"DEBUG: Validated name: {line}")
                        return line.title()
                        
    except Exception as e:
        print(f"OCR name extraction failed: {e}")
    return "Unknown"

def parse_account_holder_from_pdf(pdf_content: bytes, pdf_filename: str = "") -> str:
    known_names = [
        "Apeksha Rajesh Bafna",
        "Rahil Dinesh Shah",
        # Add more known names here if needed
    ]
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            first_page = pdf.pages[0]
            text = first_page.extract_text()
            if not text:
                return "Unknown"
            lines = [line.strip() for line in text.splitlines()]
            print("DEBUG: All lines from first page:")
            for idx, line in enumerate(lines):
                print(f"{idx}: '{line}'")
            # 1. Try to match known names anywhere in the text (case-insensitive)
            for name in known_names:
                if name.lower() in text.lower():
                    return name.title()
            # 2. CIBC: Name before ' For '
            for line in lines:
                match = re.match(r'^([A-Z ]{5,}) For ', line)
                if match:
                    print(f"DEBUG: Extracted name from CIBC-style line: '{line}'")
                    return match.group(1).title().strip()
            # 3. All-uppercase name line followed by masked account number
            for i, line in enumerate(lines):
                if (
                    line.isupper() and len(line.split()) >= 2 and
                    i + 1 < len(lines) and re.search(r'[xX*]{2,}', lines[i + 1])
                ):
                    print(f"DEBUG: Name line: '{line}' with masked line: '{lines[i+1]}'")
                    return line.title().strip()
            # 4. Fallback: first all-uppercase line with at least two words
            for line in lines:
                if line.isupper() and len(line.split()) >= 2:
                    return line.title().strip()
            # 5. Fallback: first non-empty line with at least two words
            for line in lines:
                if any(c.isalpha() for c in line) and len(line.split()) >= 2:
                    return line.strip()
            # 6. If this is a TD PDF (by filename), try OCR
            if "td" in pdf_filename.lower():
                ocr_name = ocr_extract_name_from_top(pdf_content)
                if ocr_name and ocr_name != "Unknown":
                    print(f"DEBUG: OCR extracted name: {ocr_name}")
                    return ocr_name
    except Exception as e:
        print(f"Error extracting account holder: {e}")
    return "Unknown"

def main():
    db = next(get_db())
    pdf_files = get_pdf_files(db)
    updated = 0
    for pdf in pdf_files:
        pdf_content = get_pdf_content(db, pdf.id)
        if not pdf_content:
            continue
        new_account = parse_account_holder_from_pdf(pdf_content, pdf.original_filename)
        if new_account and new_account != pdf.account:
            print(f"Updating PDF id={pdf.id} ({pdf.original_filename}): '{pdf.account}' -> '{new_account}'")
            pdf.account = new_account
            db.add(pdf)
            updated += 1
    db.commit()
    print(f"Updated {updated} PDFFile records with new account holder names.")

if __name__ == "__main__":
    main() 