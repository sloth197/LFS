import argparse
import hashlib
import json
import shutil
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DB_PATH = ROOT / "data" / "aisorter.db"
CACHE_DIR = ROOT / "data" / "text_cache"

def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT NOT NULL,
            file_hash TEXT NOT NULL, category TEXT, confidence REAL, reason TEXT,
            status TEXT NOT NULL, model TEXT, error TEXT, processed_at TEXT NOT NULL,
            destination_path TEXT, action TEXT)""")
        columns = {row[1] for row in db.execute("PRAGMA table_info(classifications)")}
        for name in ("destination_path", "action"):
            if name not in columns:
                db.execute(f"ALTER TABLE classifications ADD COLUMN {name} TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS idx_classifications_hash_status ON classifications(file_hash, status)")

def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def extract_text(path):
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".markdown"}:
        return path.read_text(encoding="utf-8-sig")
    if suffix == ".pdf":
        import pymupdf
        with pymupdf.open(path) as document:
            text = "\n".join(page.get_text() for page in document)
            return text if text.strip() else ocr_pdf(path)
    if suffix == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(path).paragraphs)
    if suffix == ".xlsx":
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            return "\n".join(" | ".join(str(cell.value or "") for cell in row)
                              for sheet in book.worksheets for row in sheet.iter_rows())
        finally:
            book.close()
    raise ValueError(f"지원하지 않는 확장자: {suffix}")

def cached_text(path, digest):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE_DIR / f"{digest}.txt"
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8")
    content = extract_text(path)
    cache_path.write_text(content, encoding="utf-8")
    return content

def ocr_pdf(path):
    import pymupdf
    import pytesseract
    from PIL import Image
    from io import BytesIO
    tesseract = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if tesseract.exists():
        pytesseract.pytesseract.tesseract_cmd = str(tesseract)
    with pymupdf.open(path) as document:
        pages = list(document)[:5]
        return "\n".join(pytesseract.image_to_string(
            Image.open(BytesIO(page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5)).tobytes("png"))),
            lang="kor+eng") for page in pages)

def call_ollama(config, filename, content, model=None):
    categories = ", ".join(config["categories"])
    prompt = f"""다음 문서를 한 개의 카테고리로 분류하세요.
