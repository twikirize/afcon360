# full_db_study.py
from sqlalchemy import create_engine, inspect, text
import os

# Use your actual MySQL connection string
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///dev.db")

engine = create_engine(DATABASE_URL)
insp = inspect(engine)

def study_database():
    print("=== FULL DATABASE STUDY REPORT ===")
    print(f"Connected to: {DATABASE_URL}\n")

    tables = insp.get_table_names()
    print(f"Tables found ({len(tables)}): {tables}\n")

    for table in tables:
        print(f"--- Table: {table} ---")

        # Columns
        columns = insp.get_columns(table)
        print("Columns:")
        for col in columns:
            print(f"  {col['name']} ({col['type']}) nullable={col['nullable']} default={col.get('default')}")

        # Primary key
        pk = insp.get_pk_constraint(table)
        print(f"Primary Key: {pk.get('constrained_columns', [])}")

        # Foreign keys
        fks = insp.get_foreign_keys(table)
        if fks:
            print("Foreign Keys:")
            for fk in fks:
                print(f"  {fk['constrained_columns']} -> {fk['referred_table']}({fk['referred_columns']})")
        else:
            print("Foreign Keys: None")

        # Indexes
        indexes = insp.get_indexes(table)
        if indexes:
            print("Indexes:")
            for idx in indexes:
                print(f"  {idx['name']} on {idx['column_names']} unique={idx['unique']}")
        else:
            print("Indexes: None")

        # Row count
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"Row count: {count}")

        print("\n")

if __name__ == "__main__":
    study_database()
