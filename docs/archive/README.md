# Historical Documentation Boundary

> **Status:** HISTORICAL  
> **Authority:** Archive policy only  
> **Owner:** Market Regime Alpha maintainers  
> **Last Updated:** 2026-08-19

Historical audits, completed delivery reports, temporary work packages, superseded architectures, obsolete roadmaps, designed-only specifications and retired static documentation are preserved by Git history rather than kept in the active documentation tree.

The former `docs/constitution/00` through `09` set was superseded during the 2026-08-19 Canonical Design convergence. Its useful principles were consolidated into `docs/architecture/Canonical-Overall-Design.md`; the original files remain recoverable from Git history for provenance or migration archaeology.

The obsolete static `docs/index.html` “A 股买卖点识别模型” page and its documentation-only data payload were likewise removed because they described an older product identity and had no canonical runtime or architecture role.

Historical material:

- may be consulted for provenance, research archaeology or migration reasoning;
- must not be loaded as current normative architecture;
- cannot override current executable code, PostgreSQL schema/writers, current tests/evidence or the Canonical Overall Design;
- should not be copied back into `docs/` merely to make history easier to browse.

The active documentation entry point is `docs/README.md`.