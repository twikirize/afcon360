"""
scripts/migrate_enums_to_strings.py

Automated helper to migrate PostgreSQL ENUM columns to String columns
using the expand-contract pattern. This script:

1. Scans models for ENUM columns
2. Generates migration scripts
3. Creates backfill scripts
4. Adds CHECK constraints

Usage:
    python scripts/migrate_enums_to_strings.py --dry-run    # Show what would be done
    python scripts/migrate_enums_to_strings.py --module wallet  # Migrate specific module
    python scripts/migrate_enums_to_strings.py --all       # Migrate all modules
"""

import argparse
import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class EnumColumn:
    """Represents an ENUM column that needs migration"""
    file_path: str
    model_name: str
    column_name: str
    enum_class: str
    values: List[str]
    nullable: bool
    default: Optional[str]
    line_number: int


class EnumScanner(ast.NodeVisitor):
    """Scans Python files for SQLAlchemy ENUM usage"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.enum_columns: List[EnumColumn] = []
        self.current_class: Optional[str] = None
        self.imports: dict = {}

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports[alias.name] = alias.asname or alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            for alias in node.names:
                self.imports[f"{node.module}.{alias.name}"] = alias.asname or alias.name
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_Call(self, node: ast.Call):
        # Check for Column(Enum(...)) or Column(SQLEnum(...))
        if isinstance(node.func, ast.Name) and node.func.id == 'Column':
            self._check_enum_in_column(node)
        elif isinstance(node.func, ast.Attribute) and node.func.attr == 'Column':
            self._check_enum_in_column(node)
        self.generic_visit(node)

    def _check_enum_in_column(self, node: ast.Call):
        """Check if a Column call contains an Enum"""
        for keyword in node.keywords:
            if keyword.arg == 'nullable':
                continue
            if self._is_enum_call(keyword.value):
                enum_info = self._extract_enum_info(keyword.value)
                if enum_info:
                    self.enum_columns.append(EnumColumn(
                        file_path=self.file_path,
                        model_name=self.current_class or "Unknown",
                        column_name=self._get_column_name(node),
                        enum_class=enum_info[0],
                        values=enum_info[1],
                        nullable=self._get_nullable(node),
                        default=self._get_default(node),
                        line_number=node.lineno,
                    ))

    def _is_enum_call(self, node) -> bool:
        """Check if a node is an Enum(...) call"""
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in ('Enum', 'SQLEnum', 'SAEnum'):
                return True
            if isinstance(node.func, ast.Attribute) and node.func.attr in ('Enum', 'SQLEnum', 'SAEnum'):
                return True
        return False

    def _extract_enum_info(self, node) -> Optional[Tuple[str, List[str]]]:
        """Extract enum class name and values"""
        if not isinstance(node, ast.Call):
            return None

        # Get enum class name
        if isinstance(node.func, ast.Name):
            enum_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            enum_name = node.func.attr
        else:
            return None

        # Get values
        values = []
        for arg in node.args:
            if isinstance(arg, ast.Constant):
                values.append(arg.value)
            elif isinstance(arg, ast.Str):  # Python 3.7 compat
                values.append(arg.s)

        return enum_name, values

    def _get_column_name(self, node) -> str:
        """Extract column name from Column(...) call"""
        for keyword in node.keywords:
            if keyword.arg == 'name':
                if isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
                elif isinstance(keyword.value, ast.Str):
                    return keyword.value.s
        # Try to find from positional args
        if node.args and isinstance(node.args[0], ast.Constant):
            return node.args[0].value
        return "unknown"

    def _get_nullable(self, node) -> bool:
        """Extract nullable from Column(...) call"""
        for keyword in node.keywords:
            if keyword.arg == 'nullable':
                if isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
        return True

    def _get_default(self, node) -> Optional[str]:
        """Extract default from Column(...) call"""
        for keyword in node.keywords:
            if keyword.arg == 'default':
                if isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
                elif isinstance(keyword.value, ast.Attribute):
                    return f"{keyword.value.attr}"
        return None


def scan_directory(base_path: str, modules: Optional[List[str]] = None) -> List[EnumColumn]:
    """Scan directory for ENUM usage"""
    all_enums: List[EnumColumn] = []

    if modules:
        paths_to_scan = []
        for module in modules:
            module_path = Path(base_path) / "app" / module
            if module_path.exists():
                paths_to_scan.append(module_path)
    else:
        paths_to_scan = [Path(base_path) / "app"]

    for path in paths_to_scan:
        for py_file in path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            scanner = EnumScanner(str(py_file))
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    tree = ast.parse(f.read())
                scanner.visit(tree)
                all_enums.extend(scanner.enum_columns)
            except Exception as e:
                print(f"Error scanning {py_file}: {e}")

    return all_enums


def generate_migration_script(enums: List[EnumColumn], output_path: str):
    """Generate Alembic migration script for ENUM to String conversion"""
    migration_template = '''"""
