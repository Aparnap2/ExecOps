"""Load SOPs from data/sops/ directory.

IMPORTANT: For Compliance SOPs, read the FULL file. Vector search is for
finding "Past Precedent" (how did we handle this last time?), NOT for
active rules. Compliance cannot be fuzzy.

Use vector_store only for historical precedent queries.
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SOPLoader:
    """Load and manage SOPs for Sentinel compliance checking.

    This loader prioritizes FULL policy reads over vector search because
    compliance requires complete context. A vector search might miss critical
    exceptions like "Friday deploys are blocked EXCEPT for emergency hotfixes."

    Vector search is reserved for "Past Precedent" - finding similar historical
    cases for contextual reference, not for rule enforcement.
    """

    def __init__(self, sop_dir: str = "data/sops") -> None:
        """Initialize SOP loader.

        Args:
            sop_dir: Directory containing SOP markdown files
        """
        self.sop_dir = Path(sop_dir)

    async def get_full_policy(self, policy_name: str) -> str:
        """Get the FULL deployment/compliance policy text.

        Why: Compliance cannot be fuzzy. We need the LLM to see the
        whole law to understand exceptions (e.g., "Friday deploys are
        blocked EXCEPT for emergency hotfixes").

        Args:
            policy_name: Name of policy file (e.g., "deployment_policy")

        Returns:
            Full policy text, or empty string if not found
        """
        policy_path = self.sop_dir / f"{policy_name}.md"

        if not policy_path.exists():
            logger.warning(f"Policy file not found: {policy_path}")
            return ""

        content = policy_path.read_text()
        logger.info(f"Loaded full policy: {policy_name} ({len(content)} chars)")
        return content

    async def get_deployment_rules(self) -> str:
        """Get FULL deployment policy text for compliance checking.

        Returns:
            Complete deployment_policy.md content
        """
        return await self.get_full_policy("deployment_policy")

    async def get_finance_rules(self) -> str:
        """Get FULL finance policy text for compliance checking.

        Returns:
            Complete finance_policy.md content
        """
        return await self.get_full_policy("finance_policy")

    async def list_available_policies(self) -> list[str]:
        """List all available policy files in the SOP directory.

        Returns:
            List of policy names (without .md extension)
        """
        if not self.sop_dir.exists():
            logger.warning(f"SOP directory not found: {self.sop_dir}")
            return []

        policies = []
        for path in self.sop_dir.glob("*.md"):
            policies.append(path.stem)

        logger.info(f"Found {len(policies)} policy files: {policies}")
        return policies

    # ==========================================================================
    # Vector Search: For "Past Precedent" only (not compliance!)
    # ==========================================================================

    async def find_similar_past_cases(
        self,
        vector_store: Any,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find similar past cases using vector search.

        This is for "How did we handle this last time?" not "What are the rules?"

        Args:
            vector_store: SemanticMemory instance
            query: Query to search past cases
            limit: Max results

        Returns:
            List of similar past cases with rule and similarity scores
        """
        if not vector_store:
            logger.debug("No vector store provided, skipping past case search")
            return []

        try:
            results = await vector_store.search(query, limit=limit)
            return [
                {"rule": r.rule, "similarity": r.similarity}
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to search past cases: {e}")
            return []


def get_sop_loader(sop_dir: str | None = None) -> SOPLoader:
    """Get SOPLoader instance.

    Args:
        sop_dir: Optional override for SOP directory

    Returns:
        Configured SOPLoader instance
    """
    return SOPLoader(sop_dir=sop_dir if sop_dir else "data/sops")
