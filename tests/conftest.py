"""Keep API integration tests deterministic and local-only.

The durable worker has dedicated tests; endpoint contract tests run synchronous
processing so each assertion can inspect the completed result immediately.
"""

import os

os.environ["RFQ_ASYNC_INGEST_ENABLED"] = "false"
