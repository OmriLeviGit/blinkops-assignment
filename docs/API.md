# TicketForge API — reverse-engineered notes

TicketForge has no public API docs. Everything below was inferred from the web
app's JavaScript bundles and verified with live requests against
`https://integrations-assignment-ticketforge.vercel.app`.

## How it was discovered

1. **Client bundles.** The app is a client-rendered Next.js site. The page
   chunks (`/_next/static/chunks/app/{login,register,dashboard,ticket/[ref]}/page-*.js`)
   contain every `fetch()` call the UI makes, including bodies and headers.
2. **`x-matched-path` header.** Vercel returns the matched route pattern on
   every response (e.g. `/api/tforge/workitem/[ref]` vs `/404`), which makes it
   possible to probe for routes the UI doesn't use.
3. **`OPTIONS` requests.** The `Allow` header lists the methods each route
   supports. This revealed `DELETE /workitem/[ref]`, which the UI never calls.
4. **Live probing** of edge cases (validation, PUT semantics, pagination
   bounds) with a test account.

## Basics

| | |
|---|---|
| Base URL | `https://integrations-assignment-ticketforge.vercel.app/api/tforge` |
| Auth | HTTP Basic (`Authorization: Basic base64(username:password)`) on every endpoint except register |
| Format | JSON request and response bodies |
| Sessions | None. The web app "logs in" by calling `GET /workitems/mine` and checking for 200 |

## Endpoints

| Method | Path | Used by UI | Notes |
|---|---|---|---|
| `POST` | `/user/register` | yes | No auth |
| `GET` | `/workitems/mine` | yes | Cursor-paginated list of the caller's tickets |
| `POST` | `/workitem/publish` | yes | Create ticket |
| `GET` | `/workitem/{ref}` | yes (`?view=deep`) | Single ticket |
| `PUT` | `/workitem/{ref}` | yes | Update ticket (see quirks) |
| `DELETE` | `/workitem/{ref}` | **no** | Hidden, discovered via `OPTIONS` |
| `GET` | `/custom-fields` | yes | List the caller's custom field definitions |
| `POST` | `/custom-fields` | yes | Create a custom field |
| `PUT` | `/custom-fields/{id}` | yes | Change a field's label |
| `DELETE` | `/custom-fields/{id}` | yes | Delete a field definition |

Probed and **not** found (404): `/workitems`, `/workitems/{ref}`, `/workitems/search`,
`/workitem/{ref}/comments`, `/workitem/{ref}/history`, `/user`, `/user/me`,
`/users`, `/stages`, `/projects`, `/tags`, `/labels`, `/comments`, `/search`,
`/health`, `/webhooks`.

### `POST /user/register`

```json
{ "username": "alice", "password": "secret" }
```

Missing field → `400 {"err":"missing_fields","message":"username and password required"}`.

### `GET /workitems/mine?limit=&cursor=`

```json
{
  "workitems": [
    { "ref": "TF-589", "title": "Second ticket", "description": null,
      "stage": "open", "created": "2026-10-28T12:05:19.274Z",
      "updated": "2026-10-28T12:05:19.274Z" }
  ],
  "pagination": { "limit": 5, "hasMore": true,
                  "nextCursor": "2026-10-28T12:05:19.274Z:cmvs2i3op0003m9q99y7e6mn9" }
}
```

- Ordered newest first (`createdAt desc, id desc`).
- `limit` is clamped: values ≤ 0 become 1 and values > 5 become 5. **The page size is at most 5.**
- A non-numeric `limit` (e.g. `abc`) causes an internal Prisma error that leaks
  the query: `400 {"err":"server_error", ..., "retryable":true}`.
- `nextCursor` has the form `<createdAt ISO>:<internal id>` and appears only when
  `hasMore` is true. A malformed cursor returns `400 invalid_cursor`, and so does
  a well-formed one that doesn't match an existing ticket ("cursor does not
  correspond to a valid ticket"), so cursors can't be forged to jump ahead.
- **There is no offset-based access.** `page`, `offset`, `skip` and `start` are
  all ignored. Reaching the Nth item means following the cursor through the
  earlier pages.
- List items do **not** include `dependsOn`, `customFields` or `owner`.
- Unknown query parameters (e.g. `stage=open`) are silently ignored, so there is no
  server-side filtering.

