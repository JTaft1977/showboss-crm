# ShowBoss AV CRM

Shared sales CRM for event rentals and permanent LED installs, with a server-side Flex Rental Solutions connection.

Do not put the Flex API key in chat or in git. Enter it in Settings after login, or set env vars before start.

## Run

```bash
cd showboss-crm-server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CRM_SECRET="change-this-long-random-string"
export FLEX_SUBDOMAIN="yourflexsite"          # optional; can set in the app
export FLEX_API_KEY="paste-key-here"          # optional; can set in the app
uvicorn app:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080

First login: `admin` / `showboss`. Change that password in Settings before anyone else uses it.

## Flex

- Auth header is `X-Auth-Token` (Flex5). Base URL is `https://{subdomain}.flexrentalsolutions.com/f5/api`.
- The key has the same permissions as the Flex user who created it. Prefer a dedicated API user.
- Swagger for your site: `https://{subdomain}.flexrentalsolutions.com/f5/swagger-ui.html`
- Flex does not support the API. Search and document calls try the common endpoints and show the raw response if the shape differs.
- Limits on Enterprise/GTS are about 2,000 requests/hour, 10,000/day, 100,000/month, shared across keys. Lite has no API.

## What is shared

SQLite file `data/crm.db` holds users, accounts, contacts, deals, activity, and the Flex key. Anyone with an account sees the same book.
