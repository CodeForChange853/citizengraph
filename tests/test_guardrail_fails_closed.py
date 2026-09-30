"""Guardrail test suite (docs/specs.md section 4).

No Neo4j, no model, no network. The guardrail must fail closed: anything it does not
positively recognise is rejected, and it never raises.
"""

from pathlib import Path

import pytest
import yaml

from citizengraph.guardrail import validator
from citizengraph.guardrail.lexer import LexError, tokenize
from citizengraph.guardrail.validator import ValidationResult, validate_cypher

LIMITS_YAML = Path(__file__).resolve().parents[1] / "config" / "limits.yaml"
MAX_LIMIT = yaml.safe_load(LIMITS_YAML.read_text())["core1"]["cypher_limit_max"]

BASE = "MATCH (s:Service) "
TAIL = " RETURN s.name LIMIT 5"


def rejected(query, *fragments: str) -> ValidationResult:
    """Assert the query is rejected, and that a reason mentions each fragment."""
    result = validate_cypher(query)
    assert result.ok is False, f"expected rejection: {query!r}"
    assert result.reasons, "a rejection must carry reasons"
    joined = " | ".join(result.reasons).lower()
    for fragment in fragments:
        assert fragment.lower() in joined, f"{fragment!r} not in reasons: {result.reasons}"
    return result


def accepted(query: str) -> None:
    result = validate_cypher(query)
    assert result.ok is True, f"expected pass: {query!r} -> {result.reasons}"
    assert result.reasons == []


# --------------------------------------------------------------------------- fail closed


@pytest.mark.parametrize(
    "bad", [None, 42, 3.5, b"MATCH (s:Service) RETURN s LIMIT 1", [], {}, object()]
)
def test_non_string_input_is_rejected_not_raised(bad):
    rejected(bad, "string")


@pytest.mark.parametrize("empty", ["", " ", "\n\t  \r\n", "// only a comment", "/* only */"])
def test_empty_input_is_rejected(empty):
    rejected(empty)


@pytest.mark.parametrize(
    "garbage",
    [
        "\x00",
        "MATCH (",
        ")))(((",
        "{{{{",
        "]]]]",
        "MATCH (s:Service RETURN s LIMIT 1",
        "MATCH (s:Service)) RETURN s LIMIT 1",
        "MATCH s:Service RETURN s LIMIT",
        "'",
        '"',
        "/*",
        "//",
        "$",
        "\\",
        "@@@",
        "MATCH (s:) RETURN s LIMIT 1",
        "MATCH (s:Service:) RETURN s LIMIT 1",
        "MATCH (s:Service) RETURN s LIMIT",
        # Long inputs get short ids: pytest puts the id in PYTEST_CURRENT_TEST, and Windows
        # rejects environment variables over 32,767 characters.
        pytest.param("😀" * 500, id="emoji-500"),
        pytest.param("A" * 100_000, id="very-long-100k"),
        pytest.param("MATCH " + "(" * 2000, id="open-parens-2000"),
    ],
)
def test_garbage_never_raises_and_never_passes(garbage):
    result = validate_cypher(garbage)
    assert isinstance(result, ValidationResult)
    assert result.ok is False
    assert result.reasons


def test_internal_error_fails_closed(monkeypatch):
    def boom(_text):
        raise RuntimeError("tokenizer exploded")

    monkeypatch.setattr(validator, "tokenize", boom)
    result = validate_cypher("MATCH (s:Service) RETURN s LIMIT 1")
    assert result.ok is False
    assert any("internal" in r.lower() for r in result.reasons)


def test_result_reasons_are_bounded():
    result = validate_cypher("CREATE " * 200)
    assert result.ok is False
    assert len(result.reasons) <= 50
    assert all(len(r) <= 200 for r in result.reasons)


# --------------------------------------------------------------------------- valid queries

