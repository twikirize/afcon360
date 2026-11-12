with open('app/admin/owner/routes.py', 'r') as f:
    content = f.read()

old = """@owner_bp.route('/settings/payment-methods/<int:method_id>/toggle', methods=['POST'])
@owner_or_superadmin_required
def toggle_payment_method(method_id):
    \"\"\"Toggle payment method marketplace collection, enabled, or active status\"\"\"
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        from app.wallet.services.admin_audit_service import AdminAuditService
        from flask_login import current_user
        
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        data = request.get_json() or {}
        field = data.get('field')
        value = data.get('value')
        
        if field not in ['marketplace_collection_implemented', 'is_enabled', 'is_active']:
            return jsonify({'success': False, 'error': 'Invalid field'}), 400
        
        old_value = getattr(method, field)
        new_value = bool(value)
        
        if old_value == new_value:
            return jsonify({'success': True, 'message': 'No change', 'value': new_value})
        
        setattr(method, field, new_value)
        db.session.commit()
        
        # Audit log
        try:
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                action_type='update',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value={field: old_value},
                new_value={field: new_value},
                reason=f'Toggled payment method {method.method_id} {field} to {new_value}'
            )
        except Exception as audit_e:
            current_app.logger.error(f"Audit log error: {audit_e}")
        
        return jsonify({'success': True, 'value': new_value, 'message': f'{field} set to {new_value}'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Toggle payment method error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500"""

new = """@owner_bp.route('/settings/payment-methods/<int:method_id>/toggle', methods=['POST'])
@owner_or_superadmin_required
def toggle_payment_method(method_id):
    \"\"\"Toggle payment method marketplace collection, enabled, or active status\"\"\"
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        from app.wallet.services.admin_audit_service import AdminAuditService
        from flask_login import current_user
        
        method = PaymentMethodConfig.query.get_or_404(method_id)
        
        data = request.get_json() or {}
        field = data.get('field')
        value = data.get('value')
        
        if field not in ['marketplace_collection_implemented', 'is_enabled', 'is_active']:
            return jsonify({'success': False, 'error': 'Invalid field'}), 400
        
        old_value = getattr(method, field)
        new_value = bool(value)
        
        if old_value == new_value:
            return jsonify({'success': True, 'message': 'No change', 'value': new_value})
        
        # Capture old audit snapshot before change
        old_snapshot = method.to_audit_dict()
        
        with AdminAuditService.audited_change():
            setattr(method, field, new_value)
            
            # Log the action with audit snapshots
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                action_type='update',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value=old_snapshot,
                new_value=method.to_audit_dict(),
                reason=f'Toggled payment method {method.method_id} {field} to {new_value}'
            )
        
        return jsonify({'success': True, 'value': new_value, 'message': f'{field} set to {new_value}'})
    except Exception as e:
        current_app.logger.error(f"Toggle payment method error: {e}")
        return jsonify({'success': False, 'error': 'Change not saved \u2014 audit record could not be created. No configuration was modified.'}), 409"""

if old in content:
    content = content.replace(old, new)
    with open('app/admin/owner/routes.py', 'w') as f:
        f.write(content)
    print('SUCCESS: toggle_payment_method updated')
else:
    print('FAIL: old text not found')