"""
Production-grade email address validation for account creation.

Layered strategy ("Option 1 Platinum"):

  1. Normalisation      - lowercase, Gmail dot/plus folding -> canonical form
  2. Syntax             - RFC-aware via ``email_validator`` (regex fallback)
  3. Role-part blocking - reject shared mailboxes (info@, admin@, noreply@)
  4. Disposable domains - burner/temp-mail blocklist (auto-refreshing)
  5. MX lookup          - cached DNS check that the domain can receive mail
  6. Typo suggestion    - "did you mean gmail.com?" via edit distance

Deliberately NOT implemented: SMTP ``RCPT TO`` probing. Modern providers
block it, it gets sending IPs blacklisted, and it adds seconds of latency.

Every layer degrades gracefully: if ``email_validator`` or ``dnspython`` is
missing, or DNS is slow/unreachable, validation falls back to the checks it
can still perform rather than blocking signups.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Limits (RFC 5321 / 5322)
# ---------------------------------------------------------------------------

MAX_EMAIL_LENGTH = 254      # RFC 5321 forward-path limit
MAX_LOCAL_LENGTH = 64       # RFC 5321 local-part limit
MAX_LABEL_LENGTH = 63       # RFC 1035 DNS label limit

# Fallback syntax pattern, used only when `email_validator` is unavailable.
# Stricter than the classic "[^@]+@[^@]+\.[^@]+": requires a sane local part,
# a real dotted domain, and an alphabetic TLD of >= 2 characters.
_FALLBACK_EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
    r"(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*"
    r"@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}$"
)

# ---------------------------------------------------------------------------
# Role / shared mailboxes - OTPs sent here are rarely read and often bounce,
# which damages sender reputation.
# ---------------------------------------------------------------------------

RESERVED_LOCAL_PARTS: Set[str] = {
    "abuse", "admin", "administrator", "billing", "compliance", "contact",
    "devnull", "enquiries", "enquiry", "everyone", "finance", "ftp", "help",
    "helpdesk", "hostmaster", "info", "inquiries", "it", "mail", "mailer",
    "mailer-daemon", "marketing", "no-reply", "noc", "noreply", "notifications",
    "office", "postmaster", "root", "sales", "security", "spam", "support",
    "sysadmin", "team", "test", "testing", "usenet", "uucp", "webmaster",
    "www", "www-data",
}

# ---------------------------------------------------------------------------
# Domains that fold "+tag" and/or "." in the local part to one inbox.
# ---------------------------------------------------------------------------

_DOT_FOLDING_DOMAINS: Set[str] = {"gmail.com", "googlemail.com"}

_PLUS_FOLDING_DOMAINS: Set[str] = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "yahoo.com", "proton.me", "protonmail.com", "pm.me",
    "icloud.com", "me.com", "mac.com", "fastmail.com", "zoho.com",
}

# Gmail is served under many country domains; all route to gmail.com.
_DOMAIN_ALIASES = {"googlemail.com": "gmail.com"}

# ---------------------------------------------------------------------------
# Popular domains used for "did you mean ...?" typo suggestions.
# ---------------------------------------------------------------------------

COMMON_DOMAINS: Tuple[str, ...] = (
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com",
    "aol.com", "icloud.com", "me.com", "mac.com", "msn.com", "proton.me",
    "protonmail.com", "zoho.com", "fastmail.com", "gmx.com", "gmx.net",
    "mail.com", "yandex.com", "qq.com", "163.com", "126.com", "naver.com",
    "hotmail.co.uk", "yahoo.co.uk", "btinternet.com", "orange.fr",
    "web.de", "t-online.de", "libero.it", "free.fr", "sfr.fr",
    "yahoo.fr", "yahoo.co.in", "rediffmail.com", "gmail.co.uk",
    "yahoo.ca", "outlook.fr", "outlook.co.uk",
    # Regional providers relevant to the AFCON audience
    "gmail.com", "yahoo.co.za", "webmail.co.za", "mweb.co.za",
    "africaonline.co.ug", "utlonline.co.ug", "orange.co.ke", "safaricom.co.ke",
)

# ---------------------------------------------------------------------------
# Disposable / burner domains. Seed list ships with the repo; refreshed at
# runtime from the community blocklist when DISPOSABLE_EMAIL_REFRESH is on.
# ---------------------------------------------------------------------------

_SEED_DISPOSABLE_DOMAINS: Set[str] = {
    "0-mail.com", "0clickemail.com", "10minutemail.com", "10minutemail.net",
    "20minutemail.com", "33mail.com", "guerrillamail.com", "guerrillamail.net",
    "guerrillamail.org", "guerrillamailblock.com", "sharklasers.com",
    "grr.la", "spam4.me", "mailinator.com", "mailinator.net", "mailinator2.com",
    "notmailinator.com", "reallymymail.com", "sogetthis.com", "suremail.info",
    "tempmail.com", "temp-mail.org", "temp-mail.io", "tempmailo.com",
    "tempail.com", "tempinbox.com", "tempmailaddress.com", "throwawaymail.com",
    "trashmail.com", "trashmail.net", "trashmail.me", "wegwerfmail.de",
    "yopmail.com", "yopmail.fr", "yopmail.net", "cool.fr.nf", "jetable.fr.nf",
    "nospam.ze.tc", "nomail.xl.cx", "mega.zik.dj", "speed.1s.fr",
    "getairmail.com", "dispostable.com", "fakeinbox.com", "fakemailgenerator.com",
    "emailondeck.com", "mohmal.com", "mytemp.email", "moakt.com",
    "burnermail.io", "maildrop.cc", "mailnesia.com", "mintemail.com",
    "spamgourmet.com", "mailcatch.com", "inboxbear.com", "tmpmail.org",
    "tmpeml.com", "linshiyouxiang.net", "1secmail.com", "1secmail.org",
    "1secmail.net", "email-temp.com", "disposablemail.com", "harakirimail.com",
    "mailsac.com", "inboxkitten.com", "tempr.email", "discard.email",
    "spambox.us", "vpn.st", "byom.de", "anonbox.net", "trbvm.com",
}

_DISPOSABLE_BLOCKLIST_URL = (
    "https://cdn.jsdelivr.net/gh/disposable-email-domains/"
    "disposable-email-domains@master/disposable_email_blocklist.conf"
)

_disposable_domains: Set[str] = set(_SEED_DISPOSABLE_DOMAINS)
_disposable_lock = threading.Lock()
_disposable_refreshed_at: float = 0.0
_DISPOSABLE_REFRESH_INTERVAL = 24 * 60 * 60  # 24 hours


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class EmailValidationResult:
    """Outcome of validating a single email address."""

    is_valid: bool
    #: Canonical, deduplicated form to persist in the database.
    normalized: Optional[str] = None
    #: Human-readable, actionable error message (empty when valid).
    message: str = ""
    #: Machine-readable failure reason, for metrics/tests.
    code: Optional[str] = None
    #: Suggested correction, e.g. "user@gmail.com" for a "gnail.com" typo.
    suggestion: Optional[str] = None
    #: True when the address passed syntax but MX could not be confirmed.
    mx_unverified: bool = False
    warnings: list = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.is_valid

    def as_tuple(self) -> Tuple[bool, str]:
        """Legacy ``(ok, message)`` shape used by existing validators."""
        return self.is_valid, self.message


# ---------------------------------------------------------------------------
# Config helpers - read Flask config when available, else use defaults.
# ---------------------------------------------------------------------------

def _config(key: str, default):
    try:
        from flask import current_app
        if current_app:
            return current_app.config.get(key, default)
    except Exception:
        pass
    return default


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> str:
    """
    Return the canonical form of *email* for storage and duplicate detection.

    Lowercases the whole address, resolves domain aliases, strips ``+tag``
    suffixes on providers that ignore them, and removes dots from the local
    part on Gmail. So ``John.Doe+afcon@googlemail.com`` and
    ``johndoe@gmail.com`` both canonicalise to ``johndoe@gmail.com``.

    Malformed input is returned trimmed/lowercased rather than raising, so
    callers can run syntax checks against a predictable value.
    """
    if not email:
        return ""

    cleaned = email.strip().strip("<>").strip()
    if "@" not in cleaned:
        return cleaned.lower()

    local, _, domain = cleaned.rpartition("@")
    local = local.lower()
    domain = domain.lower().rstrip(".")
    domain = _DOMAIN_ALIASES.get(domain, domain)

    if domain in _PLUS_FOLDING_DOMAINS and "+" in local:
        local = local.split("+", 1)[0]

    if domain in _DOT_FOLDING_DOMAINS:
        local = local.replace(".", "")

    return f"{local}@{domain}"


# ---------------------------------------------------------------------------
# Disposable domain list
# ---------------------------------------------------------------------------

def get_disposable_domains() -> Set[str]:
    """Return the active disposable-domain blocklist."""
    return _disposable_domains


def refresh_disposable_domains(force: bool = False) -> int:
    """
    Refresh the disposable blocklist from the community-maintained source.

    Safe to call on startup and from a scheduler: it is time-throttled, never
    raises, and keeps the previous list if the download fails or looks bogus.

    Returns the number of domains currently in the blocklist.
    """
    global _disposable_refreshed_at, _disposable_domains

    if not _config("DISPOSABLE_EMAIL_REFRESH", False) and not force:
        return len(_disposable_domains)

    now = time.time()
    if not force and (now - _disposable_refreshed_at) < _DISPOSABLE_REFRESH_INTERVAL:
        return len(_disposable_domains)

    try:
        import requests

        resp = requests.get(_DISPOSABLE_BLOCKLIST_URL, timeout=5)
        resp.raise_for_status()
        fetched = {
            line.strip().lower()
            for line in resp.text.splitlines()
            if line.strip() and not line.startswith("#")
        }
        # Sanity check: the real list has tens of thousands of entries. A tiny
        # response means we hit an error page - keep what we already have.
        if len(fetched) < 100:
            logger.warning(
                "Disposable blocklist download looked truncated (%d entries); keeping existing list",
                len(fetched),
            )
            return len(_disposable_domains)

        with _disposable_lock:
            _disposable_domains = fetched | _SEED_DISPOSABLE_DOMAINS
            _disposable_refreshed_at = now

        logger.info("Refreshed disposable email blocklist: %d domains", len(_disposable_domains))
    except Exception as e:
        logger.warning("Could not refresh disposable email blocklist (%s); using bundled list", e)
        _disposable_refreshed_at = now  # avoid hammering a broken endpoint

    return len(_disposable_domains)


def is_disposable_domain(domain: str) -> bool:
    """True when *domain* (or its registrable parent) is a known burner host."""
    if not domain:
        return False
    domain = domain.lower().rstrip(".")
    if domain in _disposable_domains:
        return True
    # Catch subdomains of burner hosts, e.g. "inbox.mailinator.com".
    parts = domain.split(".")
    for i in range(1, len(parts) - 1):
        if ".".join(parts[i:]) in _disposable_domains:
            return True
    return False


# ---------------------------------------------------------------------------
# Typo suggestions
# ---------------------------------------------------------------------------

def _levenshtein(a: str, b: str, max_distance: int = 3) -> int:
    """Edit distance between *a* and *b*, capped at *max_distance* + 1."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > max_distance:
        return max_distance + 1

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        best_in_row = i
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            value = min(
                previous[j] + 1,        # deletion
                current[j - 1] + 1,     # insertion
                previous[j - 1] + cost, # substitution
            )
            current.append(value)
            best_in_row = min(best_in_row, value)
        if best_in_row > max_distance:
            return max_distance + 1
        previous = current

    return previous[-1]


