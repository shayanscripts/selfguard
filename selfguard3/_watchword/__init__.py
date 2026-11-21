"""Vendored Watchword engine (https://github.com/shayanscripts/watchword, MIT).

These modules are byte-identical copies of Watchword at its freeze (commit
b51be8bf, the code SelfGuard v3's sealed SEP test was scored with). Their
SHA-256 hashes are recorded in ``frozen_config.json`` and checked by
``tests/test_vendored.py``, so do not edit them in place: change behaviour in
``selfguard3`` instead.

Only what SelfGuard uses is vendored: layout, the instruction finder
(extract), the obedience check, provenance, the system-prompt leak check, and
their helpers. Watchword's orchestrator (core), model adapters and package
init are not included; ``selfguard3.checks`` replaces the orchestrator.
"""
