import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    # Real environment variables win over .env, so deployments can override it.
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    readonly_database_url: str
    model: str
    effort: str
    max_retries: int
    max_rows: int


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        readonly_database_url=os.environ["READONLY_DATABASE_URL"],
        model=os.environ.get("MODEL", "claude-opus-5-5"),
        effort=os.environ.get("EFFORT", "medium"),
        max_retries=int(os.environ.get("MAX_RETRIES", "2")),
        max_rows=int(os.environ.get("MAX_ROWS", "200")),
    )
