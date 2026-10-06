"""RScan test suite.

    tests/unit/          fast, isolated tests (no Flask app, no fixtures)
    tests/integration/   Flask test-client flows against real services
    tests/parity/        Python <-> JavaScript/WASM parity harnesses (Node)
    tests/js/            frontend unit + asset-contract tests (bun test)
    tests/fixtures/      committed parity fixtures (do not edit by hand)

Run everything: ``bun test`` (see docs/TESTING.md).
"""
