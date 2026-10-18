# Service contracts: instructions for future changes

These files describe what this app currently does. A **service contract** says
what input an operation accepts, which external API it calls, and what it returns.
There is currently one Python `ShopifyService`; these files group its operations
by purpose. They do not imply separate deployed services.

| File | Describes |
| --- | --- |
| [shared.md](shared.md) | Settings, Shopify authentication, HTTP calls, errors |
| [shop.md](shop.md) | Connection test and store details |
| [products.md](products.md) | Product listing and CSV download |
| [orders.md](orders.md) | Validated order-status lookup and natural-language messages |
| [content.md](content.md) | Policies, pages, and FAQ search |
| [template.md](template.md) | Starting point for a new operation |

## How you use these files

1. Open the file for the feature you want to change.
2. Add your requirements under **Requested change**. Describe new inputs,
   returned fields, rules, and an example of the result you want.
3. Save the file and ask your coding agent:

   > Implement the Requested change in docs/services/products.md. Read
   > AGENTS.md and docs/services/README.md first. Compare the contract with
   > the current code, implement the change, and run relevant tests. Update
   > the contract to describe the final behavior and report any remaining gaps.

4. Review the code and test results, then deploy through GitHub Actions.

Editing a Markdown file does not automatically change or deploy the application.
You must ask the agent to implement it. Keep the existing behavior description
until implementation is complete so the agent can see what needs to change.

## Instructions for the implementing agent

- Read the affected contract, shared.md, implementation files, and existing tests.
- Treat **Requested change** as the desired behavior. The other sections describe
  the baseline; compare them with code and report differences before relying on them.
- Ask about material ambiguity. Do not silently expand the requested scope.
- Implement in the existing route -> service -> client structure. A documentation
  file per operation does not require a new Python class or microservice.
- Validate public inputs; handle errors; preserve unrelated behavior.
- Add or update relevant tests for the requested behavior, including meaningful
  error and boundary cases. Run them and report the actual result.
- Update affected contracts and examples after implementation. Describe the final
  behavior directly, remove obsolete descriptions, and remove the completed
  Requested change section. Keep that section only while work is pending.
- Check current official Shopify documentation before changing external API calls,
  scopes, or versions. These contracts record repository behavior, not a guarantee
  that Shopify will accept every query for every store or app.
- Keep credentials out of documentation, tests, logs, and commits.

## Common acceptance checks

- The documented input reaches the correct service method and Shopify variables.
- Output names and nesting match the contract; empty and missing results are covered.
- Pagination and limits behave as described.
- Errors produce the documented response and do not expose credentials.
- Existing local and Cloudflare entry points still work.

These initial contracts were derived from the implementation on 2026-10-14.