VALID = [
    "MATCH (s:Service) RETURN s LIMIT 1",
    "match (s:Service) return s limit 1",
    "MATCH (s:Service {id: 'bplo_new_permit'}) RETURN s.name LIMIT 1",
    'MATCH (s:Service {id: "bplo_new_permit"})-[:REQUIRES]->(r:Requirement) '
    "RETURN r.text, r.group, r.min_required LIMIT 50",
    "MATCH (o:Office)-[:OFFERS]->(s:Service) WHERE o.id = 'bplo' RETURN s.name ORDER BY s.name LIMIT 20",
    "MATCH (s:Service)-[:HAS_STEP]->(st:Step) WHERE s.id = $sid "
    "RETURN st.order, st.citizen_action, st.agency_action ORDER BY st.order LIMIT 30",
    "MATCH (s:Service)-[:HAS_STEP]->(st:Step)-[:PERFORMED_BY]->(ro:Role) RETURN ro.title LIMIT 10",
    "MATCH (s:Service)-[:HAS_STEP]->(a:Step)-[:NEXT]->(b:Step) RETURN a.id, b.id LIMIT 10",
    "MATCH (s:Service)-[:HAS_FEE]->(f:Fee)-[:APPLIES_WHEN]->(v:Variant) "
    "WHERE v.dimension = 'applicant_type' AND v.value = 'renewal' "
    "RETURN f.label, f.amount_min, f.amount_max, f.unit, f.note LIMIT 10",
    "MATCH (s:Service)-[:REQUIRES]->(r:Requirement) "
    "OPTIONAL MATCH (r)-[:SECURED_AT]->(a:Agency) RETURN r.text, a.name LIMIT 50",
    "MATCH (r:Requirement)-[:PART_OF]->(p:Requirement) RETURN r.id, p.id, r.parent_id LIMIT 50",
    "MATCH (s:Service)-[:KNOWN_AS]->(al:Alias) WHERE al.lang = 'fil' RETURN al.text, al.lang LIMIT 10",
    "MATCH (s:Service)-[:REQUIRES|HAS_FEE]->(x) RETURN x LIMIT 10",
    "MATCH (s:Service)-[:REQUIRES]->(r:Requirement)-[:SECURED_AT]->(a:Agency) "
    "RETURN a.name, count(r) AS n ORDER BY n DESC SKIP 5 LIMIT 10",
    "MATCH (s:Service) WITH s, size(s.name) AS len WHERE len > 3 RETURN s.name, len LIMIT 10",
    "MATCH (s:Service) WHERE s.id IN ['a', 'b', 'c'] RETURN s.name LIMIT 3",
    "MATCH (s:Service) WHERE s.name STARTS WITH 'Bus' AND NOT s.name CONTAINS 'Old' RETURN s LIMIT 5",
    "MATCH (s:Service) WHERE s:Service RETURN s.id LIMIT 5",
    "MATCH (s:Service) WHERE s.description IS NOT NULL RETURN s.description LIMIT 5",
    "UNWIND ['a', 'b'] AS sid MATCH (s:Service {id: sid}) RETURN s.name LIMIT 5",
    "MATCH (s:Service) RETURN DISTINCT s.classification ORDER BY s.classification ASC LIMIT 5",
    "MATCH (s:Service) RETURN s.id AS id, CASE WHEN s.total_fee_text IS NULL THEN 'n/a' "
    "ELSE s.total_fee_text END AS fee LIMIT 5",
    "MATCH (st:Step) RETURN st.dur_min, st.dur_max, st.dur_unit, st.minutes_min, st.minutes_max, "
    "st.day_type, st.external_agency LIMIT 5",
    "MATCH (s:Service) RETURN s.who_may_avail, s.transaction_type, s.total_time_text LIMIT 5",
    "MATCH (r:Requirement) RETURN r.condition_text, r.parent_id LIMIT 5",
    "MATCH (v:Variant) RETURN v.dimension, v.value LIMIT 5",
    "MATCH (s:Service) WHERE s.name = 'a;b' RETURN s LIMIT 5",
    "MATCH (s:Service) RETURN s LIMIT 5  ",
    "MATCH (s:Service)\n  WHERE s.id = 'x' // trailing note\n  RETURN s /* inline */ LIMIT 5\n",
    "MATCH (s:Service) WHERE s.name = 'Kasal — Ñandú' RETURN s LIMIT 5",
    f"MATCH (s:Service) RETURN s LIMIT {MAX_LIMIT}",
    "MATCH (s:Service) RETURN s.name LIMIT 1",
    "MATCH (s:Service) WHERE s.name = 'it\\'s' RETURN s LIMIT 5",
    "MATCH (s:Service)-[:REQUIRES]->(r:Requirement) WITH s, collect(r.text) AS reqs "
    "RETURN s.name, reqs LIMIT 5",
    "MATCH (s:Service) WHERE toLower(s.name) = toLower($name) RETURN s LIMIT 5",
]


@pytest.mark.parametrize("query", VALID)
def test_valid_queries_pass(query):
    accepted(query)


# --------------------------------------------------------------------------- forbidden keywords

FORBIDDEN = [
    "CREATE",
    "MERGE",
    "SET",
    "DELETE",
    "DETACH",
    "REMOVE",
    "DROP",
    "FOREACH",
    "LOAD",
    "CALL",
]


def casings(word: str) -> list[str]:
    swapped = "".join(c.lower() if i % 2 == 0 else c.upper() for i, c in enumerate(word))
    return [word.upper(), word.lower(), word.capitalize(), swapped, swapped.swapcase()]


@pytest.mark.parametrize("keyword", FORBIDDEN)
@pytest.mark.parametrize("case", range(5))
def test_forbidden_keyword_in_every_casing_mid_query(keyword, case):
    word = casings(keyword)[case]
    rejected(f"{BASE}{word} (x:Service) RETURN s LIMIT 5", keyword)


@pytest.mark.parametrize("keyword", FORBIDDEN)
def test_forbidden_keyword_at_start_middle_and_end(keyword):
    rejected(f"{keyword} (n:Service) MATCH (s:Service) RETURN s LIMIT 5", keyword)
    rejected(f"MATCH (s:Service) {keyword} s RETURN s LIMIT 5", keyword)
    rejected(f"MATCH (s:Service) RETURN s LIMIT 5 {keyword} s", keyword)


@pytest.mark.parametrize("keyword", FORBIDDEN)
def test_forbidden_keyword_split_by_whitespace_variants(keyword):
    for ws in ("\n", "\t", "\r\n", "  "):
        rejected(f"MATCH (s:Service){ws}{keyword}{ws}s RETURN s LIMIT 5", keyword)


@pytest.mark.parametrize(
    "query, word",
    [
        ("MATCH (s:Service) DETACH DELETE s", "DELETE"),
        ("MATCH (s:Service) SET s.name = 'x' RETURN s LIMIT 1", "SET"),
        ("MATCH (s:Service) REMOVE s.name RETURN s LIMIT 1", "REMOVE"),
        ("MATCH (s:Service) REMOVE s:Service RETURN s LIMIT 1", "REMOVE"),
        ("CREATE (s:Service {id: 'x'}) RETURN s LIMIT 1", "CREATE"),
        ("MERGE (s:Service {id: 'x'}) RETURN s LIMIT 1", "MERGE"),
        ("MATCH (s:Service) FOREACH (x IN [1] | SET s.a = x) RETURN s LIMIT 1", "FOREACH"),
        ("LOAD CSV FROM 'file:///x.csv' AS row RETURN row LIMIT 1", "LOAD"),
        ("LOAD CSV WITH HEADERS FROM 'http://evil/x' AS row RETURN row LIMIT 1", "LOAD"),
        ("DROP INDEX foo", "DROP"),
        ("DROP CONSTRAINT foo", "DROP"),
        ("MATCH (s:Service) CALL db.labels() YIELD label RETURN label LIMIT 1", "CALL"),
        ("CALL apoc.cypher.run('CREATE (n)', {}) YIELD value RETURN value LIMIT 1", "CALL"),
        ("CALL apoc.periodic.iterate('a','b',{}) YIELD batches RETURN batches LIMIT 1", "CALL"),
        ("CALL { MATCH (s:Service) RETURN s LIMIT 1 } RETURN s LIMIT 1", "CALL"),
        ("CALL dbms.security.createUser('a','b',false)", "CALL"),
        ("MATCH (s:Service) WHERE EXISTS { CREATE (x) } RETURN s LIMIT 1", "CREATE"),
        ("MATCH (s:Service) RETURN [x IN [1] | x] AS l LIMIT 1 UNION MATCH (s) DELETE s", "UNION"),
    ],
)
def test_named_attack_queries(query, word):
    rejected(query, word)


@pytest.mark.parametrize(
    "keyword",
    [
        "UNION",
        "USE",
        "EXPLAIN",
        "PROFILE",
        "CYPHER",
        "START",
        "FINISH",
        "SHOW",
        "TERMINATE",
        "ALTER",
        "GRANT",
        "DENY",
        "REVOKE",
        "YIELD",
        "USING",
        "INSERT",
        "ON",
        "INDEX",
        "CONSTRAINT",
    ],
)
def test_clauses_outside_allow_list_are_rejected(keyword):
    rejected(f"{BASE}{keyword} x RETURN s LIMIT 5")
    rejected(f"{keyword} MATCH (s:Service) RETURN s LIMIT 5")


def test_query_must_start_with_an_allowed_clause():
    for prefix in ("EXPLAIN ", "PROFILE ", "CYPHER 5 ", "USE neo4j "):
        rejected(prefix + "MATCH (s:Service) RETURN s LIMIT 5")


def test_optional_and_order_must_be_followed_by_their_partner():
    rejected("OPTIONAL (s:Service) RETURN s LIMIT 5")
    rejected("MATCH (s:Service) RETURN s ORDER s.name LIMIT 5")


def test_keyword_as_property_is_checked_against_schema_not_keyword_list():
    accepted("MATCH (st:Step) RETURN st.order LIMIT 5")
    rejected("MATCH (s:Service) RETURN s.set LIMIT 5", "property")
    rejected("MATCH (s:Service) RETURN s.create LIMIT 5", "property")
    rejected("MATCH (s:Service) RETURN s.\nCREATE LIMIT 5", "property")


def test_keyword_prefix_or_suffix_identifiers_are_not_false_positives():
    # `offset`/`settings`/`created_at` style names are distinct words, not the keyword.
    accepted("MATCH (s:Service) WITH s AS settings RETURN settings.name LIMIT 5")
    accepted("MATCH (s:Service) WITH s AS creator RETURN creator.name LIMIT 5")
    accepted("MATCH (s:Service) WITH s AS dropdown RETURN dropdown.name LIMIT 5")


# --------------------------------------------------------------------------- comments


@pytest.mark.parametrize("keyword", FORBIDDEN)
def test_line_comment_cannot_hide_a_real_clause(keyword):
    rejected(f"MATCH (s:Service) // harmless\n{keyword} s RETURN s LIMIT 5", keyword)
    rejected(f"MATCH (s:Service) // {keyword} in comment\n{keyword} s RETURN s LIMIT 5", keyword)


@pytest.mark.parametrize("keyword", FORBIDDEN)
def test_block_comment_cannot_hide_a_real_clause(keyword):
    rejected(f"MATCH (s:Service) /* x */ {keyword} s RETURN s LIMIT 5", keyword)
    rejected(f"MATCH (s:Service) /* {keyword} */ {keyword} s RETURN s LIMIT 5", keyword)


@pytest.mark.parametrize("keyword", FORBIDDEN)
def test_keyword_only_inside_comments_is_harmless(keyword):
    accepted(f"MATCH (s:Service) // {keyword}\nRETURN s LIMIT 5")
    accepted(f"MATCH (s:Service) /* {keyword} s */ RETURN s LIMIT 5")
    accepted(f"MATCH (s:Service) RETURN s LIMIT 5 // {keyword} s")


def test_comments_around_a_keyword_do_not_hide_it():
    # A comment between tokens is a separator, so a real keyword next to comments is still seen.
    rejected("MATCH (s:Service) /**/CREATE/**/ (x:Service) RETURN s LIMIT 5", "CREATE")


