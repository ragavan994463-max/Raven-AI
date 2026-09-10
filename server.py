
"""
================================================================
RAVEN AI
Autonomous Simulation Intelligence Platform
================================================================

FILE:
    server.py

PART:
    1 / 2

PURPOSE:
    Production-oriented backend foundation for Raven AI.

DEFAULT MODE:
    FREE_LOCAL

IMPORTANT:
    - No API key required.
    - No paid service required.
    - No external network required.
    - Deterministic local intelligence engine.
    - Optional remote-model adapter is isolated.
    - Browser never receives secrets.

ARCHITECTURE:

    index.html
          |
          v
    HTTP API
          |
          v
    Request Validation
          |
          v
    Telemetry Normalization
          |
          v
    State Estimation
          |
          v
    Risk Analysis
          |
          v
    Candidate Generation
          |
          v
    Multi-objective Evaluation
          |
          v
    Safety Gate
          |
          v
    Decision Selection
          |
          v
    Decision Validation
          |
          v
    JSON Response

PART 2 WILL ADD:

    - HTTP server
    - /api/health
    - /api/decision
    - /api/config
    - static index.html
    - request limits
    - structured HTTP errors
    - server startup
    - graceful shutdown
    - final diagnostics

================================================================
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import signal
import threading
import time
import traceback
import uuid

from dataclasses import dataclass, field
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from pathlib import Path
from typing import Any, Optional


# ================================================================
# 1. APPLICATION IDENTITY
# ================================================================

APP_NAME = "RAVEN AI"

APP_VERSION = "2.0.0"

ENGINE_NAME = "RAVEN LOCAL INTELLIGENCE ENGINE"

ENGINE_VERSION = "2.0"

ENGINE_MODE = "FREE_LOCAL"

PROTOCOL_VERSION = "raven.v2"


# ================================================================
# 2. SERVER CONFIGURATION
# ================================================================

BASE_DIR = (
    Path(__file__)
    .resolve()
    .parent
)

INDEX_FILE = (
    BASE_DIR /
    "index.html"
)

HOST = os.environ.get(
    "RAVEN_HOST",
    "127.0.0.1",
)

try:
    PORT = int(
        os.environ.get(
            "RAVEN_PORT",
            "8000",
        )
    )
except ValueError:
    PORT = 8000


MAX_BODY_BYTES = 512 * 1024

MAX_JSON_DEPTH = 12

MAX_HISTORY = 128

MAX_STRING_LENGTH = 2048

REQUEST_TIMEOUT_SECONDS = 15

SERVER_STARTED_AT = time.time()


# ================================================================
# 3. DECISION CONTRACT
# ================================================================

ALLOWED_ACTIONS = frozenset(
    {
        "HOLD",
        "DIRECT",
        "SAFE_ROUTE",
        "SLOW_ADVANCE",
        "RESOURCE_DIVERSION",
        "REPLAN",
    }
)

ALLOWED_PRIORITIES = frozenset(
    {
        "SAFETY",
        "MISSION",
        "RESOURCE",
        "UNCERTAINTY",
    }
)

ALLOWED_GATES = frozenset(
    {
        "EXECUTE",
        "WAIT",
        "REJECT",
        "REPLAN",
    }
)

DEFAULT_ACTION = "HOLD"

DEFAULT_PRIORITY = "SAFETY"

DEFAULT_GATE = "WAIT"


# ================================================================
# 4. NUMERIC SAFETY
# ================================================================

def finite_number(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Convert arbitrary input to a finite float.
    """

    try:
        result = float(value)
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return default

    if not math.isfinite(result):
        return default

    return result


def finite_integer(
    value: Any,
    default: int = 0,
) -> int:
    """
    Convert arbitrary input to a safe integer.
    """

    try:
        result = int(
            finite_number(
                value,
                default,
            )
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
    ):
        return default

    return result


def clamp(
    value: Any,
    minimum: float,
    maximum: float,
) -> float:
    """
    Clamp a value to a closed interval.
    """

    number = finite_number(
        value,
        minimum,
    )

    return max(
        minimum,
        min(
            maximum,
            number,
        ),
    )


def bounded_int(
    value: Any,
    minimum: int,
    maximum: int,
) -> int:
    """
    Integer clamp.
    """

    number = finite_integer(
        value,
        minimum,
    )

    return max(
        minimum,
        min(
            maximum,
            number,
        ),
    )


def bounded_text(
    value: Any,
    default: str = "",
    maximum: int = MAX_STRING_LENGTH,
) -> str:
    """
    Convert a value into bounded text.
    """

    if value is None:
        return default

    text = str(value).strip()

    if not text:
        return default

    return text[:maximum]


# ================================================================
# 5. JSON SAFETY
# ================================================================

def json_safe(
    value: Any,
) -> Any:
    """
    Recursively sanitize values before serialization.

    This prevents accidental NaN/Infinity values from
    reaching the browser.
    """

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        return value

    if isinstance(
        value,
        int,
    ):
        return value

    if isinstance(
        value,
        float,
    ):
        if math.isfinite(value):
            return value

        return None

    if isinstance(
        value,
        str,
    ):
        return value[:MAX_STRING_LENGTH]

    if isinstance(
        value,
        list,
    ):
        return [
            json_safe(item)
            for item in value[:256]
        ]

    if isinstance(
        value,
        tuple,
    ):
        return [
            json_safe(item)
            for item in value[:256]
        ]

    if isinstance(
        value,
        dict,
    ):
        output: dict[str, Any] = {}

        for key, item in list(
            value.items()
        )[:256]:

            output[
                bounded_text(
                    key,
                    maximum=128,
                )
            ] = json_safe(
                item
            )

        return output

    return bounded_text(
        value
    )


# ================================================================
# 6. TIME UTILITIES
# ================================================================

def unix_ms() -> int:
    return int(
        time.time() * 1000
    )


def monotonic_ms() -> float:
    return (
        time.perf_counter() *
        1000.0
    )


# ================================================================
# 7. IDENTIFIERS
# ================================================================

def create_request_id() -> str:
    return (
        "REQ-"
        +
        uuid.uuid4()
        .hex[:16]
        .upper()
    )


def create_decision_id() -> str:
    return (
        "RAVEN-"
        +
        uuid.uuid4()
        .hex[:16]
        .upper()
    )


# ================================================================
# 8. VECTOR / DISTANCE UTILITIES
# ================================================================

def distance_2d(
    ax: float,
    ay: float,
    bx: float,
    by: float,
) -> float:
    return math.hypot(
        ax - bx,
        ay - by,
    )


def distance_between(
    first: Optional[dict[str, Any]],
    second: Optional[dict[str, Any]],
) -> float:

    if not first or not second:
        return float("inf")

    return distance_2d(
        finite_number(
            first.get("x")
        ),
        finite_number(
            first.get("y")
        ),
        finite_number(
            second.get("x")
        ),
        finite_number(
            second.get("y")
        ),
    )


# ================================================================
# 9. TELEMETRY STATE
# ================================================================

@dataclass(slots=True)
class RavenState:

    request_id: str = ""

    mission_id: str = ""

    mission_status: str = "RUNNING"

    mission_progress: float = 0.0

    remaining_distance: float = 0.0

    total_distance: float = 0.0

    speed: float = 0.0

    energy: float = 100.0

    health: float = 100.0

    stability: float = 100.0

    confidence: float = 100.0

    sensor_confidence: float = 100.0

    visibility: float = 100.0

    weather_intensity: float = 0.0

    ambient_risk: float = 0.0

    overall_risk: float = 0.0

    nearest_distance: float = 9999.0

    threat_count: int = 0

    current_action: str = "HOLD"

    agent_x: float = 0.0

    agent_y: float = 0.0

    heading: float = 0.0

    nearest_threat: Optional[
        dict[str, Any]
    ] = None

    current_waypoint: Optional[
        dict[str, Any]
    ] = None

    active_hazards: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    available_resources: list[
        dict[str, Any]
    ] = field(
        default_factory=list
    )

    memory: dict[
        str,
        Any
    ] = field(
        default_factory=dict
    )


# ================================================================
# 10. STATE NORMALIZATION
# ================================================================

