# OKOA AI Dataset Curation (Phase 4.3)

## Dataset Specifications (TRD §4)

- **Target Size:** 10,000+ multi-turn dialogues across Swahili, Sheng, and Kenyan English.
- **Clinical Alignment:** Supervised by clinical advisor (Dr. Ochieng persona) and evaluated using an inter-annotator agreement target ($\kappa \ge 0.8$).
- **Privacy & Anonymization:** In strict accordance with the **Kenya Data Protection Act (2019)**:
  - Zero PII (names, phone numbers, exact geolocations, institution names) in training corpora.
  - All phone identifiers scrubbed using automated regex + human review.
  - Synthetic conversations generated via counselor-in-the-loop clinical scenarios.

## Schema

Each line in `sample_conversations_sw_sheng.jsonl` represents a complete multi-turn dialogue formatted in the standard Llama 3 conversation schema:

```json
{
  "dialogue_id": "OKOA-CBT-001",
  "language": "sw",
  "domain": "academic_stress_and_anxiety",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```
