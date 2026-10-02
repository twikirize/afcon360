"""Focused contract tests for app/utils/idempotency.py key selection.

Covers exactly:
1. String namespace generates a key; repeat identical invocation returns the
   cached result; wrapped function executes once.
2. Callable key_getter still works (legacy behavior).
3. key_getter=None reads Idempotency-Key from a Flask request context.
4. Different meaningful arguments produce different keys/results.
5. A method's ``self`` is excluded from string-namespace key material.
6. Two different service instances with the same meaningful arguments
   produce the same generated key (cache shared).
Plus the staticmethod adversarial case: first-arg objects on non-methods
are NOT excluded.
"""
import pytest

from app.utils.idempotency import (
    idempotent_request,
    generate_idempotency_key,
    clear_idempotency_keys,
    _has_self_first_param,
)


@pytest.fixture(autouse=True)
def _clean_store():
    clear_idempotency_keys()
    yield
    clear_idempotency_keys()


def test_1_string_namespace_caches_repeat_invocation():
    calls = []

    @idempotent_request('ns_contract_1', ttl=60)
    def add(a, b):
        calls.append((a, b))
        return {'sum': a + b}

    first = add(2, 3)
    second = add(2, 3)
    assert first == {'sum': 5}
    assert second == {'sum': 5}
    assert calls == [(2, 3)], "wrapped function must execute exactly once"


def test_2_callable_key_getter_still_works():
    calls = []

    @idempotent_request(lambda *a, **k: f"custom:{a[0]}", ttl=60)
    def double(x):
        calls.append(x)
        return x * 2

    assert double(21) == 42
    assert double(21) == 42
    assert calls == [21]


def test_3_none_reads_idempotency_key_header(app):
    calls = []

    @idempotent_request(None, ttl=60)
    def ping():
        calls.append(1)
        return 'pong'

    with app.test_request_context(headers={'Idempotency-Key': 'hdr-contract-1'}):
        assert ping() == 'pong'
        assert ping() == 'pong'
    assert calls == [1]


def test_4_different_arguments_do_not_collide():
    @idempotent_request('ns_contract_4', ttl=60)
    def ident(x):
        return {'x': x}

    assert ident(1) == {'x': 1}
    assert ident(2) == {'x': 2}


def test_5_self_excluded_from_method_keys():
    class Svc:
        def __init__(self):
            self.calls = 0

        @idempotent_request('ns_contract_5', ttl=60)
        def work(self, job):
            self.calls += 1
            return {'job': job}

    assert _has_self_first_param(Svc.work) is True

    a, b = Svc(), Svc()
    assert a.work('same') == {'job': 'same'}
    # Second instance, same meaningful args -> cache hit, executes zero times more
    assert b.work('same') == {'job': 'same'}
    assert a.calls == 1
    assert b.calls == 0


def test_6_staticmethod_first_arg_is_key_material():
    class Svc:
        @staticmethod
        @idempotent_request('ns_contract_6', ttl=60)
        def update(settings):
            return dict(settings)

    assert _has_self_first_param(Svc.update) is False

    r1 = Svc.update({'a': 1})
    r2 = Svc.update({'a': 2})
    assert r1 == {'a': 1}
    assert r2 == {'a': 2}
    # repeat of first connfiguration hits cache
    assert Svc.update({'a': 1}) == {'a': 1}