class StateNormalizer:
    """
    Converts browser telemetry into a bounded RavenState.

    This is a trust boundary.

    The browser is treated as untrusted input.
    """

    @staticmethod
    def normalize(
        payload: dict[str, Any],
    ) -> RavenState:

        mission = payload.get(
            "mission"
        )

        if not isinstance(
            mission,
            dict,
        ):
            mission = {}


        environment = payload.get(
            "environment"
        )

        if not isinstance(
            environment,
            dict,
        ):
            environment = {}


        agent = payload.get(
            "agent"
        )

        if not isinstance(
            agent,
            dict,
        ):
            agent = {}


        risk = payload.get(
            "risk"
        )

        if not isinstance(
            risk,
            dict,
        ):
            risk = {}


        position = agent.get(
            "position"
        )

        if not isinstance(
            position,
            dict,
        ):
            position = {}


        current_waypoint = (
            mission.get(
                "current_waypoint"
            )
        )

        if not isinstance(
            current_waypoint,
            dict,
        ):
            current_waypoint = None


        nearest_threat = payload.get(
            "nearest_threat"
        )

        if not isinstance(
            nearest_threat,
            dict,
        ):
            nearest_threat = None


        hazards = payload.get(
            "active_hazards",
            [],
        )

        if not isinstance(
            hazards,
            list,
        ):
            hazards = []


        resources = payload.get(
            "available_resources",
            [],
        )

        if not isinstance(
            resources,
            list,
        ):
            resources = []


        state = RavenState(

            request_id=
                bounded_text(
                    payload.get(
                        "request_id"
                    ),
                    create_request_id(),
                    100,
                ),

            mission_id=
                bounded_text(
                    mission.get(
                        "id"
                    ),
                    "UNKNOWN-MISSION",
                    100,
                ),

            mission_status=
                bounded_text(
                    mission.get(
                        "status"
                    ),
                    "RUNNING",
                    40,
                ).upper(),

            mission_progress=
                clamp(
                    mission.get(
                        "progress"
                    ),
                    0.0,
                    100.0,
                ),

            remaining_distance=
                max(
                    0.0,
                    finite_number(
                        mission.get(
                            "remaining_distance"
                        ),
                        0.0,
                    ),
                ),

            total_distance=
                max(
                    0.0,
                    finite_number(
                        mission.get(
                            "total_distance"
                        ),
                        0.0,
                    ),
                ),

            speed=
                max(
                    0.0,
                    finite_number(
                        agent.get(
                            "speed"
                        )
                    ),
                ),

            energy=
                clamp(
                    agent.get(
                        "energy"
                    ),
                    0.0,
                    100.0,
                ),

            health=
                clamp(
                    agent.get(
                        "health"
                    ),
                    0.0,
                    100.0,
                ),

            stability=
                clamp(
                    agent.get(
                        "stability"
                    ),
                    0.0,
                    100.0,
                ),

            confidence=
                clamp(
                    agent.get(
                        "confidence"
                    ),
                    0.0,
                    100.0,
                ),

            sensor_confidence=
                clamp(
                    agent.get(
                        "sensor_confidence"
                    ),
                    0.0,
                    100.0,
                ),

            visibility=
                clamp(
                    environment.get(
                        "visibility"
                    ),
                    0.0,
                    100.0,
                ),

            weather_intensity=
                clamp(
                    environment.get(
                        "weather_intensity"
                    ),
                    0.0,
                    100.0,
                ),

            ambient_risk=
                clamp(
                    environment.get(
                        "ambient_risk"
                    ),
                    0.0,
                    100.0,
                ),

            overall_risk=
                clamp(
                    risk.get(
                        "percentage"
                    ),
                    0.0,
                    100.0,
                ),

            nearest_distance=
                max(
                    0.0,
                    finite_number(
                        risk.get(
                            "nearest_distance"
                        ),
                        9999.0,
                    ),
                ),

            threat_count=
                bounded_int(
                    risk.get(
                        "threat_count"
                    ),
                    0,
                    1000,
                ),

            current_action=
                bounded_text(
                    agent.get(
                        "current_action"
                    ),
                    "HOLD",
                    40,
                ).upper(),

            agent_x=
                finite_number(
                    position.get(
                        "x"
                    )
                ),

            agent_y=
                finite_number(
                    position.get(
                        "y"
                    )
                ),

            heading=
                finite_number(
                    agent.get(
                        "heading"
                    )
                ),

            nearest_threat=
                StateNormalizer._clean_entity(
                    nearest_threat
                ),

            current_waypoint=
                StateNormalizer._clean_entity(
                    current_waypoint
                ),

            active_hazards=
                StateNormalizer._clean_entities(
                    hazards
                ),

            available_resources=
                StateNormalizer._clean_entities(
                    resources
                ),

            memory=
                StateNormalizer._clean_memory(
                    payload.get(
                        "memory"
                    )
                ),

        )

        return state


    @staticmethod
    def _clean_entity(
        entity: Any,
    ) -> Optional[dict[str, Any]]:

        if not isinstance(
            entity,
            dict,
        ):
            return None

        cleaned: dict[
            str,
            Any
        ] = {}

        for key, value in list(
            entity.items()
        )[:32]:

            if isinstance(
                value,
                (
                    str,
                    int,
                    float,
                    bool,
                ),
            ):

                cleaned[
                    bounded_text(
                        key,
                        maximum=64,
                    )
                ] = json_safe(
                    value
                )

        return cleaned


    @staticmethod
    def _clean_entities(
        entities: list[Any],
    ) -> list[dict[str, Any]]:

        result = []

        for entity in entities[:64]:

            cleaned =
                StateNormalizer._clean_entity(
                    entity
                )

            if cleaned is not None:
                result.append(
                    cleaned
                )

        return result


    @staticmethod
    def _clean_memory(
        memory: Any,
    ) -> dict[str, Any]:

        if not isinstance(
            memory,
            dict,
        ):
            return {}


        output: dict[
            str,
            Any
        ] = {}


        for key in (
            "recent_decisions",
            "recent_observations",
            "recent_outcomes",
        ):

            value = memory.get(
                key
            )

            if isinstance(
                value,
                list,
            ):

                output[key] = [
                    json_safe(
                        item
                    )
                    for item
                    in value[-12:]
                ]

        return output


# ================================================================
# 11. STATE QUALITY
# ================================================================

@dataclass(slots=True)
class StateQuality:

    completeness: float

    consistency: float

    uncertainty: float

    trusted: bool


class StateEstimator:

    @staticmethod
    def estimate(
        state: RavenState,
    ) -> StateQuality:

        required_values = [

            state.mission_id,

            state.mission_status,

            state.mission_progress,

            state.energy,

            state.health,

            state.stability,

            state.confidence,

            state.sensor_confidence,

            state.visibility,

            state.overall_risk,

        ]


        present = 0

        for value in required_values:

            if value is not None:
                present += 1


        completeness = (
            present /
            len(required_values)
        ) * 100.0


        consistency = 100.0


        if (
            state.energy <= 0
            and
            state.current_action != "HOLD"
        ):

            consistency -= 30.0


        if (
            state.health <= 0
            and
            state.current_action != "HOLD"
        ):

            consistency -= 40.0


        if (
            state.overall_risk > 100
        ):

            consistency -= 30.0


        if (
            state.confidence <
            state.sensor_confidence * 0.1
        ):

            consistency -= 10.0


        uncertainty = clamp(

            (
                100.0 -
                state.confidence
            ) * 0.40

            +

            (
                100.0 -
                state.sensor_confidence
            ) * 0.30

            +

            (
                100.0 -
                state.visibility
            ) * 0.20

            +

            state.weather_intensity *
            0.10,

            0.0,
            100.0,
        )


        trusted = (
            completeness >= 80.0
            and
            consistency >= 70.0
        )


        return StateQuality(

            completeness=
                round(
                    completeness,
                    2,
                ),

            consistency=
                round(
                    clamp(
                        consistency,
                        0.0,
                        100.0,
                    ),
                    2,
                ),

            uncertainty=
                round(
                    uncertainty,
                    2,
                ),

            trusted=
                trusted,

        )


# ================================================================
# 12. RISK MODEL
# ================================================================

@dataclass(slots=True)
class RiskAssessment:

    overall: float

    proximity: float

    environmental: float

    uncertainty: float

    resource: float

    health: float

    severity: str


class RiskEngine:

    @staticmethod
    def assess(
        state: RavenState,
        quality: StateQuality,
    ) -> RiskAssessment:

        proximity = 0.0


        if state.nearest_distance < 20:
            proximity = 100.0

        elif state.nearest_distance < 40:
            proximity = 80.0

        elif state.nearest_distance < 80:
            proximity = 55.0

        elif state.nearest_distance < 140:
            proximity = 30.0

        else:
            proximity = 5.0


        proximity += min(
            25.0,
            state.threat_count * 4.0,
        )


        proximity = clamp(
            proximity,
            0.0,
            100.0,
        )


        environmental = clamp(

            state.ambient_risk * 0.55

            +

            state.weather_intensity * 0.20

            +

            (
                100.0 -
                state.visibility
            ) * 0.25,

            0.0,
            100.0,
        )


        uncertainty = quality.uncertainty


        resource = clamp(

            (
                100.0 -
                state.energy
            ) * 0.70

            +

            (
                100.0 -
                state.stability
            ) * 0.30,

            0.0,
            100.0,
        )


        health = clamp(

            (
                100.0 -
                state.health
            ) * 0.75

            +

            (
                100.0 -
                state.stability
            ) * 0.25,

            0.0,
            100.0,
        )


        overall = clamp(

            proximity * 0.30

            +

            environmental * 0.20

            +

            uncertainty * 0.15

            +

            resource * 0.10

            +

            health * 0.25,

            0.0,
            100.0,
        )


        if overall >= 85:
            severity = "CRITICAL"

        elif overall >= 65:
            severity = "HIGH"

        elif overall >= 40:
            severity = "MODERATE"

        else:
            severity = "LOW"


        return RiskAssessment(

            overall=
                round(
                    overall,
                    2,
                ),

            proximity=
                round(
                    proximity,
                    2,
                ),

            environmental=
                round(
                    environmental,
                    2,
                ),

            uncertainty=
                round(
                    uncertainty,
                    2,
                ),

            resource=
                round(
                    resource,
                    2,
                ),

            health=
                round(
                    health,
                    2,
                ),

            severity=
                severity,

        )


# ================================================================
# 13. MISSION ANALYSIS
# ================================================================

@dataclass(slots=True)
class MissionAssessment:

    pressure: float

    urgency: float

    completion: float

    remaining_distance: float


