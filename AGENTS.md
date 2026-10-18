# Simple project guide

## Which file is the main file?

- `app/main.py` is the main application. It creates the FastAPI API.
- `worker.py` starts that application on Cloudflare.
- `wrangler.jsonc` tells Cloudflare to use `worker.py` and names the app `shopify-meta-connector`.

This project reads products, orders, policies, and pages from Shopify.

## Project structure

```text
app/
  main.py                     Main application
  api/                        API URLs and request handling
  services/shopify_service.py Shopify business logic
  clients/shopify_client.py   Calls the Shopify API
  clients/order_queries.py   GraphQL queries for order lookup
  services/order_lookup.py   Validated, filtered order discovery
  messaging/                 Status mappings and deterministic messages
  schemas/order_status.py    Lookup validation and response models
  core/config.py              Reads settings and credentials
  core/exceptions.py          Error definitions
  schemas/                    Reserved for data schemas
worker.py                     Cloudflare entry file
wrangler.jsonc                Cloudflare settings
pyproject.toml                Python dependencies
uv.lock                       Saved dependency versions
.env.example                  Example settings for your computer
tests/                        Automated tests
.github/workflows/
  deploy-cloudflare.yaml      GitHub's automatic deployment instructions
README.md                     More project information
docs/                         Design notes
```

## Run the app on your computer

Install Python 3.13 or newer and uv first. In PowerShell, open the project folder and run:

```powershell
uv sync --all-groups
```

If you do not already have a `.env` file, create one:

```powershell
Copy-Item .env.example .env
```

Open `.env` and fill in your Shopify store domain, client ID, and client secret.
Use a store domain such as `your-store.myshopify.com`.

Start the app:

```powershell
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/docs` in your browser to try the API.
Stop the app with Ctrl+C.

To run tests:

```powershell
uv run pytest -q
```

## How deployment works

The project already has a GitHub deployment workflow:
`.github/workflows/deploy-cloudflare.yaml`.

It reads Cloudflare and Shopify credentials from **GitHub Secrets**, then sends the app to Cloudflare Workers.
You do not need to run deployment commands on your computer when using this workflow.

The workflow expects the secrets below. You need to check GitHub to confirm that they have actually been saved; this source code cannot confirm that.

## Deploy to a different Cloudflare account

### Step 1: Get the new account's Cloudflare details

Sign in to the Cloudflare account where you want the app to run.

1. Copy its **Account ID** from the Cloudflare dashboard. Use the account ID, not a zone ID.
2. Open your Cloudflare profile's **API Tokens** page.
3. Select **Create Token**, then the **Edit Cloudflare Workers** template.
4. Select the new account under account resources and create the token.
5. Copy the token and keep it private. You will paste it into GitHub in the next step.

### Step 2: Update GitHub Secrets

Open your project repository on GitHub, then go to:

**Settings > Secrets and variables > Actions > Repository secrets**

If a secret exists, edit it. Otherwise, choose **New repository secret**.
Use these exact names:

| Secret name | What to enter |
| --- | --- |
| `CLOUDFLARE_ACCOUNT_ID` | The new Cloudflare account's ID |
| `CLOUDFLARE_API_TOKEN` | The token you just created for the new account |
| `SHOPIFY_STORE_DOMAIN` | Your store domain, such as `your-store.myshopify.com` |
| `SHOPIFY_CLIENT_ID` | Your Shopify app's client ID |
| `SHOPIFY_CLIENT_SECRET` | Your Shopify app's client secret |

**To change only the Cloudflare account, replace the first two secrets.**
Keep the three Shopify secrets if you are still using the same Shopify store and app.

GitHub hides saved secret values. Seeing a secret name confirms it exists, but you cannot open it to read the old value.

### Step 3: Start deployment on GitHub

1. Open the repository's **Actions** tab.
2. Choose **Deploy Cloudflare Worker** on the left.
3. Click **Run workflow**.
4. Choose the `main` branch and click **Run workflow** again.
5. Open the new run and wait for a green check mark.

If **Run workflow** is missing, confirm that `deploy-cloudflare.yaml` is pushed to the repository's default branch and that GitHub Actions is enabled.

Updating secrets alone does not start deployment. You must run the workflow or push a new commit to `main`.

### Step 4: Find and test the deployed app

1. Open Cloudflare and select the new account.
2. Open **Workers & Pages**.
3. Open **shopify-meta-connector**.
4. Copy its live URL. You can also find the URL in GitHub's deployment run under **Deploy to Cloudflare**.

The URL normally looks like:

```text
https://shopify-meta-connector.YOUR-ACCOUNT-SUBDOMAIN.workers.dev
```

Open these paths after your actual live URL:

