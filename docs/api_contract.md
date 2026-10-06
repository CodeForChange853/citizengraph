# API contract (frontend <-> backend)

The frontend depends only on this contract. Live schema: `GET /openapi.json`, UI: `/docs`.
Models live in `src/citizengraph/api/schemas.py`. Keep this file, the mock and `tests/test_api.py` in sync.
The frontend fixture adapter reads `frontend/src/api/fixtures.json`, generated from the mock with
`python frontend/scripts/export_fixtures.py` (a test fails if it drifts).

Changes are backward compatible: new fields have defaults, nothing was removed or renamed.

## Endpoints

- `GET /health` -> `{status, mock}`
- `GET /languages` -> `["en", "fil"]`
- `GET /services` -> list of `{id, name, office, group, summary, info_status}` for the home chips and rows.
  `group` is `business | family | health | assistance` (BPLO, civil registry, CHO, CSWDO).
- `POST /chat`

### POST /chat

Request:

```json
{ "message": "kailangan ko ng business permit", "lang": "fil", "session_id": null }
```

- `lang` is the **reply language** (UI toggle). The message itself may be English, Filipino or mixed.
- Send `session_id` from the previous response to continue a conversation (clarifications).

Response:

```json
{
  "session_id": "uuid",
  "language": "fil",
  "kind": "answer | clarify | refusal | status | fallback",
  "text": "short lead-in sentence",
  "sections": [
    {
      "service_id": "cswdo_referrals",
      "service_name": "Referrals",
      "office": "City Social Welfare Development Office",
      "info_status": "confirmed | pending_lgu",
      "summary": { "requirement_count": 5, "fee_text": null, "time_text": "1 week, 1 hour, 40 minutes" },
      "checklist": ["..."],
      "fees": [{ "label": "...", "amount_text": "..." }],
      "steps": [{ "order": 1, "text": "...", "time_text": "30 minutes", "external": false }],
      "notes": [],
      "related": [
        { "label": "Certification from BPLO that the client has no existing business",
          "office": "Business Permits & Licensing Office",
          "note": "Get this first, then come back." }
      ]
    }
  ],
  "clarify_options": ["..."],
  "meta": { "mock": true }
}
```

Rules for the frontend:

- One `section` per requested service (multi-request messages return several).
- `kind = clarify`: show `clarify_options` as tap buttons; send the chosen option back as the next message.
- `kind = fallback`: the system could not answer safely; show `text` and the four life-event chips. No contact data is sent.
- `kind = refusal`: the request tried to change data; show `text`, then the same chips.
- `kind = status`: Core 2 status/delay answer.
- `info_status = pending_lgu`: the checklist is being verified with the LGU. The API sends **no numbers** for it
  (`summary` values are null, `checklist`, `fees`, `steps` are empty). The UI must show the calm "being verified"
  banner and must not show numbers even if some arrive.
  The mock takes `info_status` from the default graph load (`graph/load.py`, see `docs/seed_status.md`): a mock
  service the loader marks `pending_lgu` is pending in the mock too. Of the six mock services that is Business
  Permit, Birth Registration (timely) and Death Registration (timely). `tests/test_api_holdback.py` checks the
  status and the held-back wording against `graph/seed`. It does not check the confirmed values, and it does not
  check `related`: the mock's cross-office routes come from link suggestions that are still `needs_review`, which
  the default load does not write.
- `summary` is the "information scent" line. A null value means the charter does not say: show "not listed",
  never "free" or a guess. `requirement_count` 0 means the charter lists nothing to bring.
- `related` is the cross-office route ("get this at another office first, then come back").
- `meta.mock = true` on every mock response: the UI shows a "Sample data" tag.
- Retrieved facts (requirement, step, fee, office text) are in the charter's own English wording in both languages.
  Only the sentences around them (`text`, `notes`, `related[].note`) are translated (templates).
- Never assume a field beyond this contract; `meta` is for debugging only.