class MissionEngine:

    @staticmethod
    def assess(
        state: RavenState,
    ) -> MissionAssessment:

        completion =
            clamp(
                state.mission_progress,
                0.0,
                100.0,
            )


        pressure =
            clamp(
                100.0 -
                completion,
                0.0,
                100.0,
            )


        if state.mission_status == "COMPLETED":

            pressure = 0.0


        urgency = clamp(

            pressure * 0.65

            +

            min(
                35.0,
                state.remaining_distance /
                20.0,
            ),

            0.0,
            100.0,
        )


        return MissionAssessment(

            pressure=
                round(
                    pressure,
                    2,
                ),

            urgency=
                round(
                    urgency,
                    2,
                ),

            completion=
                round(
                    completion,
                    2,
                ),

            remaining_distance=
                round(
                    state.remaining_distance,
                    2,
                ),

        )


# ================================================================
# 14. RESOURCE ANALYSIS
# ================================================================

@dataclass(slots=True)
class ResourceAssessment:

    pressure: float

    available: int

    best_target: Optional[str]


class ResourceEngine:

    @staticmethod
    def assess(
        state: RavenState,
    ) -> ResourceAssessment:

        pressure = clamp(

            (
                100.0 -
                state.energy
            ) * 0.75

            +

            (
                100.0 -
                state.stability
            ) * 0.25,

            0.0,
            100.0,
        )


        best_target = None


        if state.available_resources:

            first =
                state.available_resources[0]

            candidate =
                first.get(
                    "id"
                )

            if candidate is not None:

                best_target =
                    bounded_text(
                        candidate,
                        maximum=100,
                    )


        return ResourceAssessment(

            pressure=
                round(
                    pressure,
                    2,
                ),

            available=
                len(
                    state.available_resources
                ),

            best_target=
                best_target,

        )


# ================================================================
# 15. CANDIDATE MODEL
# ================================================================

@dataclass(slots=True)
class Candidate:

    action: str

    progress_score: float

    safety_score: float

    resource_score: float

    feasibility_score: float

    risk_score: float

    priority: str

    gate: str

    reason: str

    target: Optional[str] = None

    total_score: float = 0.0

    rejected: bool = False

    rejection_reason: str = ""


# ================================================================
# 16. DECISION MEMORY
# ================================================================

class DecisionMemory:

    def __init__(
        self,
        maximum: int = MAX_HISTORY,
    ) -> None:

        self.maximum = maximum

        self._items: list[
            dict[str, Any]
        ] = []

        self._lock =
            threading.RLock()


    def add(
        self,
        item: dict[str, Any],
    ) -> None:

        safe =
            json_safe(
                item
            )


        with self._lock:

            self._items.append(
                safe
            )

            if len(
                self._items
            ) > self.maximum:

                del self._items[
                    :len(self._items) -
                    self.maximum
                ]


    def recent(
        self,
        count: int = 8,
    ) -> list[
        dict[str, Any]
    ]:

        count =
            bounded_int(
                count,
                1,
                self.maximum,
            )

        with self._lock:

            return list(
                self._items[-count:]
            )


    def clear(
        self,
    ) -> None:

        with self._lock:

            self._items.clear()


    def size(
        self,
    ) -> int:

        with self._lock:

            return len(
                self._items
            )


# ================================================================
# 17. LOCAL DECISION ENGINE
# ================================================================

