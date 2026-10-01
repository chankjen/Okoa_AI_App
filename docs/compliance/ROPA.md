# OKOA AI — Records of Processing Activities (ROPA)
**Pursuant to Section 24, Kenya Data Protection Act (2019)**  
**Version:** 1.0 | **Last Review:** October 2026  
**Data Controller:** OKOA AI Foundation / ZeTA Project  
**Data Protection Officer (DPO):** `dpo@okoa.ai`  

---

## 1. Controller Details
- **Entity:** OKOA AI Digital Health Project
- **Jurisdiction:** Republic of Kenya
- **Representative:** Lead Product & Security Engineer (ZeTA)
- **Primary Processing Location:** Localized hosting within African cloud / encrypted AWS Africa instance.

---

## 2. Inventory of Processing Activities

| Activity Reference | Purpose of Processing | Data Categories | Data Subjects | Lawful Basis (DPA 2019 § 30) | Retention Period | Security Safeguards |
|---|---|---|---|---|---|---|
| **PA-01: Identity Vault Enrolment** | Resolve inbound WhatsApp MSISDN to anonymous UUID | MSISDN (Phone Number) | WhatsApp users initiating chat | Explicit Consent (§ 30(1)(a)) | Retained until user triggers *FUTA DATA YANGU* (§ 40) or 12 months inactivity | AES-256-GCM at rest, PBKDF2 blind index, strict isolation from LLM pipeline |
| **PA-02: Conversational Support (LLM)** | Deliver CBT-grounded non-clinical coping dialogue | Text messages, detected language, anonymous session history | Enrolled youth users | Consent & Legitimate Clinical Interest | Active session window (Redis: hot, DB: until purged) | No PII in LLM context; zero-log inference; output guardrails |
| **PA-03: Sentiment & Risk Screening** | Crisis pre-screening and suicide prevention routing | Inbound message text, risk category, classifier score | Inbound WhatsApp users | Vital Interests (§ 30(1)(c)) & Explicit Consent | Duration of active session or escalation resolution | Keyword blocklist, XLM-RoBERTa classifier, prompt 1199 intervention |
| **PA-04: Daily Check-in & Mood Tracking** | Self-reported mood & trigger trend monitoring | Mood score (1–5), trigger labels (work, cravings), streak days | Consented users | Explicit Consent (§ 30(1)(a)) | Retained until erasure request | Anonymized time-series tied exclusively to UUID |
| **PA-05: Resource Matching & Referrals** | Match youth to vetted NGOs, rehabs, and empowerment programs | Coarse location (County/Sub-County only), referral action | Youth seeking physical care | Explicit Consent & Public Health Interest | Aggregated for KPI reporting (target: 500+ referrals) | Never GPS coordinates; no user details forwarded to facilities |
| **PA-06: Human Escalation & Handover** | Real-time counselor intervention on crisis/spiral | Escalation status, timestamps, masked conversation | Flagged high-risk users | Vital Interests (§ 30(1)(c)) | Retained for clinical audit trail | RBAC counselor JWT auth, SHA-256 chained audit log |
| **PA-07: Right to Erasure Execution** | Hard delete user records upon command | Purge timestamp, audit hash | Data subjects requesting erasure | Legal Obligation (§ 40) | Audit log tombstone retained (immutable, no PII) | Automated cryptographic deletion across all databases |

---

## 3. Categories of Recipients
- **Licensed Counselors:** Access to masked messages and UUID-keyed risk logs via counselor dashboard (JWT authentication required).
- **Physical Rehabilitation Partners:** Zero user data transmitted. Facilities receive direct, self-initiated walk-ins or calls from users.
- **Law Enforcement / Regulators:** Disclosures made strictly in response to valid court orders under Kenyan law or imminent threat to life (§ 30(1)(c)).

---

## 4. International Data Transfers
- **Cross-Border Transfers:** None. All primary database records and encrypted vault indices reside on localized infrastructure adhering to Section 48 & 49 of the Kenya Data Protection Act (2019).
