# Valjeanli Agent Skills

Curated Hermes Agent skills for quant trading, research, and coding workflows.

## Skills

### Research

| Skill | Description |
|-------|-------------|
| [agentsmd-evaluator](research/agentsmd-evaluator) | Audit AGENTS.md/CLAUDE.md files against empirical best practices from the ETH Zurich study (arXiv:2602.11988) |
| [arxiv](../hermes-agent-skill/research/arxiv) | Search and retrieve academic papers from arXiv via their REST API |

## Installation

To install a skill, copy the SKILL.md into your local skills directory:

```bash
# Clone this repo
git clone https://github.com/valjeanli/valjeanli-agent-skills.git

# Copy a skill to your local directory
cp valjeanli-agent-skills/research/agentsmd-evaluator/SKILL.md ~/.hermes/skills/research/agentsmd-evaluator/SKILL.md
```

Or install directly:

```bash
hermes skills install https://raw.githubusercontent.com/valjeanli/valjeanli-agent-skills/main/research/agentsmd-evaluator/SKILL.md
```

## Creating Skills

New skills should follow the [Hermes skill authoring guide](https://hermes-agent.nousresearch.com/docs/reference/skills-catalog).