class RavenLocalEngine:
    """
    Raven's free autonomous decision engine.

    Design principles:

        1. Observe.
        2. Estimate.
        3. Generate alternatives.
        4. Score alternatives.
        5. Apply hard safety constraints.
        6. Select.
        7. Validate.
        8. Explain the decision.

    It does not claim to be an LLM.
    """

    def __init__(
        self,
        memory: DecisionMemory,
    ) -> None:

        self.memory = memory


    # ------------------------------------------------------------
    # Candidate generation
    # ------------------------------------------------------------

    def generate_candidates(
        self,
        state: RavenState,
        risk: RiskAssessment,
        mission: MissionAssessment,
        resources: ResourceAssessment,
    ) -> list[Candidate]:

        candidates: list[
            Candidate
        ] = []


        # ========================================================
        # HOLD
        # ========================================================

        candidates.append(

            Candidate(

                action="HOLD",

                progress_score=10.0,

                safety_score=100.0,

                resource_score=95.0,

                feasibility_score=100.0,

                risk_score=5.0,

                priority="SAFETY",

                gate="WAIT",

                reason=(
                    "Maintain a stable state while "
                    "additional certainty is obtained."
                ),

            )

        )


        # ========================================================
        # DIRECT
        # ========================================================

        candidates.append(

            Candidate(

                action="DIRECT",

                progress_score=95.0,

                safety_score=max(
                    0.0,
                    100.0 -
                    risk.overall * 0.85,
                ),

                resource_score=(
                    75.0
                    if state.energy >= 50
                    else 40.0
                ),

                feasibility_score=(
                    92.0
                    if risk.uncertainty < 35
                    else 55.0
                ),

                risk_score=clamp(
                    risk.overall + 15.0,
                    0.0,
                    100.0,
                ),

                priority="MISSION",

                gate="EXECUTE",

                reason=(
                    "Direct progression offers the "
                    "highest mission advancement."
                ),

            )

        )


        # ========================================================
        # SAFE ROUTE
        # ========================================================

        candidates.append(

            Candidate(

                action="SAFE_ROUTE",

                progress_score=72.0,

                safety_score=min(
                    100.0,
                    100.0 -
                    risk.overall * 0.45 +
                    15.0,
                ),

                resource_score=78.0,

                feasibility_score=(
                    92.0
                    if state.visibility >= 35
                    else 70.0
                ),

                risk_score=max(
                    0.0,
                    risk.overall - 20.0,
                ),

                priority="SAFETY",

                gate="EXECUTE",

                reason=(
                    "A safer route preserves mission "
                    "progress while reducing exposure."
                ),

            )

        )


        # ========================================================
        # SLOW ADVANCE
        # ========================================================

        candidates.append(

            Candidate(

                action="SLOW_ADVANCE",

                progress_score=58.0,

                safety_score=min(
                    100.0,
                    100.0 -
                    risk.overall * 0.40 +
                    20.0,
                ),

                resource_score=85.0,

                feasibility_score=95.0,

                risk_score=max(
                    0.0,
                    risk.overall - 12.0,
                ),

                priority=(
                    "UNCERTAINTY"
                    if risk.uncertainty >= 50
                    else "SAFETY"
                ),

                gate="EXECUTE",

                reason=(
                    "Controlled movement preserves "
                    "progress without aggressive exposure."
                ),

            )

        )


        # ========================================================
        # RESOURCE DIVERSION
        # ========================================================

        candidates.append(

            Candidate(

                action="RESOURCE_DIVERSION",

                progress_score=30.0,

                safety_score=min(
                    100.0,
                    85.0 +
                    (
                        100.0 -
                        risk.overall
                    ) * 0.15,
                ),

                resource_score=(
                    100.0
                    if resources.available > 0
                    else 5.0
                ),

                feasibility_score=(
                    92.0
                    if resources.available > 0
                    else 10.0
                ),

                risk_score=max(
                    0.0,
                    risk.overall - 5.0,
                ),

                priority="RESOURCE",

                gate=(
                    "EXECUTE"
                    if resources.available > 0
                    else "REPLAN"
                ),

                reason=(
                    "Prioritize resource recovery "
                    "to preserve operational endurance."
                ),

                target=
                    resources.best_target,

            )

        )


        # ========================================================
        # REPLAN
        # ========================================================

        candidates.append(

            Candidate(

                action="REPLAN",

                progress_score=38.0,

                safety_score=min(
                    100.0,
                    100.0 -
                    risk.overall * 0.30 +
                    25.0,
                ),

                resource_score=88.0,

                feasibility_score=98.0,

                risk_score=max(
                    0.0,
                    risk.overall - 25.0,
                ),

                priority="UNCERTAINTY",

                gate="REPLAN",

                reason=(
                    "Re-evaluate the mission strategy "
                    "because the current state is uncertain."
                ),

            )

        )


        return candidates


    # ------------------------------------------------------------
    # Weight calculation
    # ------------------------------------------------------------

    @staticmethod
    def weights(
        state: RavenState,
        risk: RiskAssessment,
        mission: MissionAssessment,
        resources: ResourceAssessment,
    ) -> dict[str, float]:

        weights = {

            "progress":
                0.28,

            "safety":
                0.34,

            "resource":
                0.16,

            "feasibility":
                0.22,

            "risk_penalty":
                0.16,

        }


        if risk.overall >= 70:

            weights["safety"] = 0.50

            weights["progress"] = 0.16

            weights["resource"] = 0.14

            weights["feasibility"] = 0.20


        if resources.pressure >= 70:

            weights["resource"] = max(
                weights["resource"],
                0.28,
            )


        if risk.uncertainty >= 65:

            weights["safety"] = max(
                weights["safety"],
                0.46,
            )

            weights["progress"] = min(
                weights["progress"],
                0.18,
            )


        if mission.urgency >= 80 and risk.overall < 55:

            weights["progress"] = max(
                weights["progress"],
                0.34,
            )


        return weights


    # ------------------------------------------------------------
    # Candidate scoring
    # ------------------------------------------------------------

    def score_candidates(
        self,
        candidates: list[Candidate],
        state: RavenState,
        risk: RiskAssessment,
        mission: MissionAssessment,
        resources: ResourceAssessment,
    ) -> list[Candidate]:

        weights =
            self.weights(
                state,
                risk,
                mission,
                resources,
            )


        for candidate in candidates:

            score = (

                candidate.progress_score
                *
                weights["progress"]

                +

                candidate.safety_score
                *
                weights["safety"]

                +

                candidate.resource_score
                *
                weights["resource"]

                +

                candidate.feasibility_score
                *
                weights["feasibility"]

                -

                candidate.risk_score
                *
                weights["risk_penalty"]

            )


            candidate.total_score =
                clamp(
                    score,
                    0.0,
                    100.0,
                )


        return candidates


    # ------------------------------------------------------------
    # Hard constraints
    # ------------------------------------------------------------

    @staticmethod
    def apply_constraints(
        candidate: Candidate,
        state: RavenState,
        risk: RiskAssessment,
        resources: ResourceAssessment,
    ) -> Candidate:

        # Critical health.
        if state.health <= 8:

            candidate.rejected = True

            candidate.rejection_reason = (
                "Health reserve is critically low."
            )

            return candidate


        # Critical risk.
        if risk.overall >= 92:

            if candidate.action != "HOLD":

                candidate.rejected = True

                candidate.rejection_reason = (
                    "Environmental risk exceeds "
                    "the critical safety threshold."
                )

                return candidate


        # Critical energy.
        if state.energy <= 7:

            if (
                candidate.action
                not in {
                    "HOLD",
                    "RESOURCE_DIVERSION",
                }
            ):

                candidate.rejected = True

                candidate.rejection_reason = (
                    "Energy reserve is critically low."
                )

                return candidate


        # Poor visibility.
        if (
            state.visibility <= 12
            and
            candidate.action == "DIRECT"
        ):

            candidate.rejected = True

            candidate.rejection_reason = (
                "Direct movement is not allowed "
                "under critically poor visibility."
            )

            return candidate


        # Very low confidence.
        if (
            state.confidence <= 12
            and
            candidate.action == "DIRECT"
        ):

            candidate.rejected = True

            candidate.rejection_reason = (
                "State confidence is too low "
                "for direct progression."
            )

            return candidate


        # Resource action without resources.
        if (
            candidate.action ==
            "RESOURCE_DIVERSION"
            and
            resources.available <= 0
        ):

            candidate.rejected = True

            candidate.rejection_reason = (
                "No resource target is available."
            )

            return candidate


        return candidate


    # ------------------------------------------------------------
    # Select
    # ------------------------------------------------------------

    @staticmethod
    def select(
        candidates: list[Candidate],
    ) -> Optional[Candidate]:

        valid = [

            candidate

            for candidate
            in candidates

            if not candidate.rejected

        ]


        if not valid:
            return None


        valid.sort(

            key=lambda candidate: (

                candidate.total_score,

                candidate.safety_score,

                candidate.feasibility_score,

                candidate.resource_score,

            ),

            reverse=True,

        )


        return valid[0]


    # ------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------

    @staticmethod
    def confidence(
        state: RavenState,
        risk: RiskAssessment,
        selected: Candidate,
        candidates: list[Candidate],
    ) -> float:

        base = (

            state.confidence * 0.25

            +

            state.sensor_confidence * 0.25

            +

            state.visibility * 0.15

            +

            state.stability * 0.15

            +

            selected.feasibility_score * 0.20

        )


        ordered = sorted(

            [
                candidate
                for candidate
                in candidates
                if not candidate.rejected
            ],

            key=lambda candidate:
                candidate.total_score,

            reverse=True,

        )


        if len(ordered) >= 2:

            margin = (

                ordered[0].total_score
                -
                ordered[1].total_score

            )

            base += clamp(
                margin * 0.35,
                0.0,
                12.0,
            )


        if risk.overall >= 80:
            base *= 0.82


        if risk.uncertainty >= 70:
            base *= 0.80


        return clamp(
            base,
            5.0,
            98.0,
        )


    # ------------------------------------------------------------
    # Rationale
    # ------------------------------------------------------------

    @staticmethod
    def rationale(
        state: RavenState,
        risk: RiskAssessment,
        mission: MissionAssessment,
        resources: ResourceAssessment,
        selected: Candidate,
    ) -> str:

        factors: list[str] = []


        if risk.overall >= 70:

            factors.append(
                f"risk is elevated at "
                f"{risk.overall:.0f}%"
            )

        elif risk.overall <= 25:

            factors.append(
                f"risk is controlled at "
                f"{risk.overall:.0f}%"
            )


        if state.energy <= 25:

            factors.append(
                f"energy is limited at "
                f"{state.energy:.0f}%"
            )


        if state.visibility < 40:

            factors.append(
                f"visibility is "
                f"{state.visibility:.0f}%"
            )


        if state.threat_count > 0:

            factors.append(
                f"{state.threat_count} "
                f"active threat signal(s)"
            )


        if risk.uncertainty >= 60:

            factors.append(
                f"state uncertainty is "
                f"{risk.uncertainty:.0f}%"
            )


        if not factors:

            factors.append(
                "operating conditions remain "
                "within normal bounds"
            )


        text = (

            selected.reason

            +

            " Key factors: "

            +

            "; ".join(
                factors
            )

            +

            "."

        )


        return text[
            :420
        ]


    # ------------------------------------------------------------
    # Full decision
    # ------------------------------------------------------------

    def decide(
        self,
        state: RavenState,
        quality: StateQuality,
        risk: RiskAssessment,
        mission: MissionAssessment,
        resources: ResourceAssessment,
    ) -> dict[str, Any]:

        candidates =
            self.generate_candidates(
                state,
                risk,
                mission,
                resources,
            )


        candidates =
            self.score_candidates(
                candidates,
                state,
                risk,
                mission,
                resources,
            )


        constrained: list[
            Candidate
        ] = []


        for candidate in candidates:

            constrained.append(

                self.apply_constraints(
                    candidate,
                    state,
                    risk,
                    resources,
                )

            )


        selected =
            self.select(
                constrained
            )


        if selected is None:

            selected =
                Candidate(

                    action="HOLD",

                    progress_score=5.0,

                    safety_score=100.0,

                    resource_score=100.0,

                    feasibility_score=100.0,

                    risk_score=0.0,

                    priority="SAFETY",

                    gate="WAIT",

                    reason=(
                        "No candidate passed the "
                        "safety constraints."
                    ),

                    total_score=100.0,

                )


        confidence =
            self.confidence(
                state,
                risk,
                selected,
                constrained,
            )


        if confidence < 18:

            action = "HOLD"

            gate = "WAIT"

            priority = "UNCERTAINTY"

        else:

            action =
                selected.action

            gate =
                selected.gate

            priority =
                selected.priority


        if (
            action not in
            ALLOWED_ACTIONS
        ):

            action = "HOLD"

            gate = "WAIT"

            priority = "SAFETY"


        if (
            priority not in
            ALLOWED_PRIORITIES
        ):

            priority = "SAFETY"


        if (
            gate not in
            ALLOWED_GATES
        ):

            gate = "WAIT"


        target =
            selected.target


        if (
            target is None
            and
            state.current_waypoint
        ):

            target =
                bounded_text(
                    state.current_waypoint.get(
                        "id"
                    ),
                    "",
                    100,
                )


        if action == "HOLD":

            target = None


        decision = {

            "id":
                create_decision_id(),

            "action":
                action,

            "target":
                target,

            "confidence":
                round(
                    confidence,
                    2,
                ),

            "priority":
                priority,

            "gate":
                gate,

            "rationale":
                self.rationale(
                    state,
                    risk,
                    mission,
                    resources,
                    selected,
                ),

            "progress_score":
                round(
                    selected.progress_score,
                    2,
                ),

            "safety_score":
                round(
                    selected.safety_score,
                    2,
                ),

            "resource_score":
                round(
                    selected.resource_score,
                    2,
                ),

            "feasibility_score":
                round(
                    selected.feasibility_score,
                    2,
                ),

            "risk_score":
                round(
                    selected.risk_score,
                    2,
                ),

            "replan_after":
                (
                    2
                    if risk.overall >= 75
                    else 4
                ),

            "source":
                "RAVEN_LOCAL_ENGINE",

            "mode":
                ENGINE_MODE,

            "engine_version":
                ENGINE_VERSION,

            "valid":
                True,

        }


        return decision


# ================================================================
# 18. DECISION VALIDATOR
# ================================================================

