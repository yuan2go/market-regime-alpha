"""Read-only canonical historical inventory, including full exclusion denominators."""

from collections import Counter, defaultdict
import json
from hashlib import sha256
from uuid import UUID

from psycopg.rows import dict_row

from market_regime_alpha.infrastructure.postgres.pool import TargetPostgresPool
from market_regime_alpha.infrastructure.postgres.queries.historical_failures import read_historical_failure_requests
from market_regime_alpha.research_qualification.ports.artifacts import ResearchArtifactByteStore
from market_regime_alpha.runtime.errors import ArtifactIntegrityError
from market_regime_alpha.shared.hashing import canonical_json_sha256


class PostgresHistoricalInventory:
    def __init__(self, pool: TargetPostgresPool, byte_store: ResearchArtifactByteStore) -> None:
        self._pool, self._bytes = pool, byte_store

    def inspect(self, archive_id: UUID, seal_id: UUID) -> dict:
        with self._pool.connection(read_only=True) as connection:
            connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            with connection.cursor(row_factory=dict_row) as cursor:
                root = cursor.execute("""SELECT archive.*, seal.market_archive_seal_id, seal.knowledge_cutoff,
                    seal.content_sha256 AS seal_sha256 FROM mra.market_archive archive
                    JOIN mra.market_archive_seal seal USING(market_archive_id)
                    WHERE archive.market_archive_id=%s AND seal.market_archive_seal_id=%s
                    AND archive.lane='RETROSPECTIVE_BACKFILL'""", (archive_id,seal_id)).fetchone()
                if root is None:
                    raise ValueError("historical inventory requires an exact retrospective Archive and seal")
                config = cursor.execute("""SELECT content_sha256,size_bytes,
                    mra.market_artifact_is_readable(integrity_state,last_verified_at) AS readable
                    FROM mra.artifact WHERE artifact_id=%s""",(root["config_artifact_id"],)).fetchone()
                captures = cursor.execute("""SELECT capture.*, artifact.content_sha256, artifact.size_bytes,
                    mra.market_artifact_is_readable(artifact.integrity_state,artifact.last_verified_at) AS readable
                    FROM mra.market_archive_capture_observation observation JOIN mra.data_capture capture USING(capture_id)
                    LEFT JOIN mra.artifact artifact USING(artifact_id)
                    WHERE observation.market_archive_id=%s AND observation.known_at<=%s ORDER BY capture_id""",
                    (archive_id,root["knowledge_cutoff"])).fetchall()
                capture_ids = [c["capture_id"] for c in captures]
                securities = cursor.execute("""SELECT DISTINCT instrument.instrument_id, instrument.canonical_code, instrument.exchange,
                    identifier.identifier_value FROM mra.market_capture_instrument_normalization binding
                    JOIN mra.instrument instrument USING(instrument_id)
                    JOIN mra.instrument_identifier identifier USING(instrument_id)
                    WHERE binding.capture_id=ANY(%s) AND identifier.identifier_scheme='BAOSTOCK'
                    AND EXISTS (SELECT 1 FROM mra.market_capture_instrument_identifier_normalization source
                        WHERE source.instrument_identifier_id=identifier.instrument_identifier_id AND source.capture_id=ANY(%s))
                    ORDER BY instrument_id, identifier_value""",(capture_ids,capture_ids)).fetchall()
                sessions = cursor.execute("""SELECT DISTINCT session.* FROM mra.market_capture_trading_session_normalization binding
                    JOIN mra.trading_session session USING(session_id) WHERE binding.capture_id=ANY(%s)
                    ORDER BY exchange,session_date""",(capture_ids,)).fetchall()
                bars = cursor.execute("""SELECT bar_revision_id,instrument_id,session_id,timeframe,price_basis,revision,supersedes_revision_id
                    FROM mra.market_bar_revision bar WHERE capture_id=ANY(%s)
                    AND known_at<=%s ORDER BY instrument_id,session_id,timeframe,price_basis,revision""",(capture_ids,root["knowledge_cutoff"])).fetchall()
                gaps = cursor.execute("""SELECT gap.* FROM mra.source_gap gap WHERE (capture_id=ANY(%s)
                    OR EXISTS (SELECT 1 FROM mra.market_archive_slice_gap binding WHERE binding.market_archive_id=%s AND binding.gap_id=gap.gap_id))
                    AND gap.known_at<=%s ORDER BY gap_id""",(capture_ids,archive_id,root["knowledge_cutoff"])).fetchall()
                facts = cursor.execute("""SELECT * FROM mra.instrument_fact_revision WHERE capture_id=ANY(%s) AND fact_kind='LISTING_STATUS'
                    ORDER BY instrument_id,fact_kind,event_start,revision""",(capture_ids,)).fetchall()
                fact_summary = cursor.execute("""SELECT instrument_id,fact_kind,status_value,count(*) AS count,
                    min(event_start) AS first_event,max(event_start) AS last_event FROM mra.instrument_fact_revision
                    WHERE capture_id=ANY(%s) GROUP BY instrument_id,fact_kind,status_value ORDER BY instrument_id,fact_kind,status_value""",(capture_ids,)).fetchall()
            failed_requests = read_historical_failure_requests(connection, archive_id, root["knowledge_cutoff"],
                tuple(g["gap_id"] for g in gaps if g["fact_kind"] == "DATA_CAPTURE" and g["gap_kind"] == "PROVIDER_FAILURE"))
            fact_digest = sha256()
            fact_count = 0
            # Server cursor bounds transport and memory; only immutable identity
            # bytes are hashed, with the exact Capture/code artifacts retained.
            with connection.cursor(name="historical_fact_identity_roster") as cursor:
                cursor.execute("SELECT fact_revision_id FROM mra.instrument_fact_revision WHERE capture_id=ANY(%s) ORDER BY fact_revision_id",(capture_ids,))
                for row in cursor:
                    fact_digest.update(row[0].bytes)
                    fact_count += 1
        if config is None or not config["readable"]:
            raise ArtifactIntegrityError("historical inventory config is not readable")
        frozen = json.loads(self._bytes.read_bytes(config["content_sha256"],expected_size=config["size_bytes"]))
        if frozen.get("schema") != "mra-historical-acquisition-freeze-v1":
            raise ValueError("history-inventory requires the explicit historical acquisition contract")
        roster_hash = canonical_json_sha256({"securities":frozen["securities"],"price_inventory":frozen["price_inventory"],"limitation":frozen["universe"]})
        if roster_hash != root["instrument_scope_sha256"]:
            raise ArtifactIntegrityError("historical inventory frozen scope hash mismatch")
        observed = {s["instrument_id"]:s for s in securities}
        frozen_ids = [UUID(item[1]) for item in frozen["securities"]]
        if not set(observed).issubset(frozen_ids):
            raise ArtifactIntegrityError("historical acquisition observed an unplanned instrument")
        with self._pool.connection(read_only=True) as connection:
            original = connection.execute("SELECT instrument_id,canonical_code,exchange FROM mra.instrument WHERE instrument_id=ANY(%s)",(frozen_ids,)).fetchall()
        original_by_id = {r[0]:r for r in original}
        if set(original_by_id) != set(frozen_ids):
            raise ArtifactIntegrityError("frozen historical population lost its original instrument identities")
        securities = [{"instrument_id":UUID(identity),"canonical_code":original_by_id[UUID(identity)][1],
            "exchange":original_by_id[UUID(identity)][2],"identifier_value":identifier,
            "archive_security_master_observed":UUID(identity) in observed} for identifier,identity in frozen["securities"]]
        for capture in captures:
            if capture["status"] != "CAPTURED" or not capture["readable"]:
                raise ArtifactIntegrityError("historical inventory Capture Artifact is not readable")
            self._bytes.read_bytes(str(capture["content_sha256"]),expected_size=int(capture["size_bytes"]))
        by_bar = defaultdict(list)
        for bar in bars:
            if bar["timeframe"] == "DAILY":
                by_bar[(bar["instrument_id"],bar["session_id"],bar["price_basis"])].append(bar)
        by_gap = defaultdict(list)
        exchange_by_instrument = {s["instrument_id"]:s["exchange"] for s in securities}
        for gap in gaps:
            by_gap[(gap["instrument_id"],gap["session_id"],gap["price_basis"])].append(gap)
            request = failed_requests.get(gap["gap_id"])
            if request is not None:
                # The request's inclusive civil-date bounds select only observed
                # Archive sessions. This is failure attribution, never new facts.
                for session in sessions:
                    if (session["exchange"] == exchange_by_instrument.get(request.instrument_id)
                            and request.window_start.date() <= session["session_date"] <= request.window_end.date()):
                        by_gap[(request.instrument_id,session["session_id"],request.price_basis)].append(gap)
        # The frozen static roster is the denominator, including pre-listing days.
        inventory, exclusions = [], []
        for security in securities:
            counts: Counter[tuple[str,str]] = Counter()
            for session in sessions:
                if session["exchange"] != security["exchange"]:
                    continue
                for basis in ("RAW_UNADJUSTED","BACKWARD_ADJUSTED"):
                    key = (security["instrument_id"],session["session_id"],basis)
                    revisions = by_bar[key]
                    heads = [b for b in revisions if not any(s["supersedes_revision_id"]==b["bar_revision_id"] for s in revisions)]
                    missing = by_gap[key]
                    state = "AVAILABLE" if len(heads)==1 and not missing else "CONFLICT" if len(heads)>1 or (heads and missing) or any(g["gap_kind"] in {"CONFLICT","INVALID_OHLC"} for g in missing) else "SOURCE_GAP" if missing else "ABSENT"
                    counts[(basis,state)] += 1
                    if state != "AVAILABLE":
                        exclusions.append({"instrument_id":security["instrument_id"],"session_id":session["session_id"],
                            "session_date":session["session_date"],"price_basis":basis,"state":state,
                            "bar_revision_ids":[b["bar_revision_id"] for b in revisions],
                            "gaps":[{"gap_id":g["gap_id"],"kind":g["gap_kind"],"reason":g["reason_code"]} for g in missing]})
            inventory.append({**security,"counts":[{"price_basis":k[0],"state":k[1],"count":v} for k,v in sorted(counts.items())]})
        return {"schema":"mra-historical-inventory-v2","archive":root,"captures":captures,"securities":inventory,
            "calendar":sessions,"bar_revision_count":len(bars),"bar_revision_roster_sha256":sha256(b"".join(sorted(b["bar_revision_id"].bytes for b in bars))).hexdigest(),
            "roster_hash_algorithm":"SHA256_SORTED_UUID_BYTES_V1","instrument_fact_count":fact_count,
            "instrument_fact_roster_sha256":fact_digest.hexdigest(),"instrument_fact_summary":fact_summary,
            "source_gaps":gaps,"exclusions":exclusions,"instrument_facts":facts,
            "quality_sha256":canonical_json_sha256({"inventory":inventory,"exclusions":exclusions,"facts":facts}),
            "calendar_coverage_state":"OBSERVED" if sessions else "NOT_ESTIMABLE",
            "frozen_acquisition":frozen,
            "limitations":["STATIC_UNIVERSE","SURVIVORSHIP_LIMITED","EXPLORATORY_RETROSPECTIVE_NOT_FORMAL_PIT",
                "CALENDAR_AND_BAR_COVERAGE_DO_NOT_ESTABLISH_FEATURE_OR_LABEL_READINESS"],
            "database_bytes":self._database_bytes(),"physically_verified_capture_count":len(captures)}

    def _database_bytes(self) -> int:
        with self._pool.connection(read_only=True) as connection:
            row = connection.execute("SELECT pg_database_size(current_database())").fetchone()
        if row is None:
            raise RuntimeError("database size observation absent")
        return int(row[0])
