The Anatomy of a Claude Code Project 👇

━━━━━━━━━━━━━━━

1️⃣ CLAUDE.md = Repo Memory (keep it short)

This is the north star file.

Not a knowledge dump. Just:

• Purpose (WHY)
• Repo map (WHAT)
• Rules + commands (HOW)

If it gets too long, the model starts missing important context.

━━━━━━━━━━━━━━━

2️⃣ .claude/skills/ = Reusable Expert Modes

Stop rewriting instructions.

Turn common workflows into skills:

• code review checklist
• refactor playbook
• release procedure
• debugging flow

Result:
Consistency across sessions and teammates.

━━━━━━━━━━━━━━━

3️⃣ .claude/hooks/ = Guardrails

Models forget.

Hooks don’t.

Use them for things that must be deterministic:

• run formatter after edits
• run tests on core changes
• block unsafe directories (auth, billing, migrations)

━━━━━━━━━━━━━━━

4️⃣ docs/ = Progressive Context

Don’t bloat prompts.

Claude just needs to know where truth lives:

• architecture overview
• ADRs (engineering decisions)
• operational runbooks

━━━━━━━━━━━━━━━

5️⃣ Local CLAUDE.md for risky modules

Put small files near sharp edges:

src/auth/CLAUDE.md
src/persistence/CLAUDE.md
infra/CLAUDE.md

Now Claude sees the gotchas exactly when it works there.
