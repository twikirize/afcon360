"""
Global Moderation Analytics and Reporting Service

Enterprise-level analytics dashboard for Facebook/Airbnb/PayPal/Alibaba
scale moderation operations with comprehensive reporting capabilities.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from collections import defaultdict
import json

from sqlalchemy import func, and_, or_, desc, extract
from app.extensions import db
from app.admin.models.moderation import ContentFlag, ModerationLog


@dataclass
class AnalyticsMetric:
    """Analytics metric with metadata"""
    name: str
    value: Any
    unit: str
    trend: Optional[float]  # Percentage change
    comparison_period: str


@dataclass
class PerformanceMetric:
    """Performance metric for moderators"""
    moderator_id: int
    moderator_name: str
    flags_processed: int
    avg_response_time: float  # minutes
    accuracy_score: float
    escalation_rate: float
    user_satisfaction: float


class ModerationAnalytics:
    """Enterprise moderation analytics service"""
    
    def __init__(self):
        self.time_ranges = {
            'today': timedelta(days=1),
            'week': timedelta(days=7),
            'month': timedelta(days=30),
            'quarter': timedelta(days=90),
            'year': timedelta(days=365)
        }
    
    def get_dashboard_metrics(self, time_range: str = 'week') -> Dict[str, Any]:
        """
        Get comprehensive dashboard metrics
        
        Args:
            time_range: Time period for metrics (today, week, month, quarter, year)
            
        Returns:
            Dictionary of all dashboard metrics
        """
        end_date = datetime.now(timezone.utc)
        start_date = end_date - self.time_ranges.get(time_range, timedelta(days=7))
        
        metrics = {
            'overview': self._get_overview_metrics(start_date, end_date),
            'performance': self._get_performance_metrics(start_date, end_date),
            'content_analysis': self._get_content_analysis_metrics(start_date, end_date),
            'sla_metrics': self._get_sla_metrics(start_date, end_date),
            'escalation_metrics': self._get_escalation_metrics(start_date, end_date),
            'team_performance': self._get_team_performance_metrics(start_date, end_date),
            'trend_analysis': self._get_trend_analysis(time_range),
            'geographic_analysis': self._get_geographic_analysis(start_date, end_date),
            'ai_performance': self._get_ai_performance_metrics(start_date, end_date)
        }
        
        return metrics
    
    def _get_overview_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get overview metrics for the time period"""
        # Total flags processed
        total_flags = ContentFlag.query.filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).count()
        
        # Flags by status
        flags_by_status = db.session.query(
            ContentFlag.status,
            func.count(ContentFlag.id)
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.status).all()
        
        status_counts = dict(flags_by_status)
        
        # Resolution rate
        resolved_flags = status_counts.get('resolved', 0)
        resolution_rate = (resolved_flags / total_flags * 100) if total_flags > 0 else 0
        
        # Average processing time
        processing_times = db.session.query(
            func.avg(ContentFlag.processing_time_seconds)
        ).filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.processing_time_seconds.isnot(None)
            )
        ).scalar()
        
        avg_processing_time = processing_times / 60 if processing_times else 0  # Convert to minutes
        
        # High-risk flags
        high_risk_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.risk_score >= 80
            )
        ).count()
        
        return {
            'total_flags': total_flags,
            'resolved_flags': resolved_flags,
            'resolution_rate': round(resolution_rate, 2),
            'avg_processing_time_minutes': round(avg_processing_time, 2),
            'high_risk_flags': high_risk_flags,
            'status_breakdown': status_counts
        }
    
    def _get_performance_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get performance metrics"""
        # Moderator performance
        moderator_stats = db.session.query(
            ContentFlag.resolved_by,
            func.count(ContentFlag.id).label('flags_processed'),
            func.avg(ContentFlag.processing_time_seconds).label('avg_time'),
            func.avg(ContentFlag.reviewer_quality_score).label('quality_score'),
            func.avg(ContentFlag.user_satisfaction_score).label('satisfaction')
        ).filter(
            and_(
                ContentFlag.resolved_at.between(start_date, end_date),
                ContentFlag.resolved_by.isnot(None)
            )
        ).group_by(ContentFlag.resolved_by).all()
        
        # Calculate escalation rate per moderator
        escalation_stats = db.session.query(
            ContentFlag.resolved_by,
            func.count(ContentFlag.id).label('escalated_count')
        ).filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.escalation_count > 0,
                ContentFlag.resolved_by.isnot(None)
            )
        ).group_by(ContentFlag.resolved_by).all()
        
        escalation_counts = {stat.resolved_by: stat.escalated_count for stat in escalation_stats}
        
        # Build performance metrics
        performance_data = []
        for stat in moderator_stats:
            total_processed = stat.flags_processed
            escalated_count = escalation_counts.get(stat.resolved_by, 0)
            escalation_rate = (escalated_count / total_processed * 100) if total_processed > 0 else 0
            
            performance_data.append({
                'moderator_id': stat.resolved_by,
                'flags_processed': total_processed,
                'avg_response_time_minutes': round((stat.avg_time or 0) / 60, 2),
                'quality_score': round(stat.quality_score or 0, 2),
                'user_satisfaction': round(stat.satisfaction or 0, 2),
                'escalation_rate': round(escalation_rate, 2)
            })
        
        # Sort by performance score
        performance_data.sort(key=lambda x: x['quality_score'], reverse=True)
        
        return {
            'top_performers': performance_data[:10],
            'total_moderators': len(performance_data),
            'avg_quality_score': round(sum(p['quality_score'] for p in performance_data) / len(performance_data), 2) if performance_data else 0
        }
    
    def _get_content_analysis_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get content analysis metrics"""
        # Flags by category
        category_stats = db.session.query(
            ContentFlag.category,
            func.count(ContentFlag.id).label('count'),
            func.avg(ContentFlag.risk_score).label('avg_risk')
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.category).all()
        
        # Flags by severity
        severity_stats = db.session.query(
            ContentFlag.severity,
            func.count(ContentFlag.id).label('count')
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.severity).all()
        
        # Detection source analysis
        source_stats = db.session.query(
            ContentFlag.detection_source,
            func.count(ContentFlag.id).label('count'),
            func.avg(ContentFlag.ai_confidence).label('avg_confidence')
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.detection_source).all()
        
        # Entity type distribution
        entity_stats = db.session.query(
            ContentFlag.entity_type,
            func.count(ContentFlag.id).label('count')
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.entity_type).all()
        
        return {
            'categories': [{'name': cat.category, 'count': cat.count, 'avg_risk': round(cat.avg_risk or 0, 2)} for cat in category_stats],
            'severity_distribution': dict(severity_stats),
            'detection_sources': [{'source': src.detection_source, 'count': src.count, 'avg_confidence': round(src.avg_confidence or 0, 2)} for src in source_stats],
            'entity_types': dict(entity_stats)
        }
    
    def _get_sla_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get SLA compliance metrics"""
        # Total flags with SLA
        total_sla_flags = ContentFlag.query.filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).count()
        
        # SLA breaches
        sla_breached = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.sla_breached == True
            )
        ).count()
        
        # SLA compliance rate
        sla_compliance_rate = ((total_sla_flags - sla_breached) / total_sla_flags * 100) if total_sla_flags > 0 else 0
        
        # Average SLA performance
        resolved_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.resolved_at.isnot(None),
                ContentFlag.sla_due_at.isnot(None)
            )
        ).all()
        
        sla_performance = []
        for flag in resolved_flags:
            if flag.resolved_at and flag.sla_due_at:
                time_diff = (flag.resolved_at - flag.sla_due_at).total_seconds()
                sla_performance.append(time_diff)
        
        avg_sla_performance = sum(sla_performance) / len(sla_performance) / 3600 if sla_performance else 0  # hours
        
        # SLA by priority
        sla_by_priority = db.session.query(
            ContentFlag.priority,
            func.count(ContentFlag.id).label('total'),
            func.sum(func.cast(ContentFlag.sla_breached, db.Integer)).label('breached')
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.priority).all()
        
        priority_sla = {}
        for stat in sla_by_priority:
            total = stat.total
            breached = stat.breached or 0
            compliance_rate = ((total - breached) / total * 100) if total > 0 else 0
            priority_sla[stat.priority] = {
                'total': total,
                'breached': breached,
                'compliance_rate': round(compliance_rate, 2)
            }
        
        return {
            'total_sla_flags': total_sla_flags,
            'sla_breached': sla_breached,
            'sla_compliance_rate': round(sla_compliance_rate, 2),
            'avg_sla_performance_hours': round(avg_sla_performance, 2),
            'sla_by_priority': priority_sla
        }
    
    def _get_escalation_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get escalation metrics"""
        # Total escalations
        total_escalations = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.escalation_count > 0
            )
        ).count()
        
        # Escalations by level
        escalation_by_level = db.session.query(
            ContentFlag.escalated_to_level,
            func.count(ContentFlag.id).label('count')
        ).filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.escalated_to_level.isnot(None)
            )
        ).group_by(ContentFlag.escalated_to_level).all()
        
        # Escalation reasons
        escalation_reasons = db.session.query(
            ContentFlag.escalation_reason,
            func.count(ContentFlag.id).label('count')
        ).filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.escalation_reason.isnot(None)
            )
        ).group_by(ContentFlag.escalation_reason).all()
        
        # Average escalation time
        escalated_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.escalated_at.isnot(None)
            )
        ).all()
        
        escalation_times = []
        for flag in escalated_flags:
            if flag.escalated_at and flag.created_at:
                time_diff = (flag.escalated_at - flag.created_at).total_seconds()
                escalation_times.append(time_diff)
        
        avg_escalation_time = sum(escalation_times) / len(escalation_times) / 3600 if escalation_times else 0  # hours
        
        return {
            'total_escalations': total_escalations,
            'escalations_by_level': dict(escalation_by_level),
            'escalation_reasons': dict(escalation_reasons),
            'avg_escalation_time_hours': round(avg_escalation_time, 2)
        }
    
    def _get_team_performance_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get team performance metrics"""
        # Team workload distribution
        team_workload = db.session.query(
            ContentFlag.assigned_team,
            func.count(ContentFlag.id).label('assigned_count'),
            func.sum(func.cast(ContentFlag.status == 'resolved', db.Integer)).label('resolved_count')
        ).filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).group_by(ContentFlag.assigned_team).all()
        
        team_stats = {}
        for stat in team_workload:
            assigned = stat.assigned_count
            resolved = stat.resolved_count or 0
            resolution_rate = (resolved / assigned * 100) if assigned > 0 else 0
            
            team_stats[stat.assigned_team or 'unassigned'] = {
                'assigned': assigned,
                'resolved': resolved,
                'resolution_rate': round(resolution_rate, 2)
            }
        
        return {
            'team_performance': team_stats,
            'total_teams': len(team_stats)
        }
    
    def _get_trend_analysis(self, time_range: str) -> Dict[str, Any]:
        """Get trend analysis over time"""
        # Daily trends for the last 30 days
        days = 30
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        
        daily_stats = db.session.query(
            func.date(ContentFlag.created_at).label('date'),
            func.count(ContentFlag.id).label('total_flags'),
            func.sum(func.cast(ContentFlag.status == 'resolved', db.Integer)).label('resolved_flags'),
            func.avg(ContentFlag.risk_score).label('avg_risk_score')
        ).filter(
            ContentFlag.created_at >= start_date
        ).group_by(func.date(ContentFlag.created_at)).all()
        
        # Build daily trend data
        trends = []
        for stat in daily_stats:
            trends.append({
                'date': stat.date.isoformat(),
                'total_flags': stat.total_flags,
                'resolved_flags': stat.resolved_flags or 0,
                'resolution_rate': round(((stat.resolved_flags or 0) / stat.total_flags * 100), 2) if stat.total_flags > 0 else 0,
                'avg_risk_score': round(stat.avg_risk_score or 0, 2)
            })
        
        # Calculate trends
        if len(trends) >= 7:
            recent_week = trends[-7:]
            previous_week = trends[-14:-7] if len(trends) >= 14 else trends[:-7]
            
            recent_avg = sum(day['total_flags'] for day in recent_week) / len(recent_week)
            previous_avg = sum(day['total_flags'] for day in previous_week) / len(previous_week)
            
            volume_trend = round(((recent_avg - previous_avg) / previous_avg * 100), 2) if previous_avg > 0 else 0
        else:
            volume_trend = 0
        
        return {
            'daily_trends': trends,
            'volume_trend_percent': volume_trend,
            'period_analyzed': f'Last {days} days'
        }
    
    def _get_geographic_analysis(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get geographic distribution of flags"""
        # Flags by country
        country_stats = db.session.query(
            ContentFlag.country_code,
            func.count(ContentFlag.id).label('count'),
            func.avg(ContentFlag.risk_score).label('avg_risk')
        ).filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.country_code.isnot(None)
            )
        ).group_by(ContentFlag.country_code).all()
        
        # Flags by language
        language_stats = db.session.query(
            ContentFlag.language_code,
            func.count(ContentFlag.id).label('count')
        ).filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.language_code.isnot(None)
            )
        ).group_by(ContentFlag.language_code).all()
        
        return {
            'by_country': [{'country': stat.country_code, 'count': stat.count, 'avg_risk': round(stat.avg_risk or 0, 2)} for stat in country_stats],
            'by_language': dict(language_stats)
        }
    
    def _get_ai_performance_metrics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get AI detection performance metrics"""
        # AI vs Human detection accuracy
        ai_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.detection_source == 'ai'
            )
        ).all()
        
        human_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.detection_source == 'human'
            )
        ).all()
        
        # Calculate AI accuracy (based on resolution outcomes)
        ai_resolved = [f for f in ai_flags if f.status == 'resolved']
        ai_correct = len([f for f in ai_resolved if f.resolution_action in ['rejected', 'removed']])
        ai_accuracy = (ai_correct / len(ai_resolved) * 100) if ai_resolved else 0
        
        # Average AI confidence
        avg_ai_confidence = db.session.query(
            func.avg(ContentFlag.ai_confidence)
        ).filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.detection_source == 'ai',
                ContentFlag.ai_confidence.isnot(None)
            )
        ).scalar()
        
        # Auto-processed flags
        auto_processed = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.auto_processed == True
            )
        ).count()
        
        return {
            'ai_flags_count': len(ai_flags),
            'human_flags_count': len(human_flags),
            'ai_accuracy_percent': round(ai_accuracy, 2),
            'avg_ai_confidence': round(avg_ai_confidence or 0, 2),
            'auto_processed_count': auto_processed,
            'auto_processing_rate': round((auto_processed / (len(ai_flags) + len(human_flags)) * 100), 2) if (ai_flags or human_flags) else 0
        }
    
    def generate_report(self, report_type: str, start_date: datetime, 
                       end_date: datetime, format: str = 'json') -> Dict[str, Any]:
        """
        Generate comprehensive moderation report
        
        Args:
            report_type: Type of report (daily, weekly, monthly, quarterly)
            start_date: Report start date
            end_date: Report end date
            format: Output format (json, csv, pdf)
            
        Returns:
            Report data
        """
        report_data = {
            'report_metadata': {
                'type': report_type,
                'period': f"{start_date.date()} to {end_date.date()}",
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'format': format
            },
            'executive_summary': self._get_executive_summary(start_date, end_date),
            'detailed_metrics': self.get_dashboard_metrics('custom'),
            'recommendations': self._generate_recommendations(start_date, end_date)
        }
        
        return report_data
    
    def _get_executive_summary(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Generate executive summary"""
        total_flags = ContentFlag.query.filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).count()
        
        resolved_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.status == 'resolved'
            )
        ).count()
        
        high_risk_flags = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.risk_score >= 80
            )
        ).count()
        
        sla_breached = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.sla_breached == True
            )
        ).count()
        
        return {
            'total_flags_reviewed': total_flags,
            'resolution_rate': round((resolved_flags / total_flags * 100), 2) if total_flags > 0 else 0,
            'high_risk_content': high_risk_flags,
            'sla_compliance': round(((total_flags - sla_breached) / total_flags * 100), 2) if total_flags > 0 else 0,
            'key_insights': self._generate_key_insights(start_date, end_date)
        }
    
    def _generate_key_insights(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Generate key insights from data"""
        insights = []
        
        # Compare with previous period
        previous_start = start_date - (end_date - start_date)
        previous_end = start_date
        
        current_flags = ContentFlag.query.filter(
            ContentFlag.created_at.between(start_date, end_date)
        ).count()
        
        previous_flags = ContentFlag.query.filter(
            ContentFlag.created_at.between(previous_start, previous_end)
        ).count()
        
        if current_flags > previous_flags * 1.2:
            insights.append("Content flag volume increased significantly compared to previous period")
        elif current_flags < previous_flags * 0.8:
            insights.append("Content flag volume decreased compared to previous period")
        
        # Check for SLA issues
        sla_breach_rate = ContentFlag.query.filter(
            and_(
                ContentFlag.created_at.between(start_date, end_date),
                ContentFlag.sla_breached == True
            )
        ).count() / current_flags if current_flags > 0 else 0
        
        if sla_breach_rate > 0.1:  # > 10% breach rate
            insights.append("SLA compliance issues detected - consider resource allocation")
        
        # Check AI performance
        ai_accuracy = self._get_ai_performance_metrics(start_date, end_date)['ai_accuracy_percent']
        if ai_accuracy < 70:
            insights.append("AI detection accuracy below threshold - consider model retraining")
        
        return insights
    
    def _generate_recommendations(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Analyze team performance
        team_metrics = self._get_team_performance_metrics(start_date, end_date)
        
        # Check for underperforming teams
        for team, metrics in team_metrics['team_performance'].items():
            if metrics['resolution_rate'] < 80:
                recommendations.append(f"Consider additional training for {team} - resolution rate at {metrics['resolution_rate']}%")
        
        # Check for high escalation rates
        escalation_metrics = self._get_escalation_metrics(start_date, end_date)
        if escalation_metrics['total_escalations'] > 0:
            escalation_rate = escalation_metrics['total_escalations'] / ContentFlag.query.filter(
                ContentFlag.created_at.between(start_date, end_date)
            ).count() if ContentFlag.query.filter(
                ContentFlag.created_at.between(start_date, end_date)
            ).count() > 0 else 0
            
            if escalation_rate > 0.2:  # > 20% escalation rate
                recommendations.append("High escalation rate detected - review initial moderation quality")
        
        return recommendations


# Global analytics instance
moderation_analytics = ModerationAnalytics()
