"""
Registra o servidor MCP do SecureData Central no ~/.claude.json (Claude
Code) OU imprime o trecho .mcp.json para colar manualmente.

Uso:
    python scripts/install_mcp.py                # registra global (~/.claude.json)
    python scripts/install_mcp.py --print        # so imprime o JSON
    python scripts/install_mcp.py --db /data/securedata.db
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVER_KEY = "securedata"


def build_entry(db_path: str) -> dict:
    return {
        "command": shutil.which("python") or sys.executable,
        "args": ["-m", "sdc.mcp.server"],
        "cwd": str(ROOT),
        "env": {
            "SDC_DB_PATH": db_path,
            "SDC_LOG_LEVEL": "INFO",
            "SDC_MAX_CONTEXT_TOKENS": "2000",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="just_print")
    ap.add_argument("--db", default=str(ROOT / "storage" / "securedata.db"))
    ap.add_argument("--config", default=str(Path.home() / ".claude.json"))
    args = ap.parse_args()

    entry = build_entry(args.db)

    if args.just_print:
        print(json.dumps({"mcpServers": {SERVER_KEY: entry}}, indent=2))
        return 0

    cfg_path = Path(args.config)
    data = {}
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"! {cfg_path} nao e JSON valido -- abortando para nao sobrescrever", file=sys.stderr)
            return 1

    data.setdefault("mcpServers", {})
    existed = SERVER_KEY in data["mcpServers"]
    data["mcpServers"][SERVER_KEY] = entry

    cfg_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"{'atualizado' if existed else 'adicionado'}: mcpServers.{SERVER_KEY} em {cfg_path}")
    print(f"  cwd = {entry['cwd']}")
    print(f"  db  = {args.db}")
    print("Reinicie o Claude Code para carregar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