Auto-generated migration: ENUM to String conversion

Revision: {revision}
DownRevision: {down_revision}
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '{revision}'
down_revision = '{down_revision}'
branch_labels = None
depends_on = None


def upgrade():
{upgrade_ops}


def downgrade():
{downgrade_ops}
'''

    upgrade_ops = []
    downgrade_ops = []

    for enum_col in enums:
        table_name = enum_col.model_name.lower() + 's'  # Simple pluralization
        new_column = f"{enum_col.column_name}_new"
        values_list = ", ".join([f"'{v}'" for v in enum_col.values])

        # Expand phase: Add new column
        upgrade_ops.append(f"    # Expand: Add new String column for {enum_col.column_name}")
        upgrade_ops.append(f"    op.add_column('{table_name}', sa.Column('{new_column}', sa.String(50), nullable={enum_col.nullable}, default='{enum_col.default or enum_col.values[0]}'))")
        upgrade_ops.append(f"    op.create_index('ix_{table_name}_{new_column}', '{table_name}', ['{new_column}'])")
        upgrade_ops.append("")

        # Backfill would be done via separate script
        upgrade_ops.append(f"    # Backfill: UPDATE {table_name} SET {new_column} = {enum_col.column_name}::text;")
        upgrade_ops.append("")

        # Contract phase: Drop old column, rename new
        upgrade_ops.append(f"    # Contract: Drop old ENUM column, rename new")
        upgrade_ops.append(f"    op.drop_column('{table_name}', '{enum_col.column_name}')")
        upgrade_ops.append(f"    op.alter_column('{table_name}', '{new_column}', new_column_name='{enum_col.column_name}')")
        upgrade_ops.append("")

        # Add CHECK constraint
        upgrade_ops.append(f"    # Add CHECK constraint")
        upgrade_ops.append(f"    op.create_check_constraint('chk_{table_name}_{enum_col.column_name}', '{table_name}', \"{enum_col.column_name} IN ({values_list})\")")
        upgrade_ops.append("")

        # Downgrade operations (reverse)
        downgrade_ops.append(f"    # Reverse: Drop CHECK constraint")
        downgrade_ops.append(f"    op.drop_constraint('chk_{table_name}_{enum_col.column_name}', '{table_name}', type_='check')")
        downgrade_ops.append("")
        downgrade_ops.append(f"    # Reverse: Rename column back")
        downgrade_ops.append(f"    op.alter_column('{table_name}', '{enum_col.column_name}', new_column_name='{new_column}')")
        downgrade_ops.append("")
        downgrade_ops.append(f"    # Reverse: Recreate ENUM column")
        downgrade_ops.append(f"    op.add_column('{table_name}', sa.Column('{enum_col.column_name}', postgresql.ENUM({values_list}, name='{enum_col.enum_class.lower()}'), nullable={enum_col.nullable}))")
        downgrade_ops.append(f"    op.create_index('ix_{table_name}_{enum_col.column_name}', '{table_name}', ['{enum_col.column_name}'])")
        downgrade_ops.append("")
        downgrade_ops.append(f"    # Reverse: Backfill ENUM from String")
        downgrade_ops.append(f"    # UPDATE {table_name} SET {enum_col.column_name} = {new_column}::{enum_col.enum_class.lower()};")
        downgrade_ops.append("")
        downgrade_ops.append(f"    # Reverse: Drop new column")
        downgrade_ops.append(f"    op.drop_column('{table_name}', '{new_column}')")
        downgrade_ops.append("")

    migration_content = migration_template.format(
        revision="auto_generated_enum_to_string",
        down_revision="head",
        upgrade_ops="\n".join(upgrade_ops),
        downgrade_ops="\n".join(downgrade_ops),
    )

    with open(output_path, 'w') as f:
        f.write(migration_content)

    print(f"Migration script written to: {output_path}")


def generate_backfill_script(enums: List[EnumColumn], output_path: str):
    """Generate backfill script for data migration"""
    script_template = '''"""
Backfill script for ENUM to String migration

This script migrates data from old ENUM columns to new String columns.
Run this AFTER deploying the schema changes (expand phase).

Usage:
    python scripts/backfill_enums.py --batch-size 10000
"""

