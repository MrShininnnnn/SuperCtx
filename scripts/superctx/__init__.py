"""SuperCtx engine: deterministic file I/O, hashing, and registry matching.

The visible agent-facing skills wrap this package through `superctx sync` and
`superctx add`. Setup and status logic remains available as internal Python
modules for orchestration, hooks, and tests, but not as public CLI commands.
"""

__version__ = "0.1.4"
