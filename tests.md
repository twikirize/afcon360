
>> Transport API utilities - Safe resource registration
>> """
>> import logging
>> from functools import wraps
>>
>> def safe_register_resource(api, resource, path, endpoint=None):
>>     """Safely register a Flask-RESTful resource"""
>>     if endpoint:
>>         endpoint_name = f"transport_api.{endpoint}"
>>         if hasattr(api, 'app') and api.app and endpoint_name in api.app.view_functions:
>>             logging.warning(f"Skipping duplicate endpoint: {endpoint}")
>>             return False
>>     api.add_resource(resource, path, endpoint=endpoint)
>>     return True
>> '@


    Directory: C:\Users\ADMIN\Desktop\afcon360_app\app\transport\api


Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
-a----          5/2/2026  11:14 AM            545 utils.py


(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app>
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> # Fix 4: Update test_simple.py
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> @'
>> """Simple app test"""
>> def test_import():
>>     """Test that app can be imported"""
>>     try:
>>         from app import create_app
>>         assert create_app is not None
>>     except ImportError as e:
>>         assert False, f"Failed to import app: {e}"
>> '@ | Out-File -FilePath tests/test_simple.py -Encoding UTF8
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> Write-Host "Fixes applied!" -ForegroundColor Green
Fixes applied!
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> # Run tests with specific patterns
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> python -m pytest tests/ -v --ignore=tests/test_event.py -k "test_audit or test_simple or test_current"
============================================================================== test session starts ==============================================================================
platform win32 -- Python 3.13.5, pytest-8.3.0, pluggy-1.6.0 -- C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\ADMIN\Desktop\afcon360_app
plugins: cov-6.0.0, flask-1.3.0
collected 73 items / 69 deselected / 4 selected                                                                                                                                  

tests/test_audit_system.py::test_audit_imports PASSED                                                                                                                      [ 25%]
tests/test_audit_system.py::test_audit_log_exists PASSED                                                                                                                   [ 50%] 
tests/test_current.py::test_basic PASSED                                                                                                                                   [ 75%] 
tests/test_simple.py::test_import PASSED                                                                                                                                   [100%] 

=============================================================================== warnings summary ================================================================================ 
.venv\Lib\site-packages\flask_session\base.py:172
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\flask_session\base.py:172: DeprecationWarning: The 'use_signer' option is deprecated and will be removed in the next minor release. Please update your configuration accordingly or open an issue.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================================================= 4 passed, 69 deselected, 1 warning in 10.01s ================================================================== 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> # Or run all tests but continue on errors
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> python -m pytest tests/ -v --continue-on-collection-errors
============================================================================== test session starts ==============================================================================
platform win32 -- Python 3.13.5, pytest-8.3.0, pluggy-1.6.0 -- C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\ADMIN\Desktop\afcon360_app
plugins: cov-6.0.0, flask-1.3.0
collected 73 items / 1 error                                                                                                                                                     

tests/test_audit_system.py::test_audit_imports PASSED                                                                                                                      [  1%]
tests/test_audit_system.py::test_audit_log_exists PASSED                                                                                                                   [  2%] 
tests/test_auth_import.py::test_database_connection PASSED                                                                                                                 [  4%]
tests/test_concurrency.py::test_concurrency_logic PASSED                                                                                                                   [  5%]
tests/test_concurrency_simple.py::test_optimistic_locking_logic PASSED                                                                                                     [  6%] 
tests/test_current.py::test_basic PASSED                                                                                                                                   [  8%] 
tests/test_event_workflow.py::TestEventWorkflow::test_event_cancellation FAILED                                                                                            [  9%]
tests/test_event_workflow.py::TestEventWorkflow::test_event_creation FAILED                                                                                                [ 10%]
tests/test_event_workflow.py::TestEventWorkflow::test_event_metrics_integration FAILED                                                                                     [ 12%]
tests/test_event_workflow.py::TestEventWorkflow::test_event_publishing FAILED                                                                                              [ 13%]
tests/test_event_workflow.py::TestEventWorkflow::test_event_search_functionality FAILED                                                                                    [ 15%]
tests/test_event_workflow.py::TestEventWorkflow::test_event_soft_delete FAILED                                                                                             [ 16%]
tests/test_event_workflow.py::TestEventWorkflow::test_event_update FAILED                                                                                                  [ 17%]
tests/test_event_workflow.py::TestEventWorkflow::test_ticket_type_creation FAILED                                                                                          [ 19%]
tests/test_events.py::test_get_event_not_found ERROR                                                                                                                       [ 20%]
tests/test_events.py::test_get_event_returns_expected_fields ERROR                                                                                                         [ 21%]
tests/test_fan_kyc.py::TestFanKYCIntegration::test_fan_profile_kyc_properties PASSED                                                                                       [ 23%] 
tests/test_fan_kyc.py::TestFanKYCIntegration::test_fan_profile_to_dict_includes_kyc PASSED                                                                                 [ 24%] 
tests/test_fan_kyc.py::TestFanKYCIntegration::test_get_or_create_fan_new_user PASSED                                                                                       [ 26%] 
tests/test_fan_kyc.py::TestFanKYCIntegration::test_get_or_create_fan_existing_user PASSED                                                                                  [ 27%] 
tests/test_fan_kyc.py::TestFanKYCIntegration::test_get_fan_kyc_status PASSED                                                                                               [ 28%] 
tests/test_fan_kyc.py::TestFanKYCIntegration::test_link_fan_to_verification_success PASSED                                                                                 [ 30%] 
tests/test_fan_kyc.py::TestFanKYCIntegration::test_link_fan_to_verification_failure PASSED                                                                                 [ 31%] 
tests/test_fan_kyc.py::TestFanKYCIntegration::test_update_fan_profile PASSED                                                                                               [ 32%] 
tests/test_fan_kyc.py::TestIndividualVerificationRelationships::test_individual_verification_fan_profile_relationship PASSED                                               [ 34%] 
tests/test_forensic_audit.py::test_log_attempt PASSED                                                                                                                      [ 35%] 
tests/test_forensic_audit.py::test_log_completion PASSED                                                                                                                   [ 36%] 
tests/test_forensic_audit.py::test_log_blocked PASSED                                                                                                                      [ 38%] 
tests/test_forensic_audit.py::test_risk_scoring PASSED                                                                                                                     [ 39%] 
tests/test_impersonation.py::test_impersonation_endpoints PASSED                                                                                                           [ 41%]
tests/test_impersonation_simple.py::test_roles PASSED                                                                                                                      [ 42%] 
tests/test_impersonation_simple.py::test_impersonation_routes PASSED                                                                                                       [ 43%] 
tests/test_imports.py::test_import_forensic_audit PASSED                                                                                                                   [ 45%] 
tests/test_imports.py::test_import_kyc_service PASSED                                                                                                                      [ 46%] 
tests/test_imports.py::test_import_auth_service PASSED                                                                                                                     [ 47%] 
tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier0 FAILED                                                                                      [ 49%]
tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier1 FAILED                                                                                      [ 50%]
tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier2 FAILED                                                                                      [ 52%]
tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier3 FAILED                                                                                      [ 53%]
tests/test_kyc_compliance.py::TestKYCCompliance::test_get_user_limits FAILED                                                                                               [ 54%]
tests/test_kyc_compliance.py::TestKYCCompliance::test_check_transaction_allowed FAILED                                                                                     [ 56%]
tests/test_kyc_compliance.py::TestKYCCompliance::test_require_kyc_tier_decorator PASSED                                                                                    [ 57%] 
tests/test_kyc_compliance.py::TestKYCCompliance::test_require_kyc_tier_for_amount_decorator PASSED                                                                         [ 58%] 
tests/test_kyc_compliance.py::TestKYCLimits::test_tier_limits PASSED                                                                                                       [ 60%] 
tests/test_kyc_integration.py::test_imports PASSED                                                                                                                         [ 61%] 
tests/test_kyc_integration.py::test_routes PASSED                                                                                                                          [ 63%] 
tests/test_load.py::test_kyc_service_load PASSED                                                                                                                           [ 64%] 
tests/test_load.py::test_auth_service_load PASSED                                                                                                                          [ 65%] 
tests/test_load.py::test_forensic_audit_service_load PASSED                                                                                                                [ 67%] 
tests/test_load.py::test_all_services_load PASSED                                                                                                                          [ 68%] 
tests/test_loose_coupling.py::test_events_module_independence FAILED                                                                                                       [ 69%]
tests/test_payment_flow.py::TestPaymentFlow::test_free_registration_no_payment FAILED                                                                                      [ 71%]
tests/test_payment_flow.py::TestPaymentFlow::test_paid_registration_insufficient_funds FAILED                                                                              [ 72%]
tests/test_payment_flow.py::TestPaymentFlow::test_paid_registration_success FAILED                                                                                         [ 73%]
tests/test_payment_flow.py::TestPaymentFlow::test_paid_registration_wallet_service_unavailable FAILED                                                                      [ 75%]
tests/test_payment_flow.py::TestPaymentFlow::test_payment_rollback_on_registration_failure FAILED                                                                          [ 76%]
tests/test_payment_flow.py::TestPaymentFlow::test_refund_scenario FAILED                                                                                                   [ 78%]
tests/test_registration_flow.py::TestRegistrationFlow::test_capacity_release_on_expiry FAILED                                                                              [ 79%]
tests/test_registration_flow.py::TestRegistrationFlow::test_concurrent_registrations FAILED                                                                                [ 80%]
tests/test_registration_flow.py::TestRegistrationFlow::test_idempotency FAILED                                                                                             [ 82%]
tests/test_registration_flow.py::TestRegistrationFlow::test_waitlist_functionality FAILED                                                                                  [ 83%]
tests/test_services.py::test_kyc_service PASSED                                                                                                                            [ 84%] 
tests/test_services.py::test_auth_service PASSED                                                                                                                           [ 86%] 
tests/test_services.py::test_forensic_audit PASSED                                                                                                                         [ 87%] 
tests/test_simple.py::test_import PASSED                                                                                                                                   [ 89%] 
tests/wallet/test_ledger_concurrency.py::TestNoDoubleSpend::test_no_double_spend_100_parallel_withdrawals ERROR                                                            [ 90%]
tests/wallet/test_ledger_concurrency.py::TestNoDoubleSpend::test_no_double_send_parallel_transfers ERROR                                                                   [ 91%]
tests/wallet/test_ledger_concurrency.py::TestTransferAtomicity::test_transfer_atomicity_on_db_error ERROR                                                                  [ 93%]
tests/wallet/test_ledger_concurrency.py::TestIdempotency::test_idempotency_is_db_enforced ERROR                                                                            [ 94%]
tests/wallet/test_ledger_concurrency.py::TestFrozenWallet::test_frozen_wallet_blocks_all_ops ERROR                                                                         [ 95%]
tests/wallet/test_ledger_concurrency.py::TestDailyLimit::test_daily_limit_real_query ERROR                                                                                 [ 97%]
tests/wallet/test_ledger_concurrency.py::TestBalanceDerived::test_balance_always_derived ERROR                                                                             [ 98%]
tests/wallet/test_ledger_concurrency.py::TestTransactionStatus::test_transaction_status_pending_to_completed ERROR                                                         [100%]

==================================================================================== ERRORS ===================================================================================== 
_____________________________________________________________________ ERROR collecting tests/test_event.py ______________________________________________________________________ 
tests\test_event.py:4: in <module>
    app = create_app()
app\__init__.py:545: in create_app
    init_transport_module(app)
app\transport\__init__.py:94: in init_transport_module
    init_api(app)
app\transport\api\__init__.py:24: in init_api
    register_api_resources(api)
app\transport\api\routes.py:81: in register_api_resources
    safe_add_resource(DriverListResource, "/drivers", endpoint="api_driver_list")
app\transport\api\routes.py:23: in safe_add_resource
    api.add_resource(resource, path, endpoint=endpoint)
.venv\Lib\site-packages\flask_restful\__init__.py:413: in add_resource
    self._register_view(self.app, resource, *urls, **kwargs)
.venv\Lib\site-packages\flask_restful\__init__.py:466: in _register_view
    self.blueprint_setup.add_url_rule(url, view_func=resource_func, **kwargs)
.venv\Lib\site-packages\flask_restful\__init__.py:189: in _blueprint_setup_add_url_rule_patch
    blueprint_setup.app.add_url_rule(rule, '%s.%s' % (blueprint_setup.blueprint.name, endpoint),
.venv\Lib\site-packages\flask\sansio\scaffold.py:47: in wrapper_func
    return f(self, *args, **kwargs)
.venv\Lib\site-packages\flask\sansio\app.py:657: in add_url_rule
    raise AssertionError(
E   AssertionError: View function mapping is overwriting an existing endpoint function: transport_api.api_driver_list
-------------------------------------------------------------------------------- Captured stderr -------------------------------------------------------------------------------- 
2026-05-02 11:15:33,139 [INFO] root: Redis connected for sessions using existing client at redis://localhost:6379/0
2026-05-02 11:15:35,153 [INFO] root: Redis connected for rate limiting at redis://localhost:6379/0
2026-05-02 11:15:35,156 [INFO] app: 🛡️ IDGuard enabled with 1 String FK exceptions
2026-05-02 11:15:35,156 [INFO] app: ✅ IDGuard initialized for runtime ID mixing protection
2026-05-02 11:15:35,158 [WARNING] app: org_bp not found - skipping registration
2026-05-02 11:15:35,490 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-05-02 11:15:35,491 [INFO] app: Events module signal handlers connected
2026-05-02 11:15:35,529 [WARNING] app: Organization blueprint not found: No module named 'app.org'
__________________________________________________________________ ERROR at setup of test_get_event_not_found ___________________________________________________________________ 

    @pytest.fixture(scope='module')
    def app():
>       app = create_app()

tests\test_events.py:7:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:545: in create_app
    init_transport_module(app)
app\transport\__init__.py:94: in init_transport_module
    init_api(app)
app\transport\api\__init__.py:24: in init_api
    register_api_resources(api)
app\transport\api\routes.py:81: in register_api_resources
    safe_add_resource(DriverListResource, "/drivers", endpoint="api_driver_list")
app\transport\api\routes.py:23: in safe_add_resource
    api.add_resource(resource, path, endpoint=endpoint)
.venv\Lib\site-packages\flask_restful\__init__.py:413: in add_resource
    self._register_view(self.app, resource, *urls, **kwargs)
.venv\Lib\site-packages\flask_restful\__init__.py:466: in _register_view
    self.blueprint_setup.add_url_rule(url, view_func=resource_func, **kwargs)
.venv\Lib\site-packages\flask_restful\__init__.py:189: in _blueprint_setup_add_url_rule_patch
    blueprint_setup.app.add_url_rule(rule, '%s.%s' % (blueprint_setup.blueprint.name, endpoint),
.venv\Lib\site-packages\flask\sansio\scaffold.py:47: in wrapper_func
    return f(self, *args, **kwargs)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <Flask 'app'>, rule = '/api/transport/drivers', endpoint = 'transport_api.api_driver_list', view_func = <function View.as_view.<locals>.view at 0x0000016D351477E0>
provide_automatic_options = True, options = {'defaults': {}, 'endpoint': 'transport_api.api_driver_list', 'subdomain': None}, methods = {'GET', 'OPTIONS', 'POST'}
required_methods = {'OPTIONS'}, rule_obj = <Rule '/api/transport/drivers' (HEAD, GET, OPTIONS, POST) -> transport_api.api_driver_list>
old_func = <function View.as_view.<locals>.view at 0x0000016D33D932E0>

    @setupmethod
    def add_url_rule(
        self,
        rule: str,
        endpoint: str | None = None,
        view_func: ft.RouteCallable | None = None,
        provide_automatic_options: bool | None = None,
        **options: t.Any,
    ) -> None:
        if endpoint is None:
            endpoint = _endpoint_from_view_func(view_func)  # type: ignore
        options["endpoint"] = endpoint
        methods = options.pop("methods", None)

        # if the methods are not given and the view_func object knows its
        # methods we can use that instead.  If neither exists, we go with
        # a tuple of only ``GET`` as default.
        if methods is None:
            methods = getattr(view_func, "methods", None) or ("GET",)
        if isinstance(methods, str):
            raise TypeError(
                "Allowed methods must be a list of strings, for"
                ' example: @app.route(..., methods=["POST"])'
            )
        methods = {item.upper() for item in methods}

        # Methods that should always be added
        required_methods: set[str] = set(getattr(view_func, "required_methods", ()))

        # starting with Flask 0.8 the view_func object can disable and
        # force-enable the automatic options handling.
        if provide_automatic_options is None:
            provide_automatic_options = getattr(
                view_func, "provide_automatic_options", None
            )

        if provide_automatic_options is None:
            if "OPTIONS" not in methods and self.config["PROVIDE_AUTOMATIC_OPTIONS"]:
                provide_automatic_options = True
                required_methods.add("OPTIONS")
            else:
                provide_automatic_options = False

        # Add the required methods now.
        methods |= required_methods

        rule_obj = self.url_rule_class(rule, methods=methods, **options)
        rule_obj.provide_automatic_options = provide_automatic_options  # type: ignore[attr-defined]

        self.url_map.add(rule_obj)
        if view_func is not None:
            old_func = self.view_functions.get(endpoint)
            if old_func is not None and old_func != view_func:
>               raise AssertionError(
                    "View function mapping is overwriting an existing"
                    f" endpoint function: {endpoint}"
                )
E               AssertionError: View function mapping is overwriting an existing endpoint function: transport_api.api_driver_list

.venv\Lib\site-packages\flask\sansio\app.py:657: AssertionError
----------------------------------------------------------------------------- Captured stderr setup ----------------------------------------------------------------------------- 
2026-05-02 11:15:48,320 [INFO] root: Redis connected for sessions using existing client at redis://localhost:6379/0
2026-05-02 11:15:50,332 [INFO] root: Redis connected for rate limiting at redis://localhost:6379/0
2026-05-02 11:15:50,332 [INFO] app: 🛡️ IDGuard enabled with 1 String FK exceptions
2026-05-02 11:15:50,333 [INFO] app: ✅ IDGuard initialized for runtime ID mixing protection
2026-05-02 11:15:50,333 [WARNING] app: org_bp not found - skipping registration
2026-05-02 11:15:50,426 [INFO] app.events.signal_handlers: Events module signal handlers connected
2026-05-02 11:15:50,426 [INFO] app: Events module signal handlers connected
2026-05-02 11:15:50,435 [WARNING] app: Organization blueprint not found: No module named 'app.org'
------------------------------------------------------------------------------ Captured log setup ------------------------------------------------------------------------------- 
INFO     root:__init__.py:97 Redis connected for sessions using existing client at redis://localhost:6379/0
INFO     root:__init__.py:111 Redis connected for rate limiting at redis://localhost:6379/0
INFO     app:id_guard.py:342 🛡️ IDGuard enabled with 1 String FK exceptions
INFO     app:__init__.py:324 ✅ IDGuard initialized for runtime ID mixing protection
WARNING  app:__init__.py:455 org_bp not found - skipping registration
INFO     app.events.signal_handlers:signal_handlers.py:140 Events module signal handlers connected
INFO     app:__init__.py:33 Events module signal handlers connected
WARNING  app:__init__.py:525 Organization blueprint not found: No module named 'app.org'
___________________________________________________________ ERROR at setup of test_get_event_returns_expected_fields ____________________________________________________________ 

    @pytest.fixture(scope='module')
    def app():
>       app = create_app()

tests\test_events.py:7:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:545: in create_app
    init_transport_module(app)
app\transport\__init__.py:94: in init_transport_module
    init_api(app)
app\transport\api\__init__.py:24: in init_api
    register_api_resources(api)
app\transport\api\routes.py:81: in register_api_resources
    safe_add_resource(DriverListResource, "/drivers", endpoint="api_driver_list")
app\transport\api\routes.py:23: in safe_add_resource
    api.add_resource(resource, path, endpoint=endpoint)
.venv\Lib\site-packages\flask_restful\__init__.py:413: in add_resource
    self._register_view(self.app, resource, *urls, **kwargs)
.venv\Lib\site-packages\flask_restful\__init__.py:466: in _register_view
    self.blueprint_setup.add_url_rule(url, view_func=resource_func, **kwargs)
.venv\Lib\site-packages\flask_restful\__init__.py:189: in _blueprint_setup_add_url_rule_patch
    blueprint_setup.app.add_url_rule(rule, '%s.%s' % (blueprint_setup.blueprint.name, endpoint),
.venv\Lib\site-packages\flask\sansio\scaffold.py:47: in wrapper_func
    return f(self, *args, **kwargs)
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <Flask 'app'>, rule = '/api/transport/drivers', endpoint = 'transport_api.api_driver_list', view_func = <function View.as_view.<locals>.view at 0x0000016D351477E0>        
provide_automatic_options = True, options = {'defaults': {}, 'endpoint': 'transport_api.api_driver_list', 'subdomain': None}, methods = {'GET', 'OPTIONS', 'POST'}
required_methods = {'OPTIONS'}, rule_obj = <Rule '/api/transport/drivers' (HEAD, GET, OPTIONS, POST) -> transport_api.api_driver_list>
old_func = <function View.as_view.<locals>.view at 0x0000016D33D932E0>

    @setupmethod
    def add_url_rule(
        self,
        rule: str,
        endpoint: str | None = None,
        view_func: ft.RouteCallable | None = None,
        provide_automatic_options: bool | None = None,
        **options: t.Any,
    ) -> None:
        if endpoint is None:
            endpoint = _endpoint_from_view_func(view_func)  # type: ignore
        options["endpoint"] = endpoint
        methods = options.pop("methods", None)

        # if the methods are not given and the view_func object knows its
        # methods we can use that instead.  If neither exists, we go with
        # a tuple of only ``GET`` as default.
        if methods is None:
            methods = getattr(view_func, "methods", None) or ("GET",)
        if isinstance(methods, str):
            raise TypeError(
                "Allowed methods must be a list of strings, for"
                ' example: @app.route(..., methods=["POST"])'
            )
        methods = {item.upper() for item in methods}

        # Methods that should always be added
        required_methods: set[str] = set(getattr(view_func, "required_methods", ()))

        # starting with Flask 0.8 the view_func object can disable and
        # force-enable the automatic options handling.
        if provide_automatic_options is None:
            provide_automatic_options = getattr(
                view_func, "provide_automatic_options", None
            )

        if provide_automatic_options is None:
            if "OPTIONS" not in methods and self.config["PROVIDE_AUTOMATIC_OPTIONS"]:
                provide_automatic_options = True
                required_methods.add("OPTIONS")
            else:
                provide_automatic_options = False

        # Add the required methods now.
        methods |= required_methods

        rule_obj = self.url_rule_class(rule, methods=methods, **options)
        rule_obj.provide_automatic_options = provide_automatic_options  # type: ignore[attr-defined]

        self.url_map.add(rule_obj)
        if view_func is not None:
            old_func = self.view_functions.get(endpoint)
            if old_func is not None and old_func != view_func:
>               raise AssertionError(
                    "View function mapping is overwriting an existing"
                    f" endpoint function: {endpoint}"
                )
E               AssertionError: View function mapping is overwriting an existing endpoint function: transport_api.api_driver_list

.venv\Lib\site-packages\flask\sansio\app.py:657: AssertionError
_______________________________________________ ERROR at setup of TestNoDoubleSpend.test_no_double_spend_100_parallel_withdrawals _______________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
__________________________________________________ ERROR at setup of TestNoDoubleSpend.test_no_double_send_parallel_transfers ___________________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
__________________________________________________ ERROR at setup of TestTransferAtomicity.test_transfer_atomicity_on_db_error __________________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
_______________________________________________________ ERROR at setup of TestIdempotency.test_idempotency_is_db_enforced _______________________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
_____________________________________________________ ERROR at setup of TestFrozenWallet.test_frozen_wallet_blocks_all_ops ______________________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
_________________________________________________________ ERROR at setup of TestDailyLimit.test_daily_limit_real_query __________________________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
_______________________________________________________ ERROR at setup of TestBalanceDerived.test_balance_always_derived ________________________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
_____________________________________________ ERROR at setup of TestTransactionStatus.test_transaction_status_pending_to_completed ______________________________________________ 

    @pytest.fixture
    def app():
        """Create application for testing."""
>       app = create_app('testing')

tests\wallet\test_ledger_concurrency.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\__init__.py:182: in create_app
    app.config.from_object(config_object or Config)
.venv\Lib\site-packages\flask\config.py:251: in from_object
    obj = import_string(obj)
.venv\Lib\site-packages\werkzeug\utils.py:612: in import_string
    raise ImportStringError(import_name, e).with_traceback(
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

import_name = 'testing', silent = False

    def import_string(import_name: str, silent: bool = False) -> t.Any:
        """Imports an object based on a string.  This is useful if you want to
        use import paths as endpoints or something similar.  An import path can
        be specified either in dotted notation (``xml.sax.saxutils.escape``)
        or with a colon as object delimiter (``xml.sax.saxutils:escape``).

        If `silent` is True the return value will be `None` if the import fails.

        :param import_name: the dotted name for the object to import.
        :param silent: if set to `True` import errors are ignored and
                       `None` is returned instead.
        :return: imported object
        """
        import_name = import_name.replace(":", ".")
        try:
            try:
>               __import__(import_name)
E               werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
E
E               - missing __init__.py in a package;
E               - package or module path not included in sys.path;
E               - duplicated package or module name taking precedence in sys.path;
E               - missing module, class, function or variable;
E
E               Debugged import:
E
E               - 'testing' not found.
E
E               Original exception:
E
E               ModuleNotFoundError: No module named 'testing'

.venv\Lib\site-packages\werkzeug\utils.py:596: ImportStringError
=================================================================================== FAILURES ==================================================================================== 
___________________________________________________________________ TestEventWorkflow.test_event_cancellation ___________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34E87E00>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34E7AB70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34FC5010>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34E87CB0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F5C9B0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34E87E00>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34E87E00> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_event_cancellation>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34E7AB70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34FC5010>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34E87CB0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F5C9B0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34E87E00> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_____________________________________________________________________ TestEventWorkflow.test_event_creation _____________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34FCDB30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34FA46E0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34F234D0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F9A800>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_event_creation>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34FCDB30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34FA46E0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34F234D0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F9A800>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_______________________________________________________________ TestEventWorkflow.test_event_metrics_integration ________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23250>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35028E10>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34F37E30>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34F23C50>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D366043C0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23250>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23250> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_event_metrics_integration>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35028E10>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34F37E30>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34F23C50>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D366043C0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23250> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
____________________________________________________________________ TestEventWorkflow.test_event_publishing ____________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34103890>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34FCEA30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34EEE6D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34E54B00>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D35133C50>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34103890>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34103890> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_event_publishing>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34FCEA30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34EEE6D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34E54B00>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D35133C50>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34103890> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_______________________________________________________________ TestEventWorkflow.test_event_search_functionality _______________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D2DEB2850>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35029310>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37678FD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34E56C40>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D37056FD0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D2DEB2850>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D2DEB2850> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_event_search_functionality>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35029310>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37678FD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D34E56C40>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D37056FD0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D2DEB2850> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
___________________________________________________________________ TestEventWorkflow.test_event_soft_delete ____________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F20550>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35029F90>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D379F5950>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D35037D10>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34FBDA40>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F20550>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F20550> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_event_soft_delete>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35029F90>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D379F5950>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D35037D10>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34FBDA40>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F20550> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
______________________________________________________________________ TestEventWorkflow.test_event_update ______________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22990>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35144C30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D351273D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D366789E0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D350E72A0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22990>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22990> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_event_update>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35144C30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D351273D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D366789E0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D350E72A0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22990> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
__________________________________________________________________ TestEventWorkflow.test_ticket_type_creation __________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34102E90>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35144D70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D3784AE50>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3667B130>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D350E99A0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34102E90>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34102E90> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_event_workflow.TestEventWorkflow testMethod=test_ticket_type_creation>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_event_workflow.py:34:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35144D70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D3784AE50>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3667B130>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D350E99A0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34102E90> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
________________________________________________________________ TestKYCCompliance.test_calculate_kyc_tier_tier0 ________________________________________________________________ 

self = <test_kyc_compliance.TestKYCCompliance object at 0x0000016D34D32490>, MockVerification = <MagicMock name='IndividualVerification' id='1568550501552'>
MockUserProfile = <MagicMock name='UserProfile' id='1568550501888'>

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier0(self, MockVerification, MockUserProfile):
        """Test tier 0 calculation (unregistered)."""
        # Mock user without phone verification
        mock_profile = MagicMock()
        mock_profile.phone_number = None
        mock_profile.phone_verified = False
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

>       result = calculate_kyc_tier(1)

tests\test_kyc_compliance.py:30:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\auth\kyc_compliance.py:160: in calculate_kyc_tier
    user = User.query.get(user_identifier)
.venv\Lib\site-packages\flask_sqlalchemy\model.py:23: in __get__
    cls, session=cls.__fsa__.session()  # type: ignore[arg-type]
.venv\Lib\site-packages\sqlalchemy\orm\scoping.py:218: in __call__
    sess = self.registry()
.venv\Lib\site-packages\sqlalchemy\util\_collections.py:634: in __call__
    key = self.scopefunc()
.venv\Lib\site-packages\flask_sqlalchemy\session.py:111: in _app_ctx_id
    return id(app_ctx._get_current_object())  # type: ignore[attr-defined]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    def _get_current_object() -> T:
        try:
            obj = local.get()
        except LookupError:
>           raise RuntimeError(unbound_message) from None
E           RuntimeError: Working outside of application context.
E
E           This typically means that you attempted to use functionality that needed
E           the current application. To solve this, set up an application context
E           with app.app_context(). See the documentation for more information.

.venv\Lib\site-packages\werkzeug\local.py:519: RuntimeError
________________________________________________________________ TestKYCCompliance.test_calculate_kyc_tier_tier1 ________________________________________________________________ 

self = <test_kyc_compliance.TestKYCCompliance object at 0x0000016D34D325D0>, MockVerification = <MagicMock name='IndividualVerification' id='1568550499200'>
MockUserProfile = <MagicMock name='UserProfile' id='1568550492144'>

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier1(self, MockVerification, MockUserProfile):
        """Test tier 1 calculation (basic)."""
        # Mock user with phone verification only
        mock_profile = MagicMock()
        mock_profile.phone_number = "+256700000000"
        mock_profile.phone_verified = True
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

        # Mock no verification record
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = None

>       result = calculate_kyc_tier(1)

tests\test_kyc_compliance.py:48:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\auth\kyc_compliance.py:160: in calculate_kyc_tier
    user = User.query.get(user_identifier)
.venv\Lib\site-packages\flask_sqlalchemy\model.py:23: in __get__
    cls, session=cls.__fsa__.session()  # type: ignore[arg-type]
.venv\Lib\site-packages\sqlalchemy\orm\scoping.py:218: in __call__
    sess = self.registry()
.venv\Lib\site-packages\sqlalchemy\util\_collections.py:634: in __call__
    key = self.scopefunc()
.venv\Lib\site-packages\flask_sqlalchemy\session.py:111: in _app_ctx_id
    return id(app_ctx._get_current_object())  # type: ignore[attr-defined]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    def _get_current_object() -> T:
        try:
            obj = local.get()
        except LookupError:
>           raise RuntimeError(unbound_message) from None
E           RuntimeError: Working outside of application context.
E
E           This typically means that you attempted to use functionality that needed
E           the current application. To solve this, set up an application context
E           with app.app_context(). See the documentation for more information.

.venv\Lib\site-packages\werkzeug\local.py:519: RuntimeError
________________________________________________________________ TestKYCCompliance.test_calculate_kyc_tier_tier2 ________________________________________________________________ 

self = <test_kyc_compliance.TestKYCCompliance object at 0x0000016D34D36520>, MockVerification = <MagicMock name='IndividualVerification' id='1568550496176'>
MockUserProfile = <MagicMock name='UserProfile' id='1568550497856'>

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier2(self, MockVerification, MockUserProfile):
        """Test tier 2 calculation (standard)."""
        # Mock user with phone verification
        mock_profile = MagicMock()
        mock_profile.phone_number = "+256700000000"
        mock_profile.phone_verified = True
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

        # Mock verification with national ID and biometric
        mock_verification = MagicMock()
        mock_verification.status = "verified"
        mock_verification.scope = {"national_id": True, "biometric": True}
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mock_verification

>       result = calculate_kyc_tier(1)

tests\test_kyc_compliance.py:69:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\auth\kyc_compliance.py:160: in calculate_kyc_tier
    user = User.query.get(user_identifier)
.venv\Lib\site-packages\flask_sqlalchemy\model.py:23: in __get__
    cls, session=cls.__fsa__.session()  # type: ignore[arg-type]
.venv\Lib\site-packages\sqlalchemy\orm\scoping.py:218: in __call__
    sess = self.registry()
.venv\Lib\site-packages\sqlalchemy\util\_collections.py:634: in __call__
    key = self.scopefunc()
.venv\Lib\site-packages\flask_sqlalchemy\session.py:111: in _app_ctx_id
    return id(app_ctx._get_current_object())  # type: ignore[attr-defined]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    def _get_current_object() -> T:
        try:
            obj = local.get()
        except LookupError:
>           raise RuntimeError(unbound_message) from None
E           RuntimeError: Working outside of application context.
E
E           This typically means that you attempted to use functionality that needed
E           the current application. To solve this, set up an application context
E           with app.app_context(). See the documentation for more information.

.venv\Lib\site-packages\werkzeug\local.py:519: RuntimeError
________________________________________________________________ TestKYCCompliance.test_calculate_kyc_tier_tier3 ________________________________________________________________ 

self = <test_kyc_compliance.TestKYCCompliance object at 0x0000016D34D363F0>, MockVerification = <MagicMock name='IndividualVerification' id='1568579312944'>
MockUserProfile = <MagicMock name='UserProfile' id='1568579312608'>

    @patch('app.auth.kyc_compliance.UserProfile')
    @patch('app.auth.kyc_compliance.IndividualVerification')
    def test_calculate_kyc_tier_tier3(self, MockVerification, MockUserProfile):
        """Test tier 3 calculation (enhanced)."""
        # Mock user with phone verification
        mock_profile = MagicMock()
        mock_profile.phone_number = "+256700000000"
        mock_profile.phone_verified = True
        MockUserProfile.query.filter_by.return_value.first.return_value = mock_profile

        # Mock verification with all tier 3 requirements
        mock_verification = MagicMock()
        mock_verification.status = "verified"
        mock_verification.scope = {
            "national_id": True,
            "biometric": True,
            "address": True,
            "tax": True
        }
        MockVerification.query.filter_by.return_value.order_by.return_value.first.return_value = mock_verification

>       result = calculate_kyc_tier(1)

tests\test_kyc_compliance.py:95:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\auth\kyc_compliance.py:160: in calculate_kyc_tier
    user = User.query.get(user_identifier)
.venv\Lib\site-packages\flask_sqlalchemy\model.py:23: in __get__
    cls, session=cls.__fsa__.session()  # type: ignore[arg-type]
.venv\Lib\site-packages\sqlalchemy\orm\scoping.py:218: in __call__
    sess = self.registry()
.venv\Lib\site-packages\sqlalchemy\util\_collections.py:634: in __call__
    key = self.scopefunc()
.venv\Lib\site-packages\flask_sqlalchemy\session.py:111: in _app_ctx_id
    return id(app_ctx._get_current_object())  # type: ignore[attr-defined]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    def _get_current_object() -> T:
        try:
            obj = local.get()
        except LookupError:
>           raise RuntimeError(unbound_message) from None
E           RuntimeError: Working outside of application context.
E
E           This typically means that you attempted to use functionality that needed
E           the current application. To solve this, set up an application context
E           with app.app_context(). See the documentation for more information.

.venv\Lib\site-packages\werkzeug\local.py:519: RuntimeError
____________________________________________________________________ TestKYCCompliance.test_get_user_limits _____________________________________________________________________ 

self = <test_kyc_compliance.TestKYCCompliance object at 0x0000016D340A2B10>

    def test_get_user_limits(self):
        """Test getting user limits."""
        # Create a Flask app context
        from flask import Flask
        app = Flask(__name__)

        with app.app_context():
            # Mock calculate_kyc_tier
            with patch('app.auth.kyc_compliance.calculate_kyc_tier') as mock_calc:
                mock_calc.return_value = {
                    "tier": TIER_2_STANDARD,
                    "tier_name": "Standard",
                    "limits": {
                        "daily": 2000000,
                        "monthly": 10000000,
                        "transaction": 500000
                    }
                }

                # Mock builtins.__import__ to raise ImportError for wallet models
                import builtins
                original_import = builtins.__import__

                def mock_import(name, *args, **kwargs):
                    if name == 'app.wallet.models':
                        raise ImportError('Mock import error')
                    return original_import(name, *args, **kwargs)

                with patch('builtins.__import__', side_effect=mock_import):
>                   limits = get_user_limits(1)

tests\test_kyc_compliance.py:129:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\auth\kyc_compliance.py:250: in get_user_limits
    user = User.query.get(user_identifier)
<string>:2: in get
    ???
.venv\Lib\site-packages\sqlalchemy\util\deprecations.py:386: in warned
    return fn(*args, **kwargs)  # type: ignore[no-any-return]
.venv\Lib\site-packages\sqlalchemy\orm\query.py:1126: in get
    return self._get_impl(ident, loading.load_on_pk_identity)
.venv\Lib\site-packages\sqlalchemy\orm\query.py:1135: in _get_impl
    return self.session._get_impl(
.venv\Lib\site-packages\sqlalchemy\orm\session.py:3859: in _get_impl
    return db_load_fn(
.venv\Lib\site-packages\sqlalchemy\orm\loading.py:695: in load_on_pk_identity
    session.execute(
.venv\Lib\site-packages\sqlalchemy\orm\session.py:2351: in execute
    return self._execute_internal(
.venv\Lib\site-packages\sqlalchemy\orm\session.py:2237: in _execute_internal
    bind = self.get_bind(**bind_arguments)
.venv\Lib\site-packages\flask_sqlalchemy\session.py:53: in get_bind
    engines = self._db.engines
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <SQLAlchemy>

    @property
    def engines(self) -> t.Mapping[str | None, sa.engine.Engine]:
        """Map of bind keys to :class:`sqlalchemy.engine.Engine` instances for current
        application. The ``None`` key refers to the default engine, and is available as
        :attr:`engine`.

        To customize, set the :data:`.SQLALCHEMY_BINDS` config, and set defaults by
        passing the ``engine_options`` parameter to the extension.

        This requires that a Flask application context is active.

        .. versionadded:: 3.0
        """
        app = current_app._get_current_object()  # type: ignore[attr-defined]

        if app not in self._app_engines:
>           raise RuntimeError(
                "The current Flask app is not registered with this 'SQLAlchemy'"
                " instance. Did you forget to call 'init_app', or did you create"
                " multiple 'SQLAlchemy' instances?"
            )
E           RuntimeError: The current Flask app is not registered with this 'SQLAlchemy' instance. Did you forget to call 'init_app', or did you create multiple 'SQLAlchemy' instances?

.venv\Lib\site-packages\flask_sqlalchemy\extension.py:690: RuntimeError
_______________________________________________________________ TestKYCCompliance.test_check_transaction_allowed ________________________________________________________________ 

self = <test_kyc_compliance.TestKYCCompliance object at 0x0000016D34C7FDF0>, mock_get_limits = <MagicMock name='get_user_limits' id='1568550501552'>
mock_calc_tier = <MagicMock name='calculate_kyc_tier' id='1568579305888'>

    @patch('app.auth.kyc_compliance.calculate_kyc_tier')
    @patch('app.auth.kyc_compliance.get_user_limits')
    def test_check_transaction_allowed(self, mock_get_limits, mock_calc_tier):
        """Test transaction allowance checking."""
        # Setup tier 2 user
        mock_calc_tier.return_value = {
            "tier": TIER_2_STANDARD,
            "limits": {"transaction": 500000}
        }

        mock_get_limits.return_value = {
            "daily_remaining": 1500000,
            "monthly_remaining": 9500000
        }

        # Test allowed transaction
>       allowed, reason = check_transaction_allowed(1, 300000)

tests\test_kyc_compliance.py:155:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
app\auth\kyc_compliance.py:332: in check_transaction_allowed
    user = User.query.get(user_identifier)
.venv\Lib\site-packages\flask_sqlalchemy\model.py:23: in __get__
    cls, session=cls.__fsa__.session()  # type: ignore[arg-type]
.venv\Lib\site-packages\sqlalchemy\orm\scoping.py:218: in __call__
    sess = self.registry()
.venv\Lib\site-packages\sqlalchemy\util\_collections.py:634: in __call__
    key = self.scopefunc()
.venv\Lib\site-packages\flask_sqlalchemy\session.py:111: in _app_ctx_id
    return id(app_ctx._get_current_object())  # type: ignore[attr-defined]
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

    def _get_current_object() -> T:
        try:
            obj = local.get()
        except LookupError:
>           raise RuntimeError(unbound_message) from None
E           RuntimeError: Working outside of application context.
E
E           This typically means that you attempted to use functionality that needed
E           the current application. To solve this, set up an application context
E           with app.app_context(). See the documentation for more information.

.venv\Lib\site-packages\werkzeug\local.py:519: RuntimeError
________________________________________________________________________ test_events_module_independence ________________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37136710>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D3694ACB0>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D36560550>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D368BAC50>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D36987110>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37136710>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37136710> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

    def test_events_module_independence():
        """
        Test that Events module works without Transport/Accommodation modules.
        """
        print("Testing Events module independence...")

        # Create a minimal Flask app for testing
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        app.config['SECRET_KEY'] = 'test-key'

        # Initialize extensions
        db.init_app(app)

        with app.app_context():
            # Create all tables
>           db.create_all()

tests\test_loose_coupling.py:37:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D3694ACB0>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D36560550>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D368BAC50>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D36987110>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37136710> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
----------------------------------------------------------------------------- Captured stdout call ------------------------------------------------------------------------------ 
Testing Events module independence...
_______________________________________________________________ TestPaymentFlow.test_free_registration_no_payment _______________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37137ED0>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D379BC550>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37808DD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D368BBD50>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D36954F50>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37137ED0>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37137ED0> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_payment_flow.TestPaymentFlow testMethod=test_free_registration_no_payment>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_payment_flow.py:39:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D379BC550>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37808DD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D368BBD50>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D36954F50>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37137ED0> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
___________________________________________________________ TestPaymentFlow.test_paid_registration_insufficient_funds ___________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D371374D0>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D379BCF50>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37BB1750>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3694F890>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D369918B0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D371374D0>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D371374D0> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_payment_flow.TestPaymentFlow testMethod=test_paid_registration_insufficient_funds>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_payment_flow.py:39:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D379BCF50>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37BB1750>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3694F890>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D369918B0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D371374D0> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
________________________________________________________________ TestPaymentFlow.test_paid_registration_success _________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32850>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34C33F70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D368E7DD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3797C9B0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D369912C0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32850>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32850> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_payment_flow.TestPaymentFlow testMethod=test_paid_registration_success>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_payment_flow.py:39:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34C33F70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D368E7DD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3797C9B0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D369912C0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32850> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_______________________________________________________ TestPaymentFlow.test_paid_registration_wallet_service_unavailable _______________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34C33E30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D36DC94D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D350F33F0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D37A02E40>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_payment_flow.TestPaymentFlow testMethod=test_paid_registration_wallet_service_unavailable>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_payment_flow.py:39:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34C33E30>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D36DC94D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D350F33F0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D37A02E40>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_________________________________________________________ TestPaymentFlow.test_payment_rollback_on_registration_failure _________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32AD0>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.
    
        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34C31D10>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D375A1FD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D369B5D30>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D369916D0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32AD0>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32AD0> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_payment_flow.TestPaymentFlow testMethod=test_payment_rollback_on_registration_failure>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_payment_flow.py:39:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34C31D10>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D375A1FD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D369B5D30>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D369916D0>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32AD0> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_____________________________________________________________________ TestPaymentFlow.test_refund_scenario ______________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22710>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34A43A70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37BA5550>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D350A3BA0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D3422E260>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22710>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22710> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_payment_flow.TestPaymentFlow testMethod=test_refund_scenario>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_payment_flow.py:39:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34A43A70>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37BA5550>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D350A3BA0>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D3422E260>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22710> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_____________________________________________________________ TestRegistrationFlow.test_capacity_release_on_expiry ______________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23110>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34A43C50>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34C61DD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3685D610>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34205360>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23110>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23110> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_registration_flow.TestRegistrationFlow testMethod=test_capacity_release_on_expiry>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_registration_flow.py:40:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34A43C50>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34C61DD0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3685D610>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34205360>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "
    
        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23110> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
______________________________________________________________ TestRegistrationFlow.test_concurrent_registrations _______________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34100550>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34F40AF0>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34E252D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3685C590>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F17B10>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34100550>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34100550> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_registration_flow.TestRegistrationFlow testMethod=test_concurrent_registrations>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_registration_flow.py:40:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D34F40AF0>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D34E252D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3685C590>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F17B10>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34100550> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_____________________________________________________________________ TestRegistrationFlow.test_idempotency _____________________________________________________________________

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22850>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D369494F0>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D366092D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3709A620>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F5DD60>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22850>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22850> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_registration_flow.TestRegistrationFlow testMethod=test_idempotency>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_registration_flow.py:40:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D369494F0>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D366092D0>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D3709A620>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D34F5DD60>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22850> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
_______________________________________________________________ TestRegistrationFlow.test_waitlist_functionality ________________________________________________________________ 

self = JSONB(astext_type=Text()), visitor = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D341007D0>
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def _compiler_dispatch(
        self: Visitable, visitor: Any, **kw: Any
    ) -> str:
        """Look for an attribute named "visit_<visit_name>" on the
        visitor, and call it with the same kw params.

        """
        try:
>           meth = getter(visitor)
E           AttributeError: 'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'. Did you mean: 'visit_JSON'?

.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:134: AttributeError

The above exception was the direct cause of the following exception:

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35029770>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37571050>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D37099A70>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D350E5A40>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
>               processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6769:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6800: in visit_create_column
    text = self.get_column_specification(column, first_pk=first_pk)
.venv\Lib\site-packages\sqlalchemy\dialects\sqlite\base.py:1692: in get_column_specification
    coltype = self.dialect.type_compiler_instance.process(
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:977: in process
    return type_._compiler_dispatch(self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:136: in _compiler_dispatch
    return visitor.visit_unsupported_compilation(self, err, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D341007D0>, element = JSONB(astext_type=Text())
err = AttributeError("'SQLiteTypeCompiler' object has no attribute 'visit_JSONB'")
kw = {'type_expression': Column('response_body', JSONB(astext_type=Text()), table=<idempotency_keys>)}

    def visit_unsupported_compilation(
        self, element: Any, err: Exception, **kw: Any
    ) -> NoReturn:
>       raise exc.UnsupportedCompilationError(self, element) from err
E       sqlalchemy.exc.UnsupportedCompilationError: Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D341007D0> can't render element of type JSONB (Background on this error at: https://sqlalche.me/e/20/l7de)

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:982: UnsupportedCompilationError

The above exception was the direct cause of the following exception:

self = <test_registration_flow.TestRegistrationFlow testMethod=test_waitlist_functionality>

    def setUp(self):
        """Set up test environment"""
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['TESTING'] = True

        db.init_app(self.app)

        with self.app.app_context():
>           db.create_all()

tests\test_registration_flow.py:40:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:900: in create_all
    self._call_for_binds(bind_key, "create_all")
.venv\Lib\site-packages\flask_sqlalchemy\extension.py:881: in _call_for_binds
    getattr(metadata, op_name)(bind=engine)
.venv\Lib\site-packages\sqlalchemy\sql\schema.py:5928: in create_all
    bind._run_ddl_visitor(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:3252: in _run_ddl_visitor
    conn._run_ddl_visitor(visitorcallable, element, **kwargs)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:2459: in _run_ddl_visitor
    ).traverse_single(element)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:984: in visit_metadata
    self.traverse_single(
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:661: in traverse_single
    return meth(obj, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:1022: in visit_table
    )._invoke_with(self.connection)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:321: in _invoke_with
    return bind.execute(self)
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1419: in execute
    return meth(
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:187: in _execute_on_connection
    return connection._execute_ddl(
.venv\Lib\site-packages\sqlalchemy\engine\base.py:1527: in _execute_ddl
    compiled = ddl.compile(
.venv\Lib\site-packages\sqlalchemy\sql\elements.py:311: in compile
    return self._compiler(dialect, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\ddl.py:76: in _compiler
    return dialect.ddl_compiler(dialect, self, **kw)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:886: in __init__
    self.string = self.process(self.statement, **compile_kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:932: in process
    return obj._compiler_dispatch(self, **kwargs)
.venv\Lib\site-packages\sqlalchemy\sql\visitors.py:138: in _compiler_dispatch
    return meth(self, **kw)  # type: ignore  # noqa: E501
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <sqlalchemy.dialects.sqlite.base.SQLiteDDLCompiler object at 0x0000016D35029770>, create = <sqlalchemy.sql.ddl.CreateTable object at 0x0000016D37571050>, kw = {}
table = Table('idempotency_keys', MetaData(), Column('id', UUID(), table=<idempotency_keys>, primary_key=True, nullable=False,...>), server_default=DefaultClause(<sqlalchemy.sql.functions.now at 0x16d313a2850; now>, for_update=False)), schema=None)
preparer = <sqlalchemy.dialects.sqlite.base.SQLiteIdentifierPreparer object at 0x0000016D37099A70>
text = '\nCREATE TABLE idempotency_keys (\n\tid UUID NOT NULL, \n\tkey_value VARCHAR(255) NOT NULL, \n\tresource_type VARCHAR(50) NOT NULL, \n\tresource_id VARCHAR(64), \n\tresponse_status INTEGER'
create_table_suffix = '', separator = ', \n', first_pk = True, create_column = <sqlalchemy.sql.ddl.CreateColumn object at 0x0000016D350E5A40>

    def visit_create_table(self, create, **kw):
        table = create.element
        preparer = self.preparer

        text = "\nCREATE "
        if table._prefixes:
            text += " ".join(table._prefixes) + " "

        text += "TABLE "
        if create.if_not_exists:
            text += "IF NOT EXISTS "

        text += preparer.format_table(table) + " "

        create_table_suffix = self.create_table_suffix(table)
        if create_table_suffix:
            text += create_table_suffix + " "

        text += "("

        separator = "\n"

        # if only one primary key, specify it along with the column
        first_pk = False
        for create_column in create.columns:
            column = create_column.element
            try:
                processed = self.process(
                    create_column, first_pk=column.primary_key and not first_pk
                )
                if processed is not None:
                    text += separator
                    separator = ", \n"
                    text += "\t" + processed
                if column.primary_key:
                    first_pk = True
            except exc.CompileError as ce:
>               raise exc.CompileError(
                    "(in table '%s', column '%s'): %s"
                    % (table.description, column.name, ce.args[0])
                ) from ce
E               sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D341007D0> can't render element of type JSONB

.venv\Lib\site-packages\sqlalchemy\sql\compiler.py:6779: CompileError
=============================================================================== warnings summary ================================================================================ 
.venv\Lib\site-packages\flask_session\base.py:172
.venv\Lib\site-packages\flask_session\base.py:172
tests/test_events.py::test_get_event_not_found
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\flask_session\base.py:172: DeprecationWarning: The 'use_signer' option is deprecated and will be removed in the next minor release. Please update your configuration accordingly or open an issue.
    warnings.warn(

tests/test_impersonation_simple.py::test_roles
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\_pytest\python.py:163: PytestReturnNotNoneWarning: Expected None, but tests/test_impersonation_simple.py::test_roles returned False, which will be an error in a future version of pytest.  Did you mean to use `assert` instead of `return`?
    warnings.warn(

tests/test_impersonation_simple.py::test_impersonation_routes
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\_pytest\python.py:163: PytestReturnNotNoneWarning: Expected None, but tests/test_impersonation_simple.py::test_impersonation_routes returned True, which will be an error in a future version of pytest.  Did you mean to use `assert` instead of `return`?
    warnings.warn(

tests/test_kyc_compliance.py::TestKYCCompliance::test_get_user_limits
  C:\Users\ADMIN\Desktop\afcon360_app\app\auth\kyc_compliance.py:250: LegacyAPIWarning: The Query.get() method is considered legacy as of the 1.x series of SQLAlchemy and becomes a legacy construct in 2.0. The method is now available as Session.get() (deprecated since: 2.0) (Background on SQLAlchemy 2.0 at: https://sqlalche.me/e/b8d9)
    user = User.query.get(user_identifier)

tests/test_kyc_integration.py::test_imports
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\_pytest\python.py:163: PytestReturnNotNoneWarning: Expected None, but tests/test_kyc_integration.py::test_imports returned True, which will be an error in a future version of pytest.  Did you mean to use `assert` instead of `return`?
    warnings.warn(

tests/test_kyc_integration.py::test_routes
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\_pytest\python.py:163: PytestReturnNotNoneWarning: Expected None, but tests/test_kyc_integration.py::test_routes returned True, which will be an error in a future version of pytest.  Did you mean to use `assert` instead of `return`?
    warnings.warn(

tests/test_services.py::test_kyc_service
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\_pytest\python.py:163: PytestReturnNotNoneWarning: Expected None, but tests/test_services.py::test_kyc_service returned True, which will be an error in a future version of pytest.  Did you mean to use `assert` instead of `return`?
    warnings.warn(

tests/test_services.py::test_auth_service
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\_pytest\python.py:163: PytestReturnNotNoneWarning: Expected None, but tests/test_services.py::test_auth_service returned True, which will be an error in a future version of pytest.  Did you mean to use `assert` instead of `return`?
    warnings.warn(

tests/test_services.py::test_forensic_audit
  C:\Users\ADMIN\Desktop\afcon360_app\.venv\Lib\site-packages\_pytest\python.py:163: PytestReturnNotNoneWarning: Expected None, but tests/test_services.py::test_forensic_audit returned True, which will be an error in a future version of pytest.  Did you mean to use `assert` instead of `return`?
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
============================================================================ short test summary info ============================================================================
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_event_cancellation - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34E87E00...
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_event_creation - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750...
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_event_metrics_integration - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23250...
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_event_publishing - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34103890...
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_event_search_functionality - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D2DEB2850...
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_event_soft_delete - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F20550...
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_event_update - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22990...
FAILED tests/test_event_workflow.py::TestEventWorkflow::test_ticket_type_creation - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34102E90...
FAILED tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier0 - RuntimeError: Working outside of application context.
FAILED tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier1 - RuntimeError: Working outside of application context.
FAILED tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier2 - RuntimeError: Working outside of application context.
FAILED tests/test_kyc_compliance.py::TestKYCCompliance::test_calculate_kyc_tier_tier3 - RuntimeError: Working outside of application context.
FAILED tests/test_kyc_compliance.py::TestKYCCompliance::test_get_user_limits - RuntimeError: The current Flask app is not registered with this 'SQLAlchemy' instance. Did you forget to call 'init_app', or did you create multiple 'SQLAlchemy' instances?
FAILED tests/test_kyc_compliance.py::TestKYCCompliance::test_check_transaction_allowed - RuntimeError: Working outside of application context.
FAILED tests/test_loose_coupling.py::test_events_module_independence - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37136710...
FAILED tests/test_payment_flow.py::TestPaymentFlow::test_free_registration_no_payment - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D37137ED0...
FAILED tests/test_payment_flow.py::TestPaymentFlow::test_paid_registration_insufficient_funds - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D371374D0...
FAILED tests/test_payment_flow.py::TestPaymentFlow::test_paid_registration_success - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32850...
FAILED tests/test_payment_flow.py::TestPaymentFlow::test_paid_registration_wallet_service_unavailable - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23750...
FAILED tests/test_payment_flow.py::TestPaymentFlow::test_payment_rollback_on_registration_failure - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34D32AD0...
FAILED tests/test_payment_flow.py::TestPaymentFlow::test_refund_scenario - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22710...
FAILED tests/test_registration_flow.py::TestRegistrationFlow::test_capacity_release_on_expiry - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F23110...
FAILED tests/test_registration_flow.py::TestRegistrationFlow::test_concurrent_registrations - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34100550...
FAILED tests/test_registration_flow.py::TestRegistrationFlow::test_idempotency - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D34F22850...
FAILED tests/test_registration_flow.py::TestRegistrationFlow::test_waitlist_functionality - sqlalchemy.exc.CompileError: (in table 'idempotency_keys', column 'response_body'): Compiler <sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler object at 0x0000016D341007D0...
ERROR tests/test_event.py - AssertionError: View function mapping is overwriting an existing endpoint function: transport_api.api_driver_list
ERROR tests/test_events.py::test_get_event_not_found - AssertionError: View function mapping is overwriting an existing endpoint function: transport_api.api_driver_list
ERROR tests/test_events.py::test_get_event_returns_expected_fields - AssertionError: View function mapping is overwriting an existing endpoint function: transport_api.api_driver_list
ERROR tests/wallet/test_ledger_concurrency.py::TestNoDoubleSpend::test_no_double_spend_100_parallel_withdrawals - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
ERROR tests/wallet/test_ledger_concurrency.py::TestNoDoubleSpend::test_no_double_send_parallel_transfers - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
ERROR tests/wallet/test_ledger_concurrency.py::TestTransferAtomicity::test_transfer_atomicity_on_db_error - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
ERROR tests/wallet/test_ledger_concurrency.py::TestIdempotency::test_idempotency_is_db_enforced - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
ERROR tests/wallet/test_ledger_concurrency.py::TestFrozenWallet::test_frozen_wallet_blocks_all_ops - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
ERROR tests/wallet/test_ledger_concurrency.py::TestDailyLimit::test_daily_limit_real_query - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
ERROR tests/wallet/test_ledger_concurrency.py::TestBalanceDerived::test_balance_always_derived - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
ERROR tests/wallet/test_ledger_concurrency.py::TestTransactionStatus::test_transaction_status_pending_to_completed - werkzeug.utils.ImportStringError: import_string() failed for 'testing'. Possible reasons are:
============================================================ 25 failed, 38 passed, 11 warnings, 11 errors in 36.80s ============================================================= 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> # Or run only the fixed tests
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app> python -m pytest tests/test_audit_system.py tests/test_simple.py tests/test_current.py -v
============================================================================== test session starts ==============================================================================
platform win32 -- Python 3.13.5, pytest-8.3.0, pluggy-1.6.0 -- C:\Users\ADMIN\Desktop\afcon360_app\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\ADMIN\Desktop\afcon360_app
plugins: cov-6.0.0, flask-1.3.0
collected 4 items                                                                                                                                                                 

tests/test_audit_system.py::test_audit_imports PASSED                                                                                                                      [ 25%] 
tests/test_audit_system.py::test_audit_log_exists PASSED                                                                                                                   [ 50%] 
tests/test_simple.py::test_import PASSED                                                                                                                                   [ 75%] 
tests/test_current.py::test_basic PASSED                                                                                                                                   [100%] 

=============================================================================== 4 passed in 1.34s =============================================================================== 
(.venv) PS C:\Users\ADMIN\Desktop\afcon360_app>



