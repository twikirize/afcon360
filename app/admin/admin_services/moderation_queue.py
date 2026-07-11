"""
Enterprise Moderation Queue System

Real-time processing queue for scalable content moderation
at Facebook/Airbnb/PayPal/Alibaba scale.
"""

import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict, deque
import threading
from queue import PriorityQueue, Empty
from sqlalchemy import func, and_, or_

from app.extensions import db
from app.admin.models.moderation import ContentFlag


class QueuePriority(Enum):
    """Priority levels for moderation queue"""
    CRITICAL = 1  # Risk score >= 80
    HIGH = 2      # Risk score 60-79
    MEDIUM = 3    # Risk score 40-59
    NORMAL = 4    # Risk score 20-39
    LOW = 5       # Risk score < 20


@dataclass
class QueueItem:
    """Item in the moderation queue"""
    id: int
    entity_type: str
    entity_id: int
    risk_score: float
    priority: QueuePriority
    created_at: datetime
    sla_due_at: datetime
    escalation_level: str
    assigned_team: Optional[str]
    metadata: Dict


class ModerationQueue:
    """Enterprise-grade moderation queue system"""
    
    def __init__(self):
        self.queues = {
            priority: PriorityQueue() for priority in QueuePriority
        }
        self.processing_items = set()  # Track items being processed
        self.completed_items = deque(maxlen=1000)  # Recent completions
        self.queue_stats = defaultdict(int)
        self.sla_monitor = SLAMonitor()
        self.load_balancer = QueueLoadBalancer()
        self._lock = threading.Lock()
        
    def add_item(self, flag: ContentFlag) -> bool:
        """
        Add a content flag to the moderation queue
        
        Args:
            flag: ContentFlag object to queue
            
        Returns:
            True if successfully added to queue
        """
        try:
            priority = self._determine_priority(flag)
            
            queue_item = QueueItem(
                id=flag.id,
                entity_type=flag.entity_type,
                entity_id=flag.entity_id,
                risk_score=flag.risk_score,
                priority=priority,
                created_at=flag.created_at,
                sla_due_at=flag.sla_due_at,
                escalation_level=flag.moderation_level,
                assigned_team=flag.assigned_team,
                metadata={
                    'category': flag.category,
                    'severity': flag.severity,
                    'detection_source': flag.detection_source,
                    'auto_processed': flag.auto_processed
                }
            )
            
            # Add to appropriate priority queue
            self.queues[priority].put((priority.value, time.time(), queue_item))
            
            with self._lock:
                self.queue_stats[f'queue_{priority.name.lower()}'] += 1
            
            return True
            
        except Exception as e:
            current_app.logger.error(f"Failed to add item to queue: {e}")
            return False
    
    def get_next_item(self, moderator_id: int, team: str = None) -> Optional[QueueItem]:
        """
        Get next item from queue for moderator
        
        Args:
            moderator_id: ID of moderator requesting item
            team: Team assignment (optional)
            
        Returns:
            QueueItem or None if queue is empty
        """
        # Check queues in priority order
        for priority in QueuePriority:
            try:
                queue = self.queues[priority]
                while not queue.empty():
                    _, timestamp, item = queue.get_nowait()
                    
                    # Check if item is already being processed
                    if item.id in self.processing_items:
                        continue
                    
                    # Check team assignment if specified
                    if team and item.assigned_team and item.assigned_team != team:
                        # Put back in queue
                        queue.put((priority.value, timestamp, item))
                        break
                    
                    # Mark as being processed
                    with self._lock:
                        self.processing_items.add(item.id)
                        self.queue_stats[f'queue_{priority.name.lower()}'] -= 1
                    
                    return item
                    
            except Empty:
                continue
        
        return None
    
    def complete_item(self, item_id: int, moderator_id: int, action: str):
        """Mark queue item as completed"""
        with self._lock:
            if item_id in self.processing_items:
                self.processing_items.remove(item_id)
                
                # Add to completed items
                self.completed_items.append({
                    'item_id': item_id,
                    'moderator_id': moderator_id,
                    'action': action,
                    'completed_at': datetime.now(timezone.utc)
                })
    
    def get_queue_stats(self) -> Dict:
        """Get current queue statistics"""
        with self._lock:
            stats = dict(self.queue_stats)
            stats['processing_count'] = len(self.processing_items)
            stats['total_queued'] = sum(stats.values())
            
            # Add SLA statistics
            sla_stats = self.sla_monitor.get_sla_stats()
            stats.update(sla_stats)
            
            return stats
    
    def _determine_priority(self, flag: ContentFlag) -> QueuePriority:
        """Determine queue priority based on flag properties"""
        risk_score = flag.risk_score
        
        if risk_score >= 80:
            return QueuePriority.CRITICAL
        elif risk_score >= 60:
            return QueuePriority.HIGH
        elif risk_score >= 40:
            return QueuePriority.MEDIUM
        elif risk_score >= 20:
            return QueuePriority.NORMAL
        else:
            return QueuePriority.LOW


class SLAMonitor:
    """SLA monitoring for moderation queue"""
    
    def __init__(self):
        self.sla_thresholds = {
            'critical': timedelta(minutes=15),    # 15 minutes
            'high': timedelta(hours=1),          # 1 hour
            'medium': timedelta(hours=4),         # 4 hours
            'normal': timedelta(hours=24),        # 24 hours
            'low': timedelta(days=3)              # 3 days
        }
    
    def get_sla_stats(self) -> Dict:
        """Get SLA compliance statistics"""
        now = datetime.now(timezone.utc)
        stats = {
            'sla_breached_count': 0,
            'sla_urgent_count': 0,
            'sla_at_risk_count': 0
        }
        
        # Query database for SLA status
        flags = ContentFlag.query.filter_by(status='open').all()
        
        for flag in flags:
            sla_threshold = self.sla_thresholds.get(flag.priority, timedelta(days=1))
            
            if flag.sla_breached:
                stats['sla_breached_count'] += 1
            elif now >= flag.sla_due_at - timedelta(minutes=30):
                stats['sla_urgent_count'] += 1
            elif now >= flag.sla_due_at - sla_threshold / 2:
                stats['sla_at_risk_count'] += 1
        
        return stats


class QueueLoadBalancer:
    """Load balancer for moderation queue distribution"""
    
    def __init__(self):
        self.team_capacities = {
            'content_review': 10,  # Max items per moderator
            'safety_team': 5,
            'legal_review': 3,
            'escalation_team': 2
        }
    
    def get_optimal_assignment(self, item: QueueItem, available_moderators: List[Dict]) -> Optional[str]:
        """
        Determine optimal team assignment for queue item
        
        Args:
            item: QueueItem to assign
            available_moderators: List of available moderators with their teams
            
        Returns:
            Optimal team name or None
        """
        # Priority-based assignment rules
        assignment_rules = {
            QueuePriority.CRITICAL: ['escalation_team', 'safety_team', 'content_review'],
            QueuePriority.HIGH: ['safety_team', 'content_review'],
            QueuePriority.MEDIUM: ['content_review'],
            QueuePriority.NORMAL: ['content_review'],
            QueuePriority.LOW: ['content_review']
        }
        
        preferred_teams = assignment_rules.get(item.priority, ['content_review'])
        
        # Check team capacity and availability
        for team in preferred_teams:
            team_moderators = [m for m in available_moderators if m.get('team') == team]
            if team_moderators:
                current_load = self._get_team_load(team)
                max_capacity = len(team_moderators) * self.team_capacities.get(team, 5)
                
                if current_load < max_capacity:
                    return team
        
        return None
    
    def _get_team_load(self, team: str) -> int:
        """Get current load for a team"""
        return ContentFlag.query.filter(
            and_(
                ContentFlag.assigned_team == team,
                ContentFlag.status == 'open'
            )
        ).count()


