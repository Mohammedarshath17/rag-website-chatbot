import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

LANGUAGE_MAPPING = {
    "hi": "hin_Deva",
    "ta": "tam_Taml",
    "mr": "mar_Deva",
    "te": "tel_Telu",
    "kn": "kan_Knda",
    "bn": "ben_Beng",
    "de": "deu_Latn",
    "fr": "fra_Latn",
    "ja": "jpn_Jpan",
    "en": "eng_Latn"
}

class TranslationEngine:
    def __init__(self):
        self.model_name = "facebook/nllb-200-distilled-600M"
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def load_model(self):
        """Lazily loads the translation model and tokenizer."""
        if self.model is None:
            print(f"\n--- Loading local translation model: {self.model_name} ---")
            print(f"Translation Hardware Acceleration: {self.device.upper()}")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            # Use Float16 on GPU to save memory, Float32 on CPU
            torch_dtype = torch.float16 if self.device == "cuda" else torch.float32
            
            self.model = AutoModelForSeq2SeqLM.from_pretrained(
                self.model_name,
                torch_dtype=torch_dtype,
                low_cpu_mem_usage=True
            )
            self.model = self.model.to(self.device)
            print("Translation model loaded successfully!\n")

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translates text from source language code to target language code."""
        if not text or not text.strip():
            return text
            
        src_code = LANGUAGE_MAPPING.get(source_lang, source_lang)
        tgt_code = LANGUAGE_MAPPING.get(target_lang, target_lang)
        
        if src_code == tgt_code:
            return text
            
        # Ensure model is loaded
        self.load_model()
        
        # Set source language in tokenizer
        self.tokenizer.src_lang = src_code
        
        # Tokenize inputs
        inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        
        # Determine the target language bos token ID
        forced_bos_token_id = self.tokenizer.convert_tokens_to_ids(tgt_code)
        
        # Generate translation
        with torch.no_grad():
            translated_tokens = self.model.generate(
                **inputs,
                forced_bos_token_id=forced_bos_token_id,
                max_length=512
            )
            
        # Decode and return translation
        translated_text = self.tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)[0]
        return translated_text

# Global singleton engine cache
translator_engine = TranslationEngine()
