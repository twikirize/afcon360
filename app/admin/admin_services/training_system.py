"""
Moderator Training and Certification System

Enterprise-level training platform for content moderators
with certification, skill tracking, and continuous learning.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import json

from sqlalchemy import func, and_, or_, desc
from app.extensions import db


class TrainingLevel(Enum):
    """Training certification levels"""
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    MASTER = "master"


class TrainingModuleType(Enum):
    """Types of training modules"""
    POLICY_TRAINING = "policy_training"
    PRACTICAL_ASSESSMENT = "practical_assessment"
    SIMULATION = "simulation"
    LEGAL_COMPLIANCE = "legal_compliance"
    AI_TOOLS = "ai_tools"
    CULTURAL_SENSITIVITY = "cultural_sensitivity"
    CRISIS_MANAGEMENT = "crisis_management"


@dataclass
class TrainingModule:
    """Training module definition"""
    id: str
    title: str
    description: str
    module_type: TrainingModuleType
    level: TrainingLevel
    duration_minutes: int
    required_for_levels: List[TrainingLevel]
    prerequisites: List[str]
    learning_objectives: List[str]
    content_sections: List[Dict]
    assessment_criteria: Dict
    pass_score: float
    certification_credit: float


@dataclass
class UserTrainingProgress:
    """User's training progress"""
    user_id: int
    module_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    progress_percentage: float
    assessment_scores: List[float]
    current_level: TrainingLevel
    certification_status: str
    total_credits: float


