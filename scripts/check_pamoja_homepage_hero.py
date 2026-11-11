#!/usr/bin/env python3
"""Source-level contract check for the Pamoja homepage hero presentation.

This check intentionally avoids Flask app startup and database access. It
validates the Jinja template syntax, hero placement/content, responsive CSS,
and preservation of the existing homepage sections.
"""
from pathlib import Path
import sys

from jinja2 import Environment
import tinycss2


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_PATH = ROOT / "templates" / "public_home.html"
CSS_PATH = ROOT / "static" / "css" / "global" / "home.css"


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    css = CSS_PATH.read_text(encoding="utf-8")

    # Parse the complete Jinja template without invoking request/database
    # context processors.
    Environment().parse(template)

    hero_marker = '<section class="pamoja-hero-section"'
    search_marker = '<section class="top-search">'
    if template.count(hero_marker) != 1:
        fail("Expected exactly one Pamoja hero section.")
    if template.index(hero_marker) > template.index(search_marker):
        fail("Pamoja hero must appear before the homepage search section.")

    for required in (
        'id="pamoja-hero-title"',
        "Welcome to <span>Pamoja</span>",
        "Your gateway to matches, travel, tickets, and experiences across Africa and beyond.",
        "Explore Featured Events",
        "Find Stays &amp; Hotels",
        'aria-label="Pamoja service shortcuts"',
        'class="desktop-only-search"',
        'class="mobile-only-search"',
        'type="search"',
        'id="home-mobile-search"',
        "🏟️ Events",
        "🏨 Stays",
        "🚌 Transport",
        "🌴 Tourism",
        "👛 Wallet",
    ):
        if required not in template:
            fail(f"Homepage hero is missing required content: {required}")

    # The image asset is optional until its original file is supplied. A
    # missing image must never create a broken background request.
    if "pamoja-hero-bg.jpg" in css or "pamoja-hero-bg.jpg" in template:
        fail("A non-existent hero image must not be referenced.")

    marker = "PAMOJA HERO BANNER & MOBILE SERVICE CHIPS"
    if marker not in css:
        fail("Pamoja hero CSS block is missing from the loaded global stylesheet.")
    hero_css = css[css.index(marker):]
    parsed = tinycss2.parse_stylesheet(
        hero_css, skip_comments=True, skip_whitespace=True
    )
    errors = [rule for rule in parsed if rule.type == "error"]
    if errors:
        fail("Pamoja hero CSS contains parse errors: " + "; ".join(
            error.message for error in errors
        ))

    for required in (
        ".pamoja-hero-section",
        ".hero-actions",
        ".btn-hero-primary",
        ".btn-hero-ghost",
        ".mobile-service-chips",
        ".mobile-chip",
        ".desktop-only-search",
        ".mobile-only-search",
        ".search-inner",
        ".search-btn-arrow",
        "@media",
        "max-width: 768px",
        "overflow-x: auto",
    ):
        if required not in hero_css:
            fail(f"Responsive hero CSS is missing: {required}")

    # The new introduction must not displace the existing discovery and
    # dynamic content model.
    for required in (
        'class="top-search"',
        "class=\"trending-tags\"",
        "class=\"quick-actions\"",
        "class=\"featured-grid\"",
        "class=\"live-scroll\"",
        'id="feed-container"',
        "feed/_layout_mixed.html",
        "feed/_layout_sections.html",
        "feed/_layout_tabbed.html",
        "class=\"host-banner\"",
        "left_ads",
        "right_ads",
    ):
        if required not in template:
            fail(f"Existing Pamoja homepage section was lost: {required}")

    print("PASS: Jinja syntax, hero placement/content, responsive CSS, and existing homepage sections.")
    print("NOTE: This source contract does not replace live Flask render or visual device testing.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        raise
