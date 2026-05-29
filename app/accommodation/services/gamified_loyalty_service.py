# Gamified Loyalty and Rewards System - Beyond OTA Standards
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from enum import Enum
import logging
import uuid

logger = logging.getLogger(__name__)

class LoyaltyTier(Enum):
    BRONZE = "bronze"      # 0-999 points
    SILVER = "silver"      # 1,000-4,999 points
    GOLD = "gold"          # 5,000-14,999 points
    PLATINUM = "platinum"  # 15,000-49,999 points
    DIAMOND = "diamond"    # 50,000+ points

class AchievementType(Enum):
    BOOKING_MILESTONE = "booking_milestone"
    EXPLORER = "explorer"
    REVIEWER = "reviewer"
    EARLY_BIRD = "early_bird"
    LOYALTY = "loyalty"
    SOCIAL = "social"
    SEASONAL = "seasonal"
    BONUS = "bonus"

class RewardType(Enum):
    DISCOUNT = "discount"
    FREE_NIGHT = "free_night"
    UPGRADE = "upgrade"
    CASHBACK = "cashback"
    EXPERIENCE = "experience"
    PARTNER_OFFER = "partner_offer"

@dataclass
class Achievement:
    id: str
    name: str
    description: str
    type: AchievementType
    points: int
    badge_url: str
    requirements: Dict
    progress: float  # 0-1
    unlocked_at: Optional[datetime]
    rarity: str  # "common", "rare", "epic", "legendary"

@dataclass
class LoyaltyStatus:
    user_id: int
    current_tier: LoyaltyTier
    total_points: int
    tier_points: int  # Points in current tier
    next_tier_points: int
    tier_progress: float  # 0-1
    streak_days: int
    total_bookings: int
    total_spend: float
    achievements: List[Achievement]
    badges: List[str]
    power_ups: List[Dict]

@dataclass
class Reward:
    id: str
    name: str
    description: str
    type: RewardType
    value: Union[float, Dict]
    points_cost: int
    tier_requirement: LoyaltyTier
    expiration_date: Optional[date]
    usage_limit: Optional[int]
    terms: str