허용 카테고리: {categories}
파일명: {filename}
문서 내용:\n{content[:6000]}
JSON만 반환하세요: {{"category":"허용 카테고리 중 하나", "confidence":0.0, "reason":"한국어 근거"}}"""
    payload = json.dumps({"model": model or config["ollama_model"], "prompt": prompt,
                          "stream": False, "format": "json", "keep_alive": "10m",
                          "options": {"temperature": 0.1, "num_predict": 160, "num_ctx": 4096}}).encode("utf-8")
    request = urllib.request.Request(config["ollama_endpoint"].rstrip("/") + "/api/generate",
                                     data=payload, headers={"Content-Type": "application/json"})
    # 로컬 LLM 분석은 문서 크기와 OCR 결과에 따라 오래 걸릴 수 있으므로
    # 외부 API처럼 짧은 고정 시간 제한을 두지 않는다.
    with urllib.request.urlopen(request, timeout=None) as response:
        result = json.loads(json.loads(response.read().decode("utf-8"))["response"])
    category, confidence = result.get("category"), float(result.get("confidence", 0))
    reason = str(result.get("reason", "")).strip()
    if category not in config["categories"] or not 0 <= confidence <= 1 or not reason:
        raise ValueError("LLM 응답의 카테고리·신뢰도·근거가 유효하지 않습니다.")
    return category, confidence, reason

def classify_with_fallback(config, filename, content):
    primary = config["ollama_model"]
    result = call_ollama(config, filename, content, primary)
    threshold = float(config.get("fallback_threshold", 0.85))
    fallback = config.get("fallback_model")
    if fallback and result[1] < threshold and fallback != primary:
        fallback_config = dict(config, ollama_model=fallback)
        return call_ollama(fallback_config, filename, content, fallback), fallback_config
    return result, config

def unique_path(path):
    if not path.exists(): return path
    for number in range(1, 10000):
        candidate = path.with_name(f"{path.stem} ({number}){path.suffix}")
        if not candidate.exists(): return candidate
    raise RuntimeError("중복 파일명 처리 한도를 초과했습니다.")

def save_result(path, digest, result, config, error=None):
    category, confidence, reason = result if result else (None, None, None)
    with connect() as db:
        db.execute("""INSERT INTO classifications
            (source_path,file_hash,category,confidence,reason,status,model,error,processed_at,action)
            VALUES (?,?,?,?,?,?,?,?,?,?)""", (str(path), digest, category, confidence, reason,
            "CLASSIFIED" if result else "FAILED", config["ollama_model"], error,
            datetime.now(timezone.utc).isoformat(), None))

def scan(input_dir, config):
    paths = sorted(p for p in input_dir.rglob("*") if p.is_file() and
                   p.suffix.lower() in config["input_extensions"])
    if not paths:
        print(f"처리할 지원 파일이 없습니다. 지원 확장자: {', '.join(config['input_extensions'])}")
        return
    seen_hashes = set()
    for path in paths:
        digest = ""
        try:
            digest = file_hash(path)
            if digest in seen_hashes:
                print(f"건너뜀(이번 스캔 중복): {path}")
                continue
            seen_hashes.add(digest)
            with connect() as db:
                if db.execute("SELECT 1 FROM classifications WHERE file_hash=? AND status IN ('CLASSIFIED','CONFIRMED')", (digest,)).fetchone():
                    print(f"건너뜀(중복): {path}"); continue
            print(f"분석 중: {path}")
            content = cached_text(path, digest)
            if not content.strip(): raise ValueError("빈 문서입니다.")
            result, result_config = classify_with_fallback(config, path.name, content)
            save_result(path, digest, result, result_config)
            print(f"  → {result[0]} ({result[1]:.2f})")
        except (OSError, ValueError, KeyError, ImportError, json.JSONDecodeError,
                urllib.error.URLError, TimeoutError) as exc:
            save_result(path, digest, None, config, str(exc)); print(f"  실패: {exc}")

def list_results():
    with connect() as db:
        for row in db.execute("SELECT id,status,category,confidence,source_path,destination_path FROM classifications ORDER BY id"):
            print(f"{row['id']} | {row['status']} | {row['category'] or '-'} | {row['confidence'] or '-'} | {row['source_path']} | {row['destination_path'] or '-'}")

def approve(record_ids, target_root):
    for record_id in record_ids:
        with connect() as db:
            row = db.execute("SELECT * FROM classifications WHERE id=?", (record_id,)).fetchone()
            if not row or row["status"] != "CLASSIFIED":
                print(f"승인 건너뜀({record_id}): 승인 가능한 결과가 없습니다."); continue
            source = Path(row["source_path"])
            if not source.exists():
                print(f"승인 실패({record_id}): 원본이 없습니다."); continue
            destination = unique_path(Path(target_root) / row["category"] / source.name)
            destination.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, destination)
            db.execute("UPDATE classifications SET status='CONFIRMED',destination_path=?,action='COPIED' WHERE id=?", (str(destination), record_id))
            print(f"복사 완료({record_id}): {destination}")

def revise(record_id, category, config):
    if category not in config["categories"]:
        raise ValueError(f"허용되지 않은 카테고리: {category}")
    with connect() as db:
        row = db.execute("SELECT status FROM classifications WHERE id=?", (record_id,)).fetchone()
        if not row or row["status"] not in {"CLASSIFIED", "REVIEW_REQUIRED"}:
            raise ValueError("수정 가능한 분류 결과가 없습니다.")
        db.execute("UPDATE classifications SET category=?,status='CLASSIFIED',action='REVISED' WHERE id=?", (category, record_id))
    print(f"분류 수정 완료({record_id}): {category}")

def undo(record_id):
    with connect() as db:
        row = db.execute("SELECT destination_path,action,file_hash FROM classifications WHERE id=?", (record_id,)).fetchone()
        if not row or row["action"] != "COPIED" or not row["destination_path"]: raise ValueError("되돌릴 복사 기록이 없습니다.")
        destination = Path(row["destination_path"])
        if destination.exists():
            if file_hash(destination) != row["file_hash"]:
                raise ValueError("복사본이 변경되어 자동 삭제하지 않았습니다.")
            destination.unlink()
        db.execute("UPDATE classifications SET status='CLASSIFIED',action='UNDONE' WHERE id=?", (record_id,)); print(f"복사 취소 완료: {destination}")

def delete_records(record_ids=None):
    with connect() as db:
        if record_ids:
            placeholders = ",".join("?" for _ in record_ids)
            cursor = db.execute(f"DELETE FROM classifications WHERE id IN ({placeholders})", tuple(record_ids))
        else:
            cursor = db.execute("DELETE FROM classifications")
            db.execute("DELETE FROM sqlite_sequence WHERE name='classifications'")
    print(f"분류 기록 삭제 완료: {cursor.rowcount}건 (원본 파일 유지)")

def evaluate(labels_path):
    labels = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    total = correct = 0
    with connect() as db:
        for source, expected in labels.items():
            row = db.execute("SELECT category FROM classifications WHERE source_path=? OR source_path=? ORDER BY id DESC LIMIT 1",
                             (source, str(Path(source)))).fetchone()
            if row:
                total += 1
                correct += row["category"] == expected
    accuracy = correct / total if total else 0
    print(f"정답 비교: {correct}/{total}")
    print(f"정확도: {accuracy:.2%}")

def watch(input_dir, config, interval):
    print(f"감시 시작: {input_dir} (종료: Ctrl+C)"); seen = {}; processed = set()
    try:
        while True:
            current = {str(p): p.stat().st_size for p in input_dir.rglob("*") if p.is_file()}
            stable = {name for name, size in current.items() if name in seen and seen[name] == size}
            pending = stable - processed
            for parent in {Path(name).parent for name in pending}:
                scan(parent, config)
            processed.update(pending)
            seen = current; time.sleep(interval)
    except KeyboardInterrupt: print("감시 종료")

def main():
    parser = argparse.ArgumentParser(description="내용 기반 문서 분류기")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("scan"); p.add_argument("--input", required=True, type=Path)
    sub.add_parser("list")
    p = sub.add_parser("approve"); p.add_argument("ids", type=int, nargs="+"); p.add_argument("--target", required=True, type=Path)
    p = sub.add_parser("revise"); p.add_argument("id", type=int); p.add_argument("--category", required=True)
    p = sub.add_parser("undo"); p.add_argument("id", type=int)
    p = sub.add_parser("delete"); p.add_argument("ids", type=int, nargs="*")
    p = sub.add_parser("evaluate"); p.add_argument("--labels", required=True, type=Path)
    p = sub.add_parser("watch"); p.add_argument("--input", required=True, type=Path); p.add_argument("--interval", type=int, default=5)
    args = parser.parse_args(); config = load_config(); init_db()
    if args.command == "scan":
        if not args.input.is_dir(): parser.error(f"입력 폴더가 없습니다: {args.input}")
        scan(args.input, config)
    elif args.command == "list": list_results()
    elif args.command == "approve": approve(args.ids, args.target)
    elif args.command == "revise": revise(args.id, args.category, config)
    elif args.command == "undo": undo(args.id)
    elif args.command == "delete": delete_records(args.ids)
    elif args.command == "evaluate": evaluate(args.labels)
    elif args.command == "watch": watch(args.input, config, args.interval)

if __name__ == "__main__": main()