def suggest_domain(domain: str, max_distance: int = 2) -> Optional[str]:
    """
    Return the closest common domain to *domain*, or ``None`` if it is already
    a known-good domain or nothing is close enough to suggest confidently.
    """
    if not domain:
        return None
    domain = domain.lower()
    if domain in COMMON_DOMAINS:
        return None

    best: Optional[str] = None
    best_distance = max_distance + 1
    for candidate in COMMON_DOMAINS:
        distance = _levenshtein(domain, candidate, max_distance)
        if distance < best_distance:
            best, best_distance = candidate, distance

    return best if best_distance <= max_distance else None


# ---------------------------------------------------------------------------
# MX lookup with caching
# ---------------------------------------------------------------------------

# Process-local memo, used when Redis/Flask-Caching is unavailable.
_mx_memo: dict = {}
_mx_memo_lock = threading.Lock()
_MX_MEMO_TTL = 3600


def _mx_cache_get(domain: str) -> Optional[bool]:
    key = f"mx:{domain}"
    try:
        from app.extensions import cache
        value = cache.get(key)
        if value is not None:
            return bool(value)
    except Exception:
        pass

    with _mx_memo_lock:
        entry = _mx_memo.get(domain)
    if entry and (time.time() - entry[1]) < _MX_MEMO_TTL:
        return entry[0]
    return None


