"""
Automated Backup and Disaster Recovery Service

Implements database backups, file backups, and disaster recovery procedures.
"""

import os
import subprocess
import shutil
import gzip
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from flask import current_app
from sqlalchemy import text
from app.extensions import db
import threading
import schedule
import time


class BackupType:
    """Backup type constants."""
    DATABASE = "database"
    FILES = "files"
    CONFIG = "config"
    FULL = "full"


class BackupSchedule:
    """Backup schedule configuration."""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class BackupRecord(db.Model):
    """Backup tracking record."""
    __tablename__ = 'backup_records'
    
    id = Column(Integer, primary_key=True)
    backup_type = Column(String(20), nullable=False, index=True)
    backup_schedule = Column(String(20), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=False)
    status = Column(String(20), nullable=False, index=True)  # running, completed, failed
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=True)
    
    __table_args__ = (
        db.Index('ix_backup_records_type_status', 'backup_type', 'status'),
    )


class BackupService:
    """Automated backup service."""
    
    def __init__(self):
        self.backup_dir = current_app.config.get('BACKUP_DIR', '/var/backups/afcon360')
        self.max_backups = {
            BackupSchedule.HOURLY: 24,  # Keep 24 hourly backups
            BackupSchedule.DAILY: 30,   # Keep 30 daily backups
            BackupSchedule.WEEKLY: 12,  # Keep 12 weekly backups
            BackupSchedule.MONTHLY: 24  # Keep 24 monthly backups
        }
        self.compression_enabled = True
        self.encryption_enabled = False  # Set to True when encryption key is configured
        
        # Ensure backup directory exists
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_database_backup(self, schedule: str = BackupSchedule.DAILY) -> BackupRecord:
        """Create database backup."""
        backup_record = BackupRecord(
            backup_type=BackupType.DATABASE,
            backup_schedule=schedule,
            status='running',
            started_at=datetime.utcnow(),
            metadata={'compression': self.compression_enabled}
        )
        db.session.add(backup_record)
        db.session.commit()
        
        try:
            # Generate backup filename
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"database_{schedule}_{timestamp}.sql"
            if self.compression_enabled:
                filename += ".gz"
            
            backup_path = os.path.join(self.backup_dir, filename)
            
            # Get database connection details
            db_config = self._get_database_config()
            
            # Create backup using pg_dump
            cmd = [
                'pg_dump',
                '--host', db_config['host'],
                '--port', str(db_config['port']),
                '--username', db_config['user'],
                '--dbname', db_config['database'],
                '--verbose',
                '--clean',
                '--no-owner',
                '--no-privileges'
            ]
            
            if self.compression_enabled:
                # Use gzip compression
                with open(backup_path, 'wb') as f:
                    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    with gzip.open(f, 'wb') as gz_file:
                        for chunk in iter(lambda: process.stdout.read(4096), b''):
                            gz_file.write(chunk)
                    
                    process.wait()
                    
                    if process.returncode != 0:
                        error = process.stderr.read().decode()
                        raise Exception(f"pg_dump failed: {error}")
            else:
                # No compression
                with open(backup_path, 'w') as f:
                    process = subprocess.Popen(cmd, stdout=f, stderr=subprocess.PIPE)
                    process.wait()
                    
                    if process.returncode != 0:
                        error = process.stderr.read().decode()
                        raise Exception(f"pg_dump failed: {error}")
            
            # Calculate checksum
            checksum = self._calculate_checksum(backup_path)
            file_size = os.path.getsize(backup_path)
            
            # Update backup record
            backup_record.file_path = backup_path
            backup_record.file_size = file_size
            backup_record.checksum = checksum
            backup_record.status = 'completed'
            backup_record.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            # Clean up old backups
            self._cleanup_old_backups(BackupType.DATABASE, schedule)
            
            current_app.logger.info(f"Database backup completed: {backup_path}")
            
            return backup_record
            
        except Exception as e:
            backup_record.status = 'failed'
            backup_record.error_message = str(e)
            backup_record.completed_at = datetime.utcnow()
            db.session.commit()
            
            current_app.logger.error(f"Database backup failed: {e}")
            raise
    
    def create_files_backup(self, schedule: str = BackupSchedule.WEEKLY) -> BackupRecord:
        """Create files backup."""
        backup_record = BackupRecord(
            backup_type=BackupType.FILES,
            backup_schedule=schedule,
            status='running',
            started_at=datetime.utcnow(),
            metadata={'compression': self.compression_enabled}
        )
        db.session.add(backup_record)
        db.session.commit()
        
        try:
            # Generate backup filename
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"files_{schedule}_{timestamp}.tar"
            if self.compression_enabled:
                filename += ".gz"
            
            backup_path = os.path.join(self.backup_dir, filename)
            
            # Directories to backup
            app_root = current_app.root_path
            directories_to_backup = [
                'templates',
                'static',
                'uploads',
                'logs'
            ]
            
            # Create tar archive
            cmd = ['tar', '-cf', backup_path.replace('.gz', '')]
            for directory in directories_to_backup:
                dir_path = os.path.join(app_root, directory)
                if os.path.exists(dir_path):
                    cmd.append(directory)
            
            # Run tar command
            result = subprocess.run(cmd, cwd=app_root, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"tar failed: {result.stderr}")
            
            # Compress if enabled
            if self.compression_enabled:
                with open(backup_path.replace('.gz', ''), 'rb') as f_in:
                    with gzip.open(backup_path, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                os.remove(backup_path.replace('.gz', ''))
            
            # Calculate checksum
            checksum = self._calculate_checksum(backup_path)
            file_size = os.path.getsize(backup_path)
            
            # Update backup record
            backup_record.file_path = backup_path
            backup_record.file_size = file_size
            backup_record.checksum = checksum
            backup_record.status = 'completed'
            backup_record.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            # Clean up old backups
            self._cleanup_old_backups(BackupType.FILES, schedule)
            
            current_app.logger.info(f"Files backup completed: {backup_path}")
            
            return backup_record
            
        except Exception as e:
            backup_record.status = 'failed'
            backup_record.error_message = str(e)
            backup_record.completed_at = datetime.utcnow()
            db.session.commit()
            
            current_app.logger.error(f"Files backup failed: {e}")
            raise
    
    def create_config_backup(self, schedule: str = BackupSchedule.MONTHLY) -> BackupRecord:
        """Create configuration backup."""
        backup_record = BackupRecord(
            backup_type=BackupType.CONFIG,
            backup_schedule=schedule,
            status='running',
            started_at=datetime.utcnow()
        )
        db.session.add(backup_record)
        db.session.commit()
        
        try:
            # Generate backup filename
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"config_{schedule}_{timestamp}.json"
            if self.compression_enabled:
                filename += ".gz"
            
            backup_path = os.path.join(self.backup_dir, filename)
            
            # Collect configuration data
            config_data = {
                'app_config': current_app.config,
                'environment_variables': {
                    key: value for key, value in os.environ.items()
                    if not key.lower().startswith('password') and not key.lower().startswith('secret')
                },
                'database_config': self._get_database_config(),
                'backup_timestamp': timestamp
            }
            
            # Save configuration
            if self.compression_enabled:
                with gzip.open(backup_path, 'wt', encoding='utf-8') as f:
                    json.dump(config_data, f, indent=2, default=str)
            else:
                with open(backup_path, 'w') as f:
                    json.dump(config_data, f, indent=2, default=str)
            
            # Calculate checksum
            checksum = self._calculate_checksum(backup_path)
            file_size = os.path.getsize(backup_path)
            
            # Update backup record
            backup_record.file_path = backup_path
            backup_record.file_size = file_size
            backup_record.checksum = checksum
            backup_record.status = 'completed'
            backup_record.completed_at = datetime.utcnow()
            
            db.session.commit()
            
            # Clean up old backups
            self._cleanup_old_backups(BackupType.CONFIG, schedule)
            
            current_app.logger.info(f"Configuration backup completed: {backup_path}")
            
            return backup_record
            
        except Exception as e:
            backup_record.status = 'failed'
            backup_record.error_message = str(e)
            backup_record.completed_at = datetime.utcnow()
            db.session.commit()
            
            current_app.logger.error(f"Configuration backup failed: {e}")
            raise
    
    def restore_database(self, backup_file: str) -> bool:
        """Restore database from backup."""
        try:
            backup_path = os.path.join(self.backup_dir, backup_file)
            
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            # Verify backup integrity
            stored_record = BackupRecord.query.filter_by(file_path=backup_path).first()
            if stored_record:
                current_checksum = self._calculate_checksum(backup_path)
                if current_checksum != stored_record.checksum:
                    raise ValueError("Backup file checksum mismatch - file may be corrupted")
            
            # Get database configuration
            db_config = self._get_database_config()
            
            # Restore using psql
            cmd = [
                'psql',
                '--host', db_config['host'],
                '--port', str(db_config['port']),
                '--username', db_config['user'],
                '--dbname', db_config['database']
            ]
            
            if backup_path.endswith('.gz'):
                # Decompressed restore
                with gzip.open(backup_path, 'rt') as f:
                    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate(input=f.read())
            else:
                # Direct restore
                with open(backup_path, 'r') as f:
                    process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
                    stdout, stderr = process.communicate(input=f.read())
            
            if process.returncode != 0:
                raise Exception(f"psql failed: {stderr.decode()}")
            
            current_app.logger.info(f"Database restored from: {backup_path}")
            return True
            
        except Exception as e:
            current_app.logger.error(f"Database restore failed: {e}")
            return False
    
    def _get_database_config(self) -> Dict[str, str]:
        """Get database configuration."""
        from app.config import Config
        
        return {
            'host': Config.DB_HOST,
            'port': Config.DB_PORT,
            'user': Config.DB_USER,
            'database': Config.DB_NAME
        }
    
    def _calculate_checksum(self, file_path: str) -> str:
        """Calculate SHA-256 checksum of file."""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _cleanup_old_backups(self, backup_type: str, schedule: str):
        """Clean up old backups based on retention policy."""
        max_keep = self.max_backups.get(schedule, 10)
        
        # Get old backups
        old_backups = BackupRecord.query.filter_by(
            backup_type=backup_type,
            backup_schedule=schedule,
            status='completed'
        ).order_by(BackupRecord.started_at.desc()).offset(max_keep).all()
        
        for backup in old_backups:
            try:
                if os.path.exists(backup.file_path):
                    os.remove(backup.file_path)
                    current_app.logger.info(f"Removed old backup: {backup.file_path}")
                
                db.session.delete(backup)
            except Exception as e:
                current_app.logger.error(f"Failed to remove old backup {backup.file_path}: {e}")
        
        db.session.commit()
    
    def get_backup_status(self) -> Dict[str, Any]:
        """Get backup system status."""
        recent_backups = BackupRecord.query.filter(
            BackupRecord.started_at >= datetime.utcnow() - timedelta(days=7)
        ).order_by(BackupRecord.started_at.desc()).all()
        
        status = {
            'total_backups': len(recent_backups),
            'successful_backups': len([b for b in recent_backups if b.status == 'completed']),
            'failed_backups': len([b for b in recent_backups if b.status == 'failed']),
            'last_backup': recent_backups[0].started_at if recent_backups else None,
            'backup_directory': self.backup_dir,
            'disk_usage': self._get_disk_usage()
        }
        
        return status
    
    def _get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage statistics."""
        try:
            total, used, free = shutil.disk_usage(self.backup_dir)
            return {
                'total_gb': total // (1024**3),
                'used_gb': used // (1024**3),
                'free_gb': free // (1024**3),
                'usage_percent': (used / total) * 100
            }
        except Exception:
            return {'error': 'Unable to get disk usage'}
    
    def test_backup_system(self) -> Dict[str, Any]:
        """Test backup system functionality."""
        results = {
            'database_backup': False,
            'files_backup': False,
            'config_backup': False,
            'restore_test': False,
            'errors': []
        }
        
        try:
            # Test database backup
            backup = self.create_database_backup(BackupSchedule.HOURLY)
            results['database_backup'] = backup.status == 'completed'
            
            # Test files backup
            backup = self.create_files_backup(BackupSchedule.HOURLY)
            results['files_backup'] = backup.status == 'completed'
            
            # Test config backup
            backup = self.create_config_backup(BackupSchedule.HOURLY)
            results['config_backup'] = backup.status == 'completed'
            
        except Exception as e:
            results['errors'].append(str(e))
        
        return results


class BackupScheduler:
    """Backup scheduler service."""
    
    def __init__(self):
        self.backup_service = BackupService()
        self.running = False
        self.scheduler_thread = None
    
    def start_scheduler(self):
        """Start the backup scheduler."""
        if self.running:
            return
        
        self.running = True
        
        def run_scheduler():
            # Schedule backups
            schedule.every().hour.do(self._hourly_backup)
            schedule.every().day.at("02:00").do(self._daily_backup)
            schedule.every().sunday.at("03:00").do(self._weekly_backup)
            schedule.every().month.do(self._monthly_backup)
            
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        
        self.scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        current_app.logger.info("Backup scheduler started")
    
    def stop_scheduler(self):
        """Stop the backup scheduler."""
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        
        current_app.logger.info("Backup scheduler stopped")
    
    def _hourly_backup(self):
        """Hourly backup task."""
        try:
            self.backup_service.create_database_backup(BackupSchedule.HOURLY)
        except Exception as e:
            current_app.logger.error(f"Hourly backup failed: {e}")
    
    def _daily_backup(self):
        """Daily backup task."""
        try:
            self.backup_service.create_database_backup(BackupSchedule.DAILY)
        except Exception as e:
            current_app.logger.error(f"Daily backup failed: {e}")
    
    def _weekly_backup(self):
        """Weekly backup task."""
        try:
            self.backup_service.create_database_backup(BackupSchedule.WEEKLY)
            self.backup_service.create_files_backup(BackupSchedule.WEEKLY)
        except Exception as e:
            current_app.logger.error(f"Weekly backup failed: {e}")
    
    def _monthly_backup(self):
        """Monthly backup task."""
        try:
            self.backup_service.create_database_backup(BackupSchedule.MONTHLY)
            self.backup_service.create_files_backup(BackupSchedule.MONTHLY)
            self.backup_service.create_config_backup(BackupSchedule.MONTHLY)
        except Exception as e:
            current_app.logger.error(f"Monthly backup failed: {e}")


# Global backup scheduler instance
backup_scheduler = BackupScheduler()
