with open('app/wallet/services/nonce_protection_service.py', 'r') as f:
    content = f.read()

old = """            # Store old value for audit
            old_value = config.to_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='modify',
                action_category='nonce_protection',
                target_type='nonce_config',
                target_id=str(config.id),
                target_name='Nonce Protection Configuration',
                old_value=old_value,
                new_value=config.to_dict(),
                reason='Nonce protection configuration updated'
            )
            
            return config
        except Exception as e:
            db.session.rollback()
            raise e"""

new = """            old_snapshot = config.to_audit_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='modify',
                    action_category='nonce_protection',
                    target_type='nonce_config',
                    target_id=str(config.id),
                    target_name='Nonce Protection Configuration',
                    old_value=old_snapshot,
                    new_value=config.to_audit_dict(),
                    reason='Nonce protection configuration updated'
                )
            
            return config
        except Exception as e:
            raise e"""

if old in content:
    content = content.replace(old, new)
    print('SUCCESS: nonce_protection_service updated')
else:
    print('FAIL: nonce_protection_service not found')

with open('app/wallet/services/nonce_protection_service.py', 'w') as f:
    f.write(content)