# LFS
**Local LLM File Sorter Program**


# LFS — Local LLM File Sorter

로컬 LLM을 사용해 파일 내용을 분석하고 자동으로 분류하는 Windows 프로그램입니다.

> ⚠️ Work in Progress  
> 현재 개발 중이며 기능과 UI가 변경될 수 있음

## 주요 기능

- 파일 내부 내용 기반 분류
- Ollama 로컬 LLM 연동
- Qwen 모델 지원
- PDF·DOCX·XLSX·TXT·Markdown 분석
- 스캔 PDF OCR 지원
- 다운로드 폴더 감시
- 분류 결과 검토 및 수정
- 승인된 파일을 카테고리 폴더로 복사
- Windows 95/98 스타일 GUI

## 현재 상태

- [x] 기본 파일 분류
- [x] Ollama 연동
- [x] OCR 연동
- [x] 파일 감시
- [x] 분류 수정 및 승인
- [x] 기본 GUI
- [ ] 대량 파일 성능 최적화
- [ ] 다양한 실제 파일 검증
- [ ] 설치 프로그램 제작
- [ ] `.exe` 패키징
- [ ] 최종 안정화

## 요구 사항

- Windows
- Python 3.11 이상
- Ollama
- Tesseract OCR
- Qwen 계열 로컬 모델

## 실행 방법

```powershell
pip install -r requirements.txt
python gui.py