class GamifiedLoyaltyService:
    """
    Revolutionary gamified loyalty system that creates addictive engagement
    and retention beyond traditional OTA loyalty programs
    """
    
    def __init__(self):
        self.achievement_engine = AchievementEngine()
        self.reward_engine = RewardEngine()
        self.gamification_engine = GamificationEngine()
        self.social_engine = SocialEngine()
        self.leaderboard_manager = LeaderboardManager()
    
    def get_user_loyalty_status(self, user_id: int) -> LoyaltyStatus:
        """Get comprehensive user loyalty status"""
        
        # Calculate user statistics
        user_stats = self._calculate_user_statistics(user_id)
        
        # Determine current tier
        current_tier = self._determine_loyalty_tier(user_stats["total_points"])
        
        # Calculate tier progress
        tier_info = self._get_tier_info(current_tier)
        tier_progress = self._calculate_tier_progress(user_stats["total_points"], current_tier)
        
        # Get user achievements
        achievements = self._get_user_achievements(user_id)
        
        # Get unlocked badges
        badges = self._get_user_badges(user_id)
        
        # Get active power-ups
        power_ups = self._get_user_power_ups(user_id)
        
        return LoyaltyStatus(
            user_id=user_id,
            current_tier=current_tier,
            total_points=user_stats["total_points"],
            tier_points=user_stats["tier_points"],
            next_tier_points=tier_info["next_tier_points"],
            tier_progress=tier_progress,
            streak_days=user_stats["streak_days"],
            total_bookings=user_stats["total_bookings"],
            total_spend=user_stats["total_spend"],
            achievements=achievements,
            badges=badges,
            power_ups=power_ups
        )
    
    def process_booking_activity(self, user_id: int, booking_data: Dict) -> Dict:
        """Process booking and award loyalty points"""
        
        # Calculate base points
        base_points = self._calculate_base_points(booking_data)
        
        # Apply multipliers
        multipliers = self._get_active_multipliers(user_id)
        final_points = int(base_points * multipliers["total"])
        
        # Check for achievements
        new_achievements = self._check_booking_achievements(user_id, booking_data)
        
        # Update streak
        streak_bonus = self._update_booking_streak(user_id, booking_data["check_in"])
        
        # Award bonus points
        bonus_points = self._calculate_bonus_points(user_id, booking_data, new_achievements, streak_bonus)
        
        total_points = final_points + bonus_points
        
        # Update user points
        self._update_user_points(user_id, total_points)
        
        # Create gamification notifications
        notifications = self._create_loyalty_notifications(user_id, total_points, new_achievements, streak_bonus)
        
        return {
            "points_awarded": total_points,
            "base_points": base_points,
            "multipliers": multipliers,
            "bonus_points": bonus_points,
            "new_achievements": [a.name for a in new_achievements],
            "streak_bonus": streak_bonus,
            "notifications": notifications
        }
    
    def get_available_rewards(self, user_id: int) -> List[Reward]:
        """Get rewards available to user based on tier"""
        
        user_status = self.get_user_loyalty_status(user_id)
        
        # Get all rewards
        all_rewards = self.reward_engine.get_all_rewards()
        
        # Filter by user tier
        available_rewards = []
        for reward in all_rewards:
            if self._is_tier_eligible(user_status.current_tier, reward.tier_requirement):
                if self._can_afford_reward(user_status.total_points, reward.points_cost):
                    available_rewards.append(reward)
        
        # Sort by relevance and value
        available_rewards.sort(key=lambda r: self._calculate_reward_relevance(r, user_status), reverse=True)
        
        return available_rewards
    
    def redeem_reward(self, user_id: int, reward_id: str) -> Dict:
        """Redeem reward for user"""
        
        user_status = self.get_user_loyalty_status(user_id)
        reward = self.reward_engine.get_reward(reward_id)
        
        if not reward:
            return {"success": False, "error": "Reward not found"}
        
        # Check eligibility
        if not self._is_tier_eligible(user_status.current_tier, reward.tier_requirement):
            return {"success": False, "error": "Tier requirement not met"}
        
        if not self._can_afford_reward(user_status.total_points, reward.points_cost):
            return {"success": False, "error": "Insufficient points"}
        
        # Process redemption
        redemption_result = self._process_reward_redemption(user_id, reward)
        
        if redemption_result["success"]:
            # Deduct points
            self._update_user_points(user_id, -reward.points_cost)
            
            # Create redemption record
            self._create_redemption_record(user_id, reward_id, reward.points_cost)
            
            # Send notification
            self._send_reward_notification(user_id, reward)
            
            # Check for redemption achievements
            self._check_redemption_achievements(user_id, reward)
        
        return redemption_result
    
    def get_leaderboard(self, timeframe: str = "monthly", category: str = "points") -> List[Dict]:
        """Get leaderboard rankings"""
        
        return self.leaderboard_manager.get_leaderboard(timeframe, category)
    
    def _calculate_user_statistics(self, user_id: int) -> Dict:
        """Calculate comprehensive user statistics"""
        
        # Get booking history
        booking_history = self._get_user_booking_history(user_id)
        
        # Calculate total points
        total_points = sum(b.get("points_earned", 0) for b in booking_history)
        
        # Calculate tier points (points in current tier)
        current_tier = self._determine_loyalty_tier(total_points)
        tier_info = self._get_tier_info(current_tier)
        tier_points = total_points - tier_info["tier_start_points"]
        
        # Calculate streak days
        streak_days = self._calculate_booking_streak(user_id)
        
        # Calculate total bookings and spend
        total_bookings = len(booking_history)
        total_spend = sum(b.get("total_amount", 0) for b in booking_history)
        
        return {
            "total_points": total_points,
            "tier_points": tier_points,
            "streak_days": streak_days,
            "total_bookings": total_bookings,
            "total_spend": total_spend
        }
    
    def _determine_loyalty_tier(self, total_points: int) -> LoyaltyTier:
        """Determine user's loyalty tier based on points"""
        
        if total_points >= 50000:
            return LoyaltyTier.DIAMOND
        elif total_points >= 15000:
            return LoyaltyTier.PLATINUM
        elif total_points >= 5000:
            return LoyaltyTier.GOLD
        elif total_points >= 1000:
            return LoyaltyTier.SILVER
        else:
            return LoyaltyTier.BRONZE
    
    def _get_tier_info(self, tier: LoyaltyTier) -> Dict:
        """Get tier information including point ranges"""
        
        tier_ranges = {
            LoyaltyTier.BRONZE: {"start": 0, "end": 999, "next_tier": 1000},
            LoyaltyTier.SILVER: {"start": 1000, "end": 4999, "next_tier": 5000},
            LoyaltyTier.GOLD: {"start": 5000, "end": 14999, "next_tier": 15000},
            LoyaltyTier.PLATINUM: {"start": 15000, "end": 49999, "next_tier": 50000},
            LoyaltyTier.DIAMOND: {"start": 50000, "end": float("inf"), "next_tier": None}
        }
        
        range_info = tier_ranges[tier]
        
        return {
            "tier_start_points": range_info["start"],
            "tier_end_points": range_info["end"],
            "next_tier_points": range_info["next_tier"]
        }
    
    def _calculate_tier_progress(self, total_points: int, current_tier: LoyaltyTier) -> float:
        """Calculate progress toward next tier"""
        
        if current_tier == LoyaltyTier.DIAMOND:
            return 1.0  # Max tier
        
        tier_info = self._get_tier_info(current_tier)
        tier_start = tier_info["tier_start_points"]
        next_tier_points = tier_info["next_tier_points"]
        
        if next_tier_points is None:
            return 1.0
        
        progress = (total_points - tier_start) / (next_tier_points - tier_start)
        return min(progress, 1.0)
    
    def _calculate_base_points(self, booking_data: Dict) -> int:
        """Calculate base loyalty points for booking"""
        
        # Points per dollar spent
        spend_points = int(booking_data.get("total_amount", 0) * 10)
        
        # Points per night
        night_points = booking_data.get("num_nights", 1) * 50
        
        # Property quality bonus
        rating_bonus = int(booking_data.get("property_rating", 3.0) * 20)
        
        # Property type bonus
        property_type = booking_data.get("property_type", "")
        type_bonus = {
            "hotel": 25,
            "apartment": 30,
            "house": 35,
            "villa": 50
        }.get(property_type, 20)
        
        return spend_points + night_points + rating_bonus + type_bonus
    
    def _get_active_multipliers(self, user_id: int) -> Dict:
        """Get active point multipliers for user"""
        
        multipliers = {
            "base": 1.0,
            "tier": 1.0,
            "streak": 1.0,
            "power_up": 1.0,
            "seasonal": 1.0,
            "total": 1.0
        }
        
        # Tier multiplier
        user_status = self.get_user_loyalty_status(user_id)
        tier_multipliers = {
            LoyaltyTier.BRONZE: 1.0,
            LoyaltyTier.SILVER: 1.1,
            LoyaltyTier.GOLD: 1.25,
            LoyaltyTier.PLATINUM: 1.5,
            LoyaltyTier.DIAMOND: 2.0
        }
        multipliers["tier"] = tier_multipliers[user_status.current_tier]
        
        # Streak multiplier
        if user_status.streak_days >= 30:
            multipliers["streak"] = 1.5
        elif user_status.streak_days >= 14:
            multipliers["streak"] = 1.25
        elif user_status.streak_days >= 7:
            multipliers["streak"] = 1.1
        
        # Power-up multipliers
        power_ups = self._get_user_power_ups(user_id)
        for power_up in power_ups:
            if power_up.get("type") == "points_multiplier":
                multipliers["power_up"] *= power_up.get("multiplier", 1.0)
        
        # Seasonal multiplier
        if self._is_peak_season():
            multipliers["seasonal"] = 1.2
        
        # Calculate total multiplier
        multipliers["total"] = (
            multipliers["base"] * 
            multipliers["tier"] * 
            multipliers["streak"] * 
            multipliers["power_up"] * 
            multipliers["seasonal"]
        )
        
        return multipliers
    
    def _check_booking_achievements(self, user_id: int, booking_data: Dict) -> List[Achievement]:
        """Check for new booking achievements"""
        
        new_achievements = []
        
        # Get user stats
        user_stats = self._calculate_user_statistics(user_id)
        
        # Check booking milestone achievements
        milestone_achievements = self.achievement_engine.check_booking_milestones(
            user_stats["total_bookings"] + 1
        )
        new_achievements.extend(milestone_achievements)
        
        # Check explorer achievements
        explorer_achievements = self.achievement_engine.check_explorer_achievements(
            user_id, booking_data.get("city")
        )
        new_achievements.extend(explorer_achievements)
        
        # Check spending achievements
        spending_achievements = self.achievement_engine.check_spending_achievements(
            user_stats["total_spend"] + booking_data.get("total_amount", 0)
        )
        new_achievements.extend(spending_achievements)
        
        # Unlock new achievements
        for achievement in new_achievements:
            self._unlock_achievement(user_id, achievement)
        
        return new_achievements
    
    def _update_booking_streak(self, user_id: int, check_in: date) -> int:
        """Update booking streak and return bonus"""
        
        current_streak = self._get_current_streak(user_id)
        last_booking_date = self._get_last_booking_date(user_id)
        
        streak_bonus = 0
        
        if last_booking_date:
            days_since_last = (check_in - last_booking_date).days
            
            if days_since_last <= 30:  # Within 30 days maintains streak
                if days_since_last <= 7:  # Within 7 days increases streak
                    new_streak = current_streak + 1
                    streak_bonus = min(new_streak * 10, 100)  # Max 100 bonus points
                else:
                    new_streak = current_streak
            else:
                new_streak = 1  # Reset streak
        else:
            new_streak = 1
        
        self._update_streak(user_id, new_streak)
        
        return streak_bonus
    
    def _calculate_bonus_points(self, user_id: int, booking_data: Dict, 
                              achievements: List[Achievement], streak_bonus: int) -> int:
        """Calculate bonus points"""
        
        bonus_points = streak_bonus
        
        # Achievement bonus
        bonus_points += len(achievements) * 50
        
        # Early booking bonus
        days_until_booking = (booking_data["check_in"] - date.today()).days
        if days_until_booking >= 30:
            bonus_points += 100
        elif days_until_booking >= 14:
            bonus_points += 50
        
        # Property rating bonus
        if booking_data.get("property_rating", 0) >= 4.5:
            bonus_points += 75
        
        # Length of stay bonus
        if booking_data.get("num_nights", 1) >= 7:
            bonus_points += 100
        
        return bonus_points
    
    def _create_loyalty_notifications(self, user_id: int, points: int, 
                                     achievements: List[Achievement], streak_bonus: int) -> List[Dict]:
        """Create loyalty notifications"""
        
        notifications = []
        
        # Points notification
        notifications.append({
            "type": "points_awarded",
            "title": f"🎉 {points} Points Earned!",
            "message": f"You've earned {points} loyalty points from your booking.",
            "icon": "points",
            "priority": "high"
        })
        
        # Achievement notifications
        for achievement in achievements:
            notifications.append({
                "type": "achievement_unlocked",
                "title": f"🏆 Achievement Unlocked: {achievement.name}!",
                "message": achievement.description,
                "icon": achievement.badge_url,
                "priority": "high"
            })
        
        # Streak notification
        if streak_bonus > 0:
            notifications.append({
                "type": "streak_bonus",
                "title": f"🔥 Streak Bonus: +{streak_bonus} Points!",
                "message": "Keep the momentum going!",
                "icon": "streak",
                "priority": "medium"
            })
        
        return notifications
    
    # Helper methods (simplified for demo)
    def _get_user_booking_history(self, user_id: int) -> List[Dict]:
        return []  # Mock data
    
    def _get_user_achievements(self, user_id: int) -> List[Achievement]:
        return []  # Mock data
    
    def _get_user_badges(self, user_id: int) -> List[str]:
        return []  # Mock data
    
    def _get_user_power_ups(self, user_id: int) -> List[Dict]:
        return []  # Mock data
    
    def _update_user_points(self, user_id: int, points: int):
        logger.info(f"Updated user {user_id} points by {points}")
    
    def _is_tier_eligible(self, current_tier: LoyaltyTier, required_tier: LoyaltyTier) -> bool:
        tier_order = [LoyaltyTier.BRONZE, LoyaltyTier.SILVER, LoyaltyTier.GOLD, 
                     LoyaltyTier.PLATINUM, LoyaltyTier.DIAMOND]
        current_index = tier_order.index(current_tier)
        required_index = tier_order.index(required_tier)
        return current_index >= required_index
    
    def _can_afford_reward(self, user_points: int, reward_cost: int) -> bool:
        return user_points >= reward_cost
    
    def _calculate_reward_relevance(self, reward: Reward, user_status: LoyaltyStatus) -> float:
        return 0.8  # Mock data
    
    def _process_reward_redemption(self, user_id: int, reward: Reward) -> Dict:
        return {"success": True, "reward_code": "REWARD123"}  # Mock data
    
    def _create_redemption_record(self, user_id: int, reward_id: str, points_cost: int):
        logger.info(f"Created redemption record for user {user_id}, reward {reward_id}")
    
    def _send_reward_notification(self, user_id: int, reward: Reward):
        logger.info(f"Sent reward notification to user {user_id}")
    
    def _check_redemption_achievements(self, user_id: int, reward: Reward):
        logger.info(f"Checked redemption achievements for user {user_id}")
    
    def _calculate_booking_streak(self, user_id: int) -> int:
        return 5  # Mock data
    
    def _get_current_streak(self, user_id: int) -> int:
        return 5  # Mock data
    
    def _get_last_booking_date(self, user_id: int) -> Optional[date]:
        return date.today() - timedelta(days=10)  # Mock data
    
    def _update_streak(self, user_id: int, new_streak: int):
        logger.info(f"Updated streak for user {user_id} to {new_streak}")
    
    def _is_peak_season(self) -> bool:
        return False  # Mock data
    
    def _unlock_achievement(self, user_id: int, achievement: Achievement):
        logger.info(f"Unlocked achievement {achievement.id} for user {user_id}")