def test_unterminated_block_comment_is_rejected():
    rejected("MATCH (s:Service) RETURN s LIMIT 5 /* CREATE", "comment")
    rejected("MATCH (s:Service) /* never closed RETURN s LIMIT 5", "comment")


def test_block_comment_does_not_nest():
    # In Cypher `/* a /* b */` is closed by the first `*/`; the remainder is real code.
    rejected("MATCH (s:Service) /* a /* b */ DELETE s */ RETURN s LIMIT 5", "DELETE")


def test_comment_markers_inside_strings_are_not_comments():
    rejected("MATCH (s:Service) WHERE s.name = '//' DELETE s RETURN s LIMIT 5", "DELETE")
    rejected("MATCH (s:Service) WHERE s.name = '/*' DELETE s RETURN s LIMIT 5 // */", "DELETE")


@pytest.mark.parametrize("sep", [" ", " ", "\x85", "\x0b", "\x0c", "\r"])
def test_unicode_line_separators_cannot_end_a_comment_unseen(sep):
    # Neo4j may treat these as newlines, ending the comment; we must not hide what follows.
    result = validate_cypher(f"MATCH (s:Service) // note{sep}DELETE s RETURN s LIMIT 5")
    assert result.ok is False


def test_line_comment_after_limit_does_not_defeat_limit_rule():
    rejected("MATCH (s:Service) RETURN s // LIMIT 5", "limit")


def test_limit_inside_comment_does_not_count():
    rejected("MATCH (s:Service) RETURN s /* LIMIT 5 */", "limit")
    rejected("MATCH (s:Service) RETURN s // LIMIT 5", "limit")


# --------------------------------------------------------------------------- string literals


@pytest.mark.parametrize("keyword", FORBIDDEN)
def test_keyword_inside_string_literal_is_data(keyword):
    accepted(f"MATCH (s:Service) WHERE s.name = '{keyword} everything' RETURN s LIMIT 5")
    accepted(f'MATCH (s:Service) WHERE s.name = "{keyword} everything" RETURN s LIMIT 5')
    accepted(f"MATCH (s:Service) WHERE s.name CONTAINS '{keyword.lower()}' RETURN s LIMIT 5")


def test_string_literal_with_semicolon_and_comment_markers_is_data():
    accepted("MATCH (s:Service) WHERE s.name = 'a; DROP b' RETURN s LIMIT 5")
    accepted("MATCH (s:Service) WHERE s.name = '// not a comment' RETURN s LIMIT 5")
    accepted("MATCH (s:Service) WHERE s.name = '/* nor this */' RETURN s LIMIT 5")
    accepted("MATCH (s:Service) WHERE s.name = 'x`y' RETURN s LIMIT 5")


def test_escaped_quote_does_not_end_string_early():
    accepted("MATCH (s:Service) WHERE s.name = 'a\\' DELETE s //' RETURN s LIMIT 5")
    accepted('MATCH (s:Service) WHERE s.name = "a\\" DELETE s //" RETURN s LIMIT 5')
    accepted("MATCH (s:Service) WHERE s.name = 'a\\\\' RETURN s LIMIT 5")


def test_escaped_backslash_then_quote_does_end_string():
    # 'a\\' is a complete string (escaped backslash); the following DELETE is real code.
    rejected("MATCH (s:Service) WHERE s.name = 'a\\\\' DELETE s RETURN s LIMIT 5", "DELETE")


def test_quote_break_out_attempt_is_caught():
    rejected("MATCH (s:Service) WHERE s.name = 'x' DELETE s //' RETURN s LIMIT 5", "DELETE")
    rejected("MATCH (s:Service) WHERE s.name = 'x' OR 1=1 DELETE s RETURN s LIMIT 5", "DELETE")


def test_unterminated_string_is_rejected():
    rejected("MATCH (s:Service) WHERE s.name = 'abc RETURN s LIMIT 5", "string")
    rejected('MATCH (s:Service) WHERE s.name = "abc RETURN s LIMIT 5', "string")
    rejected("MATCH (s:Service) WHERE s.name = 'abc\\' RETURN s LIMIT 5", "string")


def test_string_concatenation_cannot_build_a_clause():
    # Concatenated strings are inert data; a real clause smuggled next to them is still caught.
    accepted("MATCH (s:Service) WHERE s.name = 'CRE' + 'ATE' RETURN s LIMIT 5")
    rejected("MATCH (s:Service) WHERE s.name = 'CRE' + 'ATE' CREATE (x) RETURN s LIMIT 5", "CREATE")


def test_limit_inside_string_does_not_count():
    rejected("MATCH (s:Service) WHERE s.name = 'LIMIT 5' RETURN s", "limit")


# --------------------------------------------------------------------------- semicolons


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN s LIMIT 5;",
        "MATCH (s:Service) RETURN s LIMIT 5 ;",
        "MATCH (s:Service) RETURN s LIMIT 5; MATCH (t:Service) RETURN t LIMIT 5",
        "MATCH (s:Service) RETURN s LIMIT 5; DELETE s",
        "MATCH (s:Service) RETURN s LIMIT 5;\nMATCH (n) DETACH DELETE n",
        "MATCH (s:Service) RETURN s LIMIT 5;;;",
        ";",
        "; MATCH (s:Service) RETURN s LIMIT 5",
        "MATCH (s:Service) RETURN s LIMIT 5 /* c */ ;",
        "MATCH (s:Service) RETURN s LIMIT 5 // c\n;",
    ],
)
def test_semicolons_and_multiple_statements_are_rejected(query):
    rejected(query, ";")