class DecisionValidator:

    @staticmethod
    def validate(
        decision: Any,
    ) -> dict[str, Any]:

        if not isinstance(
            decision,
            dict,
        ):

            raise ValueError(
                "Decision is not an object."
            )


        action =
            bounded_text(
                decision.get(
                    "action"
                ),
                DEFAULT_ACTION,
                40,
            ).upper()


        if action not in ALLOWED_ACTIONS:
            action = DEFAULT_ACTION


        priority =
            bounded_text(
                decision.get(
                    "priority"
                ),
                DEFAULT_PRIORITY,
                40,
            ).upper()


        if priority not in ALLOWED_PRIORITIES:
            priority = DEFAULT_PRIORITY


        gate =
            bounded_text(
                decision.get(
                    "gate"
                ),
                DEFAULT_GATE,
                40,
            ).upper()


        if gate not in ALLOWED_GATES:
            gate = DEFAULT_GATE


        confidence =
            clamp(
                decision.get(
                    "confidence"
                ),
                0.0,
                100.0,
            )


        if confidence < 18:

            action = "HOLD"

            gate = "WAIT"

            priority = "UNCERTAINTY"


        target =
            decision.get(
                "target"
            )


        if target is not None:

            target =
                bounded_text(
                    target,
                    "",
                    100,
                )

            if not target:
                target = None


        rationale =
            bounded_text(
                decision.get(
                    "rationale"
                ),
                "No decision rationale supplied.",
                420,
            )


        return {

            "id":
                bounded_text(
                    decision.get(
                        "id"
                    ),
                    create_decision_id(),
                    100,
                ),

            "action":
                action,

            "target":
                target,

            "confidence":
                round(
                    confidence,
                    2,
                ),

            "priority":
                priority,

            "gate":
                gate,

            "rationale":
                rationale,

            "progress_score":
                round(
                    clamp(
                        decision.get(
                            "progress_score"
                        ),
                        0.0,
                        100.0,
                    ),
                    2,
                ),

            "safety_score":
                round(
                    clamp(
                        decision.get(
                            "safety_score"
                        ),
                        0.0,
                        100.0,
                    ),
                    2,
                ),

            "resource_score":
                round(
                    clamp(
                        decision.get(
                            "resource_score"
                        ),
                        0.0,
                        100.0,
                    ),
                    2,
                ),

            "feasibility_score":
                round(
                    clamp(
                        decision.get(
                            "feasibility_score"
                        ),
                        0.0,
                        100.0,
                    ),
                    2,
                ),

            "risk_score":
                round(
                    clamp(
                        decision.get(
                            "risk_score"
                        ),
                        0.0,
                        100.0,
                    ),
                    2,
                ),

            "replan_after":
                bounded_int(
                    decision.get(
                        "replan_after"
                    ),
                    1,
                    30,
                ),

            "source":
                "RAVEN_LOCAL_ENGINE",

            "mode":
                ENGINE_MODE,

            "valid":
                True,

        }


# ================================================================
# 19. ENGINE COORDINATOR
# ================================================================

class RavenCoordinator:
    """
    Coordinates the entire local reasoning pipeline.
    """

    def __init__(self) -> None:

        self.memory =
            DecisionMemory()

        self.engine =
            RavenLocalEngine(
                self.memory
            )

        self.lock =
            threading.RLock()

        self.request_count = 0

        self.success_count = 0

        self.failure_count = 0

        self.total_latency_ms = 0.0


    def process(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        started =
            monotonic_ms()


        request_id =
            bounded_text(
                payload.get(
                    "request_id"
                ),
                create_request_id(),
                100,
            )


        try:

            state =
                StateNormalizer.normalize(
                    payload
                )


            state.request_id =
                request_id


            quality =
                StateEstimator.estimate(
                    state
                )


            risk =
                RiskEngine.assess(
                    state,
                    quality,
                )


            mission =
                MissionEngine.assess(
                    state
                )


            resources =
                ResourceEngine.assess(
                    state
                )


            decision =
                self.engine.decide(
                    state,
                    quality,
                    risk,
                    mission,
                    resources,
                )


            decision =
                DecisionValidator.validate(
                    decision
                )


            latency =
                monotonic_ms() -
                started


            decision["latency_ms"] =
                round(
                    latency,
                    2,
                )


            with self.lock:

                self.request_count += 1

                self.success_count += 1

                self.total_latency_ms += latency


            self.memory.add({

                "timestamp":
                    unix_ms(),

                "request_id":
                    request_id,

                "mission_id":
                    state.mission_id,

                "action":
                    decision["action"],

                "confidence":
                    decision["confidence"],

                "risk":
                    risk.overall,

                "energy":
                    state.energy,

                "progress":
                    state.mission_progress,

            })


            return {

                "ok":
                    True,

                "protocol":
                    PROTOCOL_VERSION,

                "request_id":
                    request_id,

                "engine":
                    ENGINE_NAME,

                "engine_version":
                    ENGINE_VERSION,

                "mode":
                    ENGINE_MODE,

                "model":
                    None,

                "decision":
                    decision,

                "analysis": {

                    "state_quality":
                        {
                            "completeness":
                                quality.completeness,

                            "consistency":
                                quality.consistency,

                            "uncertainty":
                                quality.uncertainty,

                            "trusted":
                                quality.trusted,
                        },

                    "risk":
                        {
                            "overall":
                                risk.overall,

                            "proximity":
                                risk.proximity,

                            "environmental":
                                risk.environmental,

                            "uncertainty":
                                risk.uncertainty,

                            "resource":
                                risk.resource,

                            "health":
                                risk.health,

                            "severity":
                                risk.severity,
                        },

                    "mission":
                        {
                            "pressure":
                                mission.pressure,

                            "urgency":
                                mission.urgency,

                            "completion":
                                mission.completion,

                            "remaining_distance":
                                mission.remaining_distance,
                        },

                    "resources":
                        {
                            "pressure":
                                resources.pressure,

                            "available":
                                resources.available,

                            "best_target":
                                resources.best_target,
                        },

                },

                "server_time":
                    unix_ms(),

            }


        except Exception as exc:

            with self.lock:

                self.request_count += 1

                self.failure_count += 1


            raise RavenProcessingError(
                str(exc)
            ) from exc


    def health(
        self,
    ) -> dict[str, Any]:

        with self.lock:

            average_latency = (

                self.total_latency_ms /
                self.success_count

                if self.success_count
                else 0.0

            )


            return {

                "ok":
                    True,

                "service":
                    APP_NAME,

                "version":
                    APP_VERSION,

                "engine":
                    ENGINE_NAME,

                "engine_version":
                    ENGINE_VERSION,

                "mode":
                    ENGINE_MODE,

                "model":
                    None,

                "paid_api":
                    False,

                "api_key_required":
                    False,

                "requests":
                    self.request_count,

                "successful_requests":
                    self.success_count,

                "failed_requests":
                    self.failure_count,

                "average_latency_ms":
                    round(
                        average_latency,
                        2,
                    ),

                "memory_entries":
                    self.memory.size(),

                "uptime_seconds":
                    round(
                        time.time()
                        -
                        SERVER_STARTED_AT,
                        2,
                    ),

                "timestamp":
                    unix_ms(),

            }


# ================================================================
# 20. CUSTOM ERRORS
# ================================================================

class RavenError(Exception):
    """
    Base Raven exception.
    """


class RavenValidationError(
    RavenError
):
    """
    Invalid client request.
    """


class RavenProcessingError(
    RavenError
):
    """
    Internal decision processing failure.
    """


# ================================================================
# 21. REQUEST VALIDATION
# ================================================================

def validate_payload(
    payload: Any,
) -> dict[str, Any]:

    if not isinstance(
        payload,
        dict,
    ):

        raise RavenValidationError(
            "Request body must be a JSON object."
        )


    if len(
        payload
    ) > 128:

        raise RavenValidationError(
            "Request contains too many fields."
        )


    schema =
        payload.get(
            "schema_version"
        )


    if schema is not None:

        schema =
            bounded_text(
                schema,
                "",
                100,
            )


        if not schema.startswith(
            "raven."
        ):

            raise RavenValidationError(
                "Unsupported Raven schema."
            )


    return payload


# ================================================================
# 22. REQUEST FINGERPRINT
# ================================================================

def request_fingerprint(
    payload: dict[str, Any],
) -> str:

    compact =
        json.dumps(
            json_safe(
                payload
            ),
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            ensure_ascii=True,
        )


    return hashlib.sha256(
        compact.encode(
            "utf-8"
        )
    ).hexdigest()[:24]


# ================================================================
# 23. GLOBAL COORDINATOR
# ================================================================

RAVEN_COORDINATOR =
    RavenCoordinator()


# ================================================================
# 24. FREE MODE STATUS
# ================================================================

def local_mode_info() -> dict[str, Any]:

    return {

        "name":
            APP_NAME,

        "mode":
            ENGINE_MODE,

        "engine":
            ENGINE_NAME,

        "version":
            ENGINE_VERSION,

        "paid_api":
            False,

        "api_key_required":
            False,

        "network_required":
            False,

        "remote_model":
            None,

        "status":
            "READY",

    }


# ================================================================
# 25. SELF TEST
# ================================================================

def build_self_test_payload() -> dict[str, Any]:

    return {

        "schema_version":
            "raven.decision_request.v2",

        "request_id":
            "SELFTEST",

        "mission": {

            "id":
                "SELFTEST-MISSION",

            "status":
                "RUNNING",

            "progress":
                35,

            "remaining_distance":
                650,

            "total_distance":
                1000,

            "current_waypoint": {

                "id":
                    "WP-02",

            },

        },

        "environment": {

            "weather":
                "CLEAR",

            "weather_intensity":
                8,

            "visibility":
                94,

            "ambient_risk":
                12,

        },

        "agent": {

            "id":
                "RAVEN-SELFTEST",

            "position": {

                "x":
                    100,

                "y":
                    120,

            },

            "heading":
                0,

            "speed":
                20,

            "energy":
                82,

            "health":
                100,

            "stability":
                94,

            "confidence":
                91,

            "sensor_confidence":
                93,

            "progress":
                35,

            "current_action":
                "HOLD",

        },

        "risk": {

            "percentage":
                14,

            "nearest_distance":
                180,

            "threat_count":
                0,

        },

        "nearest_threat":
            None,

        "active_hazards":
            [],

        "available_resources":
            [],

        "memory": {

            "recent_decisions":
                [],

            "recent_observations":
                [],

            "recent_outcomes":
                [],

        },

    }


def run_self_test() -> bool:

    try:

        payload =
            build_self_test_payload()


        result =
            RAVEN_COORDINATOR.process(
                payload
            )


        if not result.get(
            "ok"
        ):
            return False


        decision =
            result.get(
                "decision"
            )


        if not isinstance(
            decision,
            dict,
        ):
            return False


        if (
            decision.get(
                "action"
            )
            not in ALLOWED_ACTIONS
        ):
            return False


        if (
            decision.get(
                "priority"
            )
            not in ALLOWED_PRIORITIES
        ):
            return False


        if (
            decision.get(
                "gate"
            )
            not in ALLOWED_GATES
        ):
            return False


        confidence =
            finite_number(
                decision.get(
                    "confidence"
                ),
                -1,
            )


        if not (
            0 <=
            confidence <=
            100
        ):
            return False


        return True


    except Exception:

        traceback.print_exc()

        return False


# ================================================================
# 26. STARTUP INFORMATION
# ================================================================

def startup_banner() -> None:

    print()
    print("=" * 68)
    print(" RAVEN AI")
    print(" Autonomous Simulation Intelligence Platform")
    print("=" * 68)
    print(
        f" Version       : {APP_VERSION}"
    )
    print(
        f" Engine        : {ENGINE_NAME}"
    )
    print(
        f" Mode          : {ENGINE_MODE}"
    )
    print(
        f" Host          : {HOST}"
    )
    print(
        f" Port          : {PORT}"
    )
    print(
        f" Frontend      : {INDEX_FILE}"
    )
    print(
        " API billing   : DISABLED"
    )
    print(
        " Network AI    : DISABLED"
    )
    print("=" * 68)
    print()


# ================================================================
# 27. PART 1 COMPLETION MARKER
# ================================================================

PART_1_READY = True


if __name__ == "__main__":

    startup_banner()

    print(
        "Running Raven Part 1 self-test..."
    )


    if run_self_test():

        print(
            "[PASS] Raven intelligence core."
        )

        print(
            "[PASS] State normalization."
        )

        print(
            "[PASS] Risk engine."
        )

        print(
            "[PASS] Candidate engine."
        )

        print(
            "[PASS] Safety constraints."
        )

        print(
            "[PASS] Decision validation."
        )

        print()
        print(
            "Part 1 is ready."
        )

        print(
            "Part 2 adds the HTTP server."
        )

    else:

        print(
            "[FAIL] Raven self-test."
        )

        raise SystemExit(
            1
        )


# ================================================================
# END OF PART 1/2
# ================================================================
# ============================================================
# RAVEN AI
# Autonomous Decision Simulation Backend
# server.py — PART 2 / 2
#
# FINAL SERVER / HTTP / API / SAFETY / DIAGNOSTICS LAYER
#
# Requirements:
#   Python 3.10+
#
# External packages:
#   NONE
#
# Run:
#   python server.py
#
# Browser:
#   http://127.0.0.1:8000
# ============================================================

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


# ============================================================
# 1. SERVER IDENTITY
# ============================================================

RAVEN_SERVER_VERSION = "1.0.0"
RAVEN_PROTOCOL_VERSION = "1.0"
RAVEN_HOST = os.environ.get("RAVEN_HOST", "127.0.0.1")

try:
    RAVEN_PORT = int(os.environ.get("RAVEN_PORT", "8000"))
except ValueError:
    RAVEN_PORT = 8000

RAVEN_ROOT = Path(__file__).resolve().parent
RAVEN_INDEX = RAVEN_ROOT / "index.html"


# ============================================================
# 2. RUNTIME STATE
# ============================================================

SERVER_STARTED_AT = time.time()

REQUEST_COUNT = 0
DECISION_COUNT = 0
ERROR_COUNT = 0

LAST_REQUEST_AT: float | None = None
LAST_DECISION_AT: float | None = None
LAST_ERROR: str | None = None


# ============================================================
# 3. SAFE JSON UTILITIES
# ============================================================

def json_bytes(payload: Any) -> bytes:
    """
    Serialize JSON safely for HTTP responses.
    """
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def now_ms() -> int:
    return int(time.time() * 1000)


def clamp_number(
    value: Any,
    minimum: float,
    maximum: float,
    default: float,
) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if number != number:
        return default

    if number == float("inf") or number == float("-inf"):
        return default

    return max(minimum, min(maximum, number))


def clean_string(
    value: Any,
    maximum_length: int = 500,
    default: str = "",
) -> str:
    if value is None:
        return default

    text = str(value)

    text = text.replace("\x00", "")
    text = text.strip()

    if len(text) > maximum_length:
        text = text[:maximum_length]

    return text


def safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()

        if lowered in {"true", "1", "yes", "on"}:
            return True

        if lowered in {"false", "0", "no", "off"}:
            return False

    if isinstance(value, (int, float)):
        return bool(value)

    return default


# ============================================================
# 4. ERROR RESPONSE FACTORY
# ============================================================

def error_payload(
    message: str,
    code: str = "RAVEN_ERROR",
    status: int = 400,
) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": clean_string(message, 1000),
            "status": status,
        },
        "server": {
            "name": "RAVEN AI",
            "version": RAVEN_SERVER_VERSION,
            "protocol": RAVEN_PROTOCOL_VERSION,
        },
        "timestamp": now_ms(),
    }


