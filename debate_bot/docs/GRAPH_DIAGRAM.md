# Debate Graph — Node Diagram

## Mermaid Flowchart

```mermaid
flowchart TD
    START([START]) --> MO

    MO["🎙️ moderator_open\n— sets round = 'opening'"]
    MO --> PRO1

    subgraph R1["Round 1: Opening"]
        PRO1["🟢 pro_opening\n~200 words"]
        CON1["🔴 con_opening\n~200 words"]
        PRO1 --> CON1
    end

    CON1 --> MC

    MC{"🎙️ moderator_checkpoint\nadvances round"}

    MC -- "round = 'rebuttal'" --> PRO2

    subgraph R2["Round 2: Rebuttal"]
        PRO2["🟢 pro_rebuttal\n~100 words\ncounters Con opening"]
        CON2["🔴 con_rebuttal\n~100 words\ncounters Pro opening"]
        PRO2 --> CON2
    end

    CON2 --> MC

    MC -- "round = 'closing'" --> PRO3

    subgraph R3["Round 3: Closing Remarks"]
        PRO3["🟢 pro_closing\n~75 words"]
        CON3["🔴 con_closing\n~75 words"]
        PRO3 --> CON3
    end

    CON3 --> MC

    MC -- "round = 'decision'" --> MD

    MD["🎙️ moderator_decision\nSummarises both sides\nDeclares winner"]
    MD --> END_NODE([END])

    style MO    fill:#f5f0ff,stroke:#7c3aed,color:#1a1a1a
    style MC    fill:#f5f0ff,stroke:#7c3aed,color:#1a1a1a
    style MD    fill:#f5f0ff,stroke:#7c3aed,color:#1a1a1a
    style PRO1  fill:#dcfce7,stroke:#16a34a,color:#1a1a1a
    style PRO2  fill:#dcfce7,stroke:#16a34a,color:#1a1a1a
    style PRO3  fill:#dcfce7,stroke:#16a34a,color:#1a1a1a
    style CON1  fill:#fee2e2,stroke:#dc2626,color:#1a1a1a
    style CON2  fill:#fee2e2,stroke:#dc2626,color:#1a1a1a
    style CON3  fill:#fee2e2,stroke:#dc2626,color:#1a1a1a
    style R1    fill:#f0fdf4,stroke:#86efac
    style R2    fill:#fffbeb,stroke:#fcd34d
    style R3    fill:#fff7ed,stroke:#fdba74
```

---

## Node Legend

| Symbol | Role | LLM Call? | Visits per debate |
|--------|------|-----------|-------------------|
| 🎙️ Moderator (open) | Sets initial round state | No | 1 |
| 🎙️ Moderator (checkpoint) | Advances round, conditional branch | No | 3 |
| 🎙️ Moderator (decision) | Summarises + declares winner | Yes | 1 |
| 🟢 Pro Agent | Argues in favour | Yes | 3 (opening, rebuttal, closing) |
| 🔴 Con Agent | Argues against | Yes | 3 (opening, rebuttal, closing) |

---

## Conditional Edge Routing (moderator_checkpoint)

```
state["round"] after checkpoint  →  next node
─────────────────────────────────────────────
"opening"   sets → "rebuttal"   →  pro_rebuttal
"rebuttal"  sets → "closing"    →  pro_closing
"closing"   sets → "decision"   →  moderator_decision
```

The same physical node (`moderator_checkpoint`) is visited 3 times — it reads and writes `state["round"]` each time to drive the branch.

---

## Key Design Principle

> The Moderator **gates every round transition**. Pro and Con never advance the debate themselves — they only respond to what was said. All routing authority sits in `moderator_checkpoint`.
