import unittest
from unittest.mock import Mock, patch

from auth import (
    ALLOWED_REPOSITORY,
    ALLOWED_WORKFLOW,
    github_actions_refresh_token_valid,
)


class GitHubActionsAuthTest(unittest.TestCase):
    def claims(self, **overrides):
        values = {
            "repository": ALLOWED_REPOSITORY,
            "workflow_ref": ALLOWED_WORKFLOW,
            "ref": "refs/heads/main",
            "event_name": "schedule",
        }
        values.update(overrides)
        return values

    @patch("auth.jwt.decode")
    @patch("auth.PyJWKClient")
    def test_accepts_only_expected_workflow_claims(self, client_class, decode):
        client_class.return_value.get_signing_key_from_jwt.return_value = Mock(
            key="public-key"
        )
        decode.return_value = self.claims()

        self.assertTrue(github_actions_refresh_token_valid("signed-token"))
        decode.assert_called_once_with(
            "signed-token",
            "public-key",
            algorithms=["RS256"],
            audience="k-weather-refresh",
            issuer="https://token.actions.githubusercontent.com",
        )

    @patch("auth.jwt.decode")
    @patch("auth.PyJWKClient")
    def test_rejects_another_repository(self, client_class, decode):
        client_class.return_value.get_signing_key_from_jwt.return_value = Mock(
            key="public-key"
        )
        decode.return_value = self.claims(repository="someone/else")

        self.assertFalse(github_actions_refresh_token_valid("signed-token"))


if __name__ == "__main__":
    unittest.main()
