# Blockchain-Based Verified Reviews System - Beyond OTA Standards
import hashlib
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

class ReviewVerificationStatus(Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    FLAGGED = "flagged"
    DISPUTED = "disputed"

class ReviewType(Enum):
    STAY_VERIFIED = "stay_verified"  # Actual guest who stayed
    BOOKING_VERIFIED = "booking_verified"  # Verified booking
    BLOCKCHAIN_VERIFIED = "blockchain_verified"  # Blockchain verified
    COMMUNITY_VERIFIED = "community_verified"  # Community verified

@dataclass
class BlockchainReview:
    review_id: str
    booking_reference: str
    property_id: int
    guest_user_id: int
    rating: int  # 1-5
    title: str
    content: str
    review_type: ReviewType
    verification_status: ReviewVerificationStatus
    blockchain_hash: str
    digital_signature: str
    timestamp: datetime
    ip_address: str
    device_fingerprint: str
    supporting_evidence: List[Dict]
    verification_score: float  # 0-1
    authenticity_score: float  # 0-1

@dataclass
class VerificationProof:
    proof_type: str
    blockchain_tx_hash: str
    verification_timestamp: datetime
    verified_by: str
    evidence_chain: List[Dict]
    confidence_score: float

class BlockchainReviewsService:
    """
    Revolutionary blockchain-based review system that ensures authenticity
    and prevents fake reviews better than any current OTA
    """
    
    def __init__(self):
        self.blockchain_client = BlockchainClient()
        self.crypto_service = CryptoService()
        self.verification_engine = ReviewVerificationEngine()
        self.review_cache = {}
    
    def create_verified_review(self, booking_reference: str, user_id: int, rating: int,
                             title: str, content: str, ip_address: str, 
                             device_fingerprint: str, photos: List[str] = None) -> BlockchainReview:
        """
        Create a blockchain-verified review with multiple layers of verification
        """
        
        # Verify booking authenticity
        booking_verification = self._verify_booking_authenticity(booking_reference, user_id)
        
        if not booking_verification["is_authentic"]:
            raise ValueError("Invalid booking reference or user mismatch")
        
        # Create review object
        review = BlockchainReview(
            review_id=self._generate_review_id(),
            booking_reference=booking_reference,
            property_id=booking_verification["property_id"],
            guest_user_id=user_id,
            rating=rating,
            title=title,
            content=content,
            review_type=ReviewType.STAY_VERIFIED,
            verification_status=ReviewVerificationStatus.PENDING,
            blockchain_hash="",
            digital_signature="",
            timestamp=datetime.now(),
            ip_address=ip_address,
            device_fingerprint=device_fingerprint,
            supporting_evidence=[],
            verification_score=0.0,
            authenticity_score=0.0
        )
        
        # Generate supporting evidence
        evidence = self._generate_supporting_evidence(review, booking_verification, photos or [])
        review.supporting_evidence = evidence
        
        # Calculate verification scores
        verification_score = self._calculate_verification_score(review, evidence)
        authenticity_score = self._calculate_authenticity_score(review, evidence)
        
        review.verification_score = verification_score
        review.authenticity_score = authenticity_score
        
        # Generate blockchain hash
        review.blockchain_hash = self._generate_blockchain_hash(review)
        
        # Generate digital signature
        review.digital_signature = self._generate_digital_signature(review)
        
        # Submit to blockchain
        blockchain_tx = self._submit_to_blockchain(review)
        
        # Update verification status
        if verification_score > 0.8 and authenticity_score > 0.8:
            review.verification_status = ReviewVerificationStatus.VERIFIED
        elif verification_score > 0.6:
            review.verification_status = ReviewVerificationStatus.FLAGGED
        else:
            review.verification_status = ReviewVerificationStatus.REJECTED
        
        # Store review
        self._store_review(review)
        
        # Notify stakeholders
        self._notify_review_submission(review)
        
        return review
    
    def verify_review_authenticity(self, review_id: str) -> VerificationProof:
        """
        Verify review authenticity using blockchain and multiple verification layers
        """
        
        review = self._get_review(review_id)
        if not review:
            raise ValueError("Review not found")
        
        # Verify blockchain hash
        hash_verification = self._verify_blockchain_hash(review)
        
        # Verify digital signature
        signature_verification = self._verify_digital_signature(review)
        
        # Verify supporting evidence
        evidence_verification = self._verify_supporting_evidence(review)
        
        # Cross-reference with booking data
        booking_verification = self._cross_reference_booking(review)
        
        # Analyze content authenticity
        content_analysis = self._analyze_content_authenticity(review)
        
        # Check for manipulation patterns
        manipulation_check = self._check_manipulation_patterns(review)
        
        # Calculate overall verification score
        verification_scores = [
            hash_verification["score"],
            signature_verification["score"],
            evidence_verification["score"],
            booking_verification["score"],
            content_analysis["score"],
            manipulation_check["score"]
        ]
        
        overall_score = sum(verification_scores) / len(verification_scores)
        
        # Generate verification proof
        proof = VerificationProof(
            proof_type="blockchain_verification",
            blockchain_tx_hash=review.blockchain_hash,
            verification_timestamp=datetime.now(),
            verified_by="blockchain_reviews_system",
            evidence_chain=[
                {"type": "hash_verification", "data": hash_verification},
                {"type": "signature_verification", "data": signature_verification},
                {"type": "evidence_verification", "data": evidence_verification},
                {"type": "booking_verification", "data": booking_verification},
                {"type": "content_analysis", "data": content_analysis},
                {"type": "manipulation_check", "data": manipulation_check}
            ],
            confidence_score=overall_score
        )
        
        return proof
    
    def detect_fake_reviews(self, property_id: int, limit: int = 100) -> List[Dict]:
        """
        Detect potentially fake reviews using AI and blockchain analysis
        """
        
        # Get reviews for property
        reviews = self._get_property_reviews(property_id, limit)
        
        suspicious_reviews = []
        
        for review in reviews:
            # Analyze review patterns
            pattern_analysis = self._analyze_review_patterns(review)
            
            # Check blockchain consistency
            blockchain_analysis = self._check_blockchain_consistency(review)
            
            # Analyze user behavior
            behavior_analysis = self._analyze_user_behavior(review.guest_user_id)
            
            # Check content similarity
            similarity_analysis = self._check_content_similarity(review, reviews)
            
            # Analyze timing patterns
            timing_analysis = self._analyze_timing_patterns(review, reviews)
            
            # Calculate fake probability
            fake_probability = self._calculate_fake_probability([
                pattern_analysis,
                blockchain_analysis,
                behavior_analysis,
                similarity_analysis,
                timing_analysis
            ])
            
            if fake_probability > 0.7:
                suspicious_reviews.append({
                    "review_id": review.review_id,
                    "fake_probability": fake_probability,
                    "reasons": self._generate_suspicion_reasons([
                        pattern_analysis,
                        blockchain_analysis,
                        behavior_analysis,
                        similarity_analysis,
                        timing_analysis
                    ]),
                    "recommendation": "remove" if fake_probability > 0.9 else "investigate"
                })
        
        return suspicious_reviews
    
    def _verify_booking_authenticity(self, booking_reference: str, user_id: int) -> Dict:
        """Verify booking authenticity against booking system"""
        
        # Query booking system
        from app.accommodation.services.booking_service import BookingService
        
        booking = BookingService.get_booking_by_reference(booking_reference)
        
        if not booking:
            return {"is_authentic": False, "reason": "Booking not found"}
        
        if booking.guest_user_id != user_id:
            return {"is_authentic": False, "reason": "User mismatch"}
        
        if booking.status != "confirmed":
            return {"is_authentic": False, "reason": "Booking not confirmed"}
        
        # Check if stay is completed or in progress
        today = date.today()
        if booking.check_out > today:
            return {"is_authentic": False, "reason": "Stay not completed"}
        
        return {
            "is_authentic": True,
            "property_id": booking.property_id,
            "check_in": booking.check_in,
            "check_out": booking.check_out,
            "total_amount": booking.total_amount
        }
    
    def _generate_supporting_evidence(self, review: BlockchainReview, 
                                     booking_verification: Dict, photos: List[str]) -> List[Dict]:
        """Generate supporting evidence for review verification"""
        
        evidence = []
        
        # Booking evidence
        evidence.append({
            "type": "booking_confirmation",
            "data": {
                "booking_reference": review.booking_reference,
                "property_id": review.property_id,
                "stay_dates": {
                    "check_in": booking_verification["check_in"],
                    "check_out": booking_verification["check_out"]
                },
                "total_amount": booking_verification["total_amount"]
            },
            "timestamp": datetime.now(),
            "verification_method": "booking_system"
        })
        
        # IP geolocation evidence
        ip_evidence = self._verify_ip_geolocation(review.ip_address, review.property_id)
        evidence.append(ip_evidence)
        
        # Device fingerprint evidence
        device_evidence = self._verify_device_fingerprint(review.device_fingerprint, review.guest_user_id)
        evidence.append(device_evidence)
        
        # Photo evidence (if provided)
        if photos:
            photo_evidence = self._verify_photo_evidence(photos, review.property_id)
            evidence.append(photo_evidence)
        
        # Behavioral evidence
        behavior_evidence = self._analyze_user_behavior(review.guest_user_id)
        evidence.append(behavior_evidence)
        
        return evidence
    
    def _calculate_verification_score(self, review: BlockchainReview, evidence: List[Dict]) -> float:
        """Calculate overall verification score"""
        
        scores = []
        
        # Booking verification score
        booking_score = 1.0  # Already verified at this point
        scores.append(booking_score)
        
        # Evidence scores
        for evidence_item in evidence:
            if evidence_item.get("verification_score"):
                scores.append(evidence_item["verification_score"])
        
        # Content analysis score
        content_score = self._analyze_content_legitimacy(review.content)
        scores.append(content_score)
        
        # Rating consistency score
        rating_score = self._check_rating_consistency(review.rating, review.content)
        scores.append(rating_score)
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _calculate_authenticity_score(self, review: BlockchainReview, evidence: List[Dict]) -> float:
        """Calculate authenticity score"""
        
        scores = []
        
        # User history authenticity
        user_score = self._calculate_user_authenticity_score(review.guest_user_id)
        scores.append(user_score)
        
        # Content authenticity
        content_score = self._analyze_content_authenticity(review.content)
        scores.append(content_score)
        
        # Timing authenticity
        timing_score = self._analyze_timing_authenticity(review)
        scores.append(timing_score)
        
        # Evidence authenticity
        evidence_score = self._analyze_evidence_authenticity(evidence)
        scores.append(evidence_score)
        
        return sum(scores) / len(scores) if scores else 0.0
    
    def _generate_blockchain_hash(self, review: BlockchainReview) -> str:
        """Generate unique blockchain hash for review"""
        
        # Create review data string
        review_data = {
            "review_id": review.review_id,
            "booking_reference": review.booking_reference,
            "property_id": review.property_id,
            "guest_user_id": review.guest_user_id,
            "rating": review.rating,
            "title": review.title,
            "content": review.content,
            "timestamp": review.timestamp.isoformat(),
            "supporting_evidence": review.supporting_evidence
        }
        
        # Generate hash
        data_string = json.dumps(review_data, sort_keys=True)
        hash_object = hashlib.sha256(data_string.encode())
        return hash_object.hexdigest()
    
    def _generate_digital_signature(self, review: BlockchainReview) -> str:
        """Generate digital signature for review"""
        
        # Get user's private key (in production, this would be securely stored)
        private_key = self.crypto_service.get_user_private_key(review.guest_user_id)
        
        # Sign the review hash
        signature = private_key.sign(
            review.blockchain_hash.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return signature.hex()
    
    def _submit_to_blockchain(self, review: BlockchainReview) -> str:
        """Submit review to blockchain"""
        
        # Create blockchain transaction
        transaction = {
            "type": "review_submission",
            "review_hash": review.blockchain_hash,
            "digital_signature": review.digital_signature,
            "timestamp": review.timestamp.isoformat(),
            "metadata": {
                "review_id": review.review_id,
                "property_id": review.property_id,
                "guest_user_id": review.guest_user_id,
                "rating": review.rating
            }
        }
        
        # Submit to blockchain
        tx_hash = self.blockchain_client.submit_transaction(transaction)
        
        return tx_hash
    
    # Helper methods (simplified for demo)
    def _generate_review_id(self) -> str:
        """Generate unique review ID"""
        return f"rev_{int(datetime.now().timestamp())}_{hashlib.random_int(1000, 9999)}"
    
    def _verify_ip_geolocation(self, ip_address: str, property_id: int) -> Dict:
        """Verify IP geolocation matches property location"""
        return {
            "type": "ip_geolocation",
            "verification_score": 0.8,
            "data": {"ip_location": "same_city", "property_location": "same_city"}
        }
    
    def _verify_device_fingerprint(self, device_fingerprint: str, user_id: int) -> Dict:
        """Verify device fingerprint matches user history"""
        return {
            "type": "device_fingerprint",
            "verification_score": 0.9,
            "data": {"device_match": True, "user_history_match": True}
        }
    
    def _verify_photo_evidence(self, photos: List[str], property_id: int) -> Dict:
        """Verify photo evidence authenticity"""
        return {
            "type": "photo_evidence",
            "verification_score": 0.7,
            "data": {"photo_count": len(photos), "property_match": True}
        }
    
    def _analyze_user_behavior(self, user_id: int) -> Dict:
        """Analyze user behavior patterns"""
        return {
            "type": "user_behavior",
            "verification_score": 0.8,
            "data": {"review_frequency": "normal", "account_age": "mature"}
        }
    
    def _analyze_content_legitimacy(self, content: str) -> float:
        """Analyze content legitimacy"""
        # Simple content analysis
        if len(content) < 10:
            return 0.3
        elif len(content) < 50:
            return 0.6
        else:
            return 0.9
    
    def _check_rating_consistency(self, rating: int, content: str) -> float:
        """Check rating consistency with content"""
        # Simple sentiment analysis
        positive_words = ["great", "excellent", "amazing", "wonderful", "perfect"]
        negative_words = ["bad", "terrible", "awful", "horrible", "disappointing"]
        
        content_lower = content.lower()
        positive_count = sum(1 for word in positive_words if word in content_lower)
        negative_count = sum(1 for word in negative_words if word in content_lower)
        
        if rating >= 4 and positive_count > negative_count:
            return 0.9
        elif rating <= 2 and negative_count > positive_count:
            return 0.9
        elif rating == 3:
            return 0.7
        else:
            return 0.4
    
    def _calculate_user_authenticity_score(self, user_id: int) -> float:
        """Calculate user authenticity score"""
        return 0.8  # Mock data
    
    def _analyze_content_authenticity(self, content: str) -> float:
        """Analyze content authenticity"""
        return 0.8  # Mock data
    
    def _analyze_timing_authenticity(self, review: BlockchainReview) -> float:
        """Analyze timing authenticity"""
        return 0.9  # Mock data
    
    def _analyze_evidence_authenticity(self, evidence: List[Dict]) -> float:
        """Analyze evidence authenticity"""
        scores = [e.get("verification_score", 0.5) for e in evidence]
        return sum(scores) / len(scores) if scores else 0.0
    
    def _store_review(self, review: BlockchainReview):
        """Store review in database"""
        self.review_cache[review.review_id] = review
        logger.info(f"Stored review {review.review_id}")
    
    def _notify_review_submission(self, review: BlockchainReview):
        """Notify stakeholders about review submission"""
        logger.info(f"Notified review submission: {review.review_id}")
    
    def _get_review(self, review_id: str) -> Optional[BlockchainReview]:
        """Get review by ID"""
        return self.review_cache.get(review_id)
    
    def _get_property_reviews(self, property_id: int, limit: int) -> List[BlockchainReview]:
        """Get reviews for property"""
        return [r for r in self.review_cache.values() if r.property_id == property_id][:limit]
    
    def _analyze_review_patterns(self, review: BlockchainReview) -> Dict:
        """Analyze review patterns"""
        return {"score": 0.8, "patterns": "normal"}
    
    def _check_blockchain_consistency(self, review: BlockchainReview) -> Dict:
        """Check blockchain consistency"""
        return {"score": 0.9, "consistent": True}
    
    def _analyze_user_behavior(self, user_id: int) -> Dict:
        """Analyze user behavior"""
        return {"score": 0.8, "behavior": "normal"}
    
    def _check_content_similarity(self, review: BlockchainReview, all_reviews: List[BlockchainReview]) -> Dict:
        """Check content similarity with other reviews"""
        return {"score": 0.7, "similarity": "low"}
    
    def _analyze_timing_patterns(self, review: BlockchainReview, all_reviews: List[BlockchainReview]) -> Dict:
        """Analyze timing patterns"""
        return {"score": 0.9, "timing": "normal"}
    
    def _calculate_fake_probability(self, analyses: List[Dict]) -> float:
        """Calculate probability of review being fake"""
        scores = [a.get("score", 0.5) for a in analyses]
        return 1 - (sum(scores) / len(scores)) if scores else 0.5
    
    def _generate_suspicion_reasons(self, analyses: List[Dict]) -> List[str]:
        """Generate reasons for suspicion"""
        reasons = []
        for analysis in analyses:
            if analysis.get("score", 1.0) < 0.7:
                reasons.append(f"Suspicious {analysis.get('type', 'pattern')}")
        return reasons


class BlockchainClient:
    """Blockchain client for review verification"""
    
    def submit_transaction(self, transaction: Dict) -> str:
        """Submit transaction to blockchain"""
        # Mock implementation
        tx_hash = hashlib.sha256(json.dumps(transaction).encode()).hexdigest()
        logger.info(f"Submitted transaction to blockchain: {tx_hash}")
        return tx_hash


class CryptoService:
    """Cryptographic service for digital signatures"""
    
    def get_user_private_key(self, user_id: int):
        """Get user's private key for signing"""
        # In production, this would securely retrieve user's private key
        return rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )


class ReviewVerificationEngine:
    """Advanced review verification engine"""
    
    def verify_review(self, review: BlockchainReview) -> Dict:
        """Comprehensive review verification"""
        return {
            "is_verified": True,
            "confidence": 0.9,
            "verification_method": "multi_layer"
        }
