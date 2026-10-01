# OKOA AI — Data Protection Impact Assessment (DPIA)
**Pursuant to Section 31, Kenya Data Protection Act (2019)**  
**Version:** 1.0 | **Date:** October 2026  
**Clinical & Technical Lead:** ZeTA (PM/Lead Engineer) & OKOA Clinical Advisory  

---

## 1. Executive Summary & Context of Processing
OKOA AI processes sensitive health and behavioral data (substance use, psychiatric distress, emotional well-being) belonging to Kenyan youth. Because health data constitutes **sensitive personal data** under Section 2 of the Kenya Data Protection Act (2019), conducting a formal DPIA is a mandatory statutory precondition under Section 31 before public deployment.

---

## 2. Assessment of Necessity and Proportionality
- **Lawfulness & Transparency:** Users are presented with a clear Swahili/Sheng/English consent screen upon first message. Processing relies on explicit consent (§ 30(1)(a)) and vital interests in crisis situations (§ 30(1)(c)).
- **Data Minimization:** No national IDs, names, email addresses, or precise GPS coordinates are collected. The only identifier is a decoupled, cryptographically generated UUID.
- **Purpose Limitation:** Information collected (mood, streak days, county) is utilized solely for conversational coping support, safety screening, and voluntary resource referral.

---

## 3. Risk Identification & Mitigation Matrix

| Risk ID | Threat Description | Inherent Severity | Inherent Likelihood | Mitigation Safeguards & Technical Controls | Residual Severity | Residual Likelihood |
|---|---|---|---|---|---|---|
| **R-01** | Phone number leakage via database breach or backup exposure | High | Moderate | **Cryptographic Vault Isolation:** Phone numbers are AES-256-GCM encrypted with blind indexing (PBKDF2 HMAC). The main application and LLM context operate strictly on anonymous UUIDs. | Low | Low |
| **R-02** | Stigmatization of youth by community/family accessing phone | High | Moderate | **Zero-Name Design & Self-Service Wipe:** No personal names stored. User can instantly erase all conversation and mood records by sending `"FUTA DATA YANGU"`. | Medium | Low |
| **R-03** | LLM hallucinating medical/psychiatric diagnosis or medication | High | Moderate | **Strict Clinical System Guardrails & RAG:** Prompt guardrails strictly prohibit prescribing drugs or diagnosing. All coping strategies are retrieved from vetted clinical CBT tables. | Low | Low |
| **R-04** | Crisis false-negative (suicide ideation missed) | Critical | Low | **Multi-tier Safety Gate:** Keyword blocklists combined with fine-tuned multilingual transformer scoring every message BEFORE the LLM path. Immediate static 1199 helpline routing and dashboard escalation. | Medium | Very Low |
| **R-05** | Unauthorized access to counselor dashboard | High | Low | **Defense in Depth:** Argon2id password hashing, Bearer JWT session expiration, role-based access control, tamper-evident SHA-256 chained audit logs. | Low | Very Low |
| **R-06** | Third-party surveillance / MITM on WhatsApp traffic | Moderate | Low | **TLS 1.3 & HSTS Enforcement:** All API traffic strictly requires TLS 1.3 with HTTPS/HSTS preloading and webhook SHA-256 signature verification. | Low | Very Low |

---

## 4. Clinical Advisory & DPO Sign-Off
- **Clinical Governance:** Approved by Clinical Advisory (Dr. Ochieng persona / Partner Counselor).
- **Data Protection Officer Recommendation:** Approved for Phase 6 staging and controlled pilot deployment under ODPC compliance guidelines.
