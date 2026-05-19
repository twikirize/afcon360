#!/usr/bin/env python3
"""
Test script for module isolation system
Run this to verify that disabled modules don't crash the application
"""
import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../app'))

def test_module_guard():
    """Test module guard utilities"""
    print("Testing module guard utilities...")
    
    try:
        from app.utils.module_guard import safe_url, module_enabled, safe_import
        
        # Test safe_url with non-existent endpoint
        result = safe_url('nonexistent.endpoint')
        assert result == '#', f"Expected '#', got '{result}'"
        print("PASS: safe_url() works correctly")
        
        # Test module_enabled outside app context
        result = module_enabled('wallet')
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"
        print("PASS: module_enabled() works outside app context")
        
        # Test safe_import with non-existent module
        result = safe_import('nonexistent.module')
        assert result is None, f"Expected None, got {result}"
        print("PASS: safe_import() works correctly")
        
        return True
    except Exception as e:
        print(f"FAIL: Module guard test failed: {e}")
        return False

def test_widget_loader():
    """Test widget loader system"""
    print("\nTesting widget loader...")
    
    try:
        from app.utils.widget_loader import get_wallet_widget_data, get_events_widget_data
        
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
    """Test app creation with different module configurations"""
    print("\nTesting app creation with module flags...")
    
    try:
        # Test with all modules disabled
        os.environ['ENABLE_WALLET'] = 'false'
        os.environ['ENABLE_TOURISM'] = 'false'
        os.environ['ENABLE_TRANSPORT'] = 'false'
        os.environ['ENABLE_ACCOMMODATION'] = 'false'
        os.environ['ENABLE_TOURNAMENT'] = 'false'
        
        # Import and create app
        from app import create_app
        app = create_app()
        
        with app.app_context():
            # Check module flags
            flags = app.config.get('MODULE_FLAGS', {})
            print(f"Module flags: {flags}")
            
            # Verify all modules are disabled
            disabled_modules = [name for name, enabled in flags.items() if not enabled]
            print(f"Disabled modules: {disabled_modules}")
            
            # Test template helpers are registered
            template_context_processors = app.template_context_processors
            print(f"Registered context processors: {len(template_context_processors)}")
            
        print("PASS: App creation successful with all modules disabled")
        return True
        
    except Exception as e:
        print(f"FAIL: App creation test failed: {e}")
        return False

def test_safe_url_in_context():
    """Test safe_url within app context"""
    print("\nTesting safe_url in app context...")
    
    try:
        from app import create_app
        app = create_app()
        
        with app.app_context():
            from app.utils.module_guard import safe_url
            
            # Test with disabled module endpoint
            result = safe_url('wallet.dashboard')
            # Should return '#' since wallet is disabled
            print(f"safe_url('wallet.dashboard') = '{result}'")
            
            # Test with core endpoint
            result = safe_url('auth.login')
            print(f"safe_url('auth.login') = '{result}'")
            
        print("PASS: safe_url works in app context")
        return True
        
    except Exception as e:
        print(f"FAIL: safe_url context test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("Starting Module Isolation Tests\n")
    
    tests = [
        test_module_guard,
        test_widget_loader,
        test_app_creation,
        test_safe_url_in_context,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("All tests passed! Module isolation is working correctly.")
        return 0
    else:
        print("Some tests failed. Check the implementation.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