def success_payload(
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": True,
        "server": {
            "name": "RAVEN AI",
            "version": RAVEN_SERVER_VERSION,
            "protocol": RAVEN_PROTOCOL_VERSION,
        },
        "timestamp": now_ms(),
    }

    if data:
        payload.update(data)

    return payload


# ============================================================
# 5. REQUEST BODY PARSER
# ============================================================

MAX_REQUEST_BYTES = 256 * 1024


def parse_json_body(
    handler: BaseHTTPRequestHandler,
) -> dict[str, Any]:
    content_length_header = handler.headers.get("Content-Length")

    if content_length_header is None:
        raise ValueError("Missing Content-Length header.")

    try:
        content_length = int(content_length_header)
    except ValueError as exc:
        raise ValueError("Invalid Content-Length header.") from exc

    if content_length < 0:
        raise ValueError("Invalid request size.")

    if content_length > MAX_REQUEST_BYTES:
        raise ValueError("Request body exceeds the allowed limit.")

    raw = handler.rfile.read(content_length)

    if len(raw) != content_length:
        raise ValueError("Incomplete request body.")

    if not raw:
        return {}

    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Request body is not valid UTF-8.") from exc

    try:
        data = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError("Request body is not valid JSON.") from exc

    if not isinstance(data, dict):
        raise ValueError("Request JSON must be an object.")

    return data


# ============================================================
# 6. TELEMETRY NORMALIZATION
# ============================================================

