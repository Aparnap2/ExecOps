"""AWS Lambda handler using Mangum for API Gateway events.

This module provides the Lambda handler entry point for deploying
the FounderOS AI Service to AWS Lambda with API Gateway.
"""

import logging
from typing import Any

from mangum import Mangum

from .main import app

logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler for API Gateway events.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    logger.info(f"Received event: {event.get('httpMethod', 'unknown')}")

    # Create Mangum handler
    mangum_handler = Mangum(app, lifespan="off")

    # Handle the event
    response = mangum_handler(event, context)

    logger.info(f"Response status: {response.get('statusCode', 'unknown')}")
    return response


# For local testing with sam local
if __name__ == "__main__":
    import json
    import uvicorn

    # Run the app locally
    uvicorn.run(app, host="0.0.0.0", port=8000)