class ModeratorTrainingSystem:
    """Enterprise moderator training system"""
    
    def __init__(self):
        self.training_modules = self._initialize_training_modules()
        self.certification_paths = self._initialize_certification_paths()
        self.skill_requirements = self._initialize_skill_requirements()
        self.assessment_engine = AssessmentEngine()
        
    def _initialize_training_modules(self) -> Dict[str, TrainingModule]:
        """Initialize training modules"""
        modules = {}
        
        # Basic Level Modules
        modules['basic_001'] = TrainingModule(
            id='basic_001',
            title='Introduction to Content Moderation',
            description='Fundamentals of content moderation and platform policies',
            module_type=TrainingModuleType.POLICY_TRAINING,
            level=TrainingLevel.BASIC,
            duration_minutes=45,
            required_for_levels=[TrainingLevel.BASIC],
            prerequisites=[],
            learning_objectives=[
                'Understand content moderation principles',
                'Learn platform community guidelines',
                'Identify common policy violations',
                'Basic user interaction skills'
            ],
            content_sections=[
                {
                    'title': 'What is Content Moderation?',
                    'content_type': 'video',
                    'duration': 10,
                    'resources': ['intro_video.mp4', 'moderation_basics.pdf']
                },
                {
                    'title': 'Platform Policies Overview',
                    'content_type': 'interactive',
                    'duration': 15,
                    'resources': ['policy_guide.html', 'case_studies.json']
                },
                {
                    'title': 'Common Violation Types',
                    'content_type': 'text',
                    'duration': 10,
                    'resources': ['violation_types.pdf']
                },
                {
                    'title': 'Basic Assessment',
                    'content_type': 'quiz',
                    'duration': 10,
                    'resources': ['basic_quiz.json']
                }
            ],
            assessment_criteria={
                'quiz_score': 0.8,
                'participation': 0.9
            },
            pass_score=80.0,
            certification_credit=1.0
        )
        
        modules['basic_002'] = TrainingModule(
            id='basic_002',
            title='Community Guidelines and Policies',
            description='Deep dive into platform-specific community guidelines',
            module_type=TrainingModuleType.POLICY_TRAINING,
            level=TrainingLevel.BASIC,
            duration_minutes=60,
            required_for_levels=[TrainingLevel.BASIC],
            prerequisites=['basic_001'],
            learning_objectives=[
                'Master platform community guidelines',
                'Understand policy nuances',
                'Apply guidelines to real scenarios'
            ],
            content_sections=[
                {
                    'title': 'Community Standards Deep Dive',
                    'content_type': 'video',
                    'duration': 20,
                    'resources': ['community_standards.mp4']
                },
                {
                    'title': 'Policy Application Scenarios',
                    'content_type': 'simulation',
                    'duration': 25,
                    'resources': ['scenario_simulator.html']
                },
                {
                    'title': 'Guidelines Assessment',
                    'content_type': 'practical',
                    'duration': 15,
                    'resources': ['guidelines_test.json']
                }
            ],
            assessment_criteria={
                'scenario_score': 0.85,
                'guidelines_test': 0.8
            },
            pass_score=85.0,
            certification_credit=1.5
        )
        
        # Intermediate Level Modules
        modules['intermediate_001'] = TrainingModule(
            id='intermediate_001',
            title='Advanced Policy Application',
            description='Complex policy scenarios and edge cases',
            module_type=TrainingModuleType.PRACTICAL_ASSESSMENT,
            level=TrainingLevel.INTERMEDIATE,
            duration_minutes=90,
            required_for_levels=[TrainingLevel.INTERMEDIATE],
            prerequisites=['basic_001', 'basic_002'],
            learning_objectives=[
                'Handle complex moderation scenarios',
                'Apply policies to edge cases',
                'Make consistent moderation decisions'
            ],
            content_sections=[
                {
                    'title': 'Complex Scenario Analysis',
                    'content_type': 'case_study',
                    'duration': 30,
                    'resources': ['complex_cases.pdf', 'analysis_framework.md']
                },
                {
                    'title': 'Edge Case Workshop',
                    'content_type': 'interactive',
                    'duration': 35,
                    'resources': ['edge_case_simulator.html']
                },
                {
                    'title': 'Practical Assessment',
                    'content_type': 'practical',
                    'duration': 25,
                    'resources': ['advanced_assessment.json']
                }
            ],
            assessment_criteria={
                'case_analysis': 0.8,
                'practical_score': 0.85
            },
            pass_score=85.0,
            certification_credit=2.0
        )
        
        modules['intermediate_002'] = TrainingModule(
            id='intermediate_002',
            title='Legal and Compliance Fundamentals',
            description='Legal requirements and compliance for moderators',
            module_type=TrainingModuleType.LEGAL_COMPLIANCE,
            level=TrainingLevel.INTERMEDIATE,
            duration_minutes=75,
            required_for_levels=[TrainingLevel.INTERMEDIATE],
            prerequisites=['basic_001'],
            learning_objectives=[
                'Understand legal obligations',
                'Recognize reportable content',
                'Maintain compliance documentation'
            ],
            content_sections=[
                {
                    'title': 'Legal Framework Overview',
                    'content_type': 'video',
                    'duration': 25,
                    'resources': ['legal_framework.mp4', 'compliance_guide.pdf']
                },
                {
                    'title': 'Mandatory Reporting Requirements',
                    'content_type': 'interactive',
                    'duration': 30,
                    'resources': ['reporting_scenarios.html']
                },
                {
                    'title': 'Compliance Assessment',
                    'content_type': 'quiz',
                    'duration': 20,
                    'resources': ['compliance_quiz.json']
                }
            ],
            assessment_criteria={
                'legal_knowledge': 0.9,
                'compliance_score': 0.85
            },
            pass_score=90.0,
            certification_credit=2.5
        )
        
        # Advanced Level Modules
        modules['advanced_001'] = TrainingModule(
            id='advanced_001',
            title='AI-Powered Moderation Tools',
            description='Using AI tools and automation in moderation',
            module_type=TrainingModuleType.AI_TOOLS,
            level=TrainingLevel.ADVANCED,
            duration_minutes=120,
            required_for_levels=[TrainingLevel.ADVANCED],
            prerequisites=['intermediate_001', 'intermediate_002'],
            learning_objectives=[
                'Utilize AI moderation tools effectively',
                'Understand AI limitations and biases',
                'Combine human and AI moderation'
            ],
            content_sections=[
                {
                    'title': 'AI Moderation Overview',
                    'content_type': 'video',
                    'duration': 30,
                    'resources': ['ai_overview.mp4', 'tech_documentation.pdf']
                },
                {
                    'title': 'Tool Integration Workshop',
                    'content_type': 'hands_on',
                    'duration': 45,
                    'resources': ['ai_sandbox.html', 'tool_guides.md']
                },
                {
                    'title': 'AI Ethics and Limitations',
                    'content_type': 'discussion',
                    'duration': 25,
                    'resources': ['ethics_guide.pdf', 'bias_analysis.md']
                },
                {
                    'title': 'Advanced Assessment',
                    'content_type': 'practical',
                    'duration': 20,
                    'resources': ['ai_tools_test.json']
                }
            ],
            assessment_criteria={
                'tool_usage': 0.85,
                'ethics_understanding': 0.8,
                'practical_score': 0.9
            },
            pass_score=85.0,
            certification_credit=3.0
        )
        
        modules['advanced_002'] = TrainingModule(
            id='advanced_002',
            title='Crisis Management and Escalation',
            description='Handling crisis situations and escalation protocols',
            module_type=TrainingModuleType.CRISIS_MANAGEMENT,
            level=TrainingLevel.ADVANCED,
            duration_minutes=100,
            required_for_levels=[TrainingLevel.ADVANCED],
            prerequisites=['intermediate_001'],
            learning_objectives=[
                'Manage crisis moderation situations',
                'Execute escalation protocols',
                'Coordinate with legal and safety teams'
            ],
            content_sections=[
                {
                    'title': 'Crisis Identification',
                    'content_type': 'simulation',
                    'duration': 30,
                    'resources': ['crisis_simulator.html']
                },
                {
                    'title': 'Escalation Protocols',
                    'content_type': 'interactive',
                    'duration': 35,
                    'resources': ['escalation_flows.html', 'contact_trees.pdf']
                },
                {
                    'title': 'Crisis Communication',
                    'content_type': 'role_play',
                    'duration': 25,
                    'resources': ['communication_scenarios.json']
                },
                {
                    'title': 'Crisis Assessment',
                    'content_type': 'practical',
                    'duration': 10,
                    'resources': ['crisis_test.json']
                }
            ],
            assessment_criteria={
                'crisis_response': 0.9,
                'escalation_execution': 0.85,
                'communication': 0.8
            },
            pass_score=90.0,
            certification_credit=3.5
        )
        
        # Expert Level Modules
        modules['expert_001'] = TrainingModule(
            id='expert_001',
            title='Global Moderation and Cultural Sensitivity',
            description='Cross-cultural moderation and global policy application',
            module_type=TrainingModuleType.CULTURAL_SENSITIVITY,
            level=TrainingLevel.EXPERT,
            duration_minutes=150,
            required_for_levels=[TrainingLevel.EXPERT],
            prerequisites=['advanced_001', 'advanced_002'],
            learning_objectives=[
                'Apply policies across cultures',
                'Understand regional legal differences',
                'Navigate cultural nuances in moderation'
            ],
            content_sections=[
                {
                    'title': 'Global Policy Frameworks',
                    'content_type': 'video',
                    'duration': 40,
                    'resources': ['global_policies.mp4', 'regional_guide.pdf']
                },
                {
                    'title': 'Cultural Sensitivity Training',
                    'content_type': 'interactive',
                    'duration': 45,
                    'resources': ['cultural_scenarios.html']
                },
                {
                    'title': 'Regional Legal Systems',
                    'content_type': 'text',
                    'duration': 35,
                    'resources': ['legal_systems.pdf', 'compliance_matrix.xlsx']
                },
                {
                    'title': 'Global Assessment',
                    'content_type': 'comprehensive',
                    'duration': 30,
                    'resources': ['global_assessment.json']
                }
            ],
            assessment_criteria={
                'cultural_understanding': 0.85,
                'legal_knowledge': 0.9,
                'global_application': 0.85
            },
            pass_score=90.0,
            certification_credit=4.0
        )
        
        return modules
    
    def _initialize_certification_paths(self) -> Dict[TrainingLevel, List[str]]:
        """Initialize certification paths for each level"""
        return {
            TrainingLevel.BASIC: ['basic_001', 'basic_002'],
            TrainingLevel.INTERMEDIATE: ['intermediate_001', 'intermediate_002'],
            TrainingLevel.ADVANCED: ['advanced_001', 'advanced_002'],
            TrainingLevel.EXPERT: ['expert_001'],
            TrainingLevel.MASTER: []  # Requires real-world experience
        }
    
    def _initialize_skill_requirements(self) -> Dict[TrainingLevel, Dict[str, float]]:
        """Initialize skill requirements for each level"""
        return {
            TrainingLevel.BASIC: {
                'policy_knowledge': 0.8,
                'basic_judgment': 0.8,
                'communication': 0.7
            },
            TrainingLevel.INTERMEDIATE: {
                'policy_application': 0.85,
                'complex_judgment': 0.8,
                'legal_compliance': 0.85,
                'consistency': 0.8
            },
            TrainingLevel.ADVANCED: {
                'ai_tool_usage': 0.85,
                'crisis_management': 0.9,
                'escalation_handling': 0.85,
                'mentorship': 0.7
            },
            TrainingLevel.EXPERT: {
                'global_policies': 0.9,
                'cultural_sensitivity': 0.85,
                'strategic_thinking': 0.8,
                'leadership': 0.8
            },
            TrainingLevel.MASTER: {
                'innovation': 0.8,
                'system_design': 0.85,
                'training_development': 0.8,
                'policy_contribution': 0.85
            }
        }
    
    def get_user_training_path(self, user_id: int) -> Dict[str, Any]:
        """Get personalized training path for user"""
        # Get user's current level and completed modules
        user_progress = self._get_user_progress(user_id)
        current_level = self._determine_user_level(user_progress)
        
        # Get required modules for next level
        if current_level == TrainingLevel.MASTER:
            next_level_modules = []
        else:
            next_level = self._get_next_level(current_level)
            next_level_modules = self.certification_paths.get(next_level, [])
        
        # Filter out completed modules
        completed_modules = [p.module_id for p in user_progress if p.completed_at]
        pending_modules = [mod_id for mod_id in next_level_modules if mod_id not in completed_modules]
        
        # Check prerequisites
        available_modules = []
        for module_id in pending_modules:
            module = self.training_modules.get(module_id)
            if module and self._check_prerequisites(module, completed_modules):
                available_modules.append(module)
        
        return {
            'current_level': current_level.value,
            'completed_modules': completed_modules,
            'available_modules': [mod.id for mod in available_modules],
            'total_credits': sum(p.certification_credit for p in user_progress if p.completed_at),
            'next_level_requirements': self._get_level_requirements(self._get_next_level(current_level))
        }
    
    def _get_user_progress(self, user_id: int) -> List[UserTrainingProgress]:
        """Get user's training progress (simplified implementation)"""
        # In production, this would query a training_progress table
        # For now, return empty progress
        return []
    
    def _determine_user_level(self, progress: List[UserTrainingProgress]) -> TrainingLevel:
        """Determine user's current training level"""
        total_credits = sum(p.certification_credit for p in progress if p.completed_at)
        
        if total_credits >= 12:
            return TrainingLevel.EXPERT
        elif total_credits >= 8:
            return TrainingLevel.ADVANCED
        elif total_credits >= 4:
            return TrainingLevel.INTERMEDIATE
        elif total_credits >= 2:
            return TrainingLevel.BASIC
        else:
            return TrainingLevel.BASIC  # Default to basic
    
    def _get_next_level(self, current_level: TrainingLevel) -> TrainingLevel:
        """Get next training level"""
        level_order = [TrainingLevel.BASIC, TrainingLevel.INTERMEDIATE, 
                       TrainingLevel.ADVANCED, TrainingLevel.EXPERT, TrainingLevel.MASTER]
        
        current_index = level_order.index(current_level)
        if current_index < len(level_order) - 1:
            return level_order[current_index + 1]
        return current_level
    
    def _check_prerequisites(self, module: TrainingModule, completed_modules: List[str]) -> bool:
        """Check if user has completed prerequisites"""
        return all(prereq in completed_modules for prereq in module.prerequisites)
    
    def _get_level_requirements(self, level: TrainingLevel) -> Dict[str, Any]:
        """Get requirements for training level"""
        module_ids = self.certification_paths.get(level, [])
        modules = [self.training_modules[mid] for mid in module_ids if mid in self.training_modules]
        
        return {
            'required_modules': len(modules),
            'total_duration': sum(m.duration_minutes for m in modules),
            'total_credits': sum(m.certification_credit for m in modules),
            'assessment_criteria': {m.id: m.assessment_criteria for m in modules}
        }
    
    def start_training_module(self, user_id: int, module_id: str) -> Dict[str, Any]:
        """Start a training module for user"""
        module = self.training_modules.get(module_id)
        if not module:
            return {'error': 'Module not found'}
        
        # Check prerequisites
        user_progress = self._get_user_progress(user_id)
        completed_modules = [p.module_id for p in user_progress if p.completed_at]
        
        if not self._check_prerequisites(module, completed_modules):
            return {'error': 'Prerequisites not completed'}
        
        # Create training session
        session = {
            'session_id': f"{user_id}_{module_id}_{datetime.now().timestamp()}",
            'user_id': user_id,
            'module_id': module_id,
            'started_at': datetime.now(timezone.utc),
            'status': 'in_progress',
            'current_section': 0,
            'progress': 0.0
        }
        
        return {
            'session': session,
            'module': {
                'id': module.id,
                'title': module.title,
                'description': module.description,
                'duration': module.duration_minutes,
                'sections': module.content_sections
            }
        }
    
    def complete_training_module(self, user_id: int, module_id: str, 
                               assessment_data: Dict) -> Dict[str, Any]:
        """Complete a training module with assessment"""
        module = self.training_modules.get(module_id)
        if not module:
            return {'error': 'Module not found'}
        
        # Evaluate assessment
        assessment_result = self.assessment_engine.evaluate_assessment(
            module, assessment_data
        )
        
        # Check if passed
        passed = assessment_result['score'] >= module.pass_score
        
        # Update user progress (in production, this would save to database)
        progress_update = {
            'user_id': user_id,
            'module_id': module_id,
            'completed_at': datetime.now(timezone.utc) if passed else None,
            'assessment_score': assessment_result['score'],
            'passed': passed,
            'credits_earned': module.certification_credit if passed else 0
        }
        
        return {
            'assessment_result': assessment_result,
            'passed': passed,
            'credits_earned': module.certification_credit if passed else 0,
            'next_steps': self._get_next_steps(user_id, module_id, passed)
        }
    
    def _get_next_steps(self, user_id: int, completed_module_id: str, passed: bool) -> List[str]:
        """Get next steps for user after completing module"""
        if not passed:
            return [f"Retry {completed_module_id} - additional study recommended"]
        
        user_path = self.get_user_training_path(user_id)
        next_steps = []
        
        if user_path['available_modules']:
            next_steps.append(f"Continue with: {', '.join(user_path['available_modules'])}")
        
        # Check if ready for level certification
        current_level = TrainingLevel(user_path['current_level'])
        required_modules = self.certification_paths.get(current_level, [])
        completed_modules = user_path['completed_modules']
        
        if all(mod_id in completed_modules for mod_id in required_modules):
            next_steps.append(f"Ready for {current_level.value} level certification")
        
        return next_steps
    
    def get_training_analytics(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get training analytics for the period"""
        # In production, this would query training data
        # For now, return mock analytics
        
        return {
            'period': f"{start_date.date()} to {end_date.date()}",
            'total_trainees': 150,
            'modules_completed': 450,
            'certifications_earned': {
                'basic': 120,
                'intermediate': 85,
                'advanced': 45,
                'expert': 15,
                'master': 5
            },
            'average_completion_time': 2.5,  # hours
            'pass_rate': 92.5,
            'most_popular_modules': [
                {'module_id': 'basic_001', 'completions': 145},
                {'module_id': 'intermediate_001', 'completions': 95},
                {'module_id': 'advanced_001', 'completions': 50}
            ],
            'training_effectiveness': {
                'pre_training_accuracy': 65.2,
                'post_training_accuracy': 87.8,
                'improvement': 22.6
            }
        }


class AssessmentEngine:
    """Assessment engine for training modules"""
    
    def evaluate_assessment(self, module: TrainingModule, assessment_data: Dict) -> Dict[str, Any]:
        """Evaluate assessment data for a module"""
        scores = []
        feedback = []
        
        # Evaluate different assessment types
        if 'quiz_answers' in assessment_data:
            quiz_score = self._evaluate_quiz(module, assessment_data['quiz_answers'])
            scores.append(quiz_score)
            feedback.append(f"Quiz score: {quiz_score}%")
        
        if 'practical_results' in assessment_data:
            practical_score = self._evaluate_practical(module, assessment_data['practical_results'])
            scores.append(practical_score)
            feedback.append(f"Practical score: {practical_score}%")
        
        if 'simulation_performance' in assessment_data:
            simulation_score = self._evaluate_simulation(module, assessment_data['simulation_performance'])
            scores.append(simulation_score)
            feedback.append(f"Simulation score: {simulation_score}%")
        
        # Calculate overall score
        overall_score = sum(scores) / len(scores) if scores else 0
        
        return {
            'score': overall_score,
            'passed': overall_score >= module.pass_score,
            'component_scores': scores,
            'feedback': feedback,
            'recommendations': self._generate_recommendations(overall_score, module)
        }
    
    def _evaluate_quiz(self, module: TrainingModule, answers: Dict) -> float:
        """Evaluate quiz answers"""
        # Simplified quiz evaluation
        # In production, this would check against correct answers
        total_questions = len(answers)
        correct_answers = sum(1 for answer in answers.values() if answer.get('correct', False))
        
        return (correct_answers / total_questions * 100) if total_questions > 0 else 0
    
    def _evaluate_practical(self, module: TrainingModule, results: Dict) -> float:
        """Evaluate practical assessment"""
        # Simplified practical evaluation
        # In production, this would evaluate against rubric
        criteria_scores = []
        
        for criterion, score in results.items():
            criteria_scores.append(score)
        
        return sum(criteria_scores) / len(criteria_scores) if criteria_scores else 0
    
    def _evaluate_simulation(self, module: TrainingModule, performance: Dict) -> float:
        """Evaluate simulation performance"""
        # Simplified simulation evaluation
        # In production, this would evaluate simulation metrics
        metrics = ['accuracy', 'speed', 'consistency', 'judgment']
        scores = []
        
        for metric in metrics:
            score = performance.get(metric, 0)
            scores.append(score)
        
        return sum(scores) / len(scores) if scores else 0
    
    def _generate_recommendations(self, score: float, module: TrainingModule) -> List[str]:
        """Generate study recommendations based on score"""
        recommendations = []
        
        if score < module.pass_score:
            recommendations.append("Review module content and try again")
            
            if score < 60:
                recommendations.append("Consider additional study materials")
                recommendations.append("Schedule a training session with a mentor")
            elif score < 80:
                recommendations.append("Focus on areas with lowest scores")
        
        if score >= module.pass_score and score < 90:
            recommendations.append("Good performance - consider advanced modules")
        
        if score >= 90:
            recommendations.append("Excellent performance - ready for mentorship role")
        
        return recommendations


# Global training system instance
moderator_training = ModeratorTrainingSystem()