def _mx_cache_set(domain: str, has_mx: bool) -> None:
    key = f"mx:{domain}"
    try:
        from app.extensions import cache
        # Cache negatives briefly so a transient DNS blip cannot lock a real
        # domain out for a full hour.
        cache.set(key, has_mx, timeout=_MX_MEMO_TTL if has_mx else 300)
    except Exception:
        pass

    with _mx_memo_lock:
        _mx_memo[domain] = (has_mx, time.time())


def domain_has_mx(domain: str, timeout: float = 3.0) -> Optional[bool]:
    """
    Check whether *domain* can receive mail.

    Returns ``True`` (MX or A/AAAA fallback present), ``False`` (domain does
    not exist / has no mail route), or ``None`` when the check could not be
    performed - dnspython missing, DNS timeout, resolver error. ``None`` means
    "unknown", and callers must not treat it as a failure.
    """
    if not domain:
        return None

    cached = _mx_cache_get(domain)
    if cached is not None:
        return cached

    try:
        import dns.resolver
        import dns.exception
    except ImportError:
        logger.debug("dnspython not installed; skipping MX check for %s", domain)
        return None

    resolver = dns.resolver.Resolver()
    resolver.timeout = timeout
    resolver.lifetime = timeout

    try:
        answers = resolver.resolve(domain, "MX")
        # A null MX ("0 .") explicitly declares the domain accepts no mail.
        exchanges = [str(r.exchange).rstrip(".") for r in answers]
        has_mx = any(ex for ex in exchanges)
        _mx_cache_set(domain, has_mx)
        return has_mx
    except dns.resolver.NoAnswer:
        # No MX record: RFC 5321 allows falling back to an A/AAAA record.
        for rtype in ("A", "AAAA"):
            try:
                resolver.resolve(domain, rtype)
                _mx_cache_set(domain, True)
                return True
            except Exception:
                continue
        _mx_cache_set(domain, False)
        return False
    except dns.resolver.NXDOMAIN:
        _mx_cache_set(domain, False)
        return False
    except (dns.resolver.NoNameservers, dns.exception.Timeout) as e:
        logger.debug("DNS check inconclusive for %s: %s", domain, e)
        return None
    except Exception as e:
        logger.debug("Unexpected DNS error for %s: %s", domain, e)
        return None