class AchievementEngine:
    """Engine for managing achievements"""
    
    def check_booking_milestones(self, total_bookings: int) -> List[Achievement]:
        """Check booking milestone achievements"""
        milestones = {
            1: ("First Booking", "Complete your first booking", 100),
            5: ("Regular Guest", "Complete 5 bookings", 250),
            10: ("Frequent Traveler", "Complete 10 bookings", 500),
            25: ("Seasoned Explorer", "Complete 25 bookings", 1000),
            50: ("Master Traveler", "Complete 50 bookings", 2500),
            100: ("Legendary Guest", "Complete 100 bookings", 5000)
        }
        
        achievements = []
        for milestone, (name, desc, points) in milestones.items():
            if total_bookings == milestone:
                achievements.append(Achievement(
                    id=f"booking_{milestone}",
                    name=name,
                    description=desc,
                    type=AchievementType.BOOKING_MILESTONE,
                    points=points,
                    badge_url=f"/badges/booking_{milestone}.png",
                    requirements={"bookings": milestone},
                    progress=1.0,
                    unlocked_at=datetime.now(),
                    rarity="common" if milestone < 10 else "rare"
                ))
        
        return achievements
    
    def check_explorer_achievements(self, user_id: int, city: str) -> List[Achievement]:
        """Check explorer achievements"""
        return []  # Mock implementation
    
    def check_spending_achievements(self, total_spend: float) -> List[Achievement]:
        """Check spending achievements"""
        return []  # Mock implementation


