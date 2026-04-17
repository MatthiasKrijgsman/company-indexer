# API docs

HTTP API for Dutch company (KVK) data. No auth yet — local only.

Base URL: `http://localhost:8000`

## Endpoints

### `GET /companies`

List companies with optional substring search on any associated name.

Query parameters:

| Name     | Type     | Default | Description                                     |
|----------|----------|---------|-------------------------------------------------|
| `limit`  | int      | `50`    | Page size, `1`–`200`.                           |
| `offset` | int      | `0`     | Rows to skip.                                   |
| `q`      | string   | —       | Case-insensitive substring match on any name.   |

Response: `200 OK`

```json
{
  "items": [
    {
      "kvk_number": "12345678",
      "names": [{ "name": "Acme B.V.", "type": "statutory" }],
      "addresses": [
        {
          "street": "Damrak",
          "house_number": "1",
          "postcode": "1012LG",
          "city": "Amsterdam",
          "country": "NL",
          "lat": "52.3740",
          "lon": "4.8897"
        }
      ]
    }
  ],
  "limit": 50,
  "offset": 0
}
```

### `GET /companies/{kvk_number}`

Fetch a single company by KVK number.

Path parameters:

| Name         | Type   | Description           |
|--------------|--------|-----------------------|
| `kvk_number` | string | KVK registration nr.  |

Responses:

- `200 OK` — single `CompanyRead` object (same shape as `items[]` above).
- `404 Not Found` — no company with that KVK number.

## Schemas

### `CompanyRead`

| Field        | Type                  |
|--------------|-----------------------|
| `kvk_number` | string                |
| `names`      | `CompanyNameRead[]`   |
| `addresses`  | `AddressRead[]`       |

### `CompanyNameRead`

| Field  | Type                                            |
|--------|-------------------------------------------------|
| `name` | string                                          |
| `type` | enum (`statutory`, `trade`, `short`, `alias`)   |

### `AddressRead`

| Field          | Type             |
|----------------|------------------|
| `street`       | string \| null   |
| `house_number` | string \| null   |
| `postcode`     | string \| null   |
| `city`         | string \| null   |
| `country`      | string           |
| `lat`          | decimal \| null  |
| `lon`          | decimal \| null  |
