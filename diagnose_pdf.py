"""Diagnostic script to test PDF parsing pipeline components."""

import io
import sys
import os

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def diagnose():
    print("=" * 60)
    print("PDF PARSING DIAGNOSTIC")
    print("=" * 60)

    # 1. Check pikepdf
    print("\n[1] Checking pikepdf installation...")
    try:
        import pikepdf
        print(f"    OK - pikepdf version: {pikepdf.__version__}")
    except ImportError:
        print("    FAIL - pikepdf is NOT installed. Run: pip install pikepdf")
        return

    # 2. Check pdfplumber
    print("\n[2] Checking pdfplumber installation...")
    try:
        import pdfplumber
        print(f"    OK - pdfplumber version: {pdfplumber.__version__}")
    except ImportError:
        print("    FAIL - pdfplumber is NOT installed. Run: pip install pdfplumber")
        return

    # 3. Check NVIDIA API config
    print("\n[3] Checking NVIDIA API configuration...")
    from backend.config import settings
    if settings.NVIDIA_API_KEY:
        print(f"    OK - NVIDIA_API_KEY is set (starts with: {settings.NVIDIA_API_KEY[:15]}...)")
    else:
        print("    FAIL - NVIDIA_API_KEY is NOT set!")
    print(f"    NVIDIA_BASE_URL: {settings.NVIDIA_BASE_URL}")
    print(f"    NVIDIA_MODEL: {settings.NVIDIA_MODEL}")

    # 4. Test NVIDIA API connectivity
    print("\n[4] Testing NVIDIA API connectivity...")
    if settings.NVIDIA_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(
                base_url=settings.NVIDIA_BASE_URL,
                api_key=settings.NVIDIA_API_KEY,
            )
            response = client.chat.completions.create(
                model=settings.NVIDIA_MODEL,
                messages=[{"role": "user", "content": "Reply with just 'OK'"}],
                temperature=0.1,
                max_tokens=10,
            )
            reply = response.choices[0].message.content.strip()
            print(f"    OK - NVIDIA API responded: '{reply}'")
        except Exception as e:
            print(f"    FAIL - NVIDIA API call FAILED: {e}")
    else:
        print("    SKIP (no API key)")

    # 5. Test with the protected PDF if it exists
    test_files = [
        ("test_protected.pdf", "Test Protected PDF"),
        ("test_plain.pdf", "Test Plain PDF"),
    ]

    for filename, label in test_files:
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        if not os.path.exists(filepath):
            continue

        print(f"\n[5] Testing '{label}' ({filename})...")
        with open(filepath, "rb") as f:
            pdf_bytes = f.read()
        print(f"    File size: {len(pdf_bytes)} bytes")

        # 5a. Check if encrypted
        from backend.tools.pdf_parser import _is_encrypted
        encrypted = _is_encrypted(pdf_bytes)
        print(f"    Encrypted: {encrypted}")

        if encrypted:
            print("    WARNING - PDF IS encrypted - needs a password to decrypt")
            # Try with empty password
            try:
                from backend.tools.pdf_parser import _decrypt_pdf
                decrypted = _decrypt_pdf(pdf_bytes, "")
                print(f"    OK - Decrypted with empty password ({len(decrypted)} bytes)")
                pdf_bytes = decrypted
            except ValueError as e:
                print(f"    FAIL - Empty password failed: {e}")
                # Try common test passwords
                for test_pwd in ["password", "test", "1234", "123456"]:
                    try:
                        decrypted = _decrypt_pdf(pdf_bytes, test_pwd)
                        print(f"    OK - Decrypted with password '{test_pwd}' ({len(decrypted)} bytes)")
                        pdf_bytes = decrypted
                        break
                    except ValueError:
                        pass
                else:
                    print("    FAIL - Could not decrypt with any common test passwords")
                    continue
        else:
            # Not encrypted - try opening directly
            try:
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    print(f"    OK - Opened directly, {len(pdf.pages)} pages")
            except Exception as e:
                print(f"    FAIL - Cannot open: {e}")

        # 5b. Try text extraction with pdfplumber
        print(f"\n    Extracting text with pdfplumber...")
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                num_pages = len(pdf.pages)
                print(f"    Pages: {num_pages}")
                for i, page in enumerate(pdf.pages):
                    text = page.extract_text() or ""
                    tables = page.extract_tables()
                    print(f"    Page {i+1}: {len(text)} chars text, {len(tables)} tables")
                    if text.strip():
                        # Show first 300 chars
                        preview = text.strip()[:300].replace('\n', ' | ')
                        print(f"    Preview: {preview}")
                    else:
                        print("    WARNING - NO TEXT extracted from this page!")
        except Exception as e:
            print(f"    FAIL - pdfplumber failed: {e}")

    # 6. Check if there's a user-uploaded PDF in temp_uploads
    temp_dir = settings.TEMP_UPLOAD_DIR
    if os.path.exists(temp_dir):
        files = os.listdir(temp_dir)
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
        if pdf_files:
            print(f"\n[6] Found {len(pdf_files)} PDF(s) in temp_uploads/")
            for f in pdf_files:
                fpath = os.path.join(temp_dir, f)
                print(f"    - {f} ({os.path.getsize(fpath)} bytes)")
        else:
            print(f"\n[6] No PDF files in {temp_dir}/")
    
    print("\n" + "=" * 60)
    print("DIAGNOSIS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    diagnose()
