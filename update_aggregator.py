with open('app/wallet/services/aggregator_service.py', 'r') as f:
    content = f.read()

# Update create_aggregator
old1 = """            db.session.add(aggregator)
            db.session.commit()
            
            # Log the action
            if admin_id and admin_name:
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='create',
                    action_category='aggregator',
                    target_type='aggregator',
                    target_id=str(aggregator.id),
                    target_name=display_name,
                    new_value=aggregator.to_dict(),
                    reason='New aggregator created'
                )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e"""

new1 = """            db.session.add(aggregator)
            
            # Log the action
            if admin_id and admin_name:
                with AdminAuditService.audited_change():
                    AdminAuditService.log_action(
                        admin_id=admin_id,
                        admin_name=admin_name,
                        admin_role=admin_role,
                        action_type='create',
                        action_category='aggregator',
                        target_type='aggregator',
                        target_id=str(aggregator.id),
                        target_name=display_name,
                        new_value=aggregator.to_audit_dict(),
                        reason='New aggregator created'
                    )
            
            return aggregator
        except Exception as e:
            raise e"""

# Update update_aggregator
old2 = """            old_value = aggregator.to_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(aggregator, key):
                    setattr(aggregator, key, value)
            
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='modify',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                old_value=old_value,
                new_value=aggregator.to_dict(),
                reason='Aggregator configuration updated'
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e"""

new2 = """            old_snapshot = aggregator.to_audit_dict()
            
            # Update fields
            for key, value in updates.items():
                if hasattr(aggregator, key):
                    setattr(aggregator, key, value)
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='modify',
                    action_category='aggregator',
                    target_type='aggregator',
                    target_id=str(aggregator.id),
                    target_name=aggregator.display_name,
                    old_value=old_snapshot,
                    new_value=aggregator.to_audit_dict(),
                    reason='Aggregator configuration updated'
                )
            
            return aggregator
        except Exception as e:
            raise e"""

# Update suspend_aggregator
old3 = """            aggregator.status = 'suspended'
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='suspend',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                reason=reason
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e"""

new3 = """            old_snapshot = aggregator.to_audit_dict()
            aggregator.status = 'suspended'
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='suspend',
                    action_category='aggregator',
                    target_type='aggregator',
                    target_id=str(aggregator.id),
                    target_name=aggregator.display_name,
                    old_value=old_snapshot,
                    new_value=aggregator.to_audit_dict(),
                    reason=reason
                )
            
            return aggregator
        except Exception as e:
            raise e"""

# Update activate_aggregator
old4 = """            aggregator.status = 'active'
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='activate',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                reason=reason
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e"""

new4 = """            old_snapshot = aggregator.to_audit_dict()
            aggregator.status = 'active'
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='activate',
                    action_category='aggregator',
                    target_type='aggregator',
                    target_id=str(aggregator.id),
                    target_name=aggregator.display_name,
                    old_value=old_snapshot,
                    new_value=aggregator.to_audit_dict(),
                    reason=reason
                )
            
            return aggregator
        except Exception as e:
            raise e"""

# Update set_aggregator_mode
old5 = """            old_mode = aggregator.mode
            aggregator.mode = mode
            
            # If switching to live, ensure live credentials exist or copy primary if set
            if mode == 'live' and not aggregator.live_api_key and aggregator.api_key:
                aggregator.live_api_key = aggregator.api_key
                aggregator.live_api_secret = aggregator.api_secret
            
            db.session.commit()
            
            # Log the action
            AdminAuditService.log_action(
                admin_id=admin_id,
                admin_name=admin_name,
                admin_role=admin_role,
                action_type='set_mode',
                action_category='aggregator',
                target_type='aggregator',
                target_id=str(aggregator.id),
                target_name=aggregator.display_name,
                old_value=old_mode,
                new_value=mode,
                reason=reason
            )
            
            return aggregator
        except Exception as e:
            db.session.rollback()
            raise e"""

new5 = """            old_snapshot = aggregator.to_audit_dict()
            old_mode = aggregator.mode
            aggregator.mode = mode
            
            # If switching to live, ensure live credentials exist or copy primary if set
            if mode == 'live' and not aggregator.live_api_key and aggregator.api_key:
                aggregator.live_api_key = aggregator.api_key
                aggregator.live_api_secret = aggregator.api_secret
            
            with AdminAuditService.audited_change():
                AdminAuditService.log_action(
                    admin_id=admin_id,
                    admin_name=admin_name,
                    admin_role=admin_role,
                    action_type='set_mode',
                    action_category='aggregator',
                    target_type='aggregator',
                    target_id=str(aggregator.id),
                    target_name=aggregator.display_name,
                    old_value=old_snapshot,
                    new_value=aggregator.to_audit_dict(),
                    reason=reason
                )
            
            return aggregator
        except Exception as e:
            raise e"""

if old1 in content:
    content = content.replace(old1, new1)
    print('Updated create_aggregator')
else:
    print('FAIL: create_aggregator not found')

if old2 in content:
    content = content.replace(old2, new2)
    print('Updated update_aggregator')
else:
    print('FAIL: update_aggregator not found')

if old3 in content:
    content = content.replace(old3, new3)
    print('Updated suspend_aggregator')
else:
    print('FAIL: suspend_aggregator not found')

if old4 in content:
    content = content.replace(old4, new4)
    print('Updated activate_aggregator')
else:
    print('FAIL: activate_aggregator not found')

if old5 in content:
    content = content.replace(old5, new5)
    print('Updated set_aggregator_mode')
else:
    print('FAIL: set_aggregator_mode not found')

with open('app/wallet/services/aggregator_service.py', 'w') as f:
    f.write(content)