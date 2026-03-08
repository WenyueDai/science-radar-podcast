# Semantic Scholar API Key Design

Date: 2026-03-08

## Context

The Semantic Scholar collector already supports unauthenticated requests, but those requests share a public rate-limit pool and can be throttled more heavily during busy periods. This project runs through GitHub Actions, so the collector should support a repository secret for authenticated requests without adding unnecessary config plumbing.

## Goals

- Keep Semantic Scholar authentication optional.
- Use a single fixed environment variable, `SEMANTIC_SCHOLAR_API_KEY`.
- Preserve current behavior when the key is absent.
- Ensure all Semantic Scholar request paths send the same headers.

## Chosen Approach

Use a fixed environment variable read directly by the collector.

- `src/collectors/semantic_scholar.py` exposes a `_headers()` helper that adds `x-api-key` when `SEMANTIC_SCHOLAR_API_KEY` is present.
- Both the initial request and the 429 retry request use `_headers()`.
- `.github/workflows/weekly_podcast.yml` injects `SEMANTIC_SCHOLAR_API_KEY` from `secrets.SEMANTIC_SCHOLAR_API_KEY`.
- `run_weekly.py` does not need additional Semantic Scholar auth plumbing.

## Alternatives Considered

### Config-driven env var name

Add a config entry in `config.yaml` and thread it through `run_weekly.py`.

Rejected because it adds config surface area and runtime plumbing without helping the GitHub Actions deployment model.

### Pass the raw key through function arguments

Read the secret in `run_weekly.py` and pass it into collector functions explicitly.

Rejected because it is more invasive than needed and duplicates the repo's existing env-var-based secret pattern.

## Data Flow

1. GitHub Actions exposes `SEMANTIC_SCHOLAR_API_KEY` to the weekly workflow job.
2. `run_weekly.py` calls `semantic_scholar.fetch_papers()` as before.
3. The collector reads the environment variable, builds headers, and sends `x-api-key` on Semantic Scholar requests.
4. If a request receives HTTP 429, the retry path reuses the same headers.

## Error Handling

- If `SEMANTIC_SCHOLAR_API_KEY` is missing, the collector falls back to unauthenticated requests.
- If the key is present but invalid, the existing HTTP error handling surfaces the failure in workflow logs.
- No silent fallback should occur for an invalid provided key.

## Testing

- Add tests for `_headers()` when the environment variable is present and absent.
- Add a request test confirming both the initial request and the 429 retry include the same headers.
- Update README setup docs to mention the new GitHub Actions secret and optional local environment variable.
