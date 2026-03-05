---
title: POLI 319 Research Assistant
emoji: 📚
colorFrom: red
colorTo: blue
sdk: streamlit
sdk_version: 1.50.0
app_file: app.py
pinned: false
---

# POLI 319 — Latin American Politics and Society
## Textbook Addendum Research Assistant

This tool helps POLI 319 students (McGill, Winter 2026) complete the Textbook Addendum assignment (25% of grade, due April 20, 2026).

**Enter your name, student ID, and group name to begin.**

---

## Setup (instructor)

### 1. Install dependencies
```bash
cd ~/projects/poli319-assistant
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create .env file
```bash
cp .env.example .env
# Edit .env with your API key and instructor password
```

### 3. Add source documents
Copy to `data/sources/`:
- `assignment.pdf` — research assignment.pdf from the LATAM Course folder

The `trusted_sources.md` file is already in `data/sources/`.

**Note on the textbook PDF**: The copy at `~/Desktop/LATAM Course 2026/` is a scanned image PDF with no extractable text. If you obtain a text-based PDF version, place it at `data/sources/textbook.pdf` and re-run `scripts/ingest.py` to add it to the index. In the meantime, the chatbot draws on Claude's training knowledge for textbook content and works fully for assignment guidance and data source recommendations.

### 4. Run ingestion (one time)
```bash
python scripts/ingest.py
```
Then commit the index:
```bash
git add data/chromadb/
git commit -m "Add pre-built vector index"
```

### 5. Test locally
```bash
streamlit run app.py
```

### 6. Deploy to Hugging Face Spaces
1. Create a new Space at huggingface.co (SDK: Streamlit, Hardware: CPU Basic)
2. Set secrets: `ANTHROPIC_API_KEY` and `INSTRUCTOR_PASSWORD`
3. Attach persistent storage (free 50 GB, mounts at `/data/`)
4. Push this repo to the Space's git remote

The instructor dashboard is at `/2_Instructor` — access with your `INSTRUCTOR_PASSWORD`.
