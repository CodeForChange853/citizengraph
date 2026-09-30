# API contract (frontend <-> backend)

The frontend depends only on this contract. Live schema: `GET /openapi.json`, UI: `/docs`.
Models live in `src/citizengraph/api/schemas.py`. Keep this file and the mock in sync.

## Endpoints

- `GET /health` -> `{status, mock}`
- `GET /languages` -> `["en", "fil"]`
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
      "service_id": "bplo-business-permit",
      "service_name": "Business Permit",
      "office": "Business Permits & Licensing Office",
      "checklist": ["..."],
      "fees": [{ "label": "Zoning", "amount_text": "P30.00" }],
      "steps": [{ "order": 1, "text": "...", "time_text": "2 minutes", "external": false }],
      "notes": []
    }
  ],
  "clarify_options": ["..."],
  "meta": { "mock": true }
}
```

Rules for the frontend:

- One `section` per requested service (multi-request messages return several).
- `kind = clarify`: show `clarify_options` as tap buttons; send the chosen option back as the next message.
- `kind = fallback`: the system could not answer safely; show `text` and the office contact info.
- `kind = status`: Core 2 status/delay answer.
- Never assume a field beyond this contract; `meta` is for debugging only.
