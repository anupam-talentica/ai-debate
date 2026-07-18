"""One-time (idempotent) upload of the shared debate topics to LangSmith.

Reads the *same* source of truth as Approach A —
``tests/custom_pytest/evals/datasets/topics.jsonl`` — and pushes each row as an
example into a LangSmith dataset. Re-running upserts by ``id`` instead of
duplicating rows (acceptance criterion #1).

Usage:
    export LANGSMITH_API_KEY=...
    python tests/lang_smith/upload_dataset.py           # from debate_bot/
    # or:  cd tests/lang_smith && python upload_dataset.py
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

DATASET_NAME = "debate-topics"
DATASET_DESC = "Golden debate topics + weak-spot triggers (shared with Approach A)."

# Shared dataset — never duplicate topics. Resolve relative to this file so the
# script works regardless of the current working directory.
# _HERE == tests/lang_smith ; _HERE.parent == tests/
_HERE = Path(__file__).resolve().parent
TOPICS_PATH = _HERE.parent / "custom_pytest" / "evals" / "datasets" / "topics.jsonl"


def _load_topics() -> list[dict]:
    rows = []
    with TOPICS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _get_or_create_dataset(client: Client):
    """Return the existing dataset if present, else create it (idempotent)."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        print(f"Using existing dataset '{DATASET_NAME}' ({ds.id}).")
        return ds
    ds = client.create_dataset(DATASET_NAME, description=DATASET_DESC)
    print(f"Created dataset '{DATASET_NAME}' ({ds.id}).")
    return ds


def main() -> None:
    topics = _load_topics()
    if not topics:
        raise SystemExit(f"No topics found in {TOPICS_PATH}")

    client = Client()
    ds = _get_or_create_dataset(client)

    # Index existing examples by our stable business key (metadata["id"]) so a
    # re-run updates in place rather than appending duplicates.
    existing: dict[str, str] = {}
    for ex in client.list_examples(dataset_id=ds.id):
        biz_id = (ex.metadata or {}).get("id")
        if biz_id:
            existing[biz_id] = str(ex.id)

    created = updated = 0
    for row in topics:
        biz_id = row["id"]
        inputs = {"topic": row["topic"]}
        metadata = {"id": biz_id, "note": row.get("note", "")}
        if biz_id in existing:
            client.update_example(
                example_id=existing[biz_id],
                inputs=inputs,
                outputs={},          # no gold output — evaluators score behavior
                metadata=metadata,
            )
            updated += 1
        else:
            client.create_example(
                inputs=inputs,
                outputs={},
                dataset_id=ds.id,
                metadata=metadata,
            )
            created += 1

    print(f"Done. {created} created, {updated} updated, {len(topics)} total.")


if __name__ == "__main__":
    main()