def test_two_statements_without_semicolon_are_rejected():
    rejected("MATCH (s:Service) RETURN s LIMIT 5 MATCH (t:Service) RETURN t LIMIT 5")


# --------------------------------------------------------------------------- backticks


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:`Service`) RETURN s LIMIT 5",
        "MATCH (`s`:Service) RETURN `s` LIMIT 5",
        "MATCH (s:Service) RETURN s.`name` LIMIT 5",
        "MATCH (s:Service)-[:`REQUIRES`]->(r) RETURN r LIMIT 5",
        "MATCH (s:Service) `CREATE` (x) RETURN s LIMIT 5",
        "MATCH (s:Service) RETURN s.`na``me` LIMIT 5",
        "MATCH (s:Service) RETURN s.`secret` LIMIT 5",
        "MATCH (s:Service) RETURN s LIMIT 5 `",
        "MATCH (s:Service) RETURN s.`unterminated LIMIT 5",
        "MATCH (s:`Ser``vice`) RETURN s LIMIT 5",
        "MATCH (s:Service) CRE`ATE` (x) RETURN s LIMIT 5",
        "MATCH (s:Service) `MATCH` (s) RETURN s LIMIT 5",
        "MATCH (s:Service) RETURN s.`` LIMIT 5",
    ],
)
def test_backtick_identifiers_are_rejected(query):
    rejected(query, "backtick")


def test_backtick_inside_string_is_not_an_identifier():
    accepted("MATCH (s:Service) WHERE s.name = 'a`b' RETURN s LIMIT 5")


def test_backtick_inside_comment_is_ignored():
    accepted("MATCH (s:Service) // `x\nRETURN s LIMIT 5")
    accepted("MATCH (s:Service) /* ` */ RETURN s LIMIT 5")


# --------------------------------------------------------------------------- unicode


HOMOGLYPH_KEYWORDS = {
    "cyrillic C": "СREATE",  # Cyrillic Es
    "cyrillic E": "CRЕATE",  # Cyrillic Ie
    "cyrillic A": "CREАTE",  # Cyrillic A
    "fullwidth": "ＣＲＥＡＴＥ",
    "greek": "CRΕATE",  # Greek capital epsilon
    "long s": "ſET",  # LATIN SMALL LETTER LONG S upper()s to S
    "kelvin": "Keep",  # Kelvin sign lowers to k
    "dotless i": "DELETEı",
}


@pytest.mark.parametrize("name", list(HOMOGLYPH_KEYWORDS))
def test_homoglyph_keywords_are_rejected(name):
    word = HOMOGLYPH_KEYWORDS[name]
    rejected(f"MATCH (s:Service) {word} (x) RETURN s LIMIT 5", "non-ascii")


@pytest.mark.parametrize("ch", ["​", "‌", "‍", "⁠", "﻿", "­"])
def test_zero_width_characters_inside_identifiers_are_rejected(ch):
    rejected(f"MATCH (s:Service) CRE{ch}ATE (x) RETURN s LIMIT 5", "non-ascii")
    rejected(f"MATCH (s:Serv{ch}ice) RETURN s LIMIT 5", "non-ascii")
    rejected(f"MATCH (s:Service) RETURN s.na{ch}me LIMIT 5", "non-ascii")


@pytest.mark.parametrize("ws", [" ", " ", "　", " ", " ", "\x85", " "])
def test_non_ascii_whitespace_outside_strings_is_rejected(ws):
    rejected(f"MATCH{ws}(s:Service) RETURN s LIMIT 5", "non-ascii")
    rejected(f"MATCH (s:Service) RETURN s{ws}LIMIT 5", "non-ascii")


@pytest.mark.parametrize("op", ["‘", "’", "“", "”", "；", ";", "∕"])
def test_lookalike_punctuation_is_rejected(op):
    # curly quotes, fullwidth/Greek semicolon, division slash
    rejected(f"MATCH (s:Service) WHERE s.name = {op}x{op} RETURN s LIMIT 5", "non-ascii")
    rejected(f"MATCH (s:Service) RETURN s LIMIT 5{op}", "non-ascii")


def test_unicode_digits_in_limit_are_rejected():
    rejected("MATCH (s:Service) RETURN s LIMIT ٥", "non-ascii")
    rejected("MATCH (s:Service) RETURN s LIMIT ５", "non-ascii")


def test_non_ascii_text_inside_string_literals_is_allowed():
    accepted(
        "MATCH (s:Service) WHERE s.name CONTAINS 'Pagpaparehistro ng Kapanganakan ñ é' "
        "RETURN s LIMIT 5"
    )
    accepted("MATCH (s:Service) WHERE s.name = 'СREATE ​' RETURN s LIMIT 5")


def test_non_ascii_inside_comments_is_allowed_but_controls_are_not():
    accepted("MATCH (s:Service) // pabalik-balik ñ é\nRETURN s LIMIT 5")
    accepted("MATCH (s:Service) /* ñ */ RETURN s LIMIT 5")
    rejected("MATCH (s:Service) /* \x00 */ RETURN s LIMIT 5")
    rejected("MATCH (s:Service) /*   */ RETURN s LIMIT 5")
    rejected("MATCH (s:Service) /* ‮ */ RETURN s LIMIT 5")  # bidi override


