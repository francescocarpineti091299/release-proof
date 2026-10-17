# Dependency and license inventory

ReleaseProof application code is MIT. That license does **not** relicense runner tools,
firmware binaries, model weights, or third-party packages.

- `docs/DEPENDENCY_INVENTORY.json` records installed Python packages from the rebuilt API
  image and production npm lock entries, including optional platform variants and integrity.
- Reproduce with `python scripts/dependency_inventory.py` while the local stack is running.
- Runtime tool pins/licenses and GPL source-distribution obligations:
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
- Original/pre-existing work: [`CODE_PROVENANCE.md`](CODE_PROVENANCE.md).
- UI graphics originate from the project's HTML/SVG sources; screenshot assets are captures
  of this demo, not stock images. Lucide icons are from the npm dependency's license.
- Model access is the managed AMD Token Factory service; no weights are distributed.
  Its specific hardware is undisclosed. Operators must accept the service's terms.

The inventory is an application-level dependency record, **not** a full OS/container SBOM
or proof of MIT compatibility for the entire toolchain. `REVIEW_REQUIRED` metadata must be
reviewed before publication/distribution. If publishing GPL-containing runner images or
firmware artifacts, supply the corresponding sources, changes and build instructions under
the applicable licenses. Do not represent the complete images as MIT-only.

The event accepts original, MIT-compliant submissions; final rights/prior-work acceptance
belongs to the author and organizers. A generated inventory cannot attest that approval.

Before giving judges public download access to GPL firmware evidence, review the exact
corresponding-source provision: pinned upstream sources alone may not include all local
configuration/app changes. Provide the applicable license, source/access instructions and
the actual build modifications alongside the binary download. The prototype must not imply
that MIT on the wrapper removes those obligations.