def normalize_frontend_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert browser telemetry into a conservative server-side
    representation.

    Unknown fields are ignored.
    Values are bounded before entering the decision engine.
    """

    telemetry = payload.get("telemetry")

    if telemetry is None:
        telemetry = payload

    if not isinstance(telemetry, dict):
        telemetry = {}

    normalized = {
        "tick": int(
            clamp_number(
                telemetry.get("tick", 0),
                0,
                10_000_000_000,
                0,
            )
        ),

        "x": clamp_number(
            telemetry.get("x", 0),
            -1_000_000,
            1_000_000,
            0,
        ),

        "y": clamp_number(
            telemetry.get("y", 0),
            -1_000_000,
            1_000_000,
            0,
        ),

        "speed": clamp_number(
            telemetry.get("speed", 0),
            0,
            1000,
            0,
        ),

        "energy": clamp_number(
            telemetry.get("energy", 100),
            0,
            100,
            100,
        ),

        "visibility": clamp_number(
            telemetry.get("visibility", 100),
            0,
            100,
            100,
        ),

        "risk": clamp_number(
            telemetry.get("risk", 0),
            0,
            100,
            0,
        ),

        "threats": int(
            clamp_number(
                telemetry.get("threats", 0),
                0,
                1000,
                0,
            )
        ),

        "confidence": clamp_number(
            telemetry.get("confidence", 1),
            0,
            1,
            1,
        ),

        "weather": clean_string(
            telemetry.get("weather", "CLEAR"),
            100,
            "CLEAR",
        ),

        "mission_progress": clamp_number(
            telemetry.get("mission_progress", 0),
            0,
            100,
            0,
        ),
    }

    normalized["running"] = safe_bool(
        telemetry.get("running", True),
        True,
    )

    return normalized


# ============================================================
# 7. SERVER-SIDE SAFETY GATE
# ============================================================

ALLOWED_ACTIONS = {
    "ADVANCE",
    "EVADE",
    "SLOW",
    "HOLD",
    "REROUTE",
    "RESOURCE_RECOVERY",
}


def safety_gate(
    decision: dict[str, Any],
    telemetry: dict[str, Any],
) -> dict[str, Any]:
    """
    Final deterministic safety layer.

    The decision engine may recommend an action, but this layer
    has the final authority over unsafe values.
    """

    result = dict(decision)

    action = clean_string(
        result.get("action", "HOLD"),
        64,
        "HOLD",
    ).upper()

    if action not in ALLOWED_ACTIONS:
        action = "HOLD"

    risk = clamp_number(
        telemetry.get("risk", 0),
        0,
        100,
        0,
    )

    energy = clamp_number(
        telemetry.get("energy", 100),
        0,
        100,
        100,
    )

    visibility = clamp_number(
        telemetry.get("visibility", 100),
        0,
        100,
        100,
    )

    threats = int(
        clamp_number(
            telemetry.get("threats", 0),
            0,
            1000,
            0,
        )
    )

    safety_override = None

    if risk >= 85:
        action = "HOLD"
        safety_override = "CRITICAL_RISK"

    elif visibility <= 8:
        action = "SLOW"
        safety_override = "LOW_VISIBILITY"

    elif energy <= 5:
        action = "RESOURCE_RECOVERY"
        safety_override = "CRITICAL_ENERGY"

    elif threats >= 8 and action == "ADVANCE":
        action = "EVADE"
        safety_override = "THREAT_DENSITY"

    speed = clamp_number(
        result.get("speed", 1),
        0,
        100,
        1,
    )

    if action == "HOLD":
        speed = 0

    elif action == "SLOW":
        speed = min(speed, 0.45)

    elif action == "EVADE":
        speed = min(speed, 0.70)

    elif action == "RESOURCE_RECOVERY":
        speed = min(speed, 0.30)

    confidence = clamp_number(
        result.get("confidence", 0.5),
        0,
        1,
        0.5,
    )

    priority = clean_string(
        result.get("priority", "SAFETY"),
        64,
        "SAFETY",
    ).upper()

    if priority not in {
        "SAFETY",
        "MISSION",
        "RESOURCE",
        "UNCERTAINTY",
    }:
        priority = "SAFETY"

    rationale = clean_string(
        result.get("rationale", ""),
        1000,
        "",
    )

    if safety_override:
        if rationale:
            rationale = (
                f"{rationale} "
                f"Safety gate applied: {safety_override}."
            )
        else:
            rationale = (
                f"Safety gate applied: {safety_override}."
            )

    result.update(
        {
            "action": action,
            "speed": round(speed, 4),
            "confidence": round(confidence, 4),
            "priority": priority,
            "rationale": rationale,
            "safety_override": safety_override,
            "validated": True,
        }
    )

    return result


# ============================================================
# 8. DECISION CONTRACT
# ============================================================

def decision_contract(
    decision: dict[str, Any],
) -> dict[str, Any]:
    """
    Return only browser-safe decision fields.
    """

    action = clean_string(
        decision.get("action", "HOLD"),
        64,
        "HOLD",
    ).upper()

    if action not in ALLOWED_ACTIONS:
        action = "HOLD"

    target_id = decision.get("target_id")

    if target_id is not None:
        target_id = clean_string(
            target_id,
            100,
            "",
        )

        if not target_id:
            target_id = None

    return {
        "action": action,

        "target_id": target_id,

        "speed": round(
            clamp_number(
                decision.get("speed", 0),
                0,
                100,
                0,
            ),
            4,
        ),

        "priority": clean_string(
            decision.get("priority", "SAFETY"),
            64,
            "SAFETY",
        ).upper(),

        "confidence": round(
            clamp_number(
                decision.get("confidence", 0),
                0,
                1,
                0,
            ),
            4,
        ),

        "rationale": clean_string(
            decision.get("rationale", ""),
            1000,
            "",
        ),

        "replan_after": int(
            clamp_number(
                decision.get("replan_after", 10),
                1,
                500,
                10,
            )
        ),

        "safety_override": decision.get(
            "safety_override"
        ),

        "validated": True,
    }


# ============================================================
# 9. DECISION REQUEST
# ============================================================

def process_decision_request(
    payload: dict[str, Any],
) -> dict[str, Any]:
    global DECISION_COUNT
    global LAST_DECISION_AT

    telemetry = normalize_frontend_payload(payload)

    # --------------------------------------------------------
    # Prefer the local Raven intelligence engine supplied
    # by Part 1.
    # --------------------------------------------------------

    if "RAVEN_COORDINATOR" not in globals():
        raise RuntimeError(
            "RAVEN_COORDINATOR is missing. "
            "Part 1 was not loaded correctly."
        )

    coordinator = globals()["RAVEN_COORDINATOR"]

    # --------------------------------------------------------
    # Coordinator compatibility layer
    # --------------------------------------------------------

    decision: dict[str, Any]

    if hasattr(coordinator, "decide"):
        raw = coordinator.decide(telemetry)

    elif hasattr(coordinator, "process"):
        raw = coordinator.process(telemetry)

    elif hasattr(coordinator, "evaluate"):
        raw = coordinator.evaluate(telemetry)

    elif hasattr(coordinator, "run"):
        raw = coordinator.run(telemetry)

    else:
        raise RuntimeError(
            "RAVEN_COORDINATOR does not expose a supported "
            "decision method."
        )

    if not isinstance(raw, dict):
        raise RuntimeError(
            "Decision engine returned an invalid result."
        )

    decision = safety_gate(
        raw,
        telemetry,
    )

    decision = decision_contract(
        decision,
    )

    DECISION_COUNT += 1
    LAST_DECISION_AT = time.time()

    return success_payload(
        {
            "decision": decision,
            "telemetry": telemetry,
            "engine": {
                "mode": "LOCAL_RAVEN",
                "model": "RAVEN-LOCAL-ENGINE",
                "external_api": False,
                "paid_api": False,
            },
            "cycle": {
                "number": DECISION_COUNT,
                "timestamp": now_ms(),
            },
        }
    )


# ============================================================
# 10. HEALTH SYSTEM
# ============================================================

def health_payload() -> dict[str, Any]:
    uptime = max(0.0, time.time() - SERVER_STARTED_AT)

    return success_payload(
        {
            "health": {
                "status": "OPERATIONAL",
                "uptime_seconds": round(uptime, 3),
                "requests": REQUEST_COUNT,
                "decisions": DECISION_COUNT,
                "errors": ERROR_COUNT,
                "last_request": (
                    now_ms()
                    if LAST_REQUEST_AT is not None
                    else None
                ),
                "last_decision": (
                    int(LAST_DECISION_AT * 1000)
                    if LAST_DECISION_AT is not None
                    else None
                ),
            }
        }
    )


# ============================================================
# 11. SYSTEM INFORMATION
# ============================================================

def system_info_payload() -> dict[str, Any]:
    return success_payload(
        {
            "system": {
                "name": "RAVEN AI",
                "codename": "Autonomous Decision Intelligence",
                "version": RAVEN_SERVER_VERSION,
                "protocol": RAVEN_PROTOCOL_VERSION,
                "mode": "LOCAL",
                "external_api": False,
                "payment_required": False,
                "api_key_required": False,
                "python": sys.version.split()[0],
                "platform": sys.platform,
                "index_html": RAVEN_INDEX.exists(),
            },

            "capabilities": [
                "state normalization",
                "risk assessment",
                "mission reasoning",
                "resource reasoning",
                "candidate generation",
                "multi-objective scoring",
                "safety constraints",
                "decision confidence",
                "stateful decision memory",
                "simulation integration",
                "replanning",
                "diagnostics",
            ],

            "actions": sorted(ALLOWED_ACTIONS),
        }
    )


# ============================================================
# 12. RESET ENGINE
# ============================================================

def reset_engine() -> dict[str, Any]:
    """
    Reset the coordinator if Part 1 exposes a reset operation.
    """

    global RAVEN_COORDINATOR

    coordinator = globals().get(
        "RAVEN_COORDINATOR"
    )

    if coordinator is None:
        raise RuntimeError(
            "RAVEN_COORDINATOR is unavailable."
        )

    reset_performed = False

    if hasattr(coordinator, "reset"):
        coordinator.reset()
        reset_performed = True

    elif hasattr(coordinator, "clear"):
        coordinator.clear()
        reset_performed = True

    elif hasattr(coordinator, "memory"):
        memory = getattr(
            coordinator,
            "memory",
            None,
        )

        if memory is not None:
            if hasattr(memory, "clear"):
                memory.clear()
                reset_performed = True

            elif hasattr(memory, "_items"):
                memory._items.clear()
                reset_performed = True

    return success_payload(
        {
            "reset": {
                "performed": reset_performed,
                "timestamp": now_ms(),
            }
        }
    )


# ============================================================
# 13. SELF TEST
# ============================================================

def run_server_self_test() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    # --------------------------------------------------------
    # Check 1 — index
    # --------------------------------------------------------

    checks.append(
        {
            "name": "index.html",
            "passed": RAVEN_INDEX.exists(),
            "detail": str(RAVEN_INDEX),
        }
    )

    # --------------------------------------------------------
    # Check 2 — coordinator
    # --------------------------------------------------------

    coordinator_exists = (
        "RAVEN_COORDINATOR" in globals()
        and globals()["RAVEN_COORDINATOR"] is not None
    )

    checks.append(
        {
            "name": "decision_coordinator",
            "passed": coordinator_exists,
            "detail": (
                "available"
                if coordinator_exists
                else "missing"
            ),
        }
    )

    # --------------------------------------------------------
    # Check 3 — decision engine
    # --------------------------------------------------------

    engine_ok = False
    engine_detail = ""

    if coordinator_exists:
        coordinator = globals()["RAVEN_COORDINATOR"]

        methods = [
            "decide",
            "process",
            "evaluate",
            "run",
        ]

        available_methods = [
            method
            for method in methods
            if hasattr(coordinator, method)
        ]

        engine_ok = bool(available_methods)
        engine_detail = ", ".join(
            available_methods
        )

    checks.append(
        {
            "name": "decision_interface",
            "passed": engine_ok,
            "detail": engine_detail,
        }
    )

    # --------------------------------------------------------
    # Check 4 — sample decision
    # --------------------------------------------------------

    sample_ok = False
    sample_detail = ""

    if engine_ok:
        try:
            sample = process_decision_request(
                {
                    "telemetry": {
                        "tick": 1,
                        "x": 100,
                        "y": 100,
                        "speed": 1,
                        "energy": 92,
                        "visibility": 90,
                        "risk": 10,
                        "threats": 1,
                        "confidence": 0.90,
                        "weather": "CLEAR",
                        "mission_progress": 15,
                        "running": True,
                    }
                }
            )

            sample_ok = bool(
                sample.get("ok")
                and isinstance(
                    sample.get("decision"),
                    dict,
                )
            )

            sample_detail = (
                sample
                .get("decision", {})
                .get("action", "UNKNOWN")
            )

        except Exception as exc:
            sample_detail = str(exc)

    checks.append(
        {
            "name": "sample_decision",
            "passed": sample_ok,
            "detail": sample_detail,
        }
    )

    passed = sum(
        1
        for check in checks
        if check["passed"]
    )

    total = len(checks)

    return success_payload(
        {
            "self_test": {
                "passed": passed == total,
                "checks_passed": passed,
                "checks_total": total,
                "checks": checks,
            }
        }
    )


# ============================================================
# 14. HTTP HANDLER
# ============================================================

class RavenRequestHandler(
    BaseHTTPRequestHandler
):
    server_version = "RAVEN-AI/" + RAVEN_SERVER_VERSION

    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    def log_message(
        self,
        format_string: str,
        *args: Any,
    ) -> None:
        message = format_string % args

        print(
            f"[RAVEN HTTP] "
            f"{self.address_string()} "
            f"{message}"
        )

    # --------------------------------------------------------
    # Headers
    # --------------------------------------------------------

    def _send_headers(
        self,
        status: int,
        content_type: str,
        length: int,
    ) -> None:
        self.send_response(status)

        self.send_header(
            "Content-Type",
            content_type,
        )

        self.send_header(
            "Content-Length",
            str(length),
        )

        self.send_header(
            "Cache-Control",
            "no-store",
        )

        self.send_header(
            "X-Raven-Version",
            RAVEN_SERVER_VERSION,
        )

        self.send_header(
            "X-Content-Type-Options",
            "nosniff",
        )

        self.send_header(
            "Referrer-Policy",
            "no-referrer",
        )

        self.end_headers()

    # --------------------------------------------------------
    # JSON response
    # --------------------------------------------------------

    def send_json(
        self,
        payload: dict[str, Any],
        status: int = 200,
    ) -> None:
        body = json_bytes(payload)

        self._send_headers(
            status,
            "application/json; charset=utf-8",
            len(body),
        )

        self.wfile.write(body)

    # --------------------------------------------------------
    # Text response
    # --------------------------------------------------------

    def send_text(
        self,
        text: str,
        status: int = 200,
        content_type: str = "text/plain; charset=utf-8",
    ) -> None:
        body = text.encode("utf-8")

        self._send_headers(
            status,
            content_type,
            len(body),
        )

        self.wfile.write(body)

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    def do_GET(self) -> None:
        global REQUEST_COUNT
        global LAST_REQUEST_AT

        REQUEST_COUNT += 1
        LAST_REQUEST_AT = time.time()

        parsed = urlparse(self.path)
        path = parsed.path

        try:

            if path == "/":
                self.serve_index()
                return

            if path == "/index.html":
                self.serve_index()
                return

            if path == "/api/health":
                self.send_json(
                    health_payload()
                )
                return

            if path == "/api/info":
                self.send_json(
                    system_info_payload()
                )
                return

            if path == "/api/self-test":
                self.send_json(
                    run_server_self_test()
                )
                return

            if path == "/api/decision":
                self.send_json(
                    error_payload(
                        "POST telemetry to this endpoint.",
                        "METHOD_NOT_ALLOWED",
                        405,
                    ),
                    405,
                )
                return

            self.send_json(
                error_payload(
                    "Route not found.",
                    "NOT_FOUND",
                    404,
                ),
                404,
            )

        except Exception as exc:
            self.handle_exception(exc)

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    def do_POST(self) -> None:
        global REQUEST_COUNT
        global LAST_REQUEST_AT

        REQUEST_COUNT += 1
        LAST_REQUEST_AT = time.time()

        parsed = urlparse(self.path)
        path = parsed.path

        try:

            payload = parse_json_body(self)

            if path == "/api/decision":

                result = process_decision_request(
                    payload
                )

                self.send_json(
                    result
                )

                return

            if path == "/api/reset":

                result = reset_engine()

                self.send_json(
                    result
                )

                return

            if path == "/api/self-test":

                result = run_server_self_test()

                self.send_json(
                    result
                )

                return

            self.send_json(
                error_payload(
                    "POST route not found.",
                    "NOT_FOUND",
                    404,
                ),
                404,
            )

        except ValueError as exc:
            self.send_json(
                error_payload(
                    str(exc),
                    "INVALID_REQUEST",
                    400,
                ),
                400,
            )

        except Exception as exc:
            self.handle_exception(exc)

    # --------------------------------------------------------
    # OPTIONS
    # --------------------------------------------------------

    def do_OPTIONS(self) -> None:
        self.send_response(204)

        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET, POST, OPTIONS",
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type",
        )

        self.send_header(
            "Content-Length",
            "0",
        )

        self.end_headers()

    # --------------------------------------------------------
    # Index serving
    # --------------------------------------------------------

    def serve_index(self) -> None:

        if not RAVEN_INDEX.exists():

            self.send_text(
                (
                    "RAVEN AI\n\n"
                    "index.html was not found.\n"
                    f"Expected location:\n{RAVEN_INDEX}"
                ),
                404,
            )

            return

        try:
            content = RAVEN_INDEX.read_bytes()

        except OSError as exc:
            self.send_text(
                f"Unable to read index.html: {exc}",
                500,
            )
            return

        self._send_headers(
            200,
            "text/html; charset=utf-8",
            len(content),
        )

        self.wfile.write(content)

    # --------------------------------------------------------
    # Exception handling
    # --------------------------------------------------------

    def handle_exception(
        self,
        exc: Exception,
    ) -> None:

        global ERROR_COUNT
        global LAST_ERROR

        ERROR_COUNT += 1
        LAST_ERROR = str(exc)

        print(
            "\n[RAVEN ERROR]"
        )

        traceback.print_exc()

        try:
            self.send_json(
                error_payload(
                    "Internal Raven server error.",
                    "INTERNAL_ERROR",
                    500,
                ),
                500,
            )

        except Exception:
            pass


# ============================================================
# 15. THREADING SERVER
# ============================================================

class RavenHTTPServer(
    ThreadingHTTPServer
):

    allow_reuse_address = True

    daemon_threads = True


# ============================================================
# 16. STARTUP DIAGNOSTICS
# ============================================================

def print_startup_report() -> None:

    line = "=" * 68

    print()
    print(line)
    print("                    RAVEN AI")
    print("          Autonomous Decision Intelligence")
    print(line)

    print(
        f"Version       : {RAVEN_SERVER_VERSION}"
    )

    print(
        f"Protocol      : {RAVEN_PROTOCOL_VERSION}"
    )

    print(
        f"Mode          : LOCAL"
    )

    print(
        f"External API  : DISABLED"
    )

    print(
        f"Paid API      : NO"
    )

    print(
        f"API Key       : NOT REQUIRED"
    )

    print(
        f"Python        : {sys.version.split()[0]}"
    )

    print(
        f"Index         : "
        f"{'FOUND' if RAVEN_INDEX.exists() else 'MISSING'}"
    )

    print(
        f"Root          : {RAVEN_ROOT}"
    )

    print(
        f"Address       : "
        f"http://{RAVEN_HOST}:{RAVEN_PORT}"
    )

    print(line)

    try:

        test = run_server_self_test()

        self_test = test.get(
            "self_test",
            {},
        )

        passed = self_test.get(
            "checks_passed",
            0,
        )

        total = self_test.get(
            "checks_total",
            0,
        )

        print(
            f"Self-test     : "
            f"{passed}/{total}"
        )

        if self_test.get("passed"):
            print(
                "System status : READY"
            )
        else:
            print(
                "System status : CHECK REQUIRED"
            )

    except Exception as exc:

        print(
            "Self-test     : FAILED"
        )

        print(
            f"Reason        : {exc}"
        )

    print(line)
    print()


# ============================================================
# 17. SERVER CREATION
# ============================================================

def create_server() -> RavenHTTPServer:

    server = RavenHTTPServer(
        (
            RAVEN_HOST,
            RAVEN_PORT,
        ),
        RavenRequestHandler,
    )

    return server


# ============================================================
# 18. GRACEFUL SHUTDOWN
# ============================================================

def run_server() -> None:

    server = create_server()

    print_startup_report()

    print(
        "[RAVEN] Server online."
    )

    print(
        "[RAVEN] Open the URL shown above."
    )

    print(
        "[RAVEN] Press CTRL+C to stop."
    )

    print()

    try:

        server.serve_forever(
            poll_interval=0.25
        )

    except KeyboardInterrupt:

        print()
        print(
            "[RAVEN] Shutdown requested."
        )

    finally:

        try:
            server.shutdown()
        except Exception:
            pass

        try:
            server.server_close()
        except Exception:
            pass

        print(
            "[RAVEN] Server stopped."
        )


# ============================================================
# 19. MAIN ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_server()

