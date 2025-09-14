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
    from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("Transformers library not available. Using fallback mode.")

class ContentFilter:
    def __init__(self, model_name: str = "distilbert-base-uncased-finetuned-sst-2-english"):
        """
        Real AI content filter using Hugging Face transformers
        
        Args:
            model_name: Hugging Face model to use for classification
        """
        self.model_name = model_name
        self.classifier = None
        self.tokenizer = None
        self.model = None
        
        if TRANSFORMERS_AVAILABLE:
            self._initialize_model()
        else:
            logger.warning("Running in fallback mode - install transformers for real AI filtering")
            self._initialize_fallback()
    
    def _initialize_model(self):
        """Initialize the Hugging Face model"""
        try:
            logger.info(f"🤖 Loading AI model: {self.model_name}")
            
            self.classifier = pipeline(
                "text-classification",
                model=self.model_name,
                device=-1,  # Use CPU (-1), use 0 for GPU if available
                torch_dtype=torch.float32,
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
                'tiktok', 'follow', 'like', 'subscribe', 'viral', 'music', 'song'
            ]
        }
    
    def filter_irrelevant(self, texts: List[str], threshold: float = 0.7) -> List[bool]:
        """
        Filter out irrelevant content using AI sentiment analysis
        
        Args:
            texts: List of text strings to classify
            threshold: Confidence threshold for relevance (0.0-1.0)
            
        Returns:
            List of booleans indicating relevance for each text
        """
        if not texts:
            return []
            
        if self.classifier is not None:
            return self._filter_with_ai(texts, threshold)
        else:
            return self._filter_with_fallback(texts)
    
    def _filter_with_ai(self, texts: List[str], threshold: float) -> List[bool]:
        """Filter using Hugging Face transformer model"""
        try:
            # Process in batches to avoid memory issues
            batch_size = 32
            results = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                batch = [str(text) if text else "" for text in batch]  # Ensure strings
                
                try:
                    batch_results = self.classifier(batch)
                    
                    for result in batch_results:
                        if isinstance(result, list):
                            result = result[0]  # Take top prediction
                        
                        is_positive = result['label'] == 'POSITIVE'
                        is_confident = result['score'] >= threshold
                        results.append(is_positive and is_confident)
                        
                except Exception as e:
                    logger.warning(f"Error processing batch: {e}")
                    # Mark all in batch as irrelevant on error
                    results.extend([False] * len(batch))
            
            relevant_count = sum(results)
            logger.info(f"✅ AI filtering complete: {relevant_count}/{len(texts)} items marked relevant")
            return results
            
        except Exception as e:
            logger.error(f"AI filtering failed: {e}")
            return self._filter_with_fallback(texts)
    
    def _filter_with_fallback(self, texts: List[str]) -> List[bool]:
        """Fallback filtering using pattern matching"""
        results = []
        
        for text in texts:
            if not text or not isinstance(text, str):
                results.append(False)
                continue
                
            text_lower = text.lower()
            
            # Count matches for each category
            relevant_matches = sum(1 for pattern in self.fallback_patterns['relevant'] 
                                 if pattern in text_lower)
            irrelevant_matches = sum(1 for pattern in self.fallback_patterns['irrelevant'] 
                                   if pattern in text_lower)
            
            # Decide based on pattern counts
            if relevant_matches == 0 and irrelevant_matches == 0:
                results.append(True)  # Default to relevant if no patterns match
            else:
                results.append(relevant_matches > irrelevant_matches)
        
        relevant_count = sum(results)
        logger.info(f"🔄 Fallback filtering: {relevant_count}/{len(texts)} items marked relevant")
        return results
    
    def analyze_text(self, text: str) -> Dict[str, Any]:
        """
        Analyze a single text and return detailed results
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with analysis results
        """
        if not text or not isinstance(text, str):
            return {"relevant": False, "confidence": 0.0, "reason": "Invalid text"}
        
        if self.classifier is not None:
            return self._analyze_with_ai(text)
        else:
            return self._analyze_with_fallback(text)
    
    def _analyze_with_ai(self, text: str) -> Dict[str, Any]:
        """Analyze using AI model"""
        try:
            results = self.classifier([text])
            if isinstance(results[0], list):
                result = results[0][0]  # Take top prediction
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
        """Analyze using fallback patterns"""
        text_lower = text.lower()
        
        relevant_matches = [p for p in self.fallback_patterns['relevant'] 
                          if p in text_lower]
        irrelevant_matches = [p for p in self.fallback_patterns['irrelevant'] 
                            if p in text_lower]
        
        total_matches = len(relevant_matches) + len(irrelevant_matches)
        if total_matches == 0:
            confidence = 0.5
        else:
            confidence = len(relevant_matches) / total_matches
        
        return {
            "relevant": len(relevant_matches) > len(irrelevant_matches),
            "confidence": confidence,
            "relevant_matches": relevant_matches,
            "irrelevant_matches": irrelevant_matches,
            "method": "fallback"
        }

# Singleton instance
_filter_instance = None

def get_content_filter():
    """Get or create the content filter instance"""
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = ContentFilter()
    return _filter_instance

def test_filter():
    """Test the filter with sample data"""
    print("🧪 Testing Real AI content filter...")
    
    filter = get_content_filter()
    
    test_texts = [
        "How to use a power drill for DIY projects and home improvement",
        "Best cordless tools for woodworking and construction",
        "Check out this viral dance challenge! #fyp #viral",
        "New makeup tutorial for summer looks and beauty tips",
        "Kitchen appliance review: best blender and mixer for 2024",
        "Outdoor power equipment maintenance tips for lawn care",
        "",
        None,
        "This is a test of the emergency broadcast system"
    ]
    
    print(f"Using method: {'AI' if filter.classifier else 'fallback'}")
    
    results = filter.filter_irrelevant(test_texts)
    
    print(f"\n📊 Filter Results:")
    for i, (text, is_relevant) in enumerate(zip(test_texts, results)):
        status = "✅ RELEVANT" if is_relevant else "❌ IRRELEVANT"
        text_preview = str(text)[:50] + "..." if text and len(str(text)) > 50 else str(text)
        print(f"{i+1}. {status}: {text_preview}")
        
        # Show detailed analysis
        analysis = filter.analyze_text(str(text) if text else "")
        print(f"   Method: {analysis.get('method', 'unknown')}")
        if 'confidence' in analysis:
            print(f"   Confidence: {analysis['confidence']:.3f}")
        if 'relevant_matches' in analysis and analysis['relevant_matches']:
            print(f"   Relevant patterns: {analysis['relevant_matches']}")
        if 'irrelevant_matches' in analysis and analysis['irrelevant_matches']:
            print(f"   Irrelevant patterns: {analysis['irrelevant_matches']}")
        print()

if __name__ == "__main__":
    test_filter()