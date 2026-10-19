import psycopg2
url = 'postgresql://postgres@localhost:5432/afcon360_test'
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute('''
SELECT n.nspname as schema, t.typname as enum_name,
       array_agg(e.enumlabel ORDER BY e.enumsortorder) as labels
FROM pg_catalog.pg_type t
JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
JOIN pg_catalog.pg_enum e ON e.enumtypid = t.oid
WHERE n.nspname NOT IN ('pg_catalog','information_schema')
GROUP BY n.nspname, t.typname
ORDER BY n.nspname, t.typname;
''')
for row in cur.fetchall():
    print(row)
