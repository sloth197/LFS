import tempfile
import unittest
from pathlib import Path

import openpyxl
import pymupdf
from PIL import Image, ImageDraw

from main import extract_text, ocr_pdf, unique_path


class SmokeTests(unittest.TestCase):
    def test_xlsx_extraction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.xlsx"
            book = openpyxl.Workbook()
            book.active["A1"] = "receipt payment 35000"
            book.save(path)
            self.assertIn("35000", extract_text(path))

    def test_ocr_image_pdf(self):
        with tempfile.TemporaryDirectory() as folder:
            image_path = Path(folder) / "page.png"
            pdf_path = Path(folder) / "scan.pdf"
            image = Image.new("RGB", (1000, 300), "white")
            ImageDraw.Draw(image).text((40, 100), "RECEIPT PAYMENT 35000", fill="black")
            image.save(image_path)
            document = pymupdf.open()
            page = document.new_page(width=1000, height=300)
            page.insert_image(page.rect, filename=str(image_path))
            document.save(pdf_path)
            self.assertIn("RECEIPT", ocr_pdf(pdf_path).upper())

    def test_duplicate_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.txt"
            path.write_text("one", encoding="utf-8")
            self.assertEqual(unique_path(path).name, "report (1).txt")


if __name__ == "__main__":
    unittest.main()