### `POST /workitem/publish`

```json
{
  "title": "Fix login",
  "description": "optional",
  "dependsOn": ["TF-588"],
  "customFields": { "priority": "high" }
}
```

Returns `{"workitem": {...}}`. `title` is required and must be non-empty, and an
empty-string `description` is stored as `null`.

### `GET /workitem/{ref}[?view=deep]`

```json
{
  "workitem": {
    "ref": "TF-590", "title": "Third", "description": null, "stage": "open",
    "created": "...", "updated": "...",
    "dependsOn": ["TF-588"],
    "customFields": { "priority": "high" },
    "owner": { "id": "cmvs...", "username": "alice" }
  }
}
```

- `?view=deep` adds `owner`.
- `dependsOn` and `customFields` are **omitted** when empty.
- Another user's ticket → `400 forbidden "you can only view your own workitems"`.

### `PUT /workitem/{ref}`

The body has the same shape as create, plus `stage`. **It behaves as a full replace,
with inconsistent handling of omitted fields:**

| Field | Omitted | `null` |
|---|---|---|
| `title` | **rejected** (required) | rejected |
| `stage` | **rejected** (required) | rejected |
| `description` | **wiped** to `null` | cleared |
| `customFields` | **wiped** | — |
| `dependsOn` | **kept** unchanged | cleared |

A client that wants to change one field must therefore GET the ticket first
and send back every field.

### `DELETE /workitem/{ref}`

`200 {"message":"workitem TF-593 deleted successfully"}`. Deleting a ticket that
others depend on succeeds, and the ref is silently removed from their `dependsOn`.

### Custom fields

```json
GET  /custom-fields      → {"customFields":[{"id":"cmvs...","name":"priority","label":"Priority","type":"text","created":"...","updated":"..."}]}
POST /custom-fields        {"name":"priority","label":"Priority"} → {"customField":{...}}
PUT  /custom-fields/{id}   {"label":"Prio"}                      → {"customField":{...}}
DELETE /custom-fields/{id}                                          → {"success":true}
```

- `name` must match `[A-Za-z0-9_]+`, and duplicates are rejected (`duplicate`).
- `PUT` changes only `label`; a `name` in the body is silently ignored.
- Fields are per-user, and the only `type` observed is `text`.
- Deleting a field removes its value from every ticket.
- Setting an undefined field on a ticket → `400 invalid_input "custom field \"x\" does not exist"`.

## Validation rules (observed)

- `stage` ∈ `open`, `in_progress`, `review`, `closed`.
- A ticket can't depend on itself.
- Dependencies must exist (`dependency tickets do not exist: TF-999999`) and must belong
  to the caller (`forbidden: you can only depend on your own tickets`).
- **Dependency cycles are allowed** (A → B → A was accepted).
- Refs (`TF-<n>`) are global across all users and appear to be assigned as
  `max(existing) + 1`: after `TF-593` (the newest ticket) was deleted, the next
  ticket created got `TF-593` again. **A ref is not a stable identifier**, so a
  stale ref can later point at a different ticket.

## Errors

Every error body has the same shape:

```json
{ "err": "not_found", "message": "workitem TF-1 does not exist", "retryable": false }
```

| Status | `err` values seen |
|---|---|
| 401 | `unauthorized` (missing or bad credentials) |
| 400 | `not_found`, `forbidden`, `invalid_input`, `duplicate`, `invalid_cursor`, `missing_fields`, `server_error` |
| 405 | wrong method on a route (empty body) |

**Every application error is HTTP 400, including not-found and forbidden**, so
clients must branch on `err`, not on the status code. `retryable` signals transient failures.

## Rate limiting

Authenticated responses include:

```
x-ratelimit-limit: 50
x-ratelimit-remaining: 47
x-ratelimit-reset: 2026-10-28T12:04:04.410Z
```

- A fixed window of about 60 seconds, with `reset` given as an ISO timestamp.
- Error responses don't carry the headers.
- The counter appears to live **in memory per serverless instance**. In a
  60-request parallel burst, `remaining` values were scattered (38–49) with
  several different reset times, and no request was rejected. A 429 was never
  observed, so the client handles it defensively (see the README).
