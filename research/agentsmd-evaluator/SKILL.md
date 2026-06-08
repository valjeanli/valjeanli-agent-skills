---
name: agentsmd-evaluator
description: Use when auditing an AGENTS.md / CLAUDE.md file against evidence-based best practices from the ETH Zurich study (arXiv:2602.11988). User provides the file path.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, agents-md, evaluation, audit, coding-agents]
    related_skills: [arxiv]
---

# AGENTS.md Evaluator

Audit repository-level context files (AGENTS.md, CLAUDE.md, .cursorrules) against empirical best practices from the ETH Zurich study (Gloaguen et al., arXiv:2602.11988).

## Overview

A 2026 ETH Zurich study empirically evaluated AGENTS.md files across multiple coding agents and LLMs. Key findings:
- Context files REDUCE task success rates vs. no context
- Inference cost increases by 20%+
- Unnecessary requirements make agents perform worse
- LLM-generated context files perform worse than NO context
- Only genuinely repository-specific facts (not discoverable from code) are safe to include

This skill scores a user-provided AGENTS.md on a 0-100 scale with per-section breakdown and generates a fix prompt.

## When to Use

- User asks to audit, evaluate, score, or rate an AGENTS.md / CLAUDE.md
- User wants to know if their context file is too bloated
- User wants a targeted fix prompt to improve a context file

## Prerequisites

The user must provide the path to the AGENTS.md (or CLAUDE.md) file to evaluate.

```
<path/to/agents.md>
```

## Procedure

### 1. Read the File

Load the AGENTS.md/CLAUDE.md from the provided path. Count total lines, words, and extract all `##` sections.

### 2. Score Each Section

Score each section 0-100 using these factors:

**Penalties:**
- **Discoverable info** (-5 per item, max -30): language version, testing framework, coding conventions, style guides, linting/formatter rules, dependency lists, import conventions, architecture patterns visible from file structure
- **Verbosity** (>500 words: -15, >1000 words: -25): raw word count of section content
- **Prescriptive instructions** (-5 each, max -25): lines starting with "use", "should", "must", "always", "never", "follow", "create", "write", "execute", "run", or workflow steps ("step 1", "procedure", "workflow")
- **Negative constraints** (-5 each, max -15): "DO NOT", "must never", "must NOT", "never modify", "never write", "must not"

**Bonus:**
- **Genuine repo-specific facts** (+10): only if the section is under 100 words AND contains truly non-discoverable info (hidden dependencies, non-standard commands, architecture notes not visible from file paths)

**Score thresholds:**
- 90-100: Optimal — only non-discoverable repo facts, under 50 lines
- 70-89: Good — mostly repo-specific, minor convention leakage
- 50-69: Acceptable — mix of repo facts and conventions
- 30-49: Problematic — mostly conventions, style guides, workflow instructions
- 10-29: Bad — verbose procedural docs, API reference, user manual
- 0-9: Very Bad — bloated, everything agent can discover from code

### 3. Count Global Violations

Across the entire file, count:
- Total discoverable info mentions
- Total negative constraints
- Total prescriptive instruction lines
- Whether an API/script reference section exists (any section with 500+ words of command examples)

### 4. Compute Overall Score

Average of all section scores, rounded to 1 decimal.

### 5. Output Report

Produce a structured report:

```
AGENTS.md Evaluation Report

Scoring: per-section 0-100, overall = average

File: <path>
Lines: <N> | Words: <N>

Overall Score: X/100 — <ASSESSMENT>

| Section | Score | Words | Verdict |
|---------|-------|-------|---------|
| Section 1 | XX/100 | N | Good / Acceptable / Problematic / Bad / Very Bad |

Violations:
- <N> discoverable info mentions
- <N> negative constraints
- API reference section: Yes/No

Recommendations:
- What to remove (specific sections and why)
- What to keep (condensed)
- Target line count
```

### 6. Generate Fix Prompt

After the report, produce an LLM fix prompt tailored to the specific file:

```
You are tasked with rewriting <filename> following evidence-based best practices.

CONTEXT: A 2026 ETH Zurich study (Gloaguen et al., arXiv:2602.11988) found context files REDUCE task success rates by 20%+. Unnecessary context hurts coding agents.

CURRENT: <N> lines, <N> words. SCORE: X/100 — <ASSESSMENT>.

RULES:
1. Only include what the agent CANNOT discover from the codebase
2. NO style guides, conventions, workflow instructions
3. NO negative constraints ("DO NOT", "must never")
4. Keep total under <target> lines

REMOVE:
- <list specific sections to remove with word counts>

KEEP (condensed):
- <list what to keep and target line counts>

Rewrite the ENTIRE <filename>. Target ~<N> lines.
```

## Common Pitfalls

1. **Scoring the filename/header section.** The first `##` is often just "## Repository Purpose" or similar. Don't score the `# Title` line itself as a section.
2. **Missing embedded content.** Some files have long embedded report templates, code examples, or workflow diagrams between `##` headers. These count toward word count and should be penalized.
3. **Non-English content.** Files in Japanese or other languages may have different structural patterns (e.g., `### ステップ1` as sub-steps). Treat these as prescriptive instructions if they describe workflow steps.
4. **Over-penalizing config sections.** Configuration file paths (`.env`, `config.yaml`) are legitimate to include since the agent may not know where the project stores config. Don't penalize these.
5. **Architecture descriptions.** A file tree diagram is discoverable from `ls` — penalize it. But architecture notes about hidden dependencies or non-standard patterns that cannot be inferred from file paths are valid.

## Verification Checklist

- [ ] Each section has a score, word count, and verdict label
- [ ] Overall score is the average of section scores
- [ ] Global violation counts are included
- [ ] Fix prompt is specific to the evaluated file (references actual section names and word counts)
- [ ] Fix prompt includes concrete REMOVE/KEEP guidance with section-specific word counts
