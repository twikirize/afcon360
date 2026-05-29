# AFCON360 Moderator System - Complete Developer Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Database Schema](#database-schema)
4. [Routes & Endpoints](#routes--endpoints)
5. [Templates & UI](#templates--ui)
6. [Models & Data Structures](#models--data-structures)
7. [Enterprise Features](#enterprise-features)
8. [Training System](#training-system)
9. [Security & Permissions](#security--permissions)
10. [Integration Points](#integration-points)
11. [Development Guidelines](#development-guidelines)
12. [Troubleshooting](#troubleshooting)
13. [Future Development](#future-development)

---

## System Overview

The AFCON360 Moderator System is an enterprise-level content moderation platform built with Flask, designed to handle Facebook-scale moderation workloads with AI assistance, multi-tier escalation, and comprehensive analytics.

### Key Features
- **AI-Powered Moderation**: Automated content classification with human oversight
- **Multi-Tier Escalation**: Level 1-3 escalation workflows
- **Real-Time Analytics**: SLA monitoring, performance metrics, AI accuracy tracking
- **Cross-Platform Coordination**: Web, mobile, API synchronization
- **Training & Certification**: Structured learning path with certification levels
- **Enterprise Security**: Role-based access, audit trails, emergency procedures

### Role Hierarchy
```
👑 OWNER (Level 1) - Complete system control
├── 👤 SUPER_ADMIN (Level 2) - User management, role assignment
│   ├── 👤 ADMIN (Level 3) - Regular user management
│   │   ├── 👤 MODERATOR (Level 4) - Content moderation, user suspension
│   │   └── 👤 SUPPORT (Level 5) - Read-only user access
│   ├── 👤 AUDITOR (Level 4) - Read-only audit access
│   └── 👤 COMPLIANCE_OFFICER (Level 5) - AML/KYC review
└── 👤 USER (Level 13) - Default registered user
```

---

## Architecture

### Blueprint Structure
```
app/
├── admin/
│   ├── moderator/
│   │   ├── __init__.py              # Blueprint definition
│   │   ├── routes.py               # All moderator routes (3000+ lines)
│   │   └── models.py               # Moderator-specific models
│   ├── owner/                      # Owner-level functionality
│   ├── compliance/                 # Compliance team features
│   └── support/                    # Support team features
├── auth/
│   ├── decorators.py               # Role-based access decorators
│   ├── roles.py                    # Role definitions and management
│   └── helpers.py                 # Authentication helpers
└── models/
    ├── user.py                     # User model with dual ID system
    └── admin.py                    # Admin models (ContentFlag, etc.)
```

### Key Design Patterns
1. **Local Imports**: Routes use local imports to avoid circular dependencies
2. **Dual ID System**: Internal BIGINT + external UUID for security
3. **Blueprint Registration**: Nested blueprints under admin blueprint
4. **Role-Based Decorators**: Granular permission enforcement
5. **AI Integration**: Human-AI collaboration workflows

---

## Database Schema

### Core Tables

#### Users Table
```sql
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    public_id VARCHAR(36) UNIQUE NOT NULL,  -- External UUID
    username VARCHAR(80) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_protected BOOLEAN DEFAULT FALSE,       -- Executive protection
    protection_reason VARCHAR(255),
    can_be_deleted_by VARCHAR(50),           -- who can delete
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

#### ContentFlag Table (Enterprise Features)
```sql
CREATE TABLE content_flags (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    entity_type VARCHAR(50) NOT NULL,         -- 'user', 'content', 'organisation'
    entity_id BIGINT NOT NULL,
    flagged_by BIGINT NOT NULL,
    reason TEXT NOT NULL,
    priority ENUM('low', 'medium', 'high', 'critical') DEFAULT 'medium',
    status ENUM('pending', 'under_review', 'resolved', 'escalated') DEFAULT 'pending',
    ai_detected BOOLEAN DEFAULT FALSE,       -- AI vs human flag
    ai_confidence DECIMAL(5,4),               -- AI confidence score
    sla_breach_at TIMESTAMP NULL,             -- SLA deadline
    escalation_level INT DEFAULT 1,          -- Escalation tier
    assigned_to BIGINT NULL,                  -- Assigned moderator
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    INDEX idx_entity (entity_type, entity_id),
    INDEX idx_status_priority (status, priority),
    INDEX idx_sla_breach (sla_breach_at),
    INDEX idx_ai_detected (ai_detected)
);
```

#### EmergencyAccess Table (Security)
```sql
CREATE TABLE emergency_access (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    granted_to BIGINT NOT NULL,
    granted_by BIGINT NOT NULL,
    reason TEXT NOT NULL,
    jira_ticket VARCHAR(100) NOT NULL,       -- Required ticket number
    approved_by_secops BIGINT NOT NULL,      -- Secondary approval
    expires_at TIMESTAMP NOT NULL,           -- 4-hour max
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Relationships
- Users → ContentFlag (1:many) - Flags created by users
- Users → ContentFlag (1:many) - Flags assigned to moderators
- ContentFlag → Users (many:1) - Entity being flagged
- EmergencyAccess → Users (2:1) - Granted by and to users

---

## Routes & Endpoints

### Blueprint Registration
```python
# app/admin/__init__.py
from app.admin.moderator import moderator_bp
admin_bp.register_blueprint(moderator_bp)  # Registers under /admin

# app/admin/moderator/__init__.py
moderator_bp = Blueprint('moderator', __name__, url_prefix='/moderator')
# Results in: /admin/moderator/*
```

### Core Routes

#### Dashboard
- **Route**: `/admin/moderator/dashboard`
- **Methods**: GET
- **Template**: `admin/moderator/dashboard.html`
- **Features**: Real-time metrics, SLA monitoring, AI performance

#### Content Moderation
- **Route**: `/admin/moderator/content`
- **Methods**: GET, POST
- **Template**: `admin/moderator/content.html`
- **Features**: Queue management, bulk actions, AI assistance

#### Flag Management
- **Route**: `/admin/moderator/flagged`
- **Methods**: GET, POST
- **Template**: `admin/moderator/flagged.html`
- **Features**: Flag review, escalation, priority management

#### User Moderation
- **Route**: `/admin/moderator/users`
- **Methods**: GET, POST
- **Template**: `admin/moderator/users.html`
- **Features**: User profiles, suspension, activity monitoring

#### Organization Moderation
- **Route**: `/admin/moderator/orgs`
- **Methods**: GET, POST
- **Template**: `admin/moderator/orgs.html`
- **Features**: Organization review, verification, compliance

### Enterprise Feature Routes

#### AI Analytics
- **Route**: `/admin/moderator/ai-analytics`
- **Template**: `admin/moderator/ai_analytics.html`
- **Features**: Model performance, detection trends, system health

#### Training System
- **Route**: `/admin/moderator/training`
- **Template**: `admin/moderator/training.html`
- **Features**: Certification tracking, progress monitoring

#### Training Materials
- **Route**: `/admin/moderator/training-content`
- **Template**: `admin/moderator/training_content.html`
- **Features**: Course materials, assessments, certification

#### Content Safety
- **Route**: `/admin/moderator/content-safety`
- **Template**: `admin/moderator/content_safety.html`
- **Features**: Policy enforcement, compliance metrics

#### Cross-Platform
- **Route**: `/admin/moderator/cross-platform`
- **Template**: `admin/moderator/cross_platform.html`
- **Features**: Multi-platform sync, health monitoring

### API Endpoints
```python
# Queue Health API
@admin_bp.route('/api/queue-health')
def api_queue_health():
    """Returns real-time queue metrics for dashboard widgets"""

# Flag Resolution API
@admin_bp.route('/api/flags/<int:flag_id>/resolve', methods=['POST'])
def api_resolve_flag(flag_id):
    """AJAX endpoint for quick flag resolution"""

# Submission Approval API
@admin_bp.route('/api/submissions/<int:submission_id>/approve', methods=['POST'])
def api_approve_submission(submission_id):
    """AJAX endpoint for content approval"""

# Auto-Priority API
@admin_bp.route('/api/auto-priority', methods=['POST'])
def api_auto_priority():
    """AI-powered priority assignment for content"""
```

---

## Templates & UI

### Template Hierarchy
```
templates/
├── admin/
│   ├── moderator/
│   │   ├── base_moderator.html           # Base template
│   │   ├── dashboard.html                # Main dashboard
│   │   ├── content.html                  # Content moderation
│   │   ├── flagged.html                  # Flag management
│   │   ├── users.html                    # User moderation
│   │   ├── orgs.html                     # Organization moderation
│   │   ├── ai_analytics.html             # AI analytics dashboard
│   │   ├── training.html                 # Training dashboard
│   │   ├── training_content.html         # Course materials
│   │   ├── content_safety.html           # Safety policies
│   │   ├── cross_platform.html           # Cross-platform tools
│   │   ├── escalations.html              # Escalation queue
│   │   └── view_org.html                 # Organization review
│   ├── owner/                            # Owner templates
│   └── compliance/                       # Compliance templates
└── base.html                             # Global base template
```

### UI Components

#### Dashboard Widgets
```html
<!-- Real-time Stats -->
<div class="stat-grid">
  <div class="stat-card">
    <div class="stat-icon">🚨</div>
    <div class="stat-content">
      <div class="stat-value">{{ critical_flags }}</div>
      <div class="stat-label">Critical Flags</div>
    </div>
  </div>
</div>

<!-- SLA Monitoring -->
<div class="sla-panel">
  <div class="sla-indicator {{ sla_status }}">
    SLA: {{ sla_percentage }}% Compliance
  </div>
</div>
```

#### Enterprise Navigation
```html
<!-- Enterprise Features Section -->
<div class="sidebar-section">
  <div class="section-title">ENTERPRISE</div>
  <a href="{{ url_for('admin.moderator.ai_analytics') }}" class="nav-item">
    <i class="fas fa-brain"></i> AI Analytics
  </a>
  <a href="{{ url_for('admin.moderator.training') }}" class="nav-item">
    <i class="fas fa-graduation-cap"></i> Training
  </a>
  <a href="{{ url_for('admin.moderator.content_safety') }}" class="nav-item">
    <i class="fas fa-shield-alt"></i> Content Safety
  </a>
  <a href="{{ url_for('admin.moderator.cross_platform') }}" class="nav-item">
    <i class="fas fa-network-wired"></i> Cross-Platform
  </a>
</div>
```

---

## Models & Data Structures

### ContentFlag Model (Enterprise)
```python
class ContentFlag(BaseModel):
    __tablename__ = 'content_flags'
    
    id = Column(BigInteger, primary_key=True)
    entity_type = Column(String(50), nullable=False)  # 'user', 'content', 'organisation'
    entity_id = Column(BigInteger, nullable=False)
    flagged_by = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    reason = Column(Text, nullable=False)
    priority = Column(Enum('low', 'medium', 'high', 'critical'), default='medium')
    status = Column(Enum('pending', 'under_review', 'resolved', 'escalated'), default='pending')
    
    # Enterprise Features
    ai_detected = Column(Boolean, default=False)
    ai_confidence = Column(Numeric(5,4))  # 0.0000 to 1.0000
    sla_breach_at = Column(DateTime)  # Auto-calculated deadline
    escalation_level = Column(Integer, default=1)  # 1-3 escalation tiers
    assigned_to = Column(BigInteger, ForeignKey('users.id'))
    
    # Relationships
    flagger = relationship('User', foreign_keys=[flagged_by], backref='flags_created')
    assignee = relationship('User', foreign_keys=[assigned_to], backref='assigned_flags')
    
    # Enterprise Methods
    def calculate_sla_deadline(self):
        """Calculate SLA deadline based on priority"""
        sla_hours = {
            'critical': 1,    # 1 hour
            'high': 4,        # 4 hours
            'medium': 24,     # 24 hours
            'low': 72         # 72 hours
        }
        return self.created_at + timedelta(hours=sla_hours[self.priority])
    
    def escalate(self, to_level=2, reason=""):
        """Escalate flag to higher level"""
        self.escalation_level = to_level
        self.status = 'escalated'
        # Add escalation logic here
    
    def is_sla_breached(self):
        """Check if flag has breached SLA"""
        return datetime.now(timezone.utc) > self.sla_breach_at
```

### User Model (Enhanced)
```python
class User(BaseModel):
    __tablename__ = 'users'
    
    # Dual ID System
    id = Column(BigInteger, primary_key=True)          # Internal ID
    public_id = Column(String(36), unique, nullable=False)  # External UUID
    
    # Standard Fields
    username = Column(String(80), unique, nullable=False)
    email = Column(String(255), unique, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Enterprise Security Features
    is_protected = Column(Boolean, default=False)
    protection_reason = Column(String(255))  # 'Executive', 'Security', 'Compliance'
    can_be_deleted_by = Column(String(50))    # 'owner_only', 'secops_approval'
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Enterprise Methods
    def can_be_deleted_by_user(self, user):
        """Check if user can delete this account"""
        if self.is_protected:
            if not user.has_global_role('owner'):
                return False
            if self.can_be_deleted_by == 'secops_approval':
                return False  # Requires additional approval
        return True
    
    def can_be_suspended_by_user(self, user):
        """Check if user can suspend this account"""
        # Tenure-based protection
        if (datetime.now(timezone.utc) - self.created_at).days < 7:
            return False  # New accounts protected for 7 days
        
        # Role-based protection
        if user.has_global_role('moderator') and self.has_any_global_role(['admin', 'super_admin', 'owner']):
            return False  # Moderators can't suspend higher roles
        
        return True
```

---

## Enterprise Features

### AI-Powered Moderation

#### Content Classification
```python
def classify_content(content_text, content_type='text'):
    """AI-powered content classification"""
    from app.ai.services import ContentClassifier
    
    classifier = ContentClassifier()
    result = classifier.analyze(content_text, content_type)
    
    return {
        'category': result['category'],
        'confidence': result['confidence'],
        'priority': result['priority'],
        'recommendation': result['recommendation'],
        'ai_detected': True,
        'processing_time': result['processing_time']
    }
```

#### SLA Management
```python
def calculate_sla_metrics(flags):
    """Calculate SLA compliance metrics"""
    now = datetime.now(timezone.utc)
    
    metrics = {
        'total_flags': len(flags),
        'resolved_within_sla': 0,
        'breached_count': 0,
        'sla_percentage': 0.0,
        'average_resolution_time': timedelta(0)
    }
    
    resolution_times = []
    
    for flag in flags:
        if flag.status == 'resolved':
            resolution_time = flag.updated_at - flag.created_at
            resolution_times.append(resolution_time)
            
            if resolution_time <= (flag.sla_breach_at - flag.created_at):
                metrics['resolved_within_sla'] += 1
        elif flag.is_sla_breached():
            metrics['breached_count'] += 1
    
    if resolution_times:
        metrics['average_resolution_time'] = sum(resolution_times, timedelta(0)) / len(resolution_times)
    
    if metrics['total_flags'] > 0:
        metrics['sla_percentage'] = (metrics['resolved_within_sla'] / metrics['total_flags']) * 100
    
    return metrics
```

### Multi-Tier Escalation

#### Escalation Workflow
```python
def escalate_flag(flag_id, to_level, reason, escalated_by):
    """Escalate flag to higher level with proper workflow"""
    flag = ContentFlag.query.get_or_404(flag_id)
    
    # Validate escalation rules
    if to_level > 3:
        raise ValueError("Maximum escalation level is 3")
    
    if to_level <= flag.escalation_level:
        raise ValueError("Can only escalate to higher level")
    
    # Create escalation record
    escalation = EscalationRecord(
        flag_id=flag_id,
        from_level=flag.escalation_level,
        to_level=to_level,
        reason=reason,
        escalated_by=escalated_by,
        created_at=datetime.now(timezone.utc)
    )
    
    # Update flag
    flag.escalation_level = to_level
    flag.status = 'escalated'
    
    # Notify appropriate team
    notify_escalation_team(flag, to_level)
    
    db.session.add(escalation)
    db.session.commit()
    
    return flag
```

### Cross-Platform Synchronization

#### Sync Manager
```python
class CrossPlatformSync:
    """Manages synchronization across platforms"""
    
    def __init__(self):
        self.platforms = ['web', 'ios', 'android', 'api']
    
    def sync_moderation_action(self, action, entity_type, entity_id, platform):
        """Sync moderation action across all platforms"""
        sync_record = {
            'action': action,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'source_platform': platform,
            'timestamp': datetime.now(timezone.utc),
            'sync_status': 'pending'
        }
        
        # Queue for async processing
        self.queue_sync_task(sync_record)
        
        return sync_record
    
    def queue_sync_task(self, sync_record):
        """Queue sync task for background processing"""
        from app.tasks import sync_moderation_action
        sync_moderation_action.delay(sync_record)
```

---

## Training System

### Certification Levels

#### Level 1: Basic Moderator (10 credits)
```python
BASIC_MODERATOR_REQUIREMENTS = {
    'modules': ['foundation_course'],
    'credits': 10,
    'assessment_score': 80,
    'practical_exercises': 5,
    'capabilities': [
        'basic_content_review',
        'simple_flag_resolution',
        'queue_navigation'
    ]
}
```

#### Level 2: Certified Moderator (25 credits)
```python
CERTIFIED_MODERATOR_REQUIREMENTS = {
    'modules': ['foundation_course', 'intermediate_skills'],
    'credits': 25,
    'assessment_score': 85,
    'practical_exercises': 15,
    'capabilities': [
        'advanced_content_analysis',
        'escalation_handling',
        'user_suspension',
        'ai_tool_usage'
    ]
}
```

#### Level 3: Senior Moderator (50 credits)
```python
SENIOR_MODERATOR_REQUIREMENTS = {
    'modules': ['foundation_course', 'intermediate_skills', 'advanced_techniques'],
    'credits': 50,
    'assessment_score': 90,
    'practical_exercises': 30,
    'leadership_projects': 2,
    'capabilities': [
        'crisis_management',
        'team_coordination',
        'policy_interpretation',
        'training_delivery',
        'quality_assurance'
    ]
}
```

### Course Structure

#### Module 1: Foundation Course
```python
FOUNDATION_MODULE = {
    'id': 1,
    'name': 'Content Moderation Basics',
    'duration_hours': 2,
    'credits': 10,
    'lessons': [
        {
            'title': 'Introduction to Content Moderation',
            'content': 'moderation_basics.html',
            'quiz': 'basics_quiz.json',
            'estimated_minutes': 30
        },
        {
            'title': 'Platform Navigation',
            'content': 'platform_nav.html',
            'quiz': 'nav_quiz.json',
            'estimated_minutes': 45
        },
        {
            'title': 'Basic Content Policies',
            'content': 'basic_policies.html',
            'quiz': 'policies_quiz.json',
            'estimated_minutes': 45
        }
    ],
    'assessment': {
        'type': 'quiz',
        'questions': 20,
        'passing_score': 80,
        'time_limit_minutes': 30
    }
}
```

### Progress Tracking
```python
class ModeratorTraining(BaseModel):
    __tablename__ = 'moderator_training'
    
    id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    module_id = Column(Integer, nullable=False)
    status = Column(Enum('not_started', 'in_progress', 'completed'), default='not_started')
    progress_percentage = Column(Integer, default=0)
    credits_earned = Column(Integer, default=0)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    
    # Relationships
    user = relationship('User', backref='training_progress')
    
    def update_progress(self, lesson_completed):
        """Update training progress"""
        # Calculate new progress
        # Update credits earned
        # Check for module completion
        pass
```

---

## Security & Permissions

### Role-Based Access Control

#### Decorators
```python
# app/auth/decorators.py

def require_role(*allowed_roles):
    """Require specific roles to access route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login'))
            
            if not current_user.has_any_global_role(allowed_roles):
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_permission(permission):
    """Require specific permission to access route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.can(permission):
                flash('You do not have permission to perform this action.', 'error')
                return redirect(request.referrer or url_for('main.index'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Usage
@moderator_bp.route('/users')
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def user_moderation():
    """Moderator can access user moderation"""
    pass

@moderator_bp.route('/suspend/<int:user_id>', methods=['POST'])
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
@require_permission('users.suspend')
def suspend_user(user_id):
    """Require both role and permission"""
    pass
```

### Permission System

#### Permission Definitions
```python
# app/auth/permissions.py

MODERATOR_PERMISSIONS = {
    'content.moderate': 'Can moderate content submissions',
    'content.approve': 'Can approve content',
    'content.reject': 'Can reject content',
    'content.flag': 'Can flag content',
    'users.view': 'Can view user profiles',
    'users.suspend': 'Can suspend users',
    'users.view_activity': 'Can view user activity',
    'flags.view': 'Can view flagged content',
    'flags.resolve': 'Can resolve flags',
    'flags.escalate': 'Can escalate flags',
    'orgs.view': 'Can view organizations',
    'orgs.moderate': 'Can moderate organizations',
    'analytics.view': 'Can view analytics',
    'training.view': 'Can view training materials'
}
```

### Security Features

#### Tenure-Based Protections
```python
def check_account_protection(user, action, performing_user):
    """Check if account action is allowed based on tenure and protection"""
    
    # New account protection (7 days)
    if (datetime.now(timezone.utc) - user.created_at).days < 7:
        if action in ['delete', 'suspend']:
            return False, "Account is less than 7 days old"
    
    # Admin tenure protection (30 days)
    if user.has_global_role('admin'):
        admin_role_date = get_role_assignment_date(user, 'admin')
        if admin_role_date and (datetime.now(timezone.utc) - admin_role_date).days < 30:
            if action in ['delete', 'demote']:
                return False, "Admin tenure less than 30 days"
    
    # Protected accounts
    if user.is_protected:
        if not performing_user.has_global_role('owner'):
            return False, "Protected account requires owner access"
        
        if user.can_be_deleted_by == 'secops_approval':
            # Check for security operations approval
            if not has_secops_approval(performing_user, user, action):
                return False, "Requires security operations approval"
    
    return True, "Action allowed"
```

#### Emergency Access
```python
def request_emergency_access(user_id, reason, jira_ticket, requested_by):
    """Request emergency access with proper approval workflow"""
    
    # Validate JIRA ticket
    if not validate_jira_ticket(jira_ticket):
        raise ValueError("Invalid JIRA ticket number")
    
    # Get secondary approval from security operations
    secops_approval = get_secops_approval(requested_by, user_id, reason, jira_ticket)
    
    if not secops_approval:
        raise PermissionError("Security operations approval required")
    
    # Create emergency access record
    emergency_access = EmergencyAccess(
        granted_to=user_id,
        granted_by=requested_by.id,
        reason=reason,
        jira_ticket=jira_ticket,
        approved_by_secops=secops_approval.approved_by,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=4)  # 4-hour max
    )
    
    db.session.add(emergency_access)
    db.session.commit()
    
    # Log emergency access
    log_security_event('emergency_access_granted', {
        'granted_to': user_id,
        'granted_by': requested_by.id,
        'reason': reason,
        'jira_ticket': jira_ticket,
        'expires_at': emergency_access.expires_at
    })
    
    return emergency_access
```

---

## Integration Points

### External Systems

#### AI Services Integration
```python
# app/ai/services.py

class AIContentService:
    """Integration with AI content analysis services"""
    
    def __init__(self):
        self.classifier_url = os.getenv('AI_CLASSIFIER_URL')
        self.confidence_threshold = 0.7
    
    def analyze_content(self, content, content_type='text'):
        """Send content to AI for analysis"""
        payload = {
            'content': content,
            'type': content_type,
            'context': 'moderation'
        }
        
        response = requests.post(
            f"{self.classifier_url}/analyze",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            return {
                'category': result['category'],
                'confidence': result['confidence'],
                'priority': self._calculate_priority(result),
                'recommendation': result['recommendation'],
                'ai_detected': True
            }
        
        return None
    
    def _calculate_priority(self, ai_result):
        """Calculate priority based on AI confidence and category"""
        if ai_result['confidence'] > 0.9 and ai_result['category'] in ['hate_speech', 'violence']:
            return 'critical'
        elif ai_result['confidence'] > 0.8:
            return 'high'
        elif ai_result['confidence'] > 0.6:
            return 'medium'
        else:
            return 'low'
```

#### Compliance Integration
```python
# app/compliance/services.py

class ComplianceService:
    """Integration with compliance and legal systems"""
    
    def __init__(self):
        self.compliance_api_url = os.getenv('COMPLIANCE_API_URL')
        self.fia_endpoint = "/fia/uganda"
        self.aml_endpoint = "/bank-of-uganda/aml"
    
    def report_suspicious_activity(self, user_id, activity_type, details):
        """Report suspicious activity to compliance"""
        payload = {
            'user_id': user_id,
            'activity_type': activity_type,
            'details': details,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'reported_by': current_user.id
        }
        
        response = requests.post(
            f"{self.compliance_api_url}{self.aml_endpoint}/report",
            json=payload,
            headers={'Authorization': f"Bearer {self.get_compliance_token()}"}
        )
        
        return response.status_code == 201
    
    def check_sanctions(self, user_data):
        """Check user against sanctions lists"""
        payload = {
            'name': user_data.get('name'),
            'email': user_data.get('email'),
            'phone': user_data.get('phone'),
            'organization': user_data.get('organization')
        }
        
        response = requests.post(
            f"{self.compliance_api_url}{self.fia_endpoint}/sanctions-check",
            json=payload,
            headers={'Authorization': f"Bearer {self.get_compliance_token()}"}
        )
        
        if response.status_code == 200:
            return response.json()
        
        return None
```

### Internal System Integration

#### Event System
```python
# app/events/moderation.py

class ModerationEvents:
    """Event system for moderation actions"""
    
    @staticmethod
    def content_approved(content_id, moderator_id):
        """Fire event when content is approved"""
        event_data = {
            'content_id': content_id,
            'moderator_id': moderator_id,
            'action': 'approved',
            'timestamp': datetime.now(timezone.utc)
        }
        
        # Trigger internal events
        trigger_event('content.moderated', event_data)
        
        # Update analytics
        update_moderation_analytics(event_data)
        
        # Notify content creator
        notify_content_creator(content_id, 'approved')
    
    @staticmethod
    def user_suspended(user_id, moderator_id, reason):
        """Fire event when user is suspended"""
        event_data = {
            'user_id': user_id,
            'moderator_id': moderator_id,
            'reason': reason,
            'action': 'suspended',
            'timestamp': datetime.now(timezone.utc)
        }
        
        # Trigger internal events
        trigger_event('user.suspended', event_data)
        
        # Update user status
        update_user_status(user_id, 'suspended')
        
        # Log for compliance
        log_compliance_event('user_suspension', event_data)
```

#### Notification System
```python
# app/notifications/services.py

class NotificationService:
    """Centralized notification system"""
    
    def notify_moderator(self, moderator_id, notification_type, data):
        """Send notification to moderator"""
        notification = {
            'user_id': moderator_id,
            'type': notification_type,
            'title': self._get_notification_title(notification_type),
            'message': self._get_notification_message(notification_type, data),
            'priority': self._get_notification_priority(notification_type),
            'action_url': self._get_action_url(notification_type, data),
            'created_at': datetime.now(timezone.utc)
        }
        
        # Store notification
        stored_notification = store_notification(notification)
        
        # Send real-time notification
        send_websocket_notification(moderator_id, stored_notification)
        
        # Send email if high priority
        if notification['priority'] in ['high', 'critical']:
            send_email_notification(moderator_id, stored_notification)
    
    def _get_notification_title(self, type):
        titles = {
            'flag_assigned': 'New Flag Assigned',
            'sla_breach': 'SLA Breach Alert',
            'escalation_required': 'Escalation Required',
            'content_approved': 'Content Approved',
            'user_suspended': 'User Suspended'
        }
        return titles.get(type, 'Moderation Notification')
```

---

## Development Guidelines

### Code Standards

#### Route Structure
```python
# Standard route pattern
@moderator_bp.route('/endpoint')
@login_required
@require_role('moderator', 'admin', 'super_admin', 'owner')
def route_function():
    """Route description"""
    
    # Local imports to avoid circular dependencies
    from app.models import User
    from app.admin.models import ContentFlag
    
    # Input validation
    # Business logic
    # Database operations
    # Response rendering
    
    return render_template('template.html', data=data)
```

#### Model Patterns
```python
# Standard model pattern
class ModelName(BaseModel):
    __tablename__ = 'table_name'
    
    # Columns
    id = Column(BigInteger, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    related_model = relationship('RelatedModel', backref='model_name')
    
    # Methods
    def __repr__(self):
        return f'<ModelName {self.id}>'
    
    def to_dict(self):
        """Convert to dictionary for API responses"""
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
```

#### Template Patterns
```html
<!-- Standard template structure -->
{% extends "admin/moderator/base_moderator.html" %}

{% block title %}Page Title — AFCON360{% endblock %}

{% block topbar_title %}Page Title{% endblock %}

{% block content %}
<div class="breadcrumbs">
  <a href="{{ url_for('admin.moderator.dashboard') }}">Dashboard</a>
  <span class="sep">/</span>
  <span class="crumb-active">Current Page</span>
</div>

<div class="heading-row">
  <div>
    <h1 class="page-heading">Page Title</h1>
    <p class="page-subheading">Page description</p>
  </div>
</div>

<!-- Page content -->
<div class="panel">
  <div class="panel-header">
    <div class="panel-title">
      <i class="fas fa-icon"></i>
      Panel Title
    </div>
  </div>
  <div class="panel-body">
    <!-- Panel content -->
  </div>
</div>
{% endblock %}
```

### Database Guidelines

#### Migration Pattern
```python
# Standard migration pattern
"""Migration description

Revision ID: abc123def456
Revises: previous_revision
Create Date: 2024-01-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'abc123def456'
down_revision = 'previous_revision'
branch_labels = None
depends_on = None

def upgrade():
    # Create tables
    op.create_table('new_table',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Add indexes
    op.create_index('idx_table_name', 'new_table', ['name'])

def downgrade():
    # Remove indexes
    op.drop_index('idx_table_name', table_name='new_table')
    
    # Drop tables
    op.drop_table('new_table')
```

#### Query Optimization
```python
# Efficient query patterns
def get_moderation_queue(limit=50, offset=0):
    """Get moderation queue with optimized queries"""
    
    # Use joins instead of separate queries
    query = db.session.query(
        ContentSubmission,
        User,
        ContentFlag
    ).outerjoin(
        User, ContentSubmission.submitted_by == User.id
    ).outerjoin(
        ContentFlag, 
        and_(
            ContentFlag.entity_type == 'content',
            ContentFlag.entity_id == ContentSubmission.id
        )
    ).filter(
        ContentSubmission.status == 'pending'
    ).order_by(
        ContentSubmission.created_at.desc()
    ).limit(limit).offset(offset)
    
    return query.all()

# Use indexes in queries
def get_user_flags(user_id, status=None):
    """Get user flags with indexed queries"""
    
    query = ContentFlag.query.filter(
        ContentFlag.entity_type == 'user',
        ContentFlag.entity_id == user_id
    )
    
    if status:
        query = query.filter(ContentFlag.status == status)
    
    # Use indexed columns for ordering
    return query.order_by(
        ContentFlag.priority.desc(),
        ContentFlag.created_at.desc()
    ).all()
```

### Performance Guidelines

#### Caching Strategy
```python
# Cache frequently accessed data
from app.extensions import cache

@cache.memoize(timeout=300)  # 5 minutes
def get_moderation_stats():
    """Get moderation stats with caching"""
    
    stats = {
        'total_flags': ContentFlag.query.count(),
        'pending_flags': ContentFlag.query.filter_by(status='pending').count(),
        'critical_flags': ContentFlag.query.filter_by(priority='critical').count()
    }
    
    return stats

# Clear cache on data changes
def create_flag(flag_data):
    """Create flag and clear relevant caches"""
    
    flag = ContentFlag(**flag_data)
    db.session.add(flag)
    db.session.commit()
    
    # Clear cached stats
    cache.delete_memoized(get_moderation_stats)
    
    return flag
```

#### Async Processing
```python
# Use background tasks for heavy operations
from app.tasks import process_content_analysis

@moderator_bp.route('/content/<int:content_id>/analyze', methods=['POST'])
def analyze_content(content_id):
    """Trigger async content analysis"""
    
    content = ContentSubmission.query.get_or_404(content_id)
    
    # Queue for background processing
    task = process_content_analysis.delay(content_id)
    
    flash('Content analysis started. Results will be available shortly.', 'info')
    
    return redirect(url_for('admin.moderator.view_content', content_id=content_id))
```

---

## Troubleshooting

### Common Issues

#### Template Not Found Errors
```python
# Problem: Template not found
# Solution: Check template path and blueprint registration

# Correct template path
return render_template('admin/moderator/dashboard.html')

# Correct blueprint registration
# app/admin/moderator/__init__.py
moderator_bp = Blueprint('moderator', __name__, url_prefix='/moderator')
```

#### URL Prefix Issues
```python
# Problem: Double /admin/admin/ URLs
# Solution: Use relative URL prefixes

# Incorrect (causes double prefix)
moderator_bp = Blueprint('moderator', __name__, url_prefix='/admin/moderator')

# Correct (relative to admin blueprint)
moderator_bp = Blueprint('moderator', __name__, url_prefix='/moderator')
```

#### Circular Import Issues
```python
# Problem: Circular imports between models and routes
# Solution: Use local imports in routes

# Incorrect (causes circular imports)
from app.models import User, ContentFlag

@moderator_bp.route('/users')
def users():
    return User.query.all()

# Correct (local imports)
@moderator_bp.route('/users')
def users():
    from app.models import User
    return User.query.all()
```

#### Permission Issues
```python
# Problem: User can't access route they should have access to
# Solution: Check role assignment and decorator configuration

# Debug permissions
def debug_user_permissions(user_id):
    """Debug user permissions and roles"""
    user = User.query.get(user_id)
    
    print(f"User: {user.username}")
    print(f"Roles: {[role.name for role in user.roles]}")
    print(f"Global Roles: {[role.name for role in user.global_roles]}")
    print(f"Permissions: {list(user.permissions)}")
```

### Database Issues

#### Migration Problems
```python
# Problem: Migration fails due to model changes
# Solution: Check model state and migration dependencies

# Check current migration
flask db current

# Check migration history
flask db history

# Reset to previous migration if needed
flask db downgrade <previous_revision>

# Create new migration
flask db revision -m "description"
```

#### Performance Issues
```python
# Problem: Slow queries
# Solution: Add indexes and optimize queries

# Add indexes to models
class ContentFlag(BaseModel):
    __tablename__ = 'content_flags'
    
    # Add composite index for common queries
    __table_args__ = (
        Index('idx_entity_status_priority', 'entity_type', 'entity_id', 'status', 'priority'),
        Index('idx_created_at_desc', 'created_at'.desc()),
    )

# Use EXPLAIN to analyze queries
result = db.session.execute("EXPLAIN ANALYZE SELECT * FROM content_flags WHERE status = 'pending'")
print(result.fetchall())
```

### Debugging Tools

#### Logging Configuration
```python
# Configure logging for debugging
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

# Log specific components
logger = logging.getLogger('app.admin.moderator')
logger.setLevel(logging.DEBUG)

# Add request logging
@app.before_request
def log_request_info():
    logger.debug(f"Request: {request.method} {request.url}")
    logger.debug(f"User: {current_user.username if current_user.is_authenticated else 'Anonymous'}")
```

#### Performance Monitoring
```python
# Add performance monitoring
import time
from functools import wraps

def monitor_performance(func):
    """Decorator to monitor function performance"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        logger.info(f"{func.__name__} took {end_time - start_time:.2f} seconds")
        
        return result
    return wrapper

# Usage
@moderator_bp.route('/dashboard')
@monitor_performance
def dashboard():
    # Dashboard logic
    pass
```

---

## Future Development

### Planned Enhancements

#### AI Improvements
- **Multi-modal Analysis**: Image, video, and audio content analysis
- **Real-time Processing**: Stream processing for live content
- **Custom Models**: Platform-specific AI model training
- **Explainable AI**: AI decision reasoning and transparency

#### Scalability Features
- **Horizontal Scaling**: Multi-instance deployment
- **Load Balancing**: Intelligent request distribution
- **Caching Layer**: Redis cluster for distributed caching
- **Database Sharding**: Partition large tables for performance

#### Advanced Analytics
- **Predictive Analytics**: ML models for trend prediction
- **Behavioral Analysis**: User pattern recognition
- **Sentiment Analysis**: Content sentiment tracking
- **Risk Scoring**: Automated risk assessment

#### Integration Enhancements
- **Third-party APIs**: External service integrations
- **Webhook System**: Real-time event notifications
- **API Gateway**: Centralized API management
- **Microservices**: Service-oriented architecture

### Development Roadmap

#### Phase 1: Foundation (Current)
- ✅ Basic moderation system
- ✅ Role-based access control
- ✅ Enterprise features
- ✅ Training system

#### Phase 2: Enhancement (Next 3 months)
- 🔄 Advanced AI integration
- 🔄 Real-time analytics
- 🔄 Mobile optimization
- 🔄 API documentation

#### Phase 3: Scale (6-12 months)
- 📋 Microservices architecture
- 📋 Multi-region deployment
- 📋 Advanced security features
- 📋 Compliance automation

#### Phase 4: Innovation (12+ months)
- 📋 Predictive moderation
- 📋 Automated workflows
- 📋 Cross-platform intelligence
- 📋 Global compliance

### Contributing Guidelines

#### Code Review Process
1. **Create Feature Branch**: `git checkout -b feature/new-feature`
2. **Write Tests**: Unit and integration tests
3. **Update Documentation**: API docs and user guides
4. **Submit PR**: With detailed description
5. **Code Review**: Peer review and approval
6. **Merge**: After approval and tests pass

#### Testing Requirements
```python
# Unit tests
def test_moderator_can_suspend_user():
    """Test moderator user suspension capability"""
    moderator = create_user('moderator')
    target_user = create_user('regular')
    
    # Assign moderator role
    assign_role(moderator, 'moderator')
    
    # Test suspension
    result = suspend_user(target_user.id, moderator.id, 'Test suspension')
    
    assert result is True
    assert target_user.is_suspended is True

# Integration tests
def test_moderation_workflow():
    """Test complete moderation workflow"""
    # Create content
    content = create_content('Test content')
    
    # Flag content
    flag = create_flag(content.id, 'test', 'medium')
    
    # Assign to moderator
    assign_flag(flag.id, moderator.id)
    
    # Resolve flag
    resolve_flag(flag.id, moderator.id, 'resolved')
    
    # Verify workflow
    assert flag.status == 'resolved'
    assert content.status == 'approved'
```

#### Documentation Standards
- **API Documentation**: OpenAPI/Swagger specs
- **Code Comments**: Clear, concise explanations
- **User Guides**: Step-by-step instructions
- **Architecture Docs**: System design documentation

---

## Conclusion

The AFCON360 Moderator System is a comprehensive, enterprise-level content moderation platform designed to handle large-scale moderation workloads while maintaining security, compliance, and user experience standards comparable to major platforms like Facebook, Google, and TikTok.

### Key Strengths
- **Enterprise Architecture**: Scalable, secure, and maintainable
- **AI Integration**: Advanced content analysis and automation
- **Comprehensive Training**: Structured certification program
- **Security Focus**: Role-based access, audit trails, emergency procedures
- **Performance Optimized**: Efficient queries, caching, and async processing
- **Compliance Ready**: Built for regulatory requirements

### Development Best Practices
- **Local Imports**: Avoid circular dependencies
- **Role-Based Security**: Granular permission enforcement
- **Performance Monitoring**: Built-in analytics and optimization
- **Comprehensive Testing**: Unit, integration, and end-to-end tests
- **Documentation**: Complete developer and user documentation

This system provides a solid foundation for content moderation at scale while maintaining the flexibility to adapt to changing requirements and technologies.

---

*Last Updated: May 8, 2026*  
*Version: 1.0.0*  
*Documentation Version: Complete*
