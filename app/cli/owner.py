"""
AFCON360 — Owner Assignment CLI
================================
Drop this file in:  app/cli/owner.py

Then register it in your app factory (app/__init__.py):
    from app.cli.owner import register_owner_commands
    register_owner_commands(app)

Usage:
    flask assign-owner --email twikirizeobed@gmail.com
    flask assign-owner --username OBED
    flask assign-owner --email someone@example.com --force
"""

import click
from flask import current_app
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def register_owner_commands(app):
    """Register owner CLI commands with the Flask app."""

    @app.cli.command("assign-owner")
    @click.option(
        "--email",
        default=None,
        help="Email address of the user to assign as owner.",
    )
    @click.option(
        "--username",
        default=None,
        help="Username of the user to assign as owner.",
    )
    @click.option(
        "--force",
        is_flag=True,
        default=False,
        help="Force reassignment even if an owner already exists.",
    )
    @click.option(
        "--list",
        "list_owners",
        is_flag=True,
        default=False,
        help="List current owner(s) without making changes.",
    )
    def assign_owner(email, username, force, list_owners):
        """Assign the owner role to a user. Safe to run multiple times."""

        from app.extensions import db
        from app.identity.models.user import User, UserRole
        from app.identity.models.roles_permission import Role

        # ── List mode ────────────────────────────────────────────────
        if list_owners:
            _list_current_owners(db, Role, User, UserRole)
            return

        # ── Must provide at least one identifier ─────────────────────
        if not email and not username:
            console.print(
                Panel(
                    "[red]❌  Provide --email or --username[/red]\n\n"
                    "  flask assign-owner --email you@example.com\n"
                    "  flask assign-owner --username OBED",
                    title="Missing argument",
                    border_style="red",
                )
            )
            raise SystemExit(1)

        # ── Find user ─────────────────────────────────────────────────
        user = None
        if email:
            user = User.query.filter_by(email=email).first()
        if not user and username:
            user = User.query.filter_by(username=username).first()

        if not user:
            console.print(
                Panel(
                    f"[red]❌  No user found for:[/red]\n"
                    f"  email    = {email or '—'}\n"
                    f"  username = {username or '—'}",
                    title="User not found",
                    border_style="red",
                )
            )
            raise SystemExit(1)

        # ── Get or create owner role ──────────────────────────────────
        owner_role = Role.query.filter_by(name="owner", scope="global").first()

        if not owner_role:
            console.print("[yellow]⚠️  Owner role not found — creating it...[/yellow]")
            owner_role = Role(
                name="owner",
                scope="global",
                level=1,                      # highest privilege
                description="Platform owner with full system access",
                is_system=True,
            )
            db.session.add(owner_role)
            db.session.flush()               # get the id without committing
            console.print(
                f"[green]✅  Created owner role (id={owner_role.id})[/green]"
            )

        # ── Check existing owners ─────────────────────────────────────
        existing = UserRole.query.filter_by(role_id=owner_role.id).all()

        if existing and not force:
            console.print(
                Panel(
                    "[yellow]⚠️  An owner is already assigned:[/yellow]\n\n"
                    + "\n".join(
                        f"  👑  {User.query.get(ur.user_id).username}  "
                        f"({User.query.get(ur.user_id).email})"
                        for ur in existing
                        if User.query.get(ur.user_id)
                    )
                    + "\n\n[dim]Use --force to add another owner.[/dim]",
                    title="Owner already exists",
                    border_style="yellow",
                )
            )
            raise SystemExit(0)

        # ── Check if this user already has owner role ─────────────────
        already_assigned = UserRole.query.filter_by(
            user_id=user.id, role_id=owner_role.id
        ).first()

        if already_assigned:
            console.print(
                Panel(
                    f"[green]✅  {user.username} ({user.email}) is already the owner.[/green]\n"
                    f"[dim]No changes made.[/dim]",
                    title="Already owner",
                    border_style="green",
                )
            )
            raise SystemExit(0)

        # ── Assign the role ───────────────────────────────────────────
        assignment = UserRole(
            user_id=user.id,
            role_id=owner_role.id,
            scope="global",
        )
        db.session.add(assignment)
        db.session.commit()

        # ── Success output ────────────────────────────────────────────
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[dim]User ID[/dim]",    str(user.id))
        table.add_row("[dim]Username[/dim]",   user.username)
        table.add_row("[dim]Email[/dim]",      user.email)
        table.add_row("[dim]Role[/dim]",       f"owner (id={owner_role.id})")
        table.add_row("[dim]Scope[/dim]",      "global")
        table.add_row("[dim]Active[/dim]",     str(user.is_active))

        console.print(
            Panel(
                table,
                title="[green]👑  Owner assigned successfully[/green]",
                border_style="green",
            )
        )


def _list_current_owners(db, Role, User, UserRole):
    """Helper — print current owner assignments."""

    owner_role = Role.query.filter_by(name="owner", scope="global").first()

    if not owner_role:
        console.print("[red]❌  Owner role does not exist in the database.[/red]")
        console.print("    Run:  flask assign-owner --email you@example.com")
        return

    assignments = UserRole.query.filter_by(role_id=owner_role.id).all()

    if not assignments:
        console.print(
            Panel(
                "[red]❌  No owner assigned.[/red]\n\n"
                "    Run:  flask assign-owner --email you@example.com",
                title="No owner found",
                border_style="red",
            )
        )
        return

    table = Table(title="Current Owner(s)", border_style="green")
    table.add_column("ID",       style="dim")
    table.add_column("Username", style="bold")
    table.add_column("Email")
    table.add_column("Active")
    table.add_column("Verified")

    for ur in assignments:
        u = User.query.get(ur.user_id)
        if u:
            table.add_row(
                str(u.id),
                u.username,
                u.email,
                "✅" if u.is_active  else "❌",
                "✅" if u.is_verified else "❌",
            )

    console.print(table)
    console.print(f"\n[dim]Role: owner (id={owner_role.id}, scope=global, level={owner_role.level})[/dim]")
