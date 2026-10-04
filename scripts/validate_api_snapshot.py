"""Run from repository root: python -m scripts.validate_api_snapshot."""
import json

from api import app


if __name__ == "__main__":
    print(json.dumps(app.state.validate_snapshot(), default=str, ensure_ascii=False, indent=2))