@pytest.mark.parametrize("ctl", ["\x00", "\x01", "\x07", "\x1b", "\x7f"])
def test_control_characters_are_rejected(ctl):
    rejected(f"MATCH (s:Service){ctl}RETURN s LIMIT 5")
    rejected(f"MATCH (s:Service) RETURN s LIMIT 5{ctl}")


# --------------------------------------------------------------------------- LIMIT


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN s",
        "MATCH (s:Service) RETURN s ORDER BY s.name",
        "MATCH (s:Service) RETURN s SKIP 5",
        "MATCH (s:Service) RETURN s.name AS limit_name",
        "MATCH (s:Service) WITH s LIMIT 5 RETURN s",
        "MATCH (s:Service) RETURN s ORDER BY s.name LIMIT",
        "MATCH (s:Service) RETURN s LIMIT 5 SKIP 1",
    ],
)
def test_missing_limit_is_rejected(query):
    rejected(query, "limit")


def test_limit_in_intermediate_with_does_not_satisfy_final_limit():
    rejected("MATCH (s:Service) WITH s LIMIT 3 MATCH (t:Service) RETURN t", "limit")


def test_limit_in_subquery_or_brackets_does_not_count():
    rejected(
        "MATCH (s:Service) WHERE EXISTS { MATCH (t:Service) RETURN t LIMIT 1 } RETURN s", "limit"
    )
    rejected("MATCH (s:Service) RETURN [x IN [1,2,3] | x] AS l", "limit")


@pytest.mark.parametrize("n", [MAX_LIMIT + 1, MAX_LIMIT * 2, 1000, 10**12, 10**40])
def test_excessive_limit_is_rejected(n):
    rejected(f"MATCH (s:Service) RETURN s LIMIT {n}", "limit", str(MAX_LIMIT))


@pytest.mark.parametrize("n", [1, 2, 10, MAX_LIMIT - 1, MAX_LIMIT])
def test_limits_within_bounds_pass(n):
    accepted(f"MATCH (s:Service) RETURN s LIMIT {n}")


def test_limit_uses_value_from_config_file():
    accepted(f"MATCH (s:Service) RETURN s LIMIT {MAX_LIMIT}")
    rejected(f"MATCH (s:Service) RETURN s LIMIT {MAX_LIMIT + 1}", "limit")


def test_explicit_max_limit_argument_overrides_config():
    assert validate_cypher("MATCH (s:Service) RETURN s LIMIT 10", max_limit=10).ok is True
    assert validate_cypher("MATCH (s:Service) RETURN s LIMIT 11", max_limit=10).ok is False


@pytest.mark.parametrize("bad_max", [0, -1, True, 1.5, "50", []])
def test_invalid_max_limit_argument_fails_closed(bad_max):
    result = validate_cypher("MATCH (s:Service) RETURN s LIMIT 1", max_limit=bad_max)
    assert result.ok is False


@pytest.mark.parametrize(
    "lit",
    [
        "0",
        "-1",
        "-5",
        "+5",
        "05",
        "007",
        "0x10",
        "0b11",
        "0o7",
        "1_0",
        "5.0",
        "5.5",
        "1e1",
        "1E1",
        "0.5",
        ".5",
        "5.",
        "$n",
        "$1",
        "s.id",
        "size(s.name)",
        "1+1",
        "(5)",
        "'5'",
        "null",
        "true",
        "5 + 5",
        "10 * 100",
        "toInteger('5')",
        "count(s)",
    ],
)
def test_limit_must_be_a_plain_positive_decimal_integer(lit):
    rejected(f"MATCH (s:Service) RETURN s LIMIT {lit}", "limit")


def test_only_last_top_level_return_and_limit_count():
    rejected("MATCH (s:Service) RETURN s LIMIT 5 RETURN s", "limit")
    rejected("MATCH (s:Service) RETURN s LIMIT 1000", "limit")


def test_query_without_return_is_rejected():
    rejected("MATCH (s:Service) WITH s LIMIT 5", "return")
    rejected("MATCH (s:Service) WHERE s.id = 'x' LIMIT 5", "return")


def test_limit_does_not_apply_when_inside_string_or_after_semicolon():
    rejected("MATCH (s:Service) RETURN 'LIMIT 5'", "limit")


# --------------------------------------------------------------------------- schema


@pytest.mark.parametrize(
    "label",
    [
        "Person",
        "User",
        "Citizen",
        "Application",
        "service",
        "SERVICE",
        "Services",
        "Staff",
        "Employee",
        "Node",
        "_Service",
        "Service2",
    ],
)
def test_unknown_node_label_is_rejected(label):
    rejected(f"MATCH (n:{label}) RETURN n LIMIT 5", "label", label)


@pytest.mark.parametrize(
    "rel", ["OWNS", "AT_STEP", "requires", "REQUIRE", "HAS_STAFF", "KNOWS", "Requires", "HAS_STEPS"]
)
def test_unknown_relationship_type_is_rejected(rel):
    rejected(f"MATCH (s:Service)-[:{rel}]->(x) RETURN x LIMIT 5", "relationship", rel)


@pytest.mark.parametrize("rel", ["OWNS", "AT_STEP"])
def test_unknown_relationship_type_in_variable_and_alt_forms(rel):
    rejected(f"MATCH (s:Service)-[r:{rel}]->(x) RETURN x LIMIT 5", rel)
    rejected(f"MATCH (s:Service)-[r:REQUIRES|{rel}]->(x) RETURN x LIMIT 5", rel)
    rejected(f"MATCH (s:Service)<-[:{rel}]-(x) RETURN x LIMIT 5", rel)
    rejected(f"MATCH (s:Service)-[r:{rel}*1..3]->(x) RETURN x LIMIT 5", rel)