import argparse
from sqlalchemy import create_engine, text
from app.config import Config


def backfill_table(table_name: str, old_column: str, new_column: str, batch_size: int):
    """Backfill data in batches"""
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    
    with engine.connect() as conn:
        # Get total rows to migrate
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE {new_column} IS NULL"))
        total = result.scalar()
        
        print(f"Migrating {total} rows in {table_name}...")
        
        # Process in batches
        offset = 0
        while offset < total:
            conn.execute(text(f"""
                UPDATE {table_name}
                SET {new_column} = {old_column}::text
                WHERE {new_column} IS NULL
                AND {old_column} IS NOT NULL
                LIMIT {batch_size}
            """))
            conn.commit()
            offset += batch_size
            print(f"  Migrated {min(offset, total)}/{total} rows")
        
        print(f"Backfill complete for {table_name}")


def main():
    parser = argparse.ArgumentParser(description="Backfill ENUM to String columns")
    parser.add_argument('--batch-size', type=int, default=10000, help='Rows per batch')
    parser.add_argument('--table', type=str, help='Specific table to backfill')
    args = parser.parse_args()

{backfill_calls}


if __name__ == '__main__':
    main()
'''

    backfill_calls = []
    for enum_col in enums:
        table_name = enum_col.model_name.lower() + 's'
        new_column = f"{enum_col.column_name}_new"
        backfill_calls.append(f"    # Backfill {enum_col.model_name}.{enum_col.column_name}")
        backfill_calls.append(f"    if not args.table or args.table == '{table_name}':")
        backfill_calls.append(f"        backfill_table('{table_name}', '{enum_col.column_name}', '{new_column}', args.batch_size)")
        backfill_calls.append("")

    script_content = script_template.format(backfill_calls="\n".join(backfill_calls))

    with open(output_path, 'w') as f:
        f.write(script_content)

    print(f"Backfill script written to: {output_path}")


def generate_check_constraints(enums: List[EnumColumn], output_path: str):
    """Generate CHECK constraint migration script"""
    script_template = '''"""
Add CHECK constraints to String columns that replaced ENUMs

This script adds CHECK constraints for defense-in-depth validation.
Run this AFTER the expand-contract migration is complete.

Usage:
    python scripts/add_check_constraints.py --dry-run
"""

import argparse
from sqlalchemy import create_engine, text
from app.config import Config


CHECK_CONSTRAINTS = {check_constraints}


