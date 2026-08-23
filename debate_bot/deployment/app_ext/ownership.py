"""Run ownership + heartbeat, backing the automatic-failover claim logic (T3).

A row in `run_ownership` records which node is currently executing a given
run_id. Ownership is claimed via a race-safe `INSERT ... ON CONFLICT ...
WHERE` so that only one node wins when several attempt to claim the same
stale run simultaneously.
"""

import logging
import os
from typing import Optional

from psycopg_pool import AsyncConnectionPool

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/debate_bot")

# Demo-friendly values (see TRD_ARCHITECTURE.md Task 3) — tune for how patient
# the failover demo should look.
STALE_AFTER_SECONDS = 10
HEARTBEAT_INTERVAL_SECONDS = 3

_pool: Optional[AsyncConnectionPool] = None


async def init_pool() -> None:
    """Open the ownership connection pool and create its table if needed.

    Call once at process startup, alongside init_checkpointer().
    """
    global _pool
    _pool = AsyncConnectionPool(DATABASE_URL, open=False)
    await _pool.open()
    async with _pool.connection() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS run_ownership (
                run_id TEXT PRIMARY KEY,
                node_id TEXT NOT NULL,
                heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                status TEXT NOT NULL DEFAULT 'running'
            )
            """
        )


async def close_pool() -> None:
    """Release the ownership connection pool opened by init_pool()."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _pool_or_raise() -> AsyncConnectionPool:
    if _pool is None:
        raise RuntimeError("ownership pool not initialized — call init_pool() at startup")
    return _pool


async def claim(run_id: str, node_id: str) -> bool:
    """Claim run_id for node_id if it's unowned, the owner's heartbeat is
    stale, or the run is paused waiting for an audience question.

    A 'waiting_for_input' row is claimable immediately regardless of how
    fresh its heartbeat looks — nothing is heartbeating it once paused, so
    staleness is meaningless there. This is the only path that should ever
    reclaim such a row (the audience-question endpoint, once an answer
    arrives) — the ordinary crash-recovery reclaim path never calls claim()
    for one, since is_owned_and_alive() reports it permanently alive.

    Race-safe: when several nodes attempt this concurrently for the same
    run_id, Postgres's row-level locking on the UPDATE ensures exactly one
    of them observes its own node_id in the RETURNING row.

    Returns True only if this node_id ends up owning the row.
    """
    async with _pool_or_raise().connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO run_ownership (run_id, node_id, heartbeat_at, status)
            VALUES (%s, %s, now(), 'running')
            ON CONFLICT (run_id) DO UPDATE
              SET node_id = EXCLUDED.node_id, heartbeat_at = now(), status = 'running'
              WHERE run_ownership.status = 'waiting_for_input'
                 OR (run_ownership.status NOT IN ('done', 'waiting_for_input')
                     AND run_ownership.heartbeat_at < now() - (%s * interval '1 second'))
            RETURNING node_id
            """,
            (run_id, node_id, STALE_AFTER_SECONDS),
        )
        row = await cur.fetchone()
        claimed = row is not None and row[0] == node_id
        if claimed:
            logger.info(f"[{run_id}] claimed by {node_id}")
        return claimed


async def heartbeat(run_id: str, node_id: str) -> None:
    """Refresh heartbeat_at while node_id is actively executing run_id."""
    async with _pool_or_raise().connection() as conn:
        await conn.execute(
            "UPDATE run_ownership SET heartbeat_at = now() WHERE run_id = %s AND node_id = %s",
            (run_id, node_id),
        )


async def set_status(run_id: str, node_id: str, status: str) -> None:
    """Mark a run as done/failed once its node stops executing it.

    Prevents a finished run from looking perpetually "owned" once its
    heartbeat goes stale, and stops it from being reclaimed and re-executed.
    """
    async with _pool_or_raise().connection() as conn:
        await conn.execute(
            "UPDATE run_ownership SET status = %s, heartbeat_at = now() WHERE run_id = %s AND node_id = %s",
            (status, run_id, node_id),
        )


async def get_status(run_id: str) -> Optional[str]:
    """Return run_id's current status, or None if no ownership row exists for it.

    Used to give a clear rejection reason (unknown run, already answered,
    still running, already done) before attempting to claim it — claim()
    itself would otherwise happily INSERT a brand-new row for an unknown
    run_id, which is the right behavior for /debate/start but wrong for a
    question submitted against a run that was never started.
    """
    async with _pool_or_raise().connection() as conn:
        cur = await conn.execute(
            "SELECT status FROM run_ownership WHERE run_id = %s",
            (run_id,),
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def is_owned_and_alive(run_id: str) -> bool:
    """True if run_id is owned by a node with a live heartbeat, or already done,
    or paused waiting for an audience question.

    'waiting_for_input' is treated as permanently alive the same way 'done' is:
    a paused run has no active node to time out, and only the audience-question
    endpoint (which claims and resumes it directly with the answer) should ever
    move it forward — not the stale-heartbeat reclaim path used for crash
    recovery, which would otherwise just re-trigger the same interrupt on a
    ~STALE_AFTER_SECONDS cadence for as long as the human takes to respond.

    Used by the stream route to decide whether to relay only (owner is
    alive) or claim + execute (owner missing/stale).
    """
    async with _pool_or_raise().connection() as conn:
        cur = await conn.execute(
            """
            SELECT 1 FROM run_ownership
            WHERE run_id = %s
              AND (status IN ('done', 'waiting_for_input')
                   OR heartbeat_at >= now() - (%s * interval '1 second'))
            """,
            (run_id, STALE_AFTER_SECONDS),
        )
        return await cur.fetchone() is not None