class RealTimeProcessor:
    """Real-time moderation queue processor"""
    
    def __init__(self, queue: ModerationQueue):
        self.queue = queue
        self.running = False
        self.processor_thread = None
        
    def start(self):
        """Start the real-time processor"""
        if not self.running:
            self.running = True
            self.processor_thread = threading.Thread(target=self._process_loop)
            self.processor_thread.daemon = True
            self.processor_thread.start()
    
    def stop(self):
        """Stop the real-time processor"""
        self.running = False
        if self.processor_thread:
            self.processor_thread.join()
    
    def _process_loop(self):
        """Main processing loop"""
        while self.running:
            try:
                # Process auto-moderation items
                self._process_auto_items()
                
                # Check SLA breaches
                self._check_sla_breaches()
                
                # Rebalance queue if needed
                self._rebalance_queue()
                
                # Sleep for short interval
                time.sleep(5)
                
            except Exception as e:
                current_app.logger.error(f"Error in processing loop: {e}")
                time.sleep(10)
    
    def _process_auto_items(self):
        """Process items that can be auto-moderated"""
        # Get high-confidence AI detections
        auto_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.detection_source == 'ai',
                ContentFlag.ai_confidence >= 0.9,
                ContentFlag.auto_processed == False,
                ContentFlag.status == 'open'
            )
        ).all()
        
        for flag in auto_flags:
            if flag.risk_score >= 90:
                # Auto-remove critical content
                self._auto_remove_content(flag)
            elif flag.risk_score >= 75:
                # Auto-hide high-risk content
                self._auto_hide_content(flag)
    
    def _auto_remove_content(self, flag: ContentFlag):
        """Automatically remove critical content"""
        try:
            # Update flag status
            flag.status = 'resolved'
            flag.resolution_action = 'auto_removed'
            flag.resolved_at = datetime.now(timezone.utc)
            flag.auto_processed = True
            
            # Log action
            current_app.logger.info(f"Auto-removed content: {flag.entity_type}:{flag.entity_id}")
            
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Failed to auto-remove content: {e}")
            db.session.rollback()
    
    def _auto_hide_content(self, flag: ContentFlag):
        """Automatically hide high-risk content"""
        try:
            # Update flag status
            flag.status = 'resolved'
            flag.resolution_action = 'auto_hidden'
            flag.resolved_at = datetime.now(timezone.utc)
            flag.auto_processed = True
            
            # Log action
            current_app.logger.info(f"Auto-hidden content: {flag.entity_type}:{flag.entity_id}")
            
            db.session.commit()
            
        except Exception as e:
            current_app.logger.error(f"Failed to auto-hide content: {e}")
            db.session.rollback()
    
    def _check_sla_breaches(self):
        """Check for SLA breaches and escalate if needed"""
        now = datetime.now(timezone.utc)
        
        # Find overdue items
        overdue_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.status == 'open',
                ContentFlag.sla_due_at < now,
                ContentFlag.sla_breached == False
            )
        ).all()
        
        for flag in overdue_flags:
            # Mark as breached
            flag.sla_breached = True
            
            # Escalate if needed
            if flag.moderation_level != 'level_3':
                flag.moderation_level = 'level_3'
                flag.escalation_count += 1
                flag.escalation_reason = 'SLA breach auto-escalation'
            
            current_app.logger.warning(f"SLA breach for flag {flag.id}: {flag.entity_type}:{flag.entity_id}")
        
        if overdue_flags:
            db.session.commit()
    
    def _rebalance_queue(self):
        """Rebalance queue load across teams"""
        # Get current team loads
        team_loads = {}
        for team in ['content_review', 'safety_team', 'legal_review', 'escalation_team']:
            team_loads[team] = ContentFlag.query.filter(
                and_(
                    ContentFlag.assigned_team == team,
                    ContentFlag.status == 'open'
                )
            ).count()
        
        # Find overloaded teams
        max_load = max(team_loads.values()) if team_loads else 0
        avg_load = sum(team_loads.values()) / len(team_loads) if team_loads else 0
        
        if max_load > avg_load * 1.5:  # 50% above average
            overloaded_teams = [team for team, load in team_loads.items() if load == max_load]
            underloaded_teams = [team for team, load in team_loads.items() if load < avg_load * 0.8]
            
            if overloaded_teams and underloaded_teams:
                # Reassign some items
                self._reassign_items(overloaded_teams[0], underloaded_teams[0])
    
    def _reassign_items(self, from_team: str, to_team: str):
        """Reassign items from one team to another"""
        # Get items to reassign (low priority items first)
        items_to_reassign = ContentFlag.query.filter(
            and_(
                ContentFlag.assigned_team == from_team,
                ContentFlag.status == 'open',
                ContentFlag.priority.in_(['normal', 'low'])
            )
        ).limit(5).all()
        
        for item in items_to_reassign:
            item.assigned_team = to_team
            current_app.logger.info(f"Reassigned item {item.id} from {from_team} to {to_team}")
        
        if items_to_reassign:
            db.session.commit()


# Global queue instance
moderation_queue = ModerationQueue()
real_time_processor = RealTimeProcessor(moderation_queue)