def add_constraint(table_name: str, column_name: str, valid_values: list):
    """Add CHECK constraint to a column"""
    values_list = ", ".join([f"'{v}'" for v in valid_values])
    constraint_name = f"chk_{table_name}_{column_name}"
    
    engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
    
    with engine.connect() as conn:
        # Check if constraint already exists
        result = conn.execute(text(f"""
            SELECT COUNT(*) FROM information_schema.check_constraints
            WHERE constraint_name = '{constraint_name}'
        """))
        
        if result.scalar() > 0:
            print(f"Constraint {constraint_name} already exists, skipping")
            return
        
        # Add constraint
        conn.execute(text(f"""
            ALTER TABLE {table_name}
            ADD CONSTRAINT {constraint_name}
            CHECK ({column_name} IN ({values_list}))
        """))
        conn.commit()
        print(f"Added constraint {constraint_name} to {table_name}.{column_name}")


def main():
    parser = argparse.ArgumentParser(description="Add CHECK constraints")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--table', type=str, help='Specific table')
    args = parser.parse_args()

{constraint_calls}


if __name__ == '__main__':
    main()
'''

    check_constraints = {}
    constraint_calls = []

    for enum_col in enums:
        table_name = enum_col.model_name.lower() + 's'
        key = f"{table_name}.{enum_col.column_name}"
        check_constraints[key] = enum_col.values

        constraint_calls.append(f"    # Add constraint for {enum_col.model_name}.{enum_col.column_name}")
        constraint_calls.append(f"    if not args.table or args.table == '{table_name}':")
        constraint_calls.append(f"        if args.dry_run:")
        constraint_calls.append(f"            print(f\"Would add CHECK constraint to {table_name}.{enum_col.column_name}: {enum_col.values}\")")
        constraint_calls.append(f"        else:")
        constraint_calls.append(f"            add_constraint('{table_name}', '{enum_col.column_name}', {enum_col.values})")
        constraint_calls.append("")

    script_content = script_template.format(
        check_constraints=check_constraints,
        constraint_calls="\n".join(constraint_calls),
    )

    with open(output_path, 'w') as f:
        f.write(script_content)

    print(f"CHECK constraint script written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Scan and migrate ENUM columns to String")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done')
    parser.add_argument('--module', type=str, help='Specific module to scan (e.g., wallet, transport)')
    parser.add_argument('--all', action='store_true', help='Scan all modules')
    parser.add_argument('--output-dir', type=str, default='scripts', help='Output directory for scripts')
    args = parser.parse_args()

    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.module:
        modules = [args.module]
    elif args.all:
        modules = None  # Scan all
    else:
        modules = ['wallet', 'transport', 'accommodation', 'events', 'identity', 'audit', 'admin']

    print(f"Scanning for ENUM usage in: {modules or 'all modules'}")
    enums = scan_directory(base_path, modules)

    if not enums:
        print("No ENUM columns found.")
        return

    print(f"\nFound {len(enums)} ENUM columns:")
    for enum_col in enums:
        print(f"  - {enum_col.file_path}:{enum_col.line_number}")
        print(f"    {enum_col.model_name}.{enum_col.column_name} ({enum_col.enum_class})")
        print(f"    Values: {enum_col.values}")
        print()

    if args.dry_run:
        print("\nDry run complete. No files written.")
        return

    # Generate scripts
    output_dir = Path(base_path) / args.output_dir
    output_dir.mkdir(exist_ok=True)

    migration_path = output_dir / "migrate_enums_to_strings.py"
    backfill_path = output_dir / "backfill_enums.py"
    constraints_path = output_dir / "add_check_constraints.py"

    generate_migration_script(enums, str(migration_path))
    generate_backfill_script(enums, str(backfill_path))
    generate_check_constraints(enums, str(constraints_path))

    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("1. Review generated migration scripts in scripts/")
    print("2. Run: python scripts/backfill_enums.py --batch-size 10000")
    print("3. Run: python scripts/add_check_constraints.py")
    print("4. Update model files to use String columns instead of ENUMs")
    print("5. Run tests to verify everything works")
    print("="*60)


if __name__ == '__main__':
    main()