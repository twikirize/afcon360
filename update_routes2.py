with open('app/admin/owner/routes.py', 'r') as f:
    content = f.read()

old = """@owner_bp.route('/settings/payment-methods/<int:method_id>', methods=['PUT'])
@owner_or_superadmin_required
def update_payment_method(method_id):
    \"\"\"Update payment method configuration (full update)\"\"\"
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        from app.wallet.services.admin_audit_service import AdminAuditService
        from flask_login import current_user
        
        method = PaymentMethodConfig.query.get_or_404(method_id)
        data = request.get_json()
        
        # Fields that can be updated
        updatable_fields = [
            'display_name', 'method_type', 'provider_name', 'country_code',
            'is_enabled', 'is_active', 'requires_phone',
            'supported_currencies', 'allowed_timings',
            'min_amount', 'max_amount', 'transaction_fee',
            'sandbox_url', 'production_url', 'use_sandbox',
            'marketplace_collection_implemented',
            'config_json'
        ]
        
        old_values = {}
        for field in updatable_fields:
            if field in data:
                old_values[field] = getattr(method, field)
                new_value = data[field]
                
                # Type conversion for numeric fields
                if field in ['min_amount', 'max_amount', 'transaction_fee']:
                    new_value = float(new_value) if new_value is not None else None
                elif field in ['is_enabled', 'is_active', 'requires_phone', 'use_sandbox', 'marketplace_collection_implemented']:
                    new_value = bool(new_value)
                
                setattr(method, field, new_value)
        
        db.session.commit()
        
        # Audit log
        try:
            new_values = {k: data[k] for k in old_values}
            AdminAuditService.log_action(
                admin_id=current_user.id,
                admin_name=current_user.username,
                admin_role='owner',
                action_type='update',
                action_category='payment_method_config',
                target_type='payment_method',
                target_id=str(method.id),
                target_name=method.method_id,
                old_value=old_values,
                new_value=new_values,
                reason=f'Updated payment method {method.method_id} configuration'
            )
        except Exception as audit_e:
            current_app.logger.error(f"Audit log error: {audit_e}")
        
        return jsonify({'success': True, 'message': 'Payment method updated successfully'})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Update payment method error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500"""

new = """@owner_bp.route('/settings/payment-methods/<int:method_id>', methods=['PUT'])
@owner_or_superadmin_required
def update_payment_method(method_id):
    \"\"\"Update payment method configuration (full update)\"\"\"
    try:
        from app.wallet.models.payment_method import PaymentMethodConfig
        from app.wallet.services.admin_audit_service import AdminAuditService
        from flask_login import current_user
        
        method = PaymentMethodConfig.query.get_or_404(method_id)
        data = request.get_json()
        
        # Fields that can be updated
        updatable_fields = [
            'display_name', 'method_type', 'provider_name', 'country_code',
            'is_enabled', 'is_active', 'requires_phone',
            'supported_currencies', 'allowed_timings',
            'min_amount', 'max_amount', 'transaction_fee',
            'sandbox_url', 'production_url', 'use_sandbox',
            'marketplace_collection_implemented',
            'config_json'
        ]
        
        # Capture old audit snapshot before change
        old_snapshot = method.to_audit_dict()
        
        for field in updatable_fields:
            if field in data:
                new_value = data[field]
                
                # Type conversion for numeric fields
                if field in ['min_amount', 'max_amount', 'transaction_fee']:
                    new_value = float(new_value) if new_value is not None else None
                elif field in ['is_enabled', 'is_active', 'requires_phone', 'use_sandbox', 'marketplace_collection_implemented']:
                    new_value = bool(new_value)
                
                setattr(method, field, new_value)
        
        with AdminAuditService.audited_change():
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
                reason=f'Updated payment method {method.method_id} configuration'
            )
        
        return jsonify({'success': True, 'message': 'Payment method updated successfully'})
    except Exception as e:
        current_app.logger.error(f"Update payment method error: {e}")
        return jsonify({'success': False, 'error': 'Change not saved \u2014 audit record could not be created. No configuration was modified.'}), 409"""

if old in content:
    content = content.replace(old, new)
    with open('app/admin/owner/routes.py', 'w') as f:
        f.write(content)
    print('SUCCESS: update_payment_method updated')
else:
    print('FAIL: old text not found')