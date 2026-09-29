"""Create and move prompt versions in *your own* Langfuse project (keys from .env).

    python scripts/setup_prompts.py create            # v1 = baseline+production, v2 = candidate
    python scripts/setup_prompts.py promote 2         # production -> version 2
    python scripts/setup_prompts.py rollback 1        # production -> version 1 (same call, clearer name)
    python scripts/setup_prompts.py show              # list versions and labels

Then run the API with LANGFUSE_PROMPT_LABEL=baseline / candidate / production to
produce traces bound to each version (see docs/PROMPT_VERSIONING.md).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

from langfuse import get_client  # noqa: E402  (after load_dotenv so keys are visible)

NAME = os.getenv("LANGFUSE_PROMPT_NAME", "day13-chat")

# Contract from docs/PROMPT_VERSIONING.md: keep the three variables.
V1 = "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}"
V2 = (
    "Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}\n"
    "Answer in at most three short sentences and cite the doc you used."
)


def show(client) -> None:
    for label in ("baseline", "candidate", "production"):
        try:
            p = client.get_prompt(NAME, label=label, cache_ttl_seconds=0)
            print(f"{label:<11} -> version {p.version}  labels={p.labels}")
        except Exception as exc:  # label may not exist yet
            print(f"{label:<11} -> {type(exc).__name__}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create")
    sub.add_parser("show")
    for cmd in ("promote", "rollback"):
        sub.add_parser(cmd).add_argument("version", type=int)
    args = ap.parse_args()

    client = get_client()
    if not client.auth_check():
        sys.exit("Langfuse auth failed: kiểm tra LANGFUSE_* trong .env (đúng project cá nhân, đúng region).")

    if args.cmd == "create":
        client.create_prompt(name=NAME, prompt=V1, labels=["baseline", "production"], type="text",
                             commit_message="v1 baseline")
        client.create_prompt(name=NAME, prompt=V2, labels=["candidate"], type="text",
                             commit_message="v2 candidate: shorter, cites source")
    elif args.cmd in ("promote", "rollback"):
        # Langfuse moves a label to the new version automatically (a label lives on one version).
        client.update_prompt(name=NAME, version=args.version, new_labels=["production"])
    client.flush()
    show(client)


if __name__ == "__main__":
    main()
