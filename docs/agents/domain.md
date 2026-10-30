# Domain docs

This repository uses a single-context documentation layout.

## Before exploring

- Read the root `GLOSSARY.md` when it exists; use its domain vocabulary consistently.
- Read relevant decisions in `docs/adr/` when present. If these files do not exist, proceed without flagging their absence.
- If work conflicts with an existing ADR, call out the conflict rather than silently overriding it.

## Layout

```text
/
├── GLOSSARY.md
├── docs/adr/
└── src/
```

Create domain documentation as terms and decisions become established; do not invent a glossary or ADRs preemptively.