# ---------------------------------------------------------------------------
# Syntax
# ---------------------------------------------------------------------------

def _check_syntax(email: str) -> Tuple[bool, str, Optional[str]]:
    """Return ``(ok, message, code)`` for the syntax of *email*."""
    if len(email) > MAX_EMAIL_LENGTH:
        return False, f"Email address must be at most {MAX_EMAIL_LENGTH} characters.", "too_long"

    if email.count("@") != 1:
        return False, "Please enter a valid email address.", "syntax"

    local, domain = email.split("@", 1)

    if not local:
        return False, "Please enter a valid email address.", "syntax"
    if len(local) > MAX_LOCAL_LENGTH:
        return False, "The part before the @ is too long.", "local_too_long"
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return False, "Please enter a valid email address.", "syntax"

    if not domain or "." not in domain:
        return False, "Please include a valid domain, for example gmail.com.", "syntax"
    if domain.startswith("-") or domain.endswith("-") or ".." in domain:
        return False, "Please enter a valid email address.", "syntax"
    if any(len(label) > MAX_LABEL_LENGTH for label in domain.split(".")):
        return False, "Please enter a valid email address.", "syntax"

    # A real public TLD is at least two characters and never numeric.
    tld = domain.rsplit(".", 1)[1]
    if len(tld) < 2 or not tld.isalpha():
        return False, "Please include a valid domain, for example gmail.com.", "syntax"

    # Prefer the RFC-aware library when present.
    try:
        from email_validator import EmailNotValidError, validate_email as _lib_validate

        try:
            _lib_validate(email, check_deliverability=False)
            return True, "", None
        except EmailNotValidError as e:
            return False, f"Please enter a valid email address. ({e})", "syntax"
    except ImportError:
        if not _FALLBACK_EMAIL_RE.match(email):
            return False, "Please enter a valid email address.", "syntax"
        return True, "", None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def validate_email_address(
    email: Optional[str],
    *,
    check_mx: Optional[bool] = None,
    allow_role_accounts: Optional[bool] = None,
    allow_disposable: Optional[bool] = None,
) -> EmailValidationResult:
    """
    Validate *email* for account creation and return an
    :class:`EmailValidationResult`.

    Args:
        email: Raw address as typed by the user.
        check_mx: Perform the DNS/MX check. Defaults to the ``EMAIL_VALIDATE_MX``
            config value (on by default). An inconclusive lookup never blocks;
            it only sets ``mx_unverified``.
        allow_role_accounts: Permit ``info@``/``admin@`` style shared mailboxes.
            Defaults to ``EMAIL_ALLOW_ROLE_ACCOUNTS`` (off).
        allow_disposable: Permit burner domains. Defaults to
            ``EMAIL_ALLOW_DISPOSABLE`` (off).

    The returned ``normalized`` value is what should be written to the
    database, so that Gmail aliases cannot create duplicate accounts.
    """
    if check_mx is None:
        check_mx = _config("EMAIL_VALIDATE_MX", True)
    if allow_role_accounts is None:
        allow_role_accounts = _config("EMAIL_ALLOW_ROLE_ACCOUNTS", False)
    if allow_disposable is None:
        allow_disposable = _config("EMAIL_ALLOW_DISPOSABLE", False)

    if not email or not email.strip():
        return EmailValidationResult(False, message="Email address is required.", code="missing")

    raw = email.strip()

    # Reject control characters / embedded newlines outright (header injection).
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in raw):
        return EmailValidationResult(
            False, message="Email address contains invalid characters.", code="control_chars"
        )

    # 1. Normalise first so every later check sees the canonical value.
    normalized = normalize_email(raw)

    # 2. Syntax.
    ok, message, code = _check_syntax(normalized)
    if not ok:
        result = EmailValidationResult(False, message=message, code=code)
        # Only offer a "did you mean" hint when the address is structurally
        # sound (exactly one @, non-empty parts) and just the domain looks
        # mistyped - otherwise the suggestion is noise.
        if normalized.count("@") == 1:
            local, domain = normalized.split("@", 1)
            if local and domain:
                suggestion = suggest_domain(domain)
                if suggestion:
                    result.suggestion = f"{local}@{suggestion}"
                    result.message = f"Did you mean {result.suggestion}?"
        return result

    local_part, domain = normalized.split("@", 1)

    # 3. Role / shared mailboxes.
    if not allow_role_accounts and local_part in RESERVED_LOCAL_PARTS:
        return EmailValidationResult(
            False,
            normalized=normalized,
            message="Please use a personal email address, not a shared or generic mailbox.",
            code="role_account",
        )

    # 4. Disposable domains.
    if not allow_disposable and is_disposable_domain(domain):
        return EmailValidationResult(
            False,
            normalized=normalized,
            message="Temporary or disposable email addresses are not allowed. Please use a permanent address.",
            code="disposable",
        )

    # 5. Typo suggestion before the DNS round-trip - catches "gnail.com" fast.
    suggestion_domain = suggest_domain(domain)

    # 6. MX / deliverability.
    mx_unverified = False
    if check_mx:
        has_mx = domain_has_mx(domain)
        if has_mx is False:
            result = EmailValidationResult(
                False,
                normalized=normalized,
                message="We couldn't find a mail server for that domain. Please check the spelling.",
                code="no_mx",
            )
            if suggestion_domain:
                result.suggestion = f"{local_part}@{suggestion_domain}"
                result.message = f"Did you mean {result.suggestion}?"
            return result
        if has_mx is None:
            mx_unverified = True

    result = EmailValidationResult(True, normalized=normalized, mx_unverified=mx_unverified)
    if suggestion_domain:
        # Valid and deliverable, but close to a popular domain - surface it as a
        # non-blocking hint the UI can show.
        result.suggestion = f"{local_part}@{suggestion_domain}"
    if mx_unverified:
        result.warnings.append("mx_unverified")
    return result


def is_valid_email(email: Optional[str], **kwargs) -> bool:
    """Convenience boolean wrapper around :func:`validate_email_address`."""
    return validate_email_address(email, **kwargs).is_valid