class RewardEngine:
    """Engine for managing rewards"""
    
    def get_all_rewards(self) -> List[Reward]:
        """Get all available rewards"""
        return [
            Reward(
                id="discount_10",
                name="10% Off Next Booking",
                description="Get 10% off your next accommodation booking",
                type=RewardType.DISCOUNT,
                value={"percentage": 10, "max_discount": 50},
                points_cost=500,
                tier_requirement=LoyaltyTier.BRONZE,
                expiration_date=date.today() + timedelta(days=90),
                usage_limit=1,
                terms="Valid for bookings over $100"
            ),
            Reward(
                id="free_night",
                name="Free Night Stay",
                description="Enjoy a free night at participating properties",
                type=RewardType.FREE_NIGHT,
                value={"nights": 1, "max_value": 200},
                points_cost=5000,
                tier_requirement=LoyaltyTier.GOLD,
                expiration_date=date.today() + timedelta(days=180),
                usage_limit=1,
                terms="Valid for properties up to $200/night"
            )
        ]
    
    def get_reward(self, reward_id: str) -> Optional[Reward]:
        """Get specific reward"""
        for reward in self.get_all_rewards():
            if reward.id == reward_id:
                return reward
        return None


class GamificationEngine:
    """Engine for gamification features"""
    
    def create_challenge(self, challenge_data: Dict):
        """Create new challenge"""
        pass
    
    def process_challenge_progress(self, user_id: int, challenge_id: str, progress: Dict):
        """Process challenge progress"""
        pass


class SocialEngine:
    """Engine for social features"""
    
    def create_team_challenge(self, team_data: Dict):
        """Create team challenge"""
        pass
    
    def share_achievement(self, user_id: int, achievement_id: str):
        """Share achievement to social"""
        pass


class LeaderboardManager:
    """Manager for leaderboards"""
    
    def get_leaderboard(self, timeframe: str, category: str) -> List[Dict]:
        """Get leaderboard rankings"""
        return [
            {"rank": 1, "user_id": 123, "username": "travel_pro", "score": 15000},
            {"rank": 2, "user_id": 456, "username": "explorer", "score": 12000},
            {"rank": 3, "user_id": 789, "username": "guest_star", "score": 10000}
        ]
