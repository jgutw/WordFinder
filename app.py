#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Flask web application for WordFinder
"""

from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import json
from wordfinder import (
    normalize_text, select_langs, Translator, postprocess_translation_for_lang,
    analyze_translation, romanize_text, parse_overrides, PER_LANG_ZIPF,
    DEFAULT_ZIPF, DEFAULT_MIN_LEN_LATINLIKE
)
from dataclasses import dataclass

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///wordfinder.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Add CORS headers to allow requests
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


# Database models
class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    results = db.Column(db.Text)  # JSON string of results
    
    def to_dict(self):
        return {
            'id': self.id,
            'word': self.word,
            'timestamp': self.timestamp.isoformat(),
            'results': json.loads(self.results) if self.results else {}
        }


@dataclass
class AnalysisArgs:
    """Mock args object for analyze_translation"""
    zh_tokenizer: str = "jieba"
    jp_tokenizer: str = "tiny"
    th_tokenizer: str = "pythainlp"


def has_results(result: dict) -> bool:
    """Check if a result has any inner words"""
    main = result.get('inner_words_main', [])
    rare = result.get('inner_words_rare', [])
    return len(main) > 0 or len(rare) > 0


@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'Server is running'})

@app.route('/api/languages', methods=['GET'])
def get_languages():
    """Get list of available languages"""
    from wordfinder import LANGS
    languages = [{'name': lang.name, 'code': lang.trans_code} for lang in LANGS]
    return jsonify({'languages': languages})


@app.route('/api/search', methods=['POST'])
def search():
    """API endpoint to search for words"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400
        
        word = data.get('word', '').strip()
        
        if not word:
            return jsonify({'error': 'Word is required'}), 400
        
        # Get optional parameters
        zipf_threshold = float(data.get('zipf', DEFAULT_ZIPF))
        min_len = int(data.get('minlen', DEFAULT_MIN_LEN_LATINLIKE))
        top_n = int(data.get('top', 12))
        enable_morphemes = data.get('morphemes', True)
        enable_romanize = data.get('romanize', False)
        enable_lemmatize = data.get('lemmatize', False)
        zipf_override_str = data.get('zipf_override', '')
        
        # Parse zipf overrides
        per_lang_zipf = dict(PER_LANG_ZIPF)
        if zipf_override_str:
            try:
                per_lang_zipf.update(parse_overrides(zipf_override_str))
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
        
        # Normalize input
        english = normalize_text(word)
        
        # Get selected languages or use default
        selected_codes = data.get('languages', [])
        if selected_codes and len(selected_codes) > 0:
            # User selected specific languages
            if len(selected_codes) > 20:
                return jsonify({'error': 'Maximum 20 languages allowed'}), 400
            langs = select_langs(','.join(selected_codes))
        else:
            # Default: first 10 languages
            all_langs = select_langs('')
            max_langs = int(data.get('max_langs', 10))
            langs = all_langs[:max_langs]
        
        # Initialize translator and args
        translator = Translator(default_source="en")
        args = AnalysisArgs()
        
        # Process all languages
        all_results = {}
        processed_count = 0
        for lang in langs:
            try:
                # Translate with timeout protection
                translated_raw = translator.to_target(english, target=lang.trans_code)
                translated = postprocess_translation_for_lang(
                    translated_raw, lang, do_lemma=enable_lemmatize
                )
                
                # Analyze
                result = analyze_translation(
                    translated, lang, zipf_threshold, per_lang_zipf, min_len,
                    top_n, translator, enable_morphemes, args=args
                )
                
                # Add romanization if requested
                if enable_romanize:
                    rom = romanize_text(translated, lang)
                    if rom:
                        result['romanization'] = rom
                
                # Only include if it has results
                if has_results(result):
                    all_results[lang.name] = {
                        'code': lang.trans_code,
                        'translation': result['translation'],
                        'romanization': result.get('romanization', ''),
                        'segments': result['segments'],
                        'inner_words_main': result['inner_words_main'],
                        'inner_words_rare': result['inner_words_rare'],
                        'notes': result['notes']
                    }
            except Exception as e:
                # Log error but continue with other languages
                import traceback
                print(f"Error processing {lang.name}: {e}")
                traceback.print_exc()
                continue
            finally:
                processed_count += 1
                if processed_count % 5 == 0:
                    print(f"Processed {processed_count}/{len(langs)} languages...")
        
        # Save to search history
        try:
            history_entry = SearchHistory(
                word=english,
                results=json.dumps(all_results, ensure_ascii=False)
            )
            db.session.add(history_entry)
            db.session.commit()
        except Exception as e:
            print(f"Error saving to history: {e}")
        
        return jsonify({
            'input': english,
            'results': all_results,
            'total_languages': len(all_results),
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        traceback.print_exc()
        return jsonify({'error': f'Server error: {error_msg}'}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """Get search history"""
    limit = request.args.get('limit', 50, type=int)
    searches = SearchHistory.query.order_by(SearchHistory.timestamp.desc()).limit(limit).all()
    return jsonify([s.to_dict() for s in searches])


@app.route('/api/history/<int:search_id>', methods=['GET'])
def get_history_item(search_id):
    """Get a specific search from history"""
    search = SearchHistory.query.get_or_404(search_id)
    return jsonify(search.to_dict())


@app.route('/api/history/<int:search_id>', methods=['DELETE'])
def delete_history_item(search_id):
    """Delete a search from history"""
    search = SearchHistory.query.get_or_404(search_id)
    db.session.delete(search)
    db.session.commit()
    return jsonify({'message': 'Deleted successfully'})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5001, use_reloader=False)

