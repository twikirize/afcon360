#!/usr/bin/env python
"""Simplified module isolation integration tests."""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_module_guard_functions():
    """Test core module guard functions."""
    print("Testing module guard functions...")
    
    try:
        from app.utils.module_guard import safe_url, module_enabled, safe_import
        
        # Test safe_url with non-existent endpoint
        result = safe_url('nonexistent.endpoint')
        assert result == '#', f"Expected '#', got '{result}'"
        print("PASS: safe_url() works correctly")
        
        # Test safe_import with non-existent module
        result = safe_import('nonexistent.module')
        assert result is None, f"Expected None, got {result}"
        print("PASS: safe_import() works correctly")
        
        return True
    except Exception as e:
        print(f"FAIL: Module guard test failed: {e}")
        return False

def test_widget_loader():
    """Test widget loader system."""
    print("\nTesting widget loader...")
    
    try:
        from app.utils.widget_loader import get_wallet_widget_data, get_events_widget_data
        from app import create_app
        
        # Test with app context
        app = create_app()
        with app.app_context():
            # Test wallet widget with no user ID
            result = get_wallet_widget_data(None)
            assert result['enabled'] == False, f"Expected enabled=False, got {result}"
            print("PASS: Widget loader handles None user ID correctly")
            
            # Test events widget
            result = get_events_widget_data()
            assert isinstance(result, dict), f"Expected dict, got {type(result)}"
            assert 'enabled' in result, "Missing 'enabled' key in result"
            print("PASS: Events widget returns proper structure")
        
        return True
    except Exception as e:
        print(f"FAIL: Widget loader test failed: {e}")
        return False

def test_app_creation():
    """Test app creation with module isolation."""
    print("\nTesting app creation...")
    
    try:
        # Import and create app
        from app import create_app
        app = create_app()
        
        with app.app_context():
            # Test module_enabled function
            from app.utils.module_guard import module_enabled
            
            # Should return boolean without errors
            result = module_enabled('tourism')
            assert isinstance(result, bool), f"Expected bool, got {type(result)}"
            print(f"PASS: module_enabled('tourism') = {result}")
            
            # Test safe_url in app context
            from app.utils.module_guard import safe_url
            
            url = safe_url('tourism.nonexistent')
            assert url == '#', f"Expected '#', got '{url}'"
            print("PASS: safe_url works in app context")
            
        print("PASS: App creation successful")
        return True
        
    except Exception as e:
        print(f"FAIL: App creation test failed: {e}")
        return False

def test_template_helpers():
    """Test template helpers are registered."""
    print("\nTesting template helpers...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            # Check if template context processors are registered
            processors = app.template_context_processors
            print(f"PASS: {len(processors)} context processors registered")
            
            # Test module_enabled function in template context
            from app.utils.template_helpers import register_template_helpers
            register_template_helpers(app)
            
            print("PASS: Template helpers registered successfully")
            
        return True
    except Exception as e:
        print(f"FAIL: Template helpers test failed: {e}")
        return False

def test_api_blueprints():
    """Test API blueprints can be imported."""
    print("\nTesting API blueprints...")
    
    try:
        from app.admin.owner.api.module_api import module_api_bp
        from app.api.health import health_bp
        
        print("PASS: Module API blueprint imported successfully")
        print("PASS: Health API blueprint imported successfully")
        
        return True
    except Exception as e:
        print(f"FAIL: API blueprint test failed: {e}")
        return False

def test_middleware():
    """Test middleware can be imported."""
    print("\nTesting middleware...")
    
    try:
        from app.middleware.reload_modules import init_module_reload
        
        print("PASS: Module reload hooks imported successfully")
        
        return True
    except Exception as e:
        print(f"FAIL: Middleware test failed: {e}")
        return False

def run_tests():
    """Run all tests and generate report."""
    print("\n" + "="*60)
    print("SIMPLIFIED MODULE ISOLATION TEST SUITE")
    print("="*60)
    
    tests = [
        test_module_guard_functions,
        test_widget_loader,
        test_app_creation,
        test_template_helpers,
        test_api_blueprints,
        test_middleware,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests Run: {total}")
    print(f"Successes: {passed}")
    print(f"Failures: {total - passed}")
    
    if passed == total:
        print("\nALL TESTS PASSED! Module isolation is working correctly.")
        return True
    else:
        print(f"\n{total - passed} tests failed. Review the output above.")
        return False

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
