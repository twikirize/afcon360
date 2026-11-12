with open('app/wallet/services/fraud_detection_service.py', 'r') as f:
    content = f.read()

old = """            old_value = config.to_dict()
            
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            db.session.commit()
            
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='modify',
                action_category='fraud_detection',
                target_type='fraud_config',
                target_id=str(config.id),
                target_name='Fraud Detection Configuration',
                old_value=old_value,
                new_value=config.to_dict(),
                reason='Fraud detection configuration updated'
            )
            
            return config
        except Exception as e:
            db.session.rollback()
            raise e"""

new = """            old_snapshot = config.to_audit_dict()
            
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='modify',
                    action_category='fraud_detection',
                    target_type='fraud_config',
                    target_id=str(config.id),
                    target_name='Fraud Detection Configuration',
                    old_value=old_snapshot,
                    new_value=config.to_audit_dict(),
                    reason='Fraud detection configuration updated'
                )
            
            return config
        except Exception as e:
            raise e"""

if old in content:
    content = content.replace(old, new)
    print('SUCCESS: fraud_detection_service updated')
else:
    print('FAIL: fraud_detection_service not found')

with open('app/wallet/services/fraud_detection_service.py', 'w') as f:
    f.write(content)