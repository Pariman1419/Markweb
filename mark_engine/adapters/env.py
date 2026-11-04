from pathlib import Path
import os


def load_env(path: Path | None = None, override: bool = False) -> dict[str, str]:
    path = path or Path(__file__).resolve().parents[2] / '.env'
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return values
