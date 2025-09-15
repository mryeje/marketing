#!/usr/bin/env python3
"""
Real AI Content Filter using Hugging Face Transformers
Uses distilbert-base-uncased-finetuned-sst-2-english model for sentiment analysis
"""

import logging
from typing import List, Dict, Any
import numpy as np

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from transformers import pipeline
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers library not available. Using fallback mode.")

class ContentFilter:
    def __init__(self, model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"):
        self.model_name = model_name
        self.classifier = None

        if TRANSFORMERS_AVAILABLE:
            self._initialize_model()
        else:
            logger.warning("Running in fallback mode - install transformers for real AI filtering")
            self._initialize_fallback()

    def _initialize_model(self):
        """Initialize the Hugging Face model with GPU/CPU auto-detection"""
        try:
            device = 0 if torch.cuda.is_available() else -1
            if device == 0:
                logger.info(f"🤖 Loading AI model on GPU: {torch.cuda.get_device_name(0)}")
            else:
                logger.info("🤖 Loading AI model on CPU")

            self.classifier = pipeline(
                "text-classification",
                model=self.model_name,
                device=device,
                truncation=True,
                padding=True,
                max_length=512,
                top_k=1
            )
            logger.info("✅ AI model loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load AI model: {e}")
            self._initialize_fallback()

    def _initialize_fallback(self):
        """Fallback to simple pattern matching if transformers not available"""
        logger.info("🔄 Using fallback pattern matching")
        self.fallback_patterns = {
            'relevant': [
                'tool', 'diy', 'build', 'make', 'create', 'repair', 'install',
                'wood', 'metal', 'construction', 'project', 'homeimprovement',
                'appliance', 'kitchen', 'laundry', 'clean', 'garden', 'outdoor',
                'power', 'equipment', 'professional', 'review', 'tutorial', 'howto',
                'drill', 'saw', 'hammer', 'wrench', 'sander', 'grinder', 'router'
            ],
            'irrelevant': [
                'fyp', 'foryou', 'viral', 'trending', 'dance', 'music', 'prank',
                'challenge', 'comedy', 'funny', 'love', 'relationship', 'dating',
                'gaming', 'fortnite', 'minecraft', 'makeup', 'beauty', 'fashion',
                'tiktok', 'follow', 'like', 'subscribe', 'song'
            ]
        }

    def filter_irrelevant(self, texts: List[str], threshold: float = 0.7) -> List[bool]:
        """Filter out irrelevant content using AI sentiment analysis or fallback"""
        if not texts:
            return []

        if self.classifier is not None:
            return self._filter_with_ai(texts, threshold)
        else:
            return self._filter_with_fallback(texts)

    def _filter_with_ai(self, texts: List[str], threshold: float) -> List[bool]:
        results = []
        try:
            batch_size = 32
            for i in range(0, len(texts), batch_size):
                batch = [str(text) if text else "" for text in texts[i:i + batch_size]]
                try:
                    batch_results = self.classifier(batch)
                    for result in batch_results:
                        if isinstance(result, list):
                            result = result[0]
                        is_positive = result['label'] == 'POSITIVE'
                        is_confident = result['score'] >= threshold
                        results.append(is_positive and is_confident)
                except Exception as e:
                    logger.warning(f"Error processing batch: {e}")
                    results.extend([False] * len(batch))
            relevant_count = sum(results)
            logger.info(f"✅ AI filtering complete: {relevant_count}/{len(texts)} items marked relevant")
            return results
        except Exception as e:
            logger.error(f"AI filtering failed: {e}")
            return self._filter_with_fallback(texts)

    def _filter_with_fallback(self, texts: List[str]) -> List[bool]:
        results = []
        for text in texts:
            if not text or not isinstance(text, str):
                results.append(False)
                continue
            text_lower = text.lower()
            rel_matches = sum(1 for p in self.fallback_patterns['relevant'] if p in text_lower)
            irrel_matches = sum(1 for p in self.fallback_patterns['irrelevant'] if p in text_lower)
            if rel_matches == 0 and irrel_matches == 0:
                results.append(True)
            else:
                results.append(rel_matches > irrel_matches)
        relevant_count = sum(results)
        logger.info(f"🔄 Fallback filtering: {relevant_count}/{len(texts)} items marked relevant")
        return results

    def analyze_text(self, text: str) -> Dict[str, Any]:
        if not text or not isinstance(text, str):
            return {"relevant": False, "confidence": 0.0, "reason": "Invalid text"}
        if self.classifier:
            return self._analyze_with_ai(text)
        else:
            return self._analyze_with_fallback(text)

    def _analyze_with_ai(self, text: str) -> Dict[str, Any]:
        try:
            results = self.classifier([text])
            if isinstance(results[0], list):
                result = results[0][0]
            else:
                result = results[0]
            return {
                "relevant": result['label'] == 'POSITIVE',
                "confidence": float(result['score']),
                "label": result['label'],
                "model": self.model_name,
                "method": "AI"
            }
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return self._analyze_with_fallback(text)

    def _analyze_with_fallback(self, text: str) -> Dict[str, Any]:
        text_lower = text.lower()
        relevant_matches = [p for p in self.fallback_patterns['relevant'] if p in text_lower]
        irrelevant_matches = [p for p in self.fallback_patterns['irrelevant'] if p in text_lower]
        total_matches = len(relevant_matches) + len(irrelevant_matches)
        confidence = len(relevant_matches) / total_matches if total_matches else 0.5
        return {
            "relevant": len(relevant_matches) > len(irrelevant_matches),
            "confidence": confidence,
            "relevant_matches": relevant_matches,
            "irrelevant_matches": irrelevant_matches,
            "method": "fallback"
        }

# Singleton
_filter_instance = None

def get_content_filter():
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = ContentFilter()
    return _filter_instance

# Simple test
if __name__ == "__main__":
    filter = get_content_filter()
    sample_texts = [
        "DIY power tools for woodworking",
        "Viral dance challenge #fyp",
        "Kitchen appliance review"
    ]
    results = filter.filter_irrelevant(sample_texts)
    for text, keep in zip(sample_texts, results):
        status = "✅ RELEVANT" if keep else "❌ IRRELEVANT"
        print(f"{status}: {text}")
