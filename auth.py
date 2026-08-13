"""Authentication helpers for scheduled GitHub Actions refreshes."""

from __future__ import annotations

import jwt
from jwt import PyJWKClient

OIDC_ISSUER = "https://token.actions.githubusercontent.com"
OIDC_AUDIENCE = "k-weather-refresh"
OIDC_JWKS = f"{OIDC_ISSUER}/.well-known/jwks"
ALLOWED_REPOSITORY = "maphew/K-Weather"
ALLOWED_WORKFLOW = "maphew/K-Weather/.github/workflows/refresh.yml@refs/heads/main"


def github_actions_refresh_token_valid(token: str) -> bool:
    """Validate GitHub's signed short-lived OIDC token and workflow claims."""
    if not token:
        return False
    try:
        signing_key = PyJWKClient(OIDC_JWKS).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=OIDC_AUDIENCE,
            issuer=OIDC_ISSUER,
        )
    except jwt.PyJWTError:
        return False
    return bool(
        claims.get("repository") == ALLOWED_REPOSITORY
        and claims.get("workflow_ref") == ALLOWED_WORKFLOW
        and claims.get("ref") == "refs/heads/main"
        and claims.get("event_name") in {"schedule", "workflow_dispatch"}
    )
