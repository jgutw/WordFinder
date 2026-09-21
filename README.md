# WordFinder Web Application

A web-based tool for discovering inner words across 50+ languages. Enter an English word, and the application automatically finds valid subwords within translations in multiple languages.

## Features

- 🌍 **50+ Languages**: Supports Chinese, Japanese, Korean, Arabic, Hindi, European languages, and more
- 🔍 **Auto-Search**: Automatically searches as you type (with debouncing)
- ✨ **Smart Filtering**: Only shows languages that have actual results
- 📚 **Search History**: Automatically logs all searches for easy access
- 🎨 **Modern UI**: Beautiful, responsive web interface
- 🔤 **Romanization**: Optional romanization for Japanese, Korean, and Chinese
- 📊 **Word Frequency**: Uses Zipf frequency scores to validate words

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. (Optional) Install spaCy models for lemmatization:
```bash
python -m spacy download en_core_web_sm
python -m spacy download es_core_news_sm
python -m spacy download fr_core_news_sm
# ... etc for other languages
```

3. Run the application:
```bash
python app.py
```

4. Open your browser to `http://localhost:5001`

**Note**: If port 5001 is also in use, you can change it in `app.py` (line 182). Port 5000 is often used by macOS AirPlay Receiver.

## Usage

1. Enter an English word or phrase in the search box
2. Results automatically appear as you type (after 800ms pause)
3. Click on any search in the history to reload it
4. Toggle options:
   - **Show Romanization**: Display romanized text for JA/KO/ZH
   - **Enable Morphemes**: Include single-character morphemes for CJK scripts
   - **Enable Lemmatization**: Use spaCy lemmatization for supported languages

## How It Works

1. Takes your English input
2. Translates it to 50+ languages
3. For each translation, finds valid subwords (inner words)
4. Validates words using Zipf frequency scores
5. Filters out languages with no results
6. Displays results with translations and glosses
7. Automatically saves to search history

## API Endpoints

- `POST /api/search` - Search for words
- `GET /api/history` - Get search history
- `GET /api/history/<id>` - Get specific search
- `DELETE /api/history/<id>` - Delete search from history

## Database

The application uses SQLite to store search history. The database file `wordfinder.db` is created automatically on first run.

## Technical Details

- **Backend**: Flask with SQLAlchemy
- **Frontend**: Vanilla JavaScript with modern CSS
- **Translation**: Google Translate API (via deep-translator)
- **Word Frequency**: wordfreq library
- **Tokenization**: Language-specific tokenizers (jieba, tinysegmenter, pythainlp, etc.)

## Oxford 3000 dictionary (Version B)

The repo includes a full multi-language Excel dictionary built from the American Oxford 3000 word list:

- **`data/oxford_3000_version_b.xlsx`** — one row per English headword, one column per language; cells keep translations that contain inner words (with English glosses)
- **`data/oxford_3000_sample_version_a.xlsx`** / **`data/oxford_3000_sample_version_b.xlsx`** — small sample layouts used while designing the export
- Scripts: `oxford_3000_full_version_b.py`, `oxford_3000_sample.py`, source list `oxford_3000_raw.txt`

## Notes

- The application filters out languages that don't yield any inner words
- Search history is stored locally in SQLite
- Auto-search triggers after 800ms of no typing
- Results are sorted alphabetically by language name

