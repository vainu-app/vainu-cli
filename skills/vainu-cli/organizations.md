# Organizations API payloads (vainu organizations / organizations-async)

All organization commands take a JSON POST body via `--payload FILE` or `--payload -` (stdin).

## Payload structure

```json
{
  "query": { "?EQ": { "business_id": "FI05381340" } },
  "fields": ["business_id", "name"],
  "database": "FI",
  "limit": 100,
  "offset": 0
}
```

| Key | Purpose |
|-----|---------|
| `query` | VQL filter object (required) |
| `database` | Country: `FI`, `SE`, `NO`, or `DK` |
| `fields` | Output field paths to return |
| `limit` | Page size (max 100) |
| `offset` | Pagination offset |
| `aggregation` | Subdocument aggregations (contacts, vehicles, etc.) |

## Discovering field paths

List filterable and returnable fields before writing payloads:

```bash
vainu fields organizations
vainu fields organizations --filterable --search revenue
vainu fields organizations --returnable --category contacts
vainu fields organizations --permission-gated --view summary
```

Use `--view json` for the raw API catalog (includes types, allowed operators, and
`requires_permission` gates). Contact email/phone and similar fields are listed in
the catalog but require account entitlements to read or filter in practice.

## Common VQL operators

| Operator | Meaning | Example |
|----------|---------|---------|
| `?EQ` | equals | `{ "?EQ": { "business_id": "FI05381340" } }` |
| `?GTE` | greater or equal | `{ "?GTE": { "financial_data.revenue": 100000000 } }` |
| `?GT` | greater than | `{ "?GT": { "financial_data.revenue": 100000000 } }` |
| `?IN` | in list | `{ "?IN": { "business_id": ["FI001", "FI002"] } }` |
| `?ALL` | AND | `{ "?ALL": [ clause1, clause2 ] }` |
| `?ANY` | OR | `{ "?ANY": [ clause1, clause2 ] }` |
| `?MATCH` | subdocument filter | wrap contact filters on `contacts` |
| `?AGGREGATE` | aggregation pipeline | see bundled `02-filter-contacts` |

## Worked examples

### Simple lookup by business_id

Use bundled example `08-simple-filtering`:

```bash
vainu organizations --payload "$(vainu examples path 08-simple-filtering)"
```

### Revenue >= 100M in Finland

```bash
echo '{
  "query": { "?GTE": { "financial_data.revenue": 100000000 } },
  "fields": ["business_id", "name", "financial_data.revenue", "financial_data.year"],
  "database": "FI",
  "limit": 100
}' | vainu organizations --payload -
```

Revenue is typically in local currency (EUR for FI).

### CEO contacts only (aggregation)

```bash
vainu organizations --payload "$(vainu examples path 02-filter-contacts)"
```

### Large export to JSONL

```bash
vainu organizations-async \
  --payload "$(vainu examples path 04-get-all-companies-in-vainu-list-async-sync)" \
  --format jsonl \
  --output companies.jsonl
```

Replace the `list` placeholder ID in that example with the user's saved list ID before running.

### Stream to jq

```bash
vainu organizations \
  --payload payload.json \
  --format jsonl | jq -r .business_id
```

## Counting

`vainu organizations-count` returns how many companies match, without any rows — use it to size a
segment before exporting. Same `query` + `database` as `organizations`; `fields`, `limit` and
`offset` are ignored.

```bash
vainu organizations-count --payload payload.json
vainu organizations-count --list <list_id>          # count a saved list, no JSON needed
vainu organizations-count --payload payload.json | jq .count
```

Flags `--database`, `--list`, `--recount` and `--max-cache-age` override the same payload keys.

An `organizations` payload works as-is: `order` is stripped automatically (the count endpoint
returns `400 invalid order by value` for any `order`), and `fields`/`limit`/`offset` are ignored.

Counts are computed in the background, so the API answers a cold cache with
`{"count": null, "status": "scheduled"}`. The command re-sends the payload until `status` leaves
`scheduled`/`process` — pass `--no-wait` to get that first reply instead when you only need
`status` and `eta_utc`. `status: "error"` exits non-zero. Response keys: `count`, `status`,
`time`, `duration`, `rate_of_change`, `eta_utc`.

## Fuzzy search

`vainu organizations-search` hits `POST /v3/organizations/search/` — a plain text lookup by
company name, business ID or domain, for when you have a name and need a `business_id`. It takes
no VQL at all.

```bash
vainu organizations-search --search volvo --database SE
vainu organizations-search --search volvo --database SE,FI --limit 5
vainu organizations-search --payload '{"search": "volvo", "database": ["SE", "FI"]}'
vainu organizations-search --search volvo --fields business_id --format jsonl | jq -r .business_id
```

Flags: `--search`, `--database`, `--fields` (each repeatable or comma-separated), `--limit`,
`--offset`, `--include-inactive`, plus the usual `--format` / `--stream` / `--output`. A
`--payload` may carry the same keys and any flag overrides it. Several databases go as a JSON
list (`["SE", "FI"]`) — the API rejects a comma-joined `"SE,FI"`, so the CLI splits that form
itself, whether it came from the flag or from a payload; a single database stays a plain string.

The reply is a **bare JSON array** of just the requested fields — no `result`/`count`/`next`
wrapper. With no `fields` the API returns empty objects, so the CLI defaults to
`business_id,name,website`.

Paging caveats:

- The `skip` key in the API reference is **ignored** — page with `--offset`
- `--offset` slices a relevance-ranked pool sized from `--limit`, so offsetting well past
  `--limit` comes back empty. Raise `--limit` instead of paging deep
- For exhaustive or filtered result sets use `vainu organizations` / `organizations-async`

## Pitfalls

- `limit` is capped at **100** per request — page with `offset` or use `organizations-async`
- Counts come from `vainu organizations-count`, not `organizations` — see [Counting](#counting)
- Fuzzy name lookup is a separate command — `vainu organizations-search`, see [Fuzzy search](#fuzzy-search)
- Unknown field names in `query` are **silently ignored** — verify paths with `vainu fields organizations`
- For contact subdocument filters, use `?MATCH` on `contacts` or see bundled aggregation examples

## Bundled examples index

Run `vainu examples list --category organizations_api` for the full list. Key files:

| Partial name | Use case |
|--------------|----------|
| `08-simple-filtering` | Minimal exact-match filter |
| `06-simple-fuzzy-search-api` | Free-text name search — pair with `organizations-search` |
| `01-amount-of-companies` | Count-only query — pair with `organizations-count` |
| `12-count-companies-in-vainu-list` | Count a saved list — pair with `organizations-count` |
| `02-filter-contacts` | Return only CEO / Privacy Officer contacts |
| `04-get-all-companies-in-vainu-list-async-sync` | Export a saved Vainu list |
| `10-technology-search-shopify` | Technology field filter |
| `07-search-companies-with-geo-sphere` | Geo sphere search |
