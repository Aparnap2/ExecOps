"""
Load test for GitHub Sentinel webhook endpoint.

Run with:
    locust -f loadtest/locustfile.py --host http://localhost:8000 --users 50 --spawn-rate 5
"""

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner
import random
import json


class GitHubWebhookUser(HttpUser):
    """Simulates GitHub webhook requests to the Sentinel."""

    wait_time = between(1, 5)

    def on_start(self):
        """Initialize user."""
        self.pr_numbers = list(range(100, 200))
        self.authors = ["junior-dev", "senior-dev", "contributor", "bot"]
        self.titles = [
            "Add user authentication",
            "Update SQL queries",
            "Fix typo in README",
            "Add new feature",
            "Refactor codebase",
            "Update dependencies",
            "Fix critical bug",
        ]

    @task(3)
    def pr_opened_normal(self):
        """Simulate a normal PR opened event."""
        payload = {
            "action": "opened",
            "pull_request": {
                "number": random.choice(self.pr_numbers),
                "title": random.choice(self.titles),
                "user": {"login": random.choice(self.authors)},
                "head": {"sha": "abc123def456"},
                "base": {"sha": "base123"},
            },
        }
        self.client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    @task(2)
    def pr_opened_sql(self):
        """Simulate a PR that might contain SQL."""
        payload = {
            "action": "opened",
            "pull_request": {
                "number": random.choice(self.pr_numbers),
                "title": "Add database query for users",
                "user": {"login": "junior-dev"},
                "head": {"sha": "sqlsha"},
                "base": {"sha": "base123"},
            },
        }
        self.client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    @task(1)
    def pr_synchronize(self):
        """Simulate a PR synchronization event."""
        payload = {
            "action": "synchronize",
            "pull_request": {
                "number": random.choice(self.pr_numbers),
                "title": random.choice(self.titles),
                "user": {"login": random.choice(self.authors)},
                "head": {"sha": "updatedsha"},
                "base": {"sha": "basesha"},
            },
        }
        self.client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    @task(1)
    def sentinel_status(self):
        """Check Sentinel status endpoint."""
        self.client.get("/sentinel/status")

    @task(1)
    def health_check(self):
        """Health check endpoint."""
        self.client.get("/health")


class MixedLoadUser(HttpUser):
    """Mixed load with webhook and SOP endpoints."""

    wait_time = between(2, 8)

    @task(5)
    def webhook_github(self):
        """GitHub webhook endpoint."""
        payload = {
            "action": "opened",
            "pull_request": {
                "number": random.randint(100, 999),
                "title": "Load test PR",
                "user": {"login": "load-test-bot"},
                "head": {"sha": "loadtestsha"},
                "base": {"sha": "base"},
            },
        }
        self.client.post(
            "/api/v1/webhook/github",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    @task(3)
    def sop_decide(self):
        """SOP decision endpoint."""
        payload = {
            "request_id": f"load-test-{random.randint(1000, 9999)}",
            "objective": random.choice(["lead_hygiene", "support_triage", "ops_hygiene"]),
            "events": [],
            "constraints": {},
        }
        self.client.post(
            "/decide",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    @task(1)
    def list_sops(self):
        """List available SOPs."""
        self.client.get("/sops")


# Event hooks for custom metrics
@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Initialize custom metrics."""
    if isinstance(environment.runner, MasterRunner):
        print("Load test initialized with master runner")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Print summary when test stops."""
    print("\n=== Load Test Summary ===")
    print(f"Total requests: {environment.stats.total.num_requests}")
    print(f"Total failures: {environment.stats.total.num_failures}")
    print(f"Avg response time: {environment.stats.total.avg_response_time:.2f}ms")
    print(f"95th percentile: {environment.stats.total.get_response_time_percentile(0.95):.2f}ms")
    print("==========================\n")
