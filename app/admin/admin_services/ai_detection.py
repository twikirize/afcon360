"""
Enterprise AI-Powered Content Detection Service

Implements advanced content analysis with multiple AI models for
Facebook/Airbnb/PayPal/Alibaba scale moderation.
"""

import hashlib
import re
import json
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from flask import current_app

@dataclass
class ContentAnalysis:
    """Content analysis result from AI detection"""
    risk_score: float  # 0-100
    category: str
    severity: str
    confidence: float
    detection_model: str
    reasons: List[str]
    content_hash: str
    processing_time_ms: int

class AIDetectionService:
    """Enterprise AI content detection service"""
    
    def __init__(self):
        self.models = {
            'text_classifier': TextClassificationModel(),
            'image_analyzer': ImageAnalysisModel(),
            'behavior_detector': BehaviorAnalysisModel(),
            'spam_detector': SpamDetectionModel(),
            'toxicity_analyzer': ToxicityAnalysisModel()
        }
        
    def analyze_content(self, content: str, content_type: str = 'text', 
                       metadata: Dict = None) -> ContentAnalysis:
        """
        Perform comprehensive AI analysis on content
        
        Args:
            content: The content to analyze
            content_type: Type of content (text, image, video, etc.)
            metadata: Additional context metadata
            
        Returns:
            ContentAnalysis with risk assessment
        """
        start_time = datetime.now()
        
        # Generate content hash for deduplication
        content_hash = self._generate_content_hash(content)
        
        # Initialize analysis results
        analyses = []
        
        # Run relevant AI models based on content type
        if content_type == 'text':
            analyses.extend([
                self.models['text_classifier'].analyze(content),
                self.models['spam_detector'].analyze(content),
                self.models['toxicity_analyzer'].analyze(content)
            ])
        elif content_type == 'image':
            analyses.append(self.models['image_analyzer'].analyze(content))
        
        # Always run behavior analysis
        if metadata:
            analyses.append(self.models['behavior_detector'].analyze(metadata))
        
        # Aggregate results
        aggregated = self._aggregate_analyses(analyses)
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return ContentAnalysis(
            risk_score=aggregated['risk_score'],
            category=aggregated['category'],
            severity=aggregated['severity'],
            confidence=aggregated['confidence'],
            detection_model='enterprise_ensemble_v1',
            reasons=aggregated['reasons'],
            content_hash=content_hash,
            processing_time_ms=processing_time
        )
    
    def _generate_content_hash(self, content: str) -> str:
        """Generate SHA-256 hash for content deduplication"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def _aggregate_analyses(self, analyses: List[Dict]) -> Dict:
        """Aggregate multiple AI model analyses"""
        if not analyses:
            return {
                'risk_score': 0.0,
                'category': 'safe',
                'severity': 'low',
                'confidence': 0.0,
                'reasons': []
            }
        
        # Weighted scoring based on model reliability
        weights = {
            'text_classifier': 0.3,
            'image_analyzer': 0.25,
            'behavior_detector': 0.2,
            'spam_detector': 0.15,
            'toxicity_analyzer': 0.1
        }
        
        weighted_scores = []
        all_reasons = []
        
        for analysis in analyses:
            model_name = analysis.get('model', 'unknown')
            weight = weights.get(model_name, 0.1)
            weighted_score = analysis['risk_score'] * weight
            weighted_scores.append(weighted_score)
            all_reasons.extend(analysis.get('reasons', []))
        
        # Calculate final risk score
        final_risk_score = min(100.0, sum(weighted_scores))
        
        # Determine category and severity based on score
        if final_risk_score >= 80:
            category = 'harmful'
            severity = 'critical'
        elif final_risk_score >= 60:
            category = 'suspicious'
            severity = 'high'
        elif final_risk_score >= 40:
            category = 'questionable'
            severity = 'medium'
        elif final_risk_score >= 20:
            category = 'borderline'
            severity = 'normal'
        else:
            category = 'safe'
            severity = 'low'
        
        # Calculate average confidence
        avg_confidence = sum(a.get('confidence', 0) for a in analyses) / len(analyses)
        
        return {
            'risk_score': final_risk_score,
            'category': category,
            'severity': severity,
            'confidence': avg_confidence,
            'reasons': list(set(all_reasons))  # Remove duplicates
        }


class TextClassificationModel:
    """AI model for text content classification"""
    
    def analyze(self, text: str) -> Dict:
        """Analyze text content for policy violations"""
        risk_score = 0.0
        reasons = []
        
        # Define policy violation patterns
        patterns = {
            'hate_speech': [
                r'\b(hate|kill|die|death|violent|violence)\b',
                r'\b(racist|sexist|homophobic|transphobic)\b'
            ],
            'spam': [
                r'(click here|buy now|limited time|act fast)',
                r'(\$\d+|\d+\$|free money|winner|congratulations)'
            ],
            'inappropriate': [
                r'\b(nude|naked|sex|porn|adult)\b',
                r'\b(drug|drugs|cocaine|heroin|marijuana)\b'
            ],
            'harassment': [
                r'\b(stupid|idiot|moron|loser|pathetic)\b',
                r'\b(threat|threatening|blackmail|extortion)\b'
            ]
        }
        
        # Check patterns
        for category, pattern_list in patterns.items():
            for pattern in pattern_list:
                if re.search(pattern, text, re.IGNORECASE):
                    risk_score += 15
                    reasons.append(f"Detected {category.replace('_', ' ')} content")
        
        # Check for excessive capitalization (shouting)
        if len(text) > 10 and text.upper() == text:
            risk_score += 10
            reasons.append("Excessive capitalization detected")
        
        # Check for repeated characters
        if re.search(r'(.)\1{3,}', text):
            risk_score += 5
            reasons.append("Excessive character repetition")
        
        # Cap at 100
        risk_score = min(100.0, risk_score)
        
        return {
            'model': 'text_classifier',
            'risk_score': risk_score,
            'confidence': 0.85,
            'reasons': reasons
        }


class ImageAnalysisModel:
    """AI model for image content analysis"""
    
    def analyze(self, image_data: str) -> Dict:
        """Analyze image content for violations"""
        # Placeholder for actual image analysis
        # In production, this would integrate with computer vision APIs
        
        risk_score = 0.0
        reasons = []
        
        # Simulate image analysis based on metadata
        if isinstance(image_data, str) and len(image_data) > 1000:
            # Large image might contain complex content
            risk_score += 10
            reasons.append("Complex image content detected")
        
        return {
            'model': 'image_analyzer',
            'risk_score': risk_score,
            'confidence': 0.75,
            'reasons': reasons
        }


class BehaviorAnalysisModel:
    """AI model for user behavior analysis"""
    
    def analyze(self, metadata: Dict) -> Dict:
        """Analyze user behavior patterns"""
        risk_score = 0.0
        reasons = []
        
        # Check for rapid posting
        if metadata.get('posts_per_hour', 0) > 10:
            risk_score += 20
            reasons.append("High posting frequency detected")
        
        # Check for new account spam
        if metadata.get('account_age_days', 0) < 7:
            risk_score += 15
            reasons.append("New account with high activity")
        
        # Check for suspicious IP patterns
        if metadata.get('ip_risk_score', 0) > 50:
            risk_score += 25
            reasons.append("Suspicious IP address detected")
        
        # Check for account age vs content ratio
        account_age = metadata.get('account_age_days', 0)
        content_count = metadata.get('total_content', 0)
        if account_age > 0 and content_count / account_age > 50:
            risk_score += 15
            reasons.append("Unusual content-to-account-age ratio")
        
        return {
            'model': 'behavior_detector',
            'risk_score': risk_score,
            'confidence': 0.80,
            'reasons': reasons
        }


class SpamDetectionModel:
    """AI model for spam detection"""
    
    def analyze(self, text: str) -> Dict:
        """Detect spam patterns in text"""
        risk_score = 0.0
        reasons = []
        
        # Spam indicators
        spam_indicators = [
            (r'http[s]?://\S+', 15, "URL detected in content"),
            (r'\b\d{1,3}[-.]?\d{1,3}[-.]?\d{1,3}[-.]?\d{1,3}\b', 10, "IP address detected"),
            (r'\b[A-Z]{3,}\b', 5, "Excessive acronyms"),
            (r'\+\d{1,3}[-.\s]?\d{3,4}[-.\s]?\d{3,4}[-.\s]?\d{4}', 10, "Phone number detected"),
            (r'[!]{3,}', 5, "Excessive exclamation marks"),
        ]
        
        for pattern, score, reason in spam_indicators:
            if re.search(pattern, text):
                risk_score += score
                reasons.append(reason)
        
        return {
            'model': 'spam_detector',
            'risk_score': risk_score,
            'confidence': 0.90,
            'reasons': reasons
        }


class ToxicityAnalysisModel:
    """AI model for toxicity detection"""
    
    def analyze(self, text: str) -> Dict:
        """Detect toxic content patterns"""
        risk_score = 0.0
        reasons = []
        
        # Toxicity indicators
        toxicity_patterns = {
            'profanity': [
                r'\b(damn|hell|shit|fuck|bitch|ass|bastard)\b',
                r'\b(crap|suck|sucks|stupid|dumb|idiot)\b'
            ],
            'threats': [
                r'\b(kill|murder|hurt|harm|attack|beat)\b',
                r'\b(threat|threatening|dangerous|violent)\b'
            ],
            'harassment': [
                r'\b(stalker|creep|weirdo|freak|loser)\b',
                r'\b(ugly|fat|stupid|retarded|dumb)\b'
            ]
        }
        
        for category, pattern_list in toxicity_patterns.items():
            matches = 0
            for pattern in pattern_list:
                matches += len(re.findall(pattern, text, re.IGNORECASE))
            
            if matches > 0:
                score = min(30, matches * 10)
                risk_score += score
                reasons.append(f"{category.title()} content detected ({matches} instances)")
        
        return {
            'model': 'toxicity_analyzer',
            'risk_score': risk_score,
            'confidence': 0.88,
            'reasons': reasons
        }


# Auto-moderation service
class AutoModerationService:
    """Service for automatic content moderation actions"""
    
    def __init__(self, ai_service: AIDetectionService):
        self.ai_service = ai_service
        self.auto_action_thresholds = {
            'critical': 90,    # Auto-remove
            'high': 75,        # Auto-hide and flag
            'medium': 60,     # Auto-flag for review
            'low': 40          # Monitor only
        }
    
    def should_auto_moderate(self, analysis: ContentAnalysis) -> Tuple[bool, str]:
        """
        Determine if content should be auto-moderated
        
        Returns:
            Tuple of (should_moderate, action_type)
        """
        if analysis.risk_score >= self.auto_action_thresholds['critical']:
            return True, 'auto_remove'
        elif analysis.risk_score >= self.auto_action_thresholds['high']:
            return True, 'auto_hide'
        elif analysis.risk_score >= self.auto_action_thresholds['medium']:
            return True, 'auto_flag'
        else:
            return False, 'monitor'
    
    def create_auto_flag(self, entity_type: str, entity_id: int, 
                        analysis: ContentAnalysis, user_id: int) -> Dict:
        """Create an automatically generated content flag"""
        should_moderate, action = self.should_auto_moderate(analysis)
        
        flag_data = {
            'entity_type': entity_type,
            'entity_id': entity_id,
            'content_hash': analysis.content_hash,
            'content_type': 'auto_detected',
            'risk_score': analysis.risk_score,
            'category': analysis.category,
            'severity': analysis.severity,
            'reason': f"AI Detection: {', '.join(analysis.reasons)}",
            'priority': 'critical' if analysis.risk_score >= 80 else 'high',
            'status': 'auto_processed' if should_moderate else 'open',
            'detection_source': 'ai',
            'ai_confidence': analysis.confidence,
            'detection_model': analysis.detection_model,
            'auto_processed': should_moderate,
            'flagged_by': user_id,  # System user ID
            'extra_data': {
                'auto_action': action,
                'processing_time_ms': analysis.processing_time_ms,
                'detection_reasons': analysis.reasons
            }
        }
        
        return flag_data
