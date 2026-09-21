#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
WordFinder v2.7 (Smarter linguistics edition)
- Inner-word finder across many languages with translations + glosses.
- Morpheme mode:
  * Han (Kanji/Hanzi): any single CJK ideograph can count as a morpheme.
  * Kana (Japanese): whitelist of one-char particles (の, は, を, …).
  * Hangul (Korean): whitelist of one-syllable particles (은/는/이/가/…) + optional content syllables.
  * Other scripts: single chars must meet wordfreq thresholds.
- Morphemes get synthetic Zipf (3.0) so they surface in Main (labeled "morpheme").
- Optional Russian quality guard with pymorphy3.

Smarter linguistics upgrades (all optional via flags):
- Tokenizer routing: JP (tinysegmenter|sudachi), ZH (jieba|pkuseg), TH (pythainlp).
- Romanization display for JA/KO/ZH.
- Lemmatization with spaCy for selected EU languages.
"""

import sys
import time
import json
import unicodedata
import argparse
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

import regex as re
from deep_translator import GoogleTranslator
import pyphen
import jieba
try:
    from tinysegmenter import tinysegmenter
except ImportError:
    tinysegmenter = None
try:
    if tinysegmenter is None:
        from tinysegmenter import TinySegmenter
        tinysegmenter = TinySegmenter()
except (ImportError, AttributeError):
    tinysegmenter = None

from wordfreq import zipf_frequency

# ---------- Optional Russian morphology ----------
try:
    import pymorphy3
    RUS_MORPH = pymorphy3.MorphAnalyzer()
except Exception:
    RUS_MORPH = None

# ---------- Optional tokenizer / romanization plugins ----------
# JP: Sudachi
try:
    from sudachipy import tokenizer as sudachi_tokenizer
    from sudachipy import dictionary as sudachi_dictionary
    _SUDACHI = sudachi_dictionary.Dictionary().create()
    _SUDACHI_MODE = sudachi_tokenizer.Tokenizer.SplitMode.C
except Exception:
    _SUDACHI = None
    _SUDACHI_MODE = None

# ZH: pkuseg
try:
    import pkuseg as _pkuseg
    _PKUSEG = _pkuseg.pkuseg(model_name="default")
except Exception:
    _PKUSEG = None

# TH: PyThaiNLP
try:
    from pythainlp.tokenize import word_tokenize as thai_word_tokenize
    _THAI_OK = True
except Exception:
    _THAI_OK = False

# Romanization: JA/KO/ZH
try:
    from pykakasi import kakasi as _kakasi
    _kak = _kakasi(); _kak.setMode("H","a"); _kak.setMode("K","a"); _kak.setMode("J","a")
    _JP_ROM = _kak.getConverter()
except Exception:
    _JP_ROM = None

try:
    from hangul_romanize import Transliter
    from hangul_romanize.rule import academic
    _KO_ROM = Transliter(academic)
except Exception:
    _KO_ROM = None

try:
    from pypinyin import lazy_pinyin
    _ZH_ROM_OK = True
except Exception:
    _ZH_ROM_OK = False

# spaCy (optional lemmatizer)
try:
    import spacy
    _SPACY_CACHE: Dict[str, "spacy.language.Language"] = {}
    _SPACY_MAP = {
        "en": "en_core_web_sm",
        "es": "es_core_news_sm",
        "fr": "fr_core_news_sm",
        "de": "de_core_news_sm",
        "it": "it_core_news_sm",
        "pt": "pt_core_news_sm",
        "nl": "nl_core_news_sm",
    }
except Exception:
    spacy = None
    _SPACY_CACHE = {}
    _SPACY_MAP = {}

# -----------------------------
# Configuration
# -----------------------------

@dataclass
class LangConfig:
    name: str
    trans_code: str
    wordfreq_code: Optional[str]
    pyphen_code: Optional[str]
    script_hint: str
    tokenizer: Optional[str] = None  # default preference

LANGS: List[LangConfig] = [
    LangConfig("Chinese (Traditional)", "zh-TW", "zh", None, "han", tokenizer="jieba"),
    LangConfig("Chinese (Simplified)", "zh-CN", "zh", None, "han", tokenizer="jieba"),
    LangConfig("Hindi", "hi", "hi", None, "devanagari"),
    LangConfig("Spanish", "es", "es", "es", "latin"),
    LangConfig("French", "fr", "fr", "fr", "latin"),
    LangConfig("Arabic", "ar", "ar", None, "arabic"),
    LangConfig("Bengali", "bn", "bn", None, "bengali"),
    LangConfig("Portuguese", "pt", "pt", "pt", "latin"),
    LangConfig("Russian", "ru", "ru", "ru", "cyrillic"),
    LangConfig("Urdu", "ur", "ur", None, "arabic"),
    LangConfig("Indonesian", "id", "id", "id", "latin"),
    LangConfig("German", "de", "de", "de", "latin"),
    LangConfig("Japanese", "ja", "ja", None, "kana", tokenizer="tinysegmenter"),
    LangConfig("Swahili", "sw", "sw", "sw", "latin"),
    LangConfig("Marathi", "mr", "mr", None, "devanagari"),
    LangConfig("Telugu", "te", "te", None, "telugu"),
    LangConfig("Turkish", "tr", "tr", "tr", "latin"),
    LangConfig("Tamil", "ta", "ta", None, "tamil"),
    LangConfig("Vietnamese", "vi", "vi", "vi", "latin"),
    LangConfig("Korean", "ko", "ko", None, "hangul"),
    LangConfig("Italian", "it", "it", "it", "latin"),
    LangConfig("Persian (Farsi)", "fa", "fa", None, "arabic"),
    LangConfig("Hausa", "ha", "ha", "ha", "latin"),
    LangConfig("Thai", "th", "th", None, "thai"),
    LangConfig("Gujarati", "gu", "gu", None, "gujarati"),
    LangConfig("Dutch",  "nl", "nl", "nl_NL", "latin"),
    LangConfig("Romanian", "ro", "ro", "ro_RO", "latin"),
    LangConfig("Ukrainian", "uk", "uk", "uk_UA", "cyrillic"),
    LangConfig("Greek",  "el", "el", "el_GR", "greek"),
    LangConfig("Hebrew", "iw", "he", None, "hebrew"),  # Google 'iw' legacy
    LangConfig("Czech",  "cs", "cs", "cs_CZ", "latin"),
    LangConfig("Hungarian", "hu", "hu", "hu_HU", "latin"),
    LangConfig("Swedish",  "sv", "sv", "sv_SE", "latin"),
    LangConfig("Danish",  "da", "da", "da_DK", "latin"),
    LangConfig("Bulgarian", "bg", "bg", "bg_BG", "cyrillic"),
    LangConfig("Serbian", "sr", "sr", "sr_RS", "cyrillic"),
    LangConfig("Croatian", "hr", "hr", "hr_HR", "latin"),
    LangConfig("Slovak", "sk", "sk", "sk_SK", "latin"),
    LangConfig("Slovenian", "sl", "sl", "sl_SI", "latin"),
    LangConfig("Finnish", "fi", "fi", "fi_FI", "latin"),
    LangConfig("Norwegian (Bokmål)", "no", "no", "nb_NO", "latin"),
    LangConfig("Catalan", "ca", "ca", "ca", "latin"),
    LangConfig("Filipino (Tagalog)", "tl", None, None, "latin"),
    LangConfig("Khmer", "km", None, None, "khmer"),
    LangConfig("Nepali", "ne", "ne", None, "devanagari"),
    LangConfig("Yoruba", "yo", None, None, "latin"),
    LangConfig("Uzbek", "uz", "uz", None, "latin"),
    LangConfig("Kazakh", "kk", "kk", None, "cyrillic"),
    LangConfig("Azerbaijani", "az", "az", None, "latin"),
    LangConfig("Pashto", "ps", None, None, "arabic"),
    LangConfig("Kurdish (Kurmanji)", "ku", None, None, "latin"),
    LangConfig("Kurdish (Sorani)",  "ckb", None, None, "arabic"),
    LangConfig("Latin", "la", "la", "la", "latin"),
    # Newer adds
    LangConfig("Polish", "pl", "pl", "pl_PL", "latin"),
    LangConfig("Icelandic", "is", "is", "is_IS", "latin"),
    LangConfig("Punjabi (Gurmukhi)", "pa", "pa", None, "gurmukhi"),
    LangConfig("Malayalam", "ml", "ml", None, "malayalam"),
    LangConfig("Sinhala", "si", "si", None, "sinhala"),
    LangConfig("Amharic", "am", "am", None, "ethiopic"),
    LangConfig("Welsh", "cy", "cy", "cy_GB", "latin"),
    LangConfig("Zulu", "zu", "zu", None, "latin"),
    LangConfig("Armenian", "hy", "hy", None, "armenian"),
    LangConfig("Georgian", "ka", "ka", None, "georgian"),
    LangConfig("Burmese", "my", "my", None, "myanmar"),
    LangConfig("Lao", "lo", "lo", None, "lao"),
]

DEFAULT_ZIPF = 2.5
DEFAULT_MIN_LEN_LATINLIKE = 2
PER_LANG_ZIPF: Dict[str, float] = {"tr": 1.5}

MORPHEME_SYNTHETIC_ZIPF = 3.0
HANGUL_CONTENT_MORPHEME_FLOOR = 2.0

KANA_PARTICLES = {"の", "は", "を", "に", "へ", "が", "と", "も", "ね", "よ", "か"}
HANGUL_PARTICLES = {"은", "는", "이", "가", "을", "를", "와", "과", "도", "에"}

# -----------------------------
# Utilities & Caches
# -----------------------------

def normalize_text(s: str) -> str:
    return unicodedata.normalize("NFKC", s).strip()

def is_latinlike(script_hint: str) -> bool:
    return script_hint in {"latin", "cyrillic"}

def safe_lower(s: str) -> str:
    return s.casefold()

PUNCT_RE = re.compile(r"[\p{P}\p{S}\s]", re.UNICODE)

def is_cjk_ideograph(ch: str) -> bool:
    if len(ch) != 1:
        return False
    cp = ord(ch)
    return (
        0x3400 <= cp <= 0x4DBF or
        0x4E00 <= cp <= 0x9FFF or
        0x20000 <= cp <= 0x2A6DF or
        0x2A700 <= cp <= 0x2B73F or
        0x2B740 <= cp <= 0x2B81F or
        0x2B820 <= cp <= 0x2CEAF or
        0x2CEB0 <= cp <= 0x2EBEF
    )

def is_hangul_syllable(ch: str) -> bool:
    return len(ch) == 1 and 0xAC00 <= ord(ch) <= 0xD7A3

_pyphen_cache: Dict[str, pyphen.Pyphen] = {}
def get_pyphen(lang_code: Optional[str]) -> Optional[pyphen.Pyphen]:
    if not lang_code:
        return None
    if lang_code in _pyphen_cache:
        return _pyphen_cache[lang_code]
    try:
        _pyphen_cache[lang_code] = pyphen.Pyphen(lang=lang_code)
        return _pyphen_cache[lang_code]
    except Exception:
        return None

def wordfreq_zipf(token: str, lang_code: Optional[str]) -> float:
    if not lang_code:
        return 0.0
    try:
        return float(zipf_frequency(token, lang_code))
    except Exception:
        return 0.0

def hyphenate_segments(word: str, pyphen_code: Optional[str]) -> List[str]:
    dic = get_pyphen(pyphen_code)
    if not dic:
        return []
    try:
        pieces = dic.inserted(word)
        if not pieces or pieces == word:
            return []
        return [p for p in pieces.split("-") if p]
    except Exception:
        return []

VOWEL_RE = re.compile(r"[AEIOUYÄÖÜËÍÓÚÝÀÈÌÒÙáéíóúýàèìòùâêîôûãõåæœüöäëÿ]", re.IGNORECASE)
def heuristic_segments_latin(word: str) -> List[str]:
    if len(word) <= 3:
        return [word]
    segs, start = [], 0
    for i in range(1, len(word)):
        if VOWEL_RE.match(word[i-1]) and not VOWEL_RE.match(word[i]):
            segs.append(word[start:i]); start = i
    segs.append(word[start:])
    return [s for s in segs if s]

# tinysegmenter: support both legacy (tinysegmenter.tokenize) and class-based (TinySegmenter) APIs
def _tinysegmenter_tokenize(text):
    if tinysegmenter is None:
        return list(text)  # fallback: char-by-char
    if hasattr(tinysegmenter, 'tokenize'):
        return tinysegmenter.tokenize(text)
    return tinysegmenter.tokenize(text)  # TinySegmenter instance

# ---------- Romanization ----------
def romanize_text(text: str, lang: LangConfig) -> str:
    code = lang.trans_code
    try:
        if code == "ja" and _JP_ROM:
            return _JP_ROM.do(text)
        if code == "ko" and _KO_ROM:
            return _KO_ROM.translit(text)
        if code.startswith("zh") and _ZH_ROM_OK:
            return " ".join(lazy_pinyin(text))
    except Exception:
        pass
    return ""

# -----------------------------
# Translator (with gentle retries)
# -----------------------------

class Translator:
    def __init__(self, default_source: str = "en", retries: int = 2, delay: float = 0.6):
        self.default_source = default_source
        self.retries = retries
        self.delay = delay

    @staticmethod
    def _fix_code(code: str) -> str:
        # Normalize a few language codes for deep_translator
        if not code:
            return code
        return {
            "he": "iw",  # Hebrew legacy
            "nb": "no",  # Bokmål maps to 'no'
        }.get(code, code)

    def _translate(self, text: str, source: str, target: str) -> str:
        last_err = None
        src = self._fix_code(source)
        tgt = self._fix_code(target)
        for k in range(self.retries + 1):
            try:
                return GoogleTranslator(source=src, target=tgt).translate(text)
            except Exception as e:
                last_err = e
                if k < self.retries:
                    time.sleep(self.delay * (k + 1))
        return f"[translation failed: {last_err}]"

    def to_target(self, text: str, target: str) -> str:
        return self._translate(text, self.default_source, target)

    def to_english(self, text: str, source: str) -> str:
        return self._translate(text, source, "en")

# -----------------------------
# RU helpers (optional)
# -----------------------------

def ru_lemmatize(word: str) -> str:
    if not RUS_MORPH:
        return word
    p = RUS_MORPH.parse(word)
    if not p:
        return word
    return p[0].normal_form

def ru_has_known_pos(token: str) -> bool:
    if not RUS_MORPH:
        return True
    parses = RUS_MORPH.parse(token)
    return any(getattr(pr.tag, "POS", None) for pr in parses)

# spaCy helpers
def _get_spacy(code: str):
    if (not spacy) or (code not in _SPACY_MAP):
        return None
    if code in _SPACY_CACHE:
        return _SPACY_CACHE[code]
    try:
        _SPACY_CACHE[code] = spacy.load(_SPACY_MAP[code], disable=["ner", "parser", "textcat"])
        return _SPACY_CACHE[code]
    except Exception:
        return None

def lemmatize_line(text: str, lang_code: str) -> str:
    nlp = _get_spacy(lang_code)
    if not nlp:
        return text
    doc = nlp(text)
    return " ".join(t.lemma_ for t in doc)

def postprocess_translation_for_lang(translated: str, lang: LangConfig, do_lemma: bool=False) -> str:
    t = normalize_text(translated)
    # Russian: morphological normalization (if available)
    if (lang.wordfreq_code == "ru") and RUS_MORPH:
        tokens = re.findall(r"\p{L}+", t)
        if not tokens:
            pass
        elif len(tokens) == 1:
            t = ru_lemmatize(tokens[0])
        else:
            t = " ".join(ru_lemmatize(tok) for tok in tokens)
    # Optional spaCy lemmatization for supported EU languages
    if do_lemma and lang.wordfreq_code in _SPACY_MAP:
        t = lemmatize_line(t, lang.wordfreq_code)
    return t

# -----------------------------
# Morpheme admission rules
# -----------------------------

def admit_morpheme(token: str, lang: LangConfig) -> bool:
    if len(token) != 1:
        return False
    if is_cjk_ideograph(token):
        return True
    if token in KANA_PARTICLES:
        return True
    if token in HANGUL_PARTICLES:
        return True
    return False

# -----------------------------
# Tokenization (with routing)
# -----------------------------

def segment_word(word: str, lang: LangConfig, args=None) -> List[str]:
    w = normalize_text(word)

    # ZH
    if lang.trans_code.startswith("zh"):
        use = (args.zh_tokenizer if args else "jieba")
        if use == "pkuseg" and _PKUSEG:
            segs = [t for t in _PKUSEG.cut(w) if t.strip()]
            return segs or [w]
        # default jieba
        segs = [t for t in jieba.cut(w, HMM=True) if t.strip()]
        return segs or [w]

    # JA
    if lang.trans_code == "ja":
        use = (args.jp_tokenizer if args else "tiny")
        if use == "sudachi" and _SUDACHI:
            segs = [m.surface() for m in _SUDACHI.tokenize(w, _SUDACHI_MODE) if m.surface().strip()]
            return segs or [w]
        # default tinysegmenter
        segs = [t for t in _tinysegmenter_tokenize(w) if t.strip()]
        return segs or [w]

    # TH
    if lang.trans_code == "th":
        use = (args.th_tokenizer if args else "pythainlp")
        if use == "pythainlp" and _THAI_OK:
            segs = [t for t in thai_word_tokenize(w) if t.strip()]
            return segs or [w]

    # Fallbacks
    segs = hyphenate_segments(w, lang.pyphen_code)
    if segs:
        return segs
    if is_latinlike(lang.script_hint):
        return heuristic_segments_latin(w)
    return list(w)

def generate_substrings(s: str, allow_single_chars: bool, min_len_latinlike: int) -> List[str]:
    n = len(s); out: List[str] = []
    min_len = 1 if allow_single_chars else min_len_latinlike
    for i in range(n):
        for j in range(i + min_len, n + 1):
            out.append(s[i:j])
    return out

def meaningful_gloss_en(gloss: str) -> bool:
    g = gloss.strip()
    if not g:
        return False
    if re.fullmatch(r"[A-Za-z]{1,3}", g):
        return False
    if len(g) <= 4 and (g.isupper() or g.istitle()):
        return False
    return True

# -----------------------------
# Core analysis
# -----------------------------

def analyze_translation(
    translated: str,
    lang: LangConfig,
    global_zipf_thr: float,
    per_lang_zipf: Dict[str, float],
    min_len_latinlike: int,
    top_n: int,
    translator: Translator,
    enable_morphemes: bool,
    args=None,
) -> Dict:
    tnorm = normalize_text(translated)
    compact = PUNCT_RE.sub("", tnorm)
    segs = segment_word(tnorm, lang, args=args)

    allow_single = (lang.script_hint in {"han", "kana", "hangul", "thai"})
    candidates = set(generate_substrings(compact, allow_single, min_len_latinlike))
    for seg in segs:
        s2 = PUNCT_RE.sub("", seg)
        if s2:
            candidates.update(generate_substrings(s2, allow_single, min_len_latinlike))

    if compact in candidates and len(compact) > (1 if allow_single else min_len_latinlike):
        candidates.remove(compact)

    lang_floor = per_lang_zipf.get(lang.wordfreq_code or "", global_zipf_thr)

    chosen: Dict[str, Tuple[float, str]] = {}
    for c in candidates:
        token = safe_lower(c) if is_latinlike(lang.script_hint) else c
        z = wordfreq_zipf(token, lang.wordfreq_code)
        kind = None

        if z >= lang_floor:
            kind = "word"

        elif enable_morphemes and lang.script_hint == "hangul" and is_hangul_syllable(token):
            admit = (z >= HANGUL_CONTENT_MORPHEME_FLOOR)
            if not admit:
                gloss_probe = translator.to_english(token, source=lang.trans_code).strip()
                admit = meaningful_gloss_en(gloss_probe)
            if admit:
                kind = "morpheme"
                z = max(z, MORPHEME_SYNTHETIC_ZIPF)

        elif enable_morphemes and admit_morpheme(token, lang):
            kind = "morpheme"
            z = max(z, MORPHEME_SYNTHETIC_ZIPF)

        if kind:
            if lang.wordfreq_code == "ru" and kind == "word" and not ru_has_known_pos(token):
                continue
            if token not in chosen or z > chosen[token][0]:
                chosen[token] = (z, kind)

    main, rare = [], []
    for tok, (z, kind) in chosen.items():
        (main if z >= global_zipf_thr else rare).append((tok, z, kind))

    def sort_key(x: Tuple[str, float, str]):
        t, z, _ = x
        return (-z, -len(t), t)

    main_sorted = sorted(main, key=sort_key)[:top_n]
    rare_sorted = sorted(rare, key=sort_key)[:top_n]

    to_gloss = [t for (t, _, _) in (main_sorted + rare_sorted)]
    gloss_map: Dict[str, str] = {}
    for tok in to_gloss:
        gloss_map[tok] = translator.to_english(tok, source=lang.trans_code)

    def pack(items: List[Tuple[str, float, str]]) -> List[Dict]:
        return [{"token": t, "zipf": round(z, 2), "type": kind, "gloss_en": gloss_map.get(t, "")}
                for (t, z, kind) in items]

    notes = []
    if lang.wordfreq_code is None:
        notes.append("wordfreq not available; inner-word validity checks limited.")
    # tokenizer notes
    if lang.trans_code.startswith("zh"):
        notes.append(f"ZH tokenizer: {('pkuseg' if (args and args.zh_tokenizer=='pkuseg' and _PKUSEG) else 'jieba')}")
    if lang.trans_code == "ja":
        notes.append(f"JA tokenizer: {('sudachi' if (args and args.jp_tokenizer=='sudachi' and _SUDACHI) else 'tinysegmenter')}")
    if lang.trans_code == "th":
        notes.append(f"TH tokenizer: {('pythainlp' if (args and args.th_tokenizer=='pythainlp' and _THAI_OK) else 'fallback')}")
    if enable_morphemes and lang.script_hint in {"han", "kana", "hangul"}:
        notes.append("morpheme mode active for this script (single-character items may appear).")
    if not main_sorted and not rare_sorted:
        notes.append(f"no inner items at thresholds (lang floor={lang_floor}, global={global_zipf_thr}).")

    return {
        "translation": translated,
        "segments": segs,
        "inner_words_main": pack(main_sorted),
        "inner_words_rare": pack(rare_sorted),
        "thresholds": {"lang_floor": lang_floor, "global": global_zipf_thr},
        "notes": notes,
    }

# -----------------------------
# CLI
# -----------------------------

def parse_overrides(csv: str) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if not csv.strip():
        return out
    for item in csv.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Bad override entry '{item}', expected lang:val")
        lang, val = item.split(":", 1)
        out[lang.strip()] = float(val.strip())
    return out

def parse_args():
    ap = argparse.ArgumentParser(description="WordFinder v2.7")
    ap.add_argument("english", nargs="+", help="English word or phrase")
    ap.add_argument("--zipf", type=float, default=DEFAULT_ZIPF, help="Global Zipf threshold (default 2.5)")
    ap.add_argument("--zipf-override", type=str, default="", help='Per-language floors, e.g. "tr:1.5,ru:2.0"')
    ap.add_argument("--langs", type=str, default="", help="Comma list (e.g. es,fr,zh-CN). Empty = all.")
    ap.add_argument("--top", type=int, default=12, help="Max items per bucket")
    ap.add_argument("--minlen", type=int, default=DEFAULT_MIN_LEN_LATINLIKE,
                    help="Min substring length for Latin/Cyrillic (default 2)")
    ap.add_argument("--json", action="store_true", help="Emit JSON")
    ap.add_argument("--no-rare", action="store_true", help="Hide Rare bucket in pretty output")
    ap.add_argument("--no-morphemes", action="store_true", help="Disable morpheme mode for all scripts")
    # Smarter linguistics flags
    ap.add_argument("--jp-tokenizer", choices=["tiny", "sudachi"], default="tiny",
                    help="Japanese tokenizer backend")
    ap.add_argument("--zh-tokenizer", choices=["jieba", "pkuseg"], default="jieba",
                    help="Chinese tokenizer backend")
    ap.add_argument("--th-tokenizer", choices=["none", "pythainlp"], default="pythainlp",
                    help="Thai tokenizer backend")
    ap.add_argument("--romanize", action="store_true", help="Show romanization (JA/K0/ZH)")
    ap.add_argument("--lemmatize", action="store_true",
                    help="Enable lemmatization via spaCy where available (en, es, fr, de, it, pt, nl)")
    return ap.parse_args()

def select_langs(codes_csv: str) -> List[LangConfig]:
    if not codes_csv:
        return LANGS
    want = {c.strip() for c in codes_csv.split(",") if c.strip()}
    return [l for l in LANGS if l.trans_code in want]

def main():
    args = parse_args()
    english = normalize_text(" ".join(args.english))
    langs = select_langs(args.langs)

    per_lang_zipf = dict(PER_LANG_ZIPF)
    if args.zipf_override:
        per_lang_zipf.update(parse_overrides(args.zipf_override))

    translator = Translator(default_source="en")
    enable_morphemes = not args.no_morphemes

    if args.json:
        out = {"input": english, "global_zipf": args.zipf, "results": {}}
        for lang in langs:
            translated_raw = translator.to_target(english, target=lang.trans_code)
            translated = postprocess_translation_for_lang(translated_raw, lang, do_lemma=args.lemmatize)
            out["results"][lang.name] = analyze_translation(
                translated, lang, args.zipf, per_lang_zipf, args.minlen,
                args.top, translator, enable_morphemes, args=args
            )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    print("=" * 72)
    print(f'INPUT (English): "{english}"')
    print("=" * 72)

    for lang in langs:
        print("\n" + "-" * 72)
        print(f"{lang.name}  [{lang.trans_code}]")
        print("-" * 72)

        translated_raw = translator.to_target(english, target=lang.trans_code)
        translated = postprocess_translation_for_lang(translated_raw, lang, do_lemma=args.lemmatize)
        result = analyze_translation(
            translated, lang, args.zipf, per_lang_zipf, args.minlen,
            args.top, translator, enable_morphemes, args=args
        )

        print(f"Translation: {result['translation']}")
        if args.romanize:
            rom = romanize_text(result['translation'], lang)
            if rom:
                print(f"Romanization: {rom}")
        print("Segments:    " + (" · ".join(result['segments']) if result['segments'] else "(none)"))

        main_items = result["inner_words_main"]
        rare_items = result["inner_words_rare"]

        if main_items:
            inner_disp = ", ".join([f"{it['token']} → {it['gloss_en']} (Zipf {it['zipf']}, {it['type']})"
                                    for it in main_items])
            print(f"Inner words: {inner_disp}")
        else:
            print("Inner words: (none ≥ global threshold)")

        if not args.no_rare:
            if rare_items:
                rare_disp = ", ".join([f"{it['token']} → {it['gloss_en']} (Zipf {it['zipf']}, {it['type']})"
                                       for it in rare_items])
                print(f"Rare (< global): {rare_disp}")
            else:
                print("Rare:        (none)")

        if result["notes"]:
            print("Notes:       " + " | ".join(result["notes"]))

    print("\n" + "=" * 72)
    print("Done.")

if __name__ == "__main__":
    main()
