# RFQ Assistant

**Human-reviewed RFQ intake and quotation preparation for independent industrial component distributors.**

An early-stage, validation-first product project. This repository is a **product blueprint**, not a shipped application and not evidence of paying customers.

## The problem we are testing

A distributor receives an RFQ through an email, PDF bill of materials, spreadsheet, or typed part-number list. A salesperson reads the request, separates its line items, checks the company's item catalog, resolves ambiguities, and manually drafts a reply. We hypothesize that the repetitive, document-heavy steps consume enough time to justify a paid workflow assistant. Actual pain, frequency, existing systems, and willingness to pay **must be confirmed directly with buyers**.

## The proposed experience

    Buyer sends PDF / XLSX / email
                   |
                   v
            Upload / paste RFQ
                   |
                   v
       Extract lines + source evidence
                   |
                   v
      Match known SKUs / flag unknowns
                   |
                   v
          Salesperson reviews edits
                   |
                   v
       Export quote worksheet + draft
                   |
                   v
       Human sends through normal tools

**Never auto-send a quote. Never invent part numbers, prices, technical equivalence, inventory, or lead time.**

## First product slice

- Accept pasted email text and CSV/XLSX/PDF files.
- Produce editable, source-linked RFQ rows: part number, description, quantity, unit, notes, and extraction warnings.
- Import a small distributor-provided catalog CSV for **exact manufacturer part number matches**.
- Flag missing/contradictory data, duplicates, no-match lines, and possible equivalents as **review required**; no automatic engineering substitute.
- Let an operator approve every row and export a quote-preparation XLSX/CSV plus an **unsent** email draft.
- Record reviewer edits and a lightweight audit trail.

Use one component family for the initial benchmark; do not attempt a universal industrial search engine in v0.

## Who it is for

Small independent US/UK industrial electrical, automation, or electronic component distributors (ideally 5–50 people; evaluate up to 100) with manual quotation intake and a real inside-sales desk. Their website accepting RFQs is **qualification evidence**, not proof of purchasing intent.

## Repository guide

| File | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Instructions for coding agents and mandatory PR workflow |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Mission, user needs, functional boundaries, success criteria |
| [docs/SCENARIOS.md](docs/SCENARIOS.md) | Realistic illustrative workflows and expected human reactions |
| [docs/UX.md](docs/UX.md) | Screens, states, wireframes, interaction and visual design |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Lean architecture, contracts, data and security constraints |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Ordered build checkpoints and definition of done |
| [docs/TESTING.md](docs/TESTING.md) | Ground-truth, adversarial and end-to-end test plan |
| [docs/VALIDATION.md](docs/VALIDATION.md) | Buyer interviews, commercial experiments, outreach guardrails |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions, assumptions, open risks and pivot conditions |
| [SECURITY.md](SECURITY.md) | Safe handling and disclosure guidance |

## Build status

- [x] Product scope, design and build checklist documented
- [ ] Buyer conversations confirm the narrow bottleneck
- [ ] Synthetic sample pack and ground truth created
- [ ] Upload and parser working locally
- [ ] Catalog matching and review UI working locally
- [ ] Tested quotation worksheet and export
- [ ] Independent realistic end-to-end demo
- [ ] One opt-in customer pilot with measured baseline

These boxes indicate intentions; do not mark work complete without checking acceptance evidence. Engineering implementation is intentionally unstarted.

## Engineering principles

**Small, inspectable, fail-closed, privacy-aware.** Prefer deterministic extraction of IDs/quantities and exact catalog matching over fancy agents. Use models only where document layout or language extraction needs them. Each output shows a source and allows correction. Make it obvious when the system does not know.

**Ownership:** Personal project only. Do not transfer any employer-owned code, credentials, datasets, repositories or contacts.

## Development workflow

Every change to application code, documentation or configuration happens on a feature branch and is proposed to **main through a pull request**. Follow [AGENTS.md](AGENTS.md). After a PR is successfully merged, its feature branch should be deleted; the repository includes a best-effort same-repository branch cleanup workflow.

## License

No open-source license has been selected. Public visibility does **not** grant reuse permission. Choose a license explicitly before external code contributions.
