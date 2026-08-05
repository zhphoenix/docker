# Project Glossary Skill

## Purpose

Maintain consistent terminology across the entire project.

This skill ensures that every business concept, service, API, database object, UI component, document, and agent uses a single canonical name.

The goal is to prevent inconsistent naming, duplicate terminology, and documentation drift.

---

## When to Use

Automatically apply this skill whenever working on:

* Source code
* APIs
* Database schema
* React components
* LangGraph workflows
* MCP tools and servers
* Docker services
* Documentation
* Architecture documents
* README files
* User interface text

---

## Responsibilities

This skill is responsible for:

1. Detecting newly introduced terminology.
2. Checking whether a canonical term already exists.
3. Recommending reuse of existing terminology.
4. Identifying inconsistent naming across the project.
5. Suggesting glossary updates for genuinely new concepts.
6. Keeping code and documentation aligned.

---

## Canonical References

Always consult the following documents before introducing new terminology:

1. `docs/00_Glossary.md` — Project terminology (source of truth)
2. `docs/00_Project_Inventory.md` — Project modules and services
3. `docs/00_Architecture_Decisions.md` — Architecture decisions
4. Other files under `docs/glossary/` if present

Do not invent terminology without checking these references.

---

## Workflow

For every new feature or modification:

1. Identify any new business or technical terms.
2. Search the project glossary for existing canonical names.
3. If an existing term matches, reuse it.
4. If multiple names describe the same concept, recommend the canonical one.
5. If no suitable term exists, propose a new glossary entry.
6. Continue implementation using the approved terminology.

---

## Conflict Handling

When conflicting terminology is found:

* Explain the conflict.
* Recommend the canonical term.
* Use the canonical term consistently.
* Do not silently rename existing project artifacts.

---

## New Terminology

If a genuinely new concept is introduced:

Recommend adding it to `docs/00_Glossary.md` with:

* Canonical name
* Category
* Definition
* Related concepts
* Status (Draft / Approved / Deprecated)

Do not automatically modify the glossary.

---

## Naming Principles

Always follow these principles:

* One concept → One name
* One service → One name
* One page → One name
* One API → One name

Avoid:

* Synonyms
* Abbreviations without definition
* Inconsistent capitalization
* Multiple names for the same concept

---

## Expected Output

If everything is consistent:

> Continue implementation without interruption.

If a naming conflict is found:

* Describe the inconsistency.
* Recommend the canonical terminology.
* Explain the reason for the recommendation.

If a new concept is found:

* Indicate that it is not present in the glossary.
* Recommend adding it after user review.

---

## Constraints

This skill must **never**:

* Invent terminology without checking project documentation.
* Create synonyms for existing concepts.
* Modify glossary documents automatically.
* Rename existing concepts without user confirmation.
* Ignore documented project terminology.

---

## Success Criteria

The project should always maintain:

* Consistent terminology across code, UI, APIs, database, and documentation.
* A single source of truth for project vocabulary.
* Minimal naming ambiguity.
* Easy onboarding for new contributors through a well-maintained glossary.
