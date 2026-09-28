# OKOA AI — Figma Design Workflow

End-to-end design process for OKOA AI (WhatsApp-first mental-health companion + counselor dashboard), from research to developer handoff. Aligned with the PRD, TRD, and roadmap phases.

---

## 1. Team & Roles

| Role | Responsibility | Figma plan seat |
|---|---|---|
| Product Designer (lead) | Owns file structure, components, design system | Full |
| UX Researcher | Flows, test scripts, synthesis boards (FigJam) | Full or Dev+Collab |
| Counselor Experience Designer | Dashboard & escalation UX | Full |
| Frontend Engineer | Handoff consumption, tokens export | Dev seat |
| Founder / PM | Reviews, approvals via comments | Viewer/Editor |
| Clinical Advisor | Safety-critical copy review (crisis screens) | Viewer + comment access |

**Workspace:** `OKOA AI` → Projects: `00 Foundations`, `01 Mobile (WhatsApp)`, `02 Counselor Dashboard`, `03 Research & FigJam`, `04 Marketing`, `05 Archive`.

---

## 2. File Structure & Naming Conventions

```
OKOA AI (Team project)
├── 🎨 DS — Okoa Design System        (single source of truth; library published)
├── 📱 Okoa Mobile — Core Flows       (onboarding, consent, chat, opt-out)
├── 📱 Okoa Mobile — Crisis & Safety  (helpline screens, escalation notices)  ← clinical sign-off required
├── 🖥️ Okoa Dashboard — Escalations   (queue, claim/handover, reply composer)
├── 🖥️ Okoa Dashboard — Trends & Audit(Phase 5/7 analytics views)
├── 🧪 Prototypes — Usability Tests    (dupes of flows wired for testing; archive after)
└── FigJam — Research Boards           (affinity maps, journey maps, retro)
```

Naming rules:
- Files: `[Area] — [Purpose] — [Status]` e.g. `Dashboard — Escalation Queue — Ready for Dev`.
- Frames: `Flow/Screen-Name/State` e.g. `Onboarding/Karibu-Welcome/Default`, `Chat/Risk-Nudge/Distress`.
- Pages inside each file: `🚧 WIP`, `✅ Ready for Dev`, `🗄 Archive`, `📐 Specs`.
- Branches for anything touching a `Ready for Dev` page — never edit released designs directly.

---

## 3. Design System Foundations (DS — Okoa)

Build once in `00 Foundations`, publish as a team library.

### 3.1 Tokens (Variables + Styles)
- **Color**: warm, non-clinical palette. Primary `#2F6B4F` (calm green), accent `#E8A33D`, crisis red `#C0392B` reserved **only** for safety surfaces; neutral scale; dark mode set.
- **Typography**: Inter (EN/SW UI). Sizes: 12/14/16/20/24/32. Line-height 1.5 body. Swenglish text must render at ≥16px (low-literacy consideration).
- **Spacing**: 4-pt scale (4/8/12/16/24/32/48).
- **Radius/shadows/elevation**: 3 elevation levels max.
- **Semantic variables**: `risk/crisis`, `risk/distress`, `state/claimed`, `state/handed-over` — used by dashboard status chips so colors stay consistent.

### 3.2 Components (with variants)
Mobile: WhatsApp-style bubble (user/bot/system), typing indicator, quick-reply chips, consent card, helpline card (1199/line 440), opt-out confirmation.
Dashboard: escalation row (priority color = risk band), status chip (open/claimed/resolved/muted), SLA countdown badge, conversation panel (UUID-only header), audit-log entry, trend heatmap cell.
All components: descriptive names + description field noting usage rules ("crisis red only on safety screens").

### 3.3 Content patterns (localization-ready)
Text styles carry EN / SW / ShEng variants as component properties; auto-layout tolerates +30% string expansion (Swahili is longer than English).

---

## 4. Phase ↔ Design Deliverables Map

| Roadmap phase | Design deliverable | Figma location |
|---|---|---|
| P1 WhatsApp gateway | Onboarding/consent/opt-out flow, welcome (Karibu) screen | Mobile — Core Flows |
| P2 Safety engine | Crisis intercept screens, distress nudge states, counselor alert notification | Mobile — Crisis & Safety |
| P3 Counselor dashboard | Escalation queue, claim/handover/reply, audit view, SLA widgets | Dashboard — Escalations |
| P4 LLM companion | Chat UX states (typing, streaming, memory-aware greeting), disclaimer treatment | Mobile — Core Flows |
| P5 Engagement | Check-in message templates, resource cards, referral deep-link confirmations | Mobile — Core Flows |
| P6 Multilingual | Language switcher, per-language bubble samples, translation-fallback notice | Mobile — Core Flows |
| P7 Analytics | Trends dashboard, heatmap, CSV/export affordances | Dashboard — Trends & Audit |
| P8 Scale/ops | Empty/error/degraded-mode states (LLM down → static fallback messaging) | Both files |

