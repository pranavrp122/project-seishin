"""
Tableau REST API — placeholder for local development.

Real implementation (high level):
1. Create a Tableau Connected App or use Personal Access Token (PAT) on Tableau Server / Cloud.
2. Sign in via REST: POST /api/{version}/auth/signin with credentials → get `site` + `token`.
3. For embedded or published views:
   - Publish datasource/workbook: POST .../workbooks or .../datasources (multipart upload).
   - Or refresh an extract: POST .../datasources/{id}/refresh.
4. Build a view URL or use Trusted Tickets / embed token for the user-facing link.
5. Store the canonical view URL on the job record (see jobs.update_job).

Docs:
- Tableau REST API: https://help.tableau.com/current/api/rest_api/en-us/
- Authentication: sign-in, then pass `X-Tableau-Auth` header on subsequent requests.

Environment variables you would add later:
  TABLEAU_SERVER_HOST, TABLEAU_SITE_ID, TABLEAU_API_VERSION,
  TABLEAU_PAT_NAME, TABLEAU_PAT_SECRET, TABLEAU_PROJECT_ID

This placeholder returns a deterministic fake HTTPS URL so the voice pipeline can speak a link.
"""


def placeholder_workbook_link(job_id: str, base_url: str = "https://tableau.example.com") -> str:
    """Return a stable pseudo-link; replace with REST-published URL when integrated."""
    safe = job_id.replace("/", "_")
    return f"{base_url.rstrip('/')}/#/placeholder-report/{safe}"