- `/health` checks that the app is running.
- `/docs` opens the API testing page.
- `/api/v1/shopify/connection` checks that the app can connect to Shopify.

### Step 5: Use the new URL

Replace the old app URL anywhere you use it with the new URL.
Deploying to another account creates a new deployment; it does not remove the old one.
Keep the old app until the new app works. Afterwards, you can delete the old Worker from the old Cloudflare account.

If you use a custom domain, configure it for the new Worker separately.

## Deploy future code changes

Push your updated code to GitHub's `main` branch. The same workflow automatically deploys it using the saved GitHub Secrets.

You can also use **Actions > Deploy Cloudflare Worker > Run workflow** whenever you want to deploy again.

## If deployment fails

Open the failed run in GitHub Actions and expand the red step to read the error.

- Authentication or permission error: check the new Cloudflare token and its account access.
- Wrong account or account not found: check `CLOUDFLARE_ACCOUNT_ID` and confirm the token belongs to that account.
- Missing Shopify settings: check that all three Shopify secrets exist with the exact names above.
- `/health` works but the Shopify connection fails: check Shopify credentials, app installation, and read permissions.
- `multipart: message too large`: inspect **Prepare and inspect Worker bundle**
  in the GitHub run. Dependencies are uploaded as many files, so this can be a
  file-count problem as well as a byte-size problem. The workflow prints package
  counts and runs a dry run before changing secrets or deploying.

## Notes for agents working on this project

Read `docs/services/README.md` and the relevant service contract before changing
application behavior. The contracts describe inputs, external API calls, and
outputs. A contract's **Requested change** section records work to implement;
editing Markdown alone does not change the application. After implementation,
update the contract to match the final behavior and report verification results.

Keep API handling, service logic, and Shopify API calls in their existing folders.
Preserve both `app/main.py` and `worker.py` as entry points.
Never commit `.env` or credentials. Run relevant tests when changing code.

### WhatsApp chatbot and natural-language conventions

This backend will support a WhatsApp chatbot connected to a Shopify store.
Generate customer-facing status messages deterministically, without an LLM.
Keep Shopify status/keyword mappings and natural-language templates in separate,
extensible files under `app/messaging/` (orders use `order_messages.py`). Keep
formatting and status derivation in `order_formatter.py`, input validation in
`app/schemas/`, Shopify GraphQL documents in `app/clients/`, and lookup/business
logic in `app/services/`. Routes should handle HTTP concerns only.

Return structured facts alongside the readable message so a future WhatsApp
handler can use the same service without parsing prose. Add new states/templates
to the mapping module and test the formatter when extending behavior. Never
invent shipment status, product quantities, tracking numbers, or delivery dates.
Distinguish fulfilled from shipped/delivered and keep split shipments separate.
Use validated, filtered Shopify searches; never expose a general order-listing
endpoint. Order-status lookup requires both order number and email, with phone optional.
All supplied identifiers must match the same order. Compare email and phone to
Order.email/Order.phone only; do not add customer-profile/address fallback without
an explicit requirement. Keep contact fields private and fail closed on missing
or mismatching data. Matching identifiers is not proof of contact ownership.
Restrict order details to a trusted backend until customer authorization exists.
Order lookup failures must return curated, deterministic messages and stable codes
from `LOOKUP_ERROR_MESSAGES`, never raw exceptions or technical details. Keep the
order-only try/except boundary in `app/api/order_errors.py`, including validation
and settings/dependency failures. Retain meaningful HTTP status codes. Log only
safe error categories, not contacts, secrets, exception text, or tracebacks.

### Cloudflare package constraints

`wrangler.jsonc` excludes generated bytecode, type stubs, unused `dns` modules,
and `phonenumbers/shortdata/region_*.py` from the Worker bundle. Email validation
must keep `check_deliverability=False`; international full-number validation
uses `phonenumbers/data/`, which must remain bundled. Keep
`phonenumbers/shortdata/__init__.py` too. SMS short-code/emergency-number lookups
and DNS deliverability checks are not supported by these exclusions; revisit
packaging before adding either capability. The regional import-isolation test
in `tests/test_worker_bundle.py` verifies the currently supported validation.

The deployment workflow runs tests, `pywrangler sync`, a file-count preflight,
and a packaging dry run before uploading secrets/deploying. The preflight's 950
estimated-part budget is a conservative project guard, not a published Cloudflare
limit. Check actual CI output; a local unit test is not proof a deployment succeeds.

## Official Cloudflare help

- [Deploy with GitHub Actions](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)
- [Create an API token](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)

Service contracts should describe the final current behavior directly. Remove
obsolete behavior instead of retaining it as a history or a completed requested
change. Use a Requested change section only while a change is actually pending.
