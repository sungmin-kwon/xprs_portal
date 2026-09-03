#!/usr/bin/env python3
"""Build the top/bottom gene-frequency manifest and optionally pre-index it.

The default selection is the 200 most frequent queryable genes across every
individual's 10 strongest risk-increasing and 10 strongest risk-lowering gene
contributions. Running without ``--run`` is network-free and only regenerates
the manifest plus a sweep summary.

Examples:
    python scripts/preindex_frequent_genes.py
    python scripts/preindex_frequent_genes.py --run
    python scripts/preindex_frequent_genes.py --run --max-genes 300
    python scripts/preindex_frequent_genes.py --run --max-genes 0 --min-occurrences 5

Stop the portal before using ``--run``. Local embedded Chroma is not intended
to be written by this maintenance process while the web process has it open.
The checkpoint is saved after every gene, so an interrupted run can be resumed
with the same command. The first HTTP 429 opens a persistent, escalating
cooldown. Repeated 5xx responses or network failures open a shorter cooldown.
Runs started before ``cooldown_until`` exit safely with code 75 without making
an API request; after expiry, the first missing literature query doubles as the
half-open probe instead of sending a separate health-check request.
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PROJECT_VENVS = (REPO_DIR / ".venv", REPO_DIR / ".xprs_portal")

# The manifest-only path intentionally works with any environment containing
# pandas. The actual sweep needs the portal's complete dependency set. Make the
# user-facing `python ... --run` command deterministic even from `(base)`.
if "--run" in sys.argv and Path(sys.prefix).resolve() not in {
    path.resolve() for path in PROJECT_VENVS
}:
    project_python = next(
        (path / "bin" / "python" for path in PROJECT_VENVS if (path / "bin" / "python").exists()),
        None,
    )
    if project_python is None:
        raise SystemExit(
            "Project virtual environment is missing. Create .venv and install "
            "requirements before running the sweep."
        )
    os.execv(
        str(project_python),
        [str(project_python), str(Path(__file__).resolve()), *sys.argv[1:]],
    )

from dotenv import load_dotenv


sys.path.insert(0, str(REPO_DIR))
load_dotenv(REPO_DIR / ".env")

from config import GENE_IMPORTANCE_CSV, S2_CACHE_DIR  # noqa: E402
from preindexing import (  # noqa: E402
    build_frequency_manifest,
    load_checkpoint,
    preindex_gene,
    save_checkpoint,
    select_frequent_genes,
    TEMPORARY_FAILURE_EXIT_CODE,
    utc_now,
    write_manifest,
)


configured_manifest = os.getenv("PREINDEX_MANIFEST", "").strip()
DEFAULT_MANIFEST = (
    Path(configured_manifest).expanduser()
    if configured_manifest
    else REPO_DIR / "data" / "preindex_gene_frequency.csv"
)
if not DEFAULT_MANIFEST.is_absolute():
    DEFAULT_MANIFEST = REPO_DIR / DEFAULT_MANIFEST
DEFAULT_CHECKPOINT = S2_CACHE_DIR / "preindex_state.json"
RATE_LIMIT_COOLDOWN_BASE_SECONDS = max(
    1.0,
    float(os.getenv("S2_RATE_LIMIT_COOLDOWN_BASE_SECONDS", "300")),
)
RATE_LIMIT_COOLDOWN_MAX_SECONDS = max(
    RATE_LIMIT_COOLDOWN_BASE_SECONDS,
    float(os.getenv("S2_RATE_LIMIT_COOLDOWN_MAX_SECONDS", "1800")),
)
TRANSIENT_COOLDOWN_SECONDS = max(
    1.0,
    float(os.getenv("S2_TRANSIENT_COOLDOWN_SECONDS", "300")),
)
COOLDOWN_POLICY_VERSION = 3


def _parse_utc(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _retry_after_seconds(reason: dict) -> float:
    try:
        return max(0.0, float(reason.get("retry_after_seconds") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _open_circuit_breaker(
    *,
    reason: dict,
    previous: dict | None = None,
    now: datetime | None = None,
) -> dict:
    current = now or datetime.now(timezone.utc)
    prior = previous or {}
    status_code = reason.get("status_code")
    consecutive_rate_limits = int(prior.get("consecutive_rate_limits") or 0)
    if status_code == 429:
        consecutive_rate_limits += 1
        policy_seconds = min(
            RATE_LIMIT_COOLDOWN_MAX_SECONDS,
            RATE_LIMIT_COOLDOWN_BASE_SECONDS * (2 ** (consecutive_rate_limits - 1)),
        )
        cooldown_seconds = max(policy_seconds, _retry_after_seconds(reason))
    else:
        cooldown_seconds = TRANSIENT_COOLDOWN_SECONDS

    return {
        "state": "open",
        "policy_version": COOLDOWN_POLICY_VERSION,
        "opened_at": current.isoformat(),
        "cooldown_seconds": cooldown_seconds,
        "cooldown_until": (current + timedelta(seconds=cooldown_seconds)).isoformat(),
        "consecutive_rate_limits": consecutive_rate_limits,
        "successful_queries_since_rate_limit": 0,
        "reason": reason,
        "exit_code": TEMPORARY_FAILURE_EXIT_CODE,
    }


def _normalize_open_breaker(
    breaker: dict,
    *,
    now: datetime | None = None,
) -> dict:
    """Add cooldown metadata to checkpoints written by the earlier implementation."""
    if breaker.get("state") != "open":
        return breaker
    if (
        breaker.get("policy_version") == COOLDOWN_POLICY_VERSION
        and _parse_utc(breaker.get("cooldown_until"))
    ):
        return breaker
    opened_at = _parse_utc(breaker.get("opened_at")) or now or datetime.now(timezone.utc)
    reason = breaker.get("reason") or {}
    prior_strikes = int(breaker.get("consecutive_rate_limits") or 0)
    if reason.get("status_code") == 429:
        # A policy migration starts a fresh consecutive-throttle sequence.
        # Older checkpoints did not reset strikes after successful requests.
        prior_strikes = 1
    policy_seconds = (
        min(
            RATE_LIMIT_COOLDOWN_MAX_SECONDS,
            RATE_LIMIT_COOLDOWN_BASE_SECONDS * (2 ** max(0, prior_strikes - 1)),
        )
        if reason.get("status_code") == 429
        else TRANSIENT_COOLDOWN_SECONDS
    )
    cooldown_seconds = max(policy_seconds, _retry_after_seconds(reason))
    migrated = dict(breaker)
    migrated.update({
        "policy_version": COOLDOWN_POLICY_VERSION,
        "cooldown_seconds": cooldown_seconds,
        "cooldown_until": (opened_at + timedelta(seconds=cooldown_seconds)).isoformat(),
        "consecutive_rate_limits": prior_strikes,
        "successful_queries_since_rate_limit": int(
            breaker.get("successful_queries_since_rate_limit") or 0
        ),
    })
    return migrated


def _cooldown_remaining_seconds(
    breaker: dict,
    *,
    now: datetime | None = None,
) -> float:
    cooldown_until = _parse_utc(breaker.get("cooldown_until"))
    if cooldown_until is None:
        return 0.0
    return max(0.0, (cooldown_until - (now or datetime.now(timezone.utc))).total_seconds())


def _format_wait(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, remainder = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def _record_api_successes(
    breaker: dict,
    successful_query_count: int,
    *,
    now: datetime | None = None,
) -> dict:
    if successful_query_count < 1:
        return dict(breaker)
    return {
        **breaker,
        "consecutive_rate_limits": 0,
        "successful_queries_since_rate_limit": 0,
        "last_api_success_at": (now or datetime.now(timezone.utc)).isoformat(),
    }


def _port_is_open(host: str = "127.0.0.1", port: int = 9009) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _pool_ready(
    *,
    gene: str,
    label: str,
    prior: dict,
    rag_agent,
    s2_agent,
) -> bool:
    phenotype = "breast cancer" if label == "primary" else None
    pool_type = "phenotype" if phenotype else "general"
    clauses = [{"gene": gene}, {"pool_type": pool_type}]
    if phenotype:
        clauses.append({"phenotype": phenotype})
    if rag_agent.has_documents({"$and": clauses}):
        return True

    pool_state = (prior.get("pools") or {}).get(label) or {}
    document_count = pool_state.get("document_count")
    return document_count == 0 and s2_agent.cached_query_succeeded(gene, phenotype)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Perform API retrieval and Chroma indexing.")
    parser.add_argument("--sweep-n", type=int, default=10, help="Top and bottom slots per individual (default: 10).")
    parser.add_argument(
        "--max-genes",
        type=int,
        default=200,
        help="Maximum selected genes; use 0 for every gene meeting the threshold (default: 200).",
    )
    parser.add_argument(
        "--min-occurrences",
        type=int,
        default=1,
        help="Minimum number of top/bottom appearances (default: 1).",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument(
        "--query-delay",
        type=float,
        default=1.0,
        help="Seconds to wait after each uncached Semantic Scholar query (default: 1.0).",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=45,
        help="Read timeout in seconds for each pre-index search (default: 45).",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=2,
        help="Maximum attempts for connection failures and HTTP 5xx (default: 2; read timeouts and 429 are never retried).",
    )
    parser.add_argument(
        "--allow-public-api",
        action="store_true",
        help="Permit a long run without S2_API_KEY using the slower public endpoint.",
    )
    parser.add_argument(
        "--allow-live-server",
        action="store_true",
        help="Override the port-9009 safety check (not recommended with embedded Chroma).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.sweep_n < 1 or args.min_occurrences < 1 or args.max_genes < 0:
        raise SystemExit("--sweep-n and --min-occurrences must be positive; --max-genes cannot be negative")
    if args.query_delay < 0 or args.request_timeout < 1 or args.max_attempts < 1:
        raise SystemExit(
            "--query-delay cannot be negative; --request-timeout and --max-attempts must be positive"
        )

    rows, metadata = build_frequency_manifest(GENE_IMPORTANCE_CSV, sweep_n=args.sweep_n)
    write_manifest(args.manifest.resolve(), rows)
    selected = select_frequent_genes(
        rows,
        max_genes=None if args.max_genes == 0 else args.max_genes,
        min_occurrences=args.min_occurrences,
    )
    selected_slots = sum(int(row["occurrences"]) for row in selected)
    coverage = selected_slots / int(metadata["total_slots"]) if metadata["total_slots"] else 0.0

    print(f"Manifest: {args.manifest.resolve()}")
    print(
        f"Source: {metadata['source_gene_count']} genes x {metadata['individual_count']} individuals; "
        f"top {args.sweep_n} + bottom {args.sweep_n} = {metadata['total_slots']} slots"
    )
    print(
        f"Ranked: {metadata['ranked_gene_count']} unique genes "
        f"({metadata['queryable_gene_count']} queryable)"
    )
    print(
        f"Selected: {len(selected)} genes, {selected_slots} slots ({coverage:.1%} coverage), "
        f"up to {len(selected) * 2} Semantic Scholar queries"
    )

    if not args.run:
        print("\nDry run only. Add --run to retrieve and index the selected genes.")
        return 0

    if _port_is_open() and not args.allow_live_server:
        raise SystemExit(
            "Port 9009 is active. Stop the xprs web process before --run so two processes do not write embedded Chroma."
        )
    if not os.getenv("S2_API_KEY") and not args.allow_public_api:
        raise SystemExit("S2_API_KEY is absent. Use a valid key or explicitly pass --allow-public-api.")

    checkpoint_path = args.checkpoint.resolve()
    checkpoint = load_checkpoint(checkpoint_path)
    checkpoint.update({
        "schema_version": 1,
        "source_csv": metadata["source_csv"],
        "source_sha256": metadata["source_sha256"],
        "sweep_n_per_direction": args.sweep_n,
        "selection_max_genes": args.max_genes,
        "selection_min_occurrences": args.min_occurrences,
        "selected_gene_count": len(selected),
        "selected_slot_coverage": coverage,
    })
    checkpoint.setdefault("started_at", utc_now())
    checkpoint.setdefault("genes", {})
    previous_breaker = _normalize_open_breaker(checkpoint.get("circuit_breaker") or {})
    checkpoint["circuit_breaker"] = previous_breaker
    resume_half_open = previous_breaker.get("state") == "open"
    if resume_half_open:
        reason = previous_breaker.get("reason") or {}
        remaining_seconds = _cooldown_remaining_seconds(previous_breaker)
        save_checkpoint(checkpoint_path, checkpoint)
        if remaining_seconds > 0:
            print(
                "\nCIRCUIT BREAKER OPEN: no Semantic Scholar request was made. "
                f"Cooldown has {_format_wait(remaining_seconds)} remaining."
            )
            print(f"Retry at or after {previous_breaker.get('cooldown_until')}.")
            print(f"Checkpoint: {checkpoint_path}")
            return TEMPORARY_FAILURE_EXIT_CODE
        print(
            "Cooldown expired; the next missing Semantic Scholar query will be the half-open probe: "
            f"gene={reason.get('gene', '?')} pool={reason.get('pool', '?')} "
            f"status={reason.get('status_code', 'network_error')}"
        )
    save_checkpoint(checkpoint_path, checkpoint)

    from runtime_agents import get_runtime_agents

    print("\nLoading the shared BGE-M3, Semantic Scholar, and Chroma agents...")
    try:
        bundle = get_runtime_agents()
    except RuntimeError as exc:
        if "Chroma store is already open" in str(exc):
            raise SystemExit(
                "The XPRS web process currently owns the Chroma store. Stop it before running the sweep."
            ) from exc
        raise
    rag_agent = bundle["rag_agent"]
    s2_agent = bundle["s2_agent"]

    if resume_half_open:
        checkpoint["circuit_breaker"] = {
            **previous_breaker,
            "state": "half_open",
            "resumed_at": utc_now(),
        }
        save_checkpoint(checkpoint_path, checkpoint)

    completed = skipped = failed = 0
    for position, row in enumerate(selected, start=1):
        gene = str(row["gene"])
        prior = checkpoint["genes"].get(gene) or {}
        if prior.get("status") == "completed" and all(
            _pool_ready(
                gene=gene,
                label=label,
                prior=prior,
                rag_agent=rag_agent,
                s2_agent=s2_agent,
            )
            for label in ("general", "primary")
        ):
            skipped += 1
            print(f"[{position}/{len(selected)}] {gene}: already complete")
            continue

        print(f"[{position}/{len(selected)}] {gene}: indexing")
        result = preindex_gene(
            gene=gene,
            s2_agent=s2_agent,
            rag_agent=rag_agent,
            query_delay_seconds=args.query_delay,
            request_timeout_seconds=args.request_timeout,
            max_attempts=args.max_attempts,
            progress_callback=lambda message: print(f"    {message}"),
        )
        result.update({
            "rank": int(row["rank"]),
            "occurrences": int(row["occurrences"]),
            "risk_increasing_occurrences": int(row["risk_increasing_occurrences"]),
            "risk_lowering_occurrences": int(row["risk_lowering_occurrences"]),
            "attempts": int(prior.get("attempts") or 0) + 1,
        })
        checkpoint["genes"][gene] = result
        save_checkpoint(checkpoint_path, checkpoint)
        if result.get("halt_sweep"):
            reason = result.get("circuit_breaker_reason") or {}
            prior_breaker = checkpoint.get("circuit_breaker") or {}
            successful_query_count = sum(
                1 for pool in result["pools"].values() if pool.get("source") == "api"
            )
            prior_breaker = _record_api_successes(
                prior_breaker,
                successful_query_count,
            )
            checkpoint["circuit_breaker"] = _open_circuit_breaker(
                reason=reason,
                previous=prior_breaker,
            )
            save_checkpoint(checkpoint_path, checkpoint)
            failed += 1
            breaker = checkpoint["circuit_breaker"]
            status_label = reason.get("status_code")
            if status_label is None:
                status_label = "network error/timeout"
            print(f"    FAILED: {'; '.join(result['errors'])}")
            if reason.get("status_code") == 429:
                print(
                    "\nCIRCUIT BREAKER OPEN: Semantic Scholar returned 429; "
                    "the query was not retried "
                    f"(gene={gene}, pool={reason.get('pool')})."
                )
            else:
                print(
                    "\nCIRCUIT BREAKER OPEN: Semantic Scholar remained unavailable "
                    f"after its limited retry budget (gene={gene}, "
                    f"pool={reason.get('pool')}, status={status_label})."
                )
            print(
                "Sweep paused safely. Completed pools and caches are preserved; "
                f"next retry is allowed at {breaker['cooldown_until']} "
                f"({_format_wait(breaker['cooldown_seconds'])} cooldown)."
            )
            print(
                f"Progress this run: completed={completed}, already_complete={skipped}, "
                f"failed={failed}. Checkpoint: {checkpoint_path}"
            )
            return TEMPORARY_FAILURE_EXIT_CODE
        if result["status"] == "completed":
            completed += 1
            breaker = checkpoint.get("circuit_breaker") or {}
            fresh_queries = sum(
                1
                for pool in result["pools"].values()
                if pool.get("source") == "api"
            )
            breaker = _record_api_successes(breaker, fresh_queries)
            successful_queries = (
                0
                if fresh_queries > 0
                else int(breaker.get("successful_queries_since_rate_limit") or 0)
            )
            consecutive_rate_limits = int(
                breaker.get("consecutive_rate_limits") or 0
            )
            if breaker.get("state") == "half_open" and fresh_queries == 0:
                checkpoint["circuit_breaker"] = {
                    **breaker,
                    "last_cache_only_progress_at": utc_now(),
                }
            else:
                checkpoint["circuit_breaker"] = {
                    "state": "closed",
                    "closed_at": utc_now(),
                    "last_reason": breaker.get("last_reason") or breaker.get("reason"),
                    "consecutive_rate_limits": consecutive_rate_limits,
                    "successful_queries_since_rate_limit": successful_queries,
                }
            save_checkpoint(checkpoint_path, checkpoint)
            counts = [
                pool.get("document_count")
                for pool in result["pools"].values()
                if pool.get("document_count") is not None
            ]
            print(f"    completed; indexed {sum(counts)} documents")
        else:
            failed += 1
            print(f"    FAILED: {'; '.join(result['errors'])}")

    print(
        f"\nSweep finished: completed={completed}, already_complete={skipped}, failed={failed}. "
        f"Checkpoint: {checkpoint_path}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