---

## 5. Standard Flow: Idea → Shipped Design

1. **Frame (FigJam)** — problem statement, user journey slice, "How might we" notes. Link jam in the design task.
2. **Research check** — pull insights from `Research Boards`; note constraints (privacy: no PII anywhere in mockups; use UUID placeholders like `usr_7f3a…`).
3. **Low-fi (day 1–2)** — wireframes on `🚧 WIP` page using the `Wireframe` kit (grayscale only). Peer critique async via comments within 24h.
4. **Hi-fi (day 3–4)** — apply DS components/tokens. Every screen gets all states: default, loading, error, empty, degraded.
5. **Prototype** — smart-animated flow for the happy path + crisis path. Crisis path prototype must include the 1199 helpline screen within ≤2 taps from any chat state.
6. **Review gates**
   - *Design crit* (30 min, weekly Thursday): whole product team.
   - *Clinical review*: safety screens require explicit comment approval from Clinical Advisor before moving to `✅ Ready for Dev`.
   - *PM sign-off*: scope + KPI alignment (e.g., SLA <2 min reflected in countdown UI).
7. **Handoff** — move finalized frames to `✅ Ready for Dev`, add specs on `📐 Specs` page (redlines, token names, behavior notes), tag engineers in Dev Mode, link the GitHub issue/PR. Status label `Ready for Dev` + due date.
8. **Build support** — designer reviews implementation screenshots in Dev Mode annotations; QA checklist covers contrast (WCAG AA ≥4.5:1), touch targets ≥44px, localization overflow.
9. **Post-launch** — usability-test findings go back to FigJam; iterate on branch; archive superseded versions.

SLA per request: small change ≤2 days; new flow ≤1 week; new feature area ≤2 weeks.

---

## 6. Research & Testing Cadence

- **Monthly**: 5-participant moderated test (target users in Kenya, remote via WhatsApp-based tasks where possible). Use prototype links; record on FigJam affinity board.
- **Crisp metrics tracked in retro jams**: task success, time-to-opt-out, crisis-screen comprehension, dashboard claim-time before/after redesign.
- **Ethics guardrails**: never screenshot real user chats into Figma; synthetic personas only (`Amina, 22, Nairobi, student`). Participant consent form referenced in every research board.

---

## 7. Versioning & Hygiene Rules

- `Ready for Dev` pages are append-only; changes go through branches merged by the file owner.
- Weekly Friday cleanup: detach unused instances, fix broken library links, archive WIP older than 2 sprints.
- Component descriptions updated whenever behavior changes; breaking library updates announced in Slack with version note.
- Export presets defined per file: mobile @1x/@2x PNG + SVG icons; dashboard assets SVG.
- Backups: monthly duplicate of DS file to `05 Archive` named `DS-YYYY-MM`.

---

## 8. Developer Handoff Protocol

1. Engineer receives Dev Mode link (not editor link).
2. Implementation references **token names**, not hex values (supports future re-theming).
3. Each handed-off frame links to its backend contract in comments (e.g., escalation queue ↔ `GET /api/counselor/escalations` fields shown in specs).
4. Any deviation during build is annotated back on the frame; resolved jointly before merge.

---

## 9. Tooling & Integrations

- **Figma plugin**: Dev Mode inspect, Stark (contrast), Content Reel (placeholder data — pre-loaded with synthetic Swahili/Sheng strings), Locus Focus? optional.
- **Slack**: notifications for comments/review-gate status changes on `Okoa` channel.
- **GitHub**: issues reference Dev Mode links; PR template includes "design reviewed Y/N".
- **Jira/Linear (if adopted)**: sync `Ready for Dev` label → ticket status.

---

## 10. Kickstart Checklist (first week)

- [ ] Create workspace, projects, and 6 files per §1/§2; invite team with correct seats.
- [ ] Build DS v0.1: color/type/space variables + 10 core components; publish library.
- [ ] Wireframe P1 flows (onboarding, consent, opt-out) low-fi; schedule first crit.
- [ ] Draft crisis-screen content with Clinical Advisor (EN/SW); get written approval workflow agreed.
- [ ] Set up FigJam research board template + retro template.
- [ ] Document this workflow in repo (`docs/FIGMA_WORKFLOW.md`) and pin in Slack.
