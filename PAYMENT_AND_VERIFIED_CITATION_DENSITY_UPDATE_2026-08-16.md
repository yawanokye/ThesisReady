# Payment + Verified Citation Density Update — 2026-08-16

This release combines the payment reliability fix with the verified citation-density upgrade.

## Payment
- Normal African checkout routes through Paystack.
- Stripe private test checkout is inert unless `PROJECTREADY_ENABLE_TEST_CHECKOUTS=1` is deliberately enabled.
- Stale test variables therefore cannot trigger the private test-key prompt for normal customers.
- Complimentary tokens can be topped up, extended and widened to Thesis Workspace + Chapter Strengthener.

## Verified citation quality
- The existing discipline/section citation matrix remains active.
- Each substantive evidence-led paragraph targets at least 2 and preferably 3 distinct verified sources where suitable evidence exists.
- New detailed claims require accessible abstract/full-text evidence (`claim_support_eligible=true`).
- Metadata-only records do not prove detailed findings.
- Unverified generated citations cannot satisfy the target and are removed by the fail-closed provenance gate.
- If evidence is insufficient, the paragraph remains below target and ProjectReady reports the evidence gap instead of fabricating a citation.
- Objectives/questions, own results and other citation-light sections are not padded mechanically.

## Validation
- 182 automated tests pass.
- Python compilation and JavaScript syntax checks pass.
- No Python backend files are present in the public static directory.
