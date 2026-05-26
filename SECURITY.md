# Security policy

## Supported versions

Active development happens on `main`. Security fixes land there first
and are tagged as the next available version. The most recent tagged
release receives security backports; older tags do not.

## Reporting a vulnerability

If you find a security issue — credential leakage, unintended write
behaviour against the VisiblAir API, anything that exposes secrets
beyond the documented redaction set — please report it **privately**
rather than in a public GitHub issue.

Email: **jason@jasonhofmann.com**

Include:

1. A description of the issue and its impact
2. Steps to reproduce (if applicable)
3. Whether you've discussed it with anyone else, or with VisiblAir

I'll acknowledge within 7 days and aim to ship a fix within 30 days
of confirmation, depending on severity. Once fixed, I'll credit
reporters in the CHANGELOG unless they prefer to remain anonymous.

## Scope

In scope:

- Credential leakage from the integration to logs, diagnostics
  downloads, or HA's state machine
- Bypasses of the redaction set in `diagnostics.py`
- Unintended write operations to the VisiblAir cloud (the integration
  is contractually read-only)
- Code-execution paths reachable via crafted API responses

Out of scope:

- Issues in the upstream VisiblAir cloud or hardware firmware (report
  to VisiblAir directly)
- Issues in Home Assistant Core (report to the HA security team:
  https://www.home-assistant.io/security/)
- Issues in HACS itself (report to the HACS team)
