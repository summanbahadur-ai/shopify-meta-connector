# New operation contract template

Copy this file to a descriptive name in this folder and add a link to README.md.
Replace the prompts below. Label a new operation **Proposed** until implemented;
do not describe proposed behavior as already available.

## Purpose and status

Describe the user outcome. Status: Proposed / Implemented.

## Implementation

List the route, service method, client method/query, and relevant test files.
For proposed work, distinguish intended paths from files that already exist.

## Input

Specify HTTP method/path and internal method signature. For each input, define
type, required/default value, validation, and normalization. Include settings
or permissions needed, without real credentials.

## External API call

Specify method, URL pattern, GraphQL operation, variables or body, and relevant
headers. Link shared.md for common authentication. State whether it makes no
external call, one call, or multiple paginated calls.

## External response and transformation

Show an example upstream payload with fake values. Explain which fields are
selected, renamed, removed, or combined, and how missing/null values behave.

## Returned result

Document internal return value separately from HTTP status, JSON wrapper, or
download format. Include a concrete successful example and an empty result.

## Errors and limitations

Link shared errors and define operation-specific validation, not-found,
pagination, authorization, retry, and resource limits.

## Acceptance checks

List observable success, empty, invalid-input, and failure cases that establish
the operation works. Distinguish existing tests from tests still needed.

## Requested change

Describe the change you want, its reason, and an example of the desired result.
Use `None pending.` when no change is requested.
