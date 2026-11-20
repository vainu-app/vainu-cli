# Signals API payloads (vainu signals-news / signals-data-changes)

Both commands require **OAuth, JWT, or `vainu login`** — not a static API key.

```bash
vainu login
# or
export VAINU_CLIENT_ID=...
export VAINU_CLIENT_SECRET=...
vainu --auth-method oauth signals-news --payload payload.json
```

## Payload structure

```json
{
  "query": {
    "?ALL": [
      { "?IN": { "organizations.business_id": ["FI25578642"] } },
      { "?GTE": { "vainu_date": "1 years ago" } }
    ]
  },
  "limit": 20,
  "offset": 0
}
```

| Key | Purpose |
|-----|---------|
| `query` | VQL filter (required) |
| `limit` | Page size (default 20, max 100) |
| `offset` | Pagination (max 100000) |

## Response shape

- Returns a **bare JSON array**, newest first
- No `count`, `next`, or `order` field — sending `order` returns 400
- Empty array means no matches **or** query timeout — always include a date bound

## News signals (`signals-news`)

Filterable fields: `content`, `title`, `link`, `type`, `countries`, `organizations.business_id`, `organizations.country`, `tags`, `vainu_date`.

```bash
vainu signals-news --payload "$(vainu examples path 01-news-signals-for-one-company)"
```

Keyword monitor example:

```bash
vainu signals-news --payload "$(vainu examples path 04-news-signals-keyword-monitor)"
```

## Data-change signals (`signals-data-changes`)

Filterable fields: `tags`, `vainu_date`, `organizations.business_id`, `organizations.country`, `prospects` only — no text/content filters, and `countries` is ignored.

```bash
vainu signals-data-changes --payload "$(vainu examples path 05-data-changes-for-companies)"
```

## Rules and pitfalls

- **Relative dates need plural units**: `"30 days ago"` and `"1 years ago"` work; `"1 year ago"` returns 400
- **`organizations.business_id`**: country-prefixed (`FI25578642`), `?IN` or `?EQ`. Prefer it over the older `business_ids` field, which takes `?IN` only. An unprefixed id returns 400
- **Company country vs source country**: `organizations.country` filters by the linked company's country; `countries` is the news item's source country. Use uppercase codes (`"FI"`) — `"fi"` silently matches nothing
- **Tag IDs**: integer `tags` values — see [TAGS_BY_TYPE.json](https://filter.vainu.io/filtervalues/en/TAGS_BY_TYPE.json) or bundled `02-news-signals-by-tags`
- **No CSV** — use `--format jsonl` for exports
- **`csv` is not available** on signals endpoints

## Export and paging

```bash
vainu signals-data-changes \
  --payload "$(vainu examples path 06-data-changes-jsonl-paging)" \
  --format jsonl \
  --output data_changes.jsonl
```

Page by increasing `offset` by `limit` until a page returns fewer rows than `limit`.

Streaming is on by default for `jsonl`. Use `--no-stream` to buffer the full page.

## Bundled examples index

Run `vainu examples list --category signals_api` for the full list.

| Partial name | Use case |
|--------------|----------|
| `01-news-signals-for-one-company` | News for one company, last year |
| `02-news-signals-by-tags` | Funding + M&A by tag ID |
| `03-news-signals-excluding-tags` | Exclude noisy tag types |
| `04-news-signals-keyword-monitor` | Keyword search in date window |
| `05-data-changes-for-companies` | Financial statements + CEO changes |
| `06-data-changes-jsonl-paging` | JSONL export with paging |
| `07-news-signals-by-tag-and-country` | Funding signals for FI/SE companies, last 30 days |
