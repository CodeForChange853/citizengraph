"""Gateway: the deterministic front end. No model is called here.

``process(message, session, now=None)`` turns a citizen message (English, Filipino or Taglish,
with typos, several requests at once, spam or noise) into clean sub-requests, a clarifying
question, an echo to confirm, or a refusal. See ``docs/gateway_notes.md``.
"""

from citizengraph.gateway.aliases import AliasError, AliasTable, load_aliases
from citizengraph.gateway.config import GatewayConfig, GatewayConfigError, load_config
from citizengraph.gateway.pipeline import Gateway, default_gateway, process
from citizengraph.gateway.types import (
    INTENTS,
    STATUSES,
    ClarifyOption,
    Echo,
    EchoItem,
    GatewayResult,
    SessionState,
    SubRequest,
    Unavailable,
)

__all__ = [
    "INTENTS",
    "STATUSES",
    "AliasError",
    "AliasTable",
    "ClarifyOption",
    "Echo",
    "EchoItem",
    "Gateway",
    "GatewayConfig",
    "GatewayConfigError",
    "GatewayResult",
    "SessionState",
    "SubRequest",
    "Unavailable",
    "default_gateway",
    "load_aliases",
    "load_config",
    "process",
]
