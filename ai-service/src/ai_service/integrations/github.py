"""GitHub API client for PR operations.

This module provides the GitHubClient class for interacting with the
GitHub API to comment on PRs and perform other operations.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GitHubClient:
    """GitHub API client for PR operations.

    This client handles authentication and provides methods for
    interacting with GitHub issues and pull requests.
    """

    def __init__(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        base_url: str = "https://api.github.com",
    ) -> None:
        """Initialize the GitHub client.

        Args:
            token: GitHub personal access token or app installation token
            owner: Repository owner (user or organization)
            repo: Repository name
            base_url: GitHub API base URL (for GitHub Enterprise)
        """
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

        logger.info(f"GitHubClient initialized for {owner}/{repo}")

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Make an HTTP request to the GitHub API.

        Args:
            method: HTTP method
            path: API path (appended to base_url)
            **kwargs: Additional httpx arguments

        Returns:
            JSON response as dict

        Raises:
            httpx.HTTPError: On API errors
        """
        url = f"{self.base_url}/{path}"

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                url,
                headers=self.headers,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    async def get_pull_request(self, pr_number: int) -> dict[str, Any]:
        """Get a pull request by number.

        Args:
            pr_number: PR number

        Returns:
            PR data dict
        """
        logger.debug(f"Fetching PR #{pr_number}")
        return await self._request(
            "GET",
            f"repos/{self.owner}/{self.repo}/pulls/{pr_number}",
        )

    async def get_pr_diff(self, pr_number: int) -> str:
        """Fetch the diff for a pull request.

        Args:
            pr_number: PR number

        Returns:
            Diff as string
        """
        logger.debug(f"Fetching diff for PR #{pr_number}")

        # First get the PR to get the diff URL
        pr = await self.get_pull_request(pr_number)
        diff_url = pr.get("diff_url")

        if not diff_url:
            return ""

        async with httpx.AsyncClient() as client:
            response = await client.get(diff_url)
            response.raise_for_status()
            return response.text

    async def get_pr_files(self, pr_number: int) -> list[dict[str, Any]]:
        """Get the list of files changed in a PR.

        Args:
            pr_number: PR number

        Returns:
            List of file data dicts
        """
        logger.debug(f"Fetching files for PR #{pr_number}")
        return await self._request(
            "GET",
            f"repos/{self.owner}/{self.repo}/pulls/{pr_number}/files",
        )

    async def comment_on_pr(
        self,
        pr_number: int,
        body: str,
        *,
        commit_id: str | None = None,
        path: str | None = None,
        line: int | None = None,
    ) -> dict[str, Any]:
        """Create a comment on a pull request.

        Args:
            pr_number: PR number
            body: Comment body (markdown supported)
            commit_id: Commit ID for line comment (optional)
            path: File path for line comment (optional)
            line: Line number for line comment (optional)

        Returns:
            Comment data dict
        """
        logger.info(f"Commenting on PR #{pr_number}")

        if commit_id and path and line:
            # Create a review comment on a specific line
            return await self._request(
                "POST",
                f"repos/{self.owner}/{self.repo}/pulls/{pr_number}/comments",
                json={
                    "body": body,
                    "commit_id": commit_id,
                    "path": path,
                    "line": line,
                },
            )
        else:
            # Create an issue comment
            return await self._request(
                "POST",
                f"repos/{self.owner}/{self.repo}/issues/{pr_number}/comments",
                json={"body": body},
            )

    async def create_review_comment(
        self,
        pr_number: int,
        body: str,
        commit_id: str,
        path: str,
        line: int,
        side: str = "RIGHT",
    ) -> dict[str, Any]:
        """Create a review comment on a specific line.

        Args:
            pr_number: PR number
            body: Comment body
            commit_id: SHA of the commit
            path: File path
            line: Line number
            side: "RIGHT" for added lines, "LEFT" for removed

        Returns:
            Comment data dict
        """
        logger.info(f"Creating review comment on PR #{pr_number}")
        return await self._request(
            "POST",
            f"repos/{self.owner}/{self.repo}/pulls/{pr_number}/comments",
            json={
                "body": body,
                "commit_id": commit_id,
                "path": path,
                "line": line,
                "side": side,
            },
        )

    async def create_pull_request_review(
        self,
        pr_number: int,
        event: str = "COMMENT",
        body: str | None = None,
    ) -> dict[str, Any]:
        """Create a review for a pull request.

        Args:
            pr_number: PR number
            event: Review event (APPROVE, REQUEST_CHANGES, COMMENT)
            body: Review body

        Returns:
            Review data dict
        """
        logger.info(f"Creating review for PR #{pr_number} with event: {event}")
        return await self._request(
            "POST",
            f"repos/{self.owner}/{self.repo}/pulls/{pr_number}/reviews",
            json={
                "event": event,
                "body": body,
            },
        )

    async def dismiss_review(
        self,
        pr_number: int,
        review_id: int,
        message: str,
    ) -> dict[str, Any]:
        """Dismiss a review.

        Args:
            pr_number: PR number
            review_id: Review ID to dismiss
            message: Dismissal message

        Returns:
            Review data dict
        """
        logger.info(f"Dismissing review {review_id} on PR #{pr_number}")
        return await self._request(
            "PUT",
            f"repos/{self.owner}/{self.repo}/pulls/{pr_number}/reviews/{review_id}/dismissals",
            json={"message": message},
        )

    def get_repo(self) -> tuple[str, str]:
        """Get the repository owner and name.

        Returns:
            Tuple of (owner, repo)
        """
        return self.owner, self.repo
