# tests/auth/test_helpers.py
def test_owner_bypasses_all_checks():
    owner = create_user_with_role("owner")
    assert has_global_role(owner, "any_role") is True
    assert has_global_permission(owner, "any.permission") is True
