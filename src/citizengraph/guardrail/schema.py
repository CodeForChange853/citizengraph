"""Graph schema the guardrail allows (docs/specs.md section 1).

Only the official charter graph. The simulated workflow labels (Application, AT_STEP) live
in a separate store and are deliberately not allowed for Core 1 queries.
Names are matched exactly and case-sensitively, as Neo4j does.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Schema:
    labels: frozenset[str]
    relationship_types: frozenset[str]
    properties: frozenset[str]


OFFICIAL_SCHEMA = Schema(
    labels=frozenset(
        {"Office", "Service", "Requirement", "Agency", "Step", "Role", "Fee", "Variant", "Alias"}
    ),
    relationship_types=frozenset(
        {
            "OFFERS",
            "REQUIRES",
            "SECURED_AT",
            "APPLIES_WHEN",
            "PART_OF",
            "HAS_STEP",
            "NEXT",
            "PERFORMED_BY",
            "HAS_FEE",
            "KNOWN_AS",
        }
    ),
    # Union over all node labels; relationships carry no properties in the official graph.
    properties=frozenset(
        {
            # Office, Agency, Role, Service
            "id",
            "name",
            "title",
            "classification",
            "transaction_type",
            "who_may_avail",
            "total_fee_text",
            "total_time_text",
            "description",
            # Requirement
            "text",
            "group",
            "parent_id",
            "min_required",
            "condition_text",
            # Step
            "order",
            "citizen_action",
            "agency_action",
            "external_agency",
            "dur_min",
            "dur_max",
            "dur_unit",
            "minutes_min",
            "minutes_max",
            "day_type",
            # Fee
            "label",
            "amount_min",
            "amount_max",
            "unit",
            "note",
            # Variant, Alias
            "dimension",
            "value",
            "lang",
        }
    ),
)
