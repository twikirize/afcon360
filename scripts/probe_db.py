import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# load .env the same way the app does
try:
    from dotenv import load_dotenv
    for name in (".env", ".env.development", ".env.local"):
        p = ROOT / name
        if p.exists():
            load_dotenv(p)
            print(f"# loaded {name}")
except ImportError:
    print("# python-dotenv not installed; relying on ambient env vars")

from app.config import Config          # <-- if this fails, see note below
uri = getattr(Config, "SQLALCHEMY_DATABASE_URI", None)
print("URI =", uri)
if uri:
    from sqlalchemy.engine.url import make_url
    u = make_url(uri)
    print(f"host={u.host} port={u.port} user={u.username} db={u.database} driver={u.drivername}")