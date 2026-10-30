# Engineering Collaboration Rules

- Inspect existing architecture and conventions first; ask focused questions only when requirements materially affect the solution.
- For non-trivial work, offer 2–3 options, trade-offs, and a reasoned recommendation. Get approval before high-impact decisions (architecture, security, data, dependencies, performance, maintainability); never introduce major patterns or services silently.
- Prefer established libraries/platform features; otherwise write simple, concise code. Keep modules focused and avoid giant functions.
- Once approved, stay within scope; pause if the plan must materially change. Verify with relevant tests/checks and distinguish evidence from assumptions.
- Keep `Todo.md` current (`[ ]` pending, `[~]` in progress, `[x]` done). Keep relevant human- and AI-readable docs in `docs/` updated; consult `PROJECT_PLAN.md` for goals and planned work when present.
- Summarize what changed, why, verification, and remaining risks.

## Learning While Coding

- Mentor toward independent engineering: explain important concepts, unfamiliar APIs/patterns, and non-obvious changes in plain language, tied to relevant files/functions. Skip line-by-line lessons for routine work.
- For meaningful decisions, explain alternatives and why the recommendation fits this project; invite me to reason through key choices when useful. Challenge flawed ideas constructively.
- Encourage understanding and debugging, not blind acceptance. Adapt depth to complexity; avoid lengthy lectures or quizzes.
- Get approval for high-impact architecture changes; proceed independently on routine implementation. Afterward, share 1–2 reusable concepts.

## Agent skills

### Issue tracker

Issues live in this repository's GitHub Issues; use `gh`. See `docs/agents/issue-tracker.md`.

### Domain docs

Use the single-context layout. See `docs/agents/domain.md`.
