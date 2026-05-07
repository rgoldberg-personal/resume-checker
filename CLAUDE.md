# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Resume Checker App — a new project (not yet scaffolded). The repository currently contains agent configurations and skill references but no application source code.

## Agent System

Multi-agent workflow configured in `.claude/agents/`:
- **team-lead** — orchestrates other agents
- **agent-architect** — system design and technical decisions
- **agent-backend** — Python backend development
- **agent-frontend** — UI development
- **agent-product-owner** — requirements, user flows, edge cases
- **agent-qa** — quality assurance and testing
- **security-qa-agent** — security review
- **ios-performance** — iOS performance optimization

## Skills

`.agent/skills/` and `.claude/skills/` contain reusable skill definitions (mostly iOS/Swift frameworks and Python patterns). Notable non-symlinked skills:
- `ai-engineer` — AI/ML integration patterns
- `python-pro` — Python best practices
- `async-python-patterns` — async Python with implementation playbook
- `architecture-patterns` — system architecture with implementation playbook
- `database-architect` — database design
- `frontend-developer` — frontend development
- `mobile-app-ui-design` — mobile UI design system

## Development Environment

- Python 3.12 available (`python3.12`)
- Docker/Docker Compose available
- React frontend


## Permissions

Pre-approved shell commands include: `xcodebuild`, `git`, `python3`, `pip install`, `docker-compose`, `docker exec`, `curl`, `ssh`, `rsync`, `brew install`.