@pytest.mark.parametrize("label", ["Person", "Application"])
def test_unknown_label_in_alternative_and_where_forms(label):
    rejected(f"MATCH (n:Service:{label}) RETURN n LIMIT 5", label)
    rejected(f"MATCH (n:Service|{label}) RETURN n LIMIT 5", label)
    rejected(f"MATCH (n) WHERE n:{label} RETURN n LIMIT 5", label)
    rejected(f"MATCH (:{label}) RETURN 1 AS x LIMIT 5", label)
    rejected(f"OPTIONAL MATCH (n:{label}) RETURN n LIMIT 5", label)


@pytest.mark.parametrize(
    "prop",
    [
        "password",
        "staff_name",
        "staff",
        "email",
        "ID",
        "Name",
        "secret",
        "created_at",
        "__typename",
        "amount",
    ],
)
def test_unknown_property_is_rejected(prop):
    rejected(f"MATCH (s:Service) RETURN s.{prop} LIMIT 5", "property", prop)
    rejected(f"MATCH (s:Service) WHERE s.{prop} = 'x' RETURN s LIMIT 5", prop)
    rejected(f"MATCH (s:Service) RETURN s LIMIT 5 ORDER BY s.{prop}", prop)
    rejected(f"MATCH (s:Service {{{prop}: 'x'}}) RETURN s LIMIT 5", prop)
    rejected(f"MATCH (s:Service) WITH s.{prop} AS x RETURN x LIMIT 5", prop)


def test_unknown_property_in_order_by_before_limit():
    rejected("MATCH (s:Service) RETURN s ORDER BY s.secret LIMIT 5", "secret")


def test_unknown_property_in_relationship_map():
    rejected("MATCH (s:Service)-[r:REQUIRES {weight: 1}]->(x) RETURN x LIMIT 5", "weight")


def test_unknown_property_deep_in_expressions():
    rejected("MATCH (s:Service) WHERE toLower(s.secret) = 'x' RETURN s LIMIT 5", "secret")
    rejected(
        "MATCH (s:Service) RETURN CASE WHEN s.secret = 1 THEN 1 ELSE 0 END AS c LIMIT 5", "secret"
    )
    rejected("MATCH (s:Service) WHERE NOT (s.a = 1) RETURN s LIMIT 5", "property")


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN s['secret'] LIMIT 5",
        "MATCH (s:Service) RETURN s[$key] LIMIT 5",
        "MATCH (s:Service) RETURN s.name['x'] LIMIT 5",
        "MATCH (s:Service) RETURN (s)['secret'] LIMIT 5",
        "MATCH (s:Service) WHERE s['secret'] = 1 RETURN s LIMIT 5",
        "MATCH (s:Service) WITH [s] AS l RETURN l[0]['secret'] LIMIT 5",
        "MATCH (s:Service) RETURN s .secret LIMIT 5",
        "MATCH (s:Service) RETURN s. secret LIMIT 5",
    ],
)
def test_dynamic_or_hidden_property_access_is_rejected(query):
    result = validate_cypher(query)
    assert result.ok is False


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (s:Service) RETURN s {.*} AS m LIMIT 5",
        "MATCH (s:Service) RETURN s {.name, .secret} AS m LIMIT 5",
        "MATCH (s:Service) RETURN properties(s) LIMIT 5",
        "MATCH (s:Service) RETURN keys(s) LIMIT 5",
        "MATCH (s:Service) RETURN PROPERTIES(s) LIMIT 5",
        "MATCH (s:Service) RETURN s += {a: 1} LIMIT 5",
    ],
)
def test_property_introspection_is_rejected(query):
    result = validate_cypher(query)
    assert result.ok is False


def test_map_projection_with_schema_properties_only_is_still_checked():
    accepted("MATCH (s:Service) RETURN s {.name, .id} AS m LIMIT 5")


@pytest.mark.parametrize(
    "fn",
    [
        "apoc.text.join(['a'], ',')",
        "apoc.cypher.runFirstColumn('x', {})",
        "db.labels()",
        "dbms.components()",
        "custom.fn(1)",
        "a.b.c(1)",
    ],
)
def test_namespaced_function_calls_are_rejected(fn):
    rejected(f"MATCH (s:Service) RETURN {fn} AS x LIMIT 5", "function")


def test_schema_is_case_sensitive_and_exact():
    rejected("MATCH (s:service) RETURN s LIMIT 5", "label")
    rejected("MATCH (s:Service) RETURN s.Id LIMIT 5", "property")


def test_workflow_labels_are_not_in_the_official_schema():
    # docs/specs.md section 1: workflow data never mixes with the official graph.
    rejected(
        "MATCH (a:Application)-[:AT_STEP]->(st:Step) RETURN a LIMIT 5", "Application", "AT_STEP"
    )
    rejected("MATCH (s:Service) RETURN s.submitted_at LIMIT 5", "property")


def test_custom_schema_can_be_supplied():
    from citizengraph.guardrail.schema import Schema

    custom = Schema(
        labels=frozenset({"Thing"}),
        relationship_types=frozenset({"REL"}),
        properties=frozenset({"x"}),
    )
    assert validate_cypher("MATCH (t:Thing) RETURN t.x LIMIT 5", schema=custom).ok is True
    assert validate_cypher("MATCH (s:Service) RETURN s LIMIT 5", schema=custom).ok is False


def test_default_schema_matches_specs_section_1():
    from citizengraph.guardrail.schema import OFFICIAL_SCHEMA

    assert OFFICIAL_SCHEMA.labels == {
        "Office",
        "Service",
        "Requirement",
        "Agency",
        "Step",
        "Role",
        "Fee",
        "Variant",
        "Alias",
    }
    assert OFFICIAL_SCHEMA.relationship_types == {
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
    assert OFFICIAL_SCHEMA.properties == {
        "id",
        "name",
        "classification",
        "transaction_type",
        "who_may_avail",
        "total_fee_text",
        "total_time_text",
        "description",
        "text",
        "group",
        "parent_id",
        "min_required",
        "condition_text",
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
        "title",
        "label",
        "amount_min",
        "amount_max",
        "unit",
        "note",
        "dimension",
        "value",
        "lang",
    }


def test_reasons_are_all_collected():
    result = validate_cypher("MATCH (n:Person) SET n.pw = 1 RETURN n.secret")
    assert result.ok is False
    text = " ".join(result.reasons)
    for expected in ("Person", "SET", "limit"):
        assert expected.lower() in text.lower()


# --------------------------------------------------------------------------- config


@pytest.fixture
def limits_file(tmp_path, monkeypatch):
    path = tmp_path / "limits.yaml"
    monkeypatch.setattr(validator, "LIMITS_PATH", path)
    validator._load_max_limit.cache_clear()
    yield path
    validator._load_max_limit.cache_clear()


def test_config_value_is_read_from_yaml(limits_file):
    limits_file.write_text("core1:\n  cypher_limit_max: 7\n")
    assert validate_cypher("MATCH (s:Service) RETURN s LIMIT 7").ok is True
    assert validate_cypher("MATCH (s:Service) RETURN s LIMIT 8").ok is False


@pytest.mark.parametrize(
    "content",
    [
        None,  # file missing
        "",
        "core1: {}",
        "core1:\n  cypher_limit_max: fifty\n",
        "core1:\n  cypher_limit_max: 0\n",
        "core1:\n  cypher_limit_max: -3\n",
        "core1:\n  cypher_limit_max: 2.5\n",
        "core1:\n  cypher_limit_max: true\n",
        "core1:\n  cypher_limit_max: [1]\n",
        "just a string",
        "core1: [unclosed",
        "\x00\x01",
    ],
)
def test_unreadable_or_invalid_config_fails_closed(limits_file, content):
    if content is not None:
        limits_file.write_text(content)
    result = validate_cypher("MATCH (s:Service) RETURN s LIMIT 1")
    assert result.ok is False
    assert any("config" in r.lower() for r in result.reasons)


def test_explicit_max_limit_does_not_need_config(limits_file):
    # config file is absent here, but an explicit max means it is never consulted
    assert validate_cypher("MATCH (s:Service) RETURN s LIMIT 5", max_limit=10).ok is True


# --------------------------------------------------------------------------- lexer unit tests


def kinds(text):
    return [(t.kind, t.value) for t in tokenize(text)]


def test_lexer_basic_tokens():
    assert kinds("MATCH (s:Service {id: $x}) RETURN s.id LIMIT 5") == [
        ("WORD", "MATCH"),
        ("PUNCT", "("),
        ("WORD", "s"),
        ("PUNCT", ":"),
        ("WORD", "Service"),
        ("PUNCT", "{"),
        ("WORD", "id"),
        ("PUNCT", ":"),
        ("PARAM", "x"),
        ("PUNCT", "}"),
        ("PUNCT", ")"),
        ("WORD", "RETURN"),
        ("WORD", "s"),
        ("PUNCT", "."),
        ("WORD", "id"),
        ("WORD", "LIMIT"),
        ("NUMBER", "5"),
    ]


def test_lexer_drops_comments_and_keeps_strings_whole():
    assert kinds("a // CREATE\nb /* DELETE */ c 'SET x' \"MERGE\"") == [
        ("WORD", "a"),
        ("WORD", "b"),
        ("WORD", "c"),
        ("STRING", "SET x"),
        ("STRING", "MERGE"),
    ]


def test_lexer_string_escapes():
    assert kinds(r"'a\'b'") == [("STRING", "a'b")]
    assert kinds(r"'a\\'") == [("STRING", "a\\")]
    assert kinds(r'"a\"b"') == [("STRING", 'a"b')]


def test_lexer_numbers_and_ranges():
    assert kinds("1..3") == [("NUMBER", "1"), ("PUNCT", ".."), ("NUMBER", "3")]
    assert kinds("0x1F") == [("NUMBER", "0x1F")]
    assert kinds("1.5e3") == [("NUMBER", "1.5e3")]


def test_lexer_records_positions():
    toks = tokenize("MATCH (s)")
    assert [t.pos for t in toks] == [0, 6, 7, 8]


@pytest.mark.parametrize(
    "text",
    ["'abc", '"abc', "/* abc", "`x`", ";", "С", "a\x00", "$", "\\", "@", "#", "?", "'a\\"],
)
def test_lexer_raises_lexerror_on_bad_input(text):
    with pytest.raises(LexError):
        tokenize(text)


def test_lexer_error_messages_do_not_echo_long_input():
    with pytest.raises(LexError) as exc:
        tokenize("A" * 500 + ";")
    assert len(str(exc.value)) < 200
