---
name: open-code-review
description: >
  Performs AI-powered code review on Git changes using the `ocr` CLI from alibaba/open-code-review.
  Use when the user asks to review code, review a pull request, review staged/unstaged changes,
  review a commit, or compare branches for code quality issues.
  Produces line-level review comments and can automatically apply fixes when requested.
  With appropriate review rules, can detect various types of issues including bugs, security
  vulnerabilities, performance problems, and code quality concerns.
license: Apache-2.0
compatibility: >
  Requires the `ocr` CLI installed (via `npm install -g @alibaba-group/open-code-review`).
  Uses Delegation Mode — the agent performs the review using its own LLM; no OCR API key required.
metadata:
  author: alibaba
  homepage: https://github.com/alibaba/open-code-review
  version: 1.0.0
---

# Open Code Review (Delegate Mode)

A skill for invoking open-code-review (ocr) in **Delegation Mode** — OCR handles file selection
and rule resolution; the agent performs the actual review using its own LLM capabilities.

## Prerequisites check

Before starting a review, verify the environment:

```bash
# 1. Check the CLI is installed
which ocr || echo "NOT INSTALLED — run: npm install -g @alibaba-group/open-code-review"

# 2. Verify version
ocr version
```

If ocr is not installed, install it first:

```bash
npm install -g @alibaba-group/open-code-review
```

No LLM configuration is needed for Delegation Mode.

## Workflow

### Step 1: Preview Reviewable Files

Run delegate preview to determine which files need review:

```bash
# Workspace mode — all staged, unstaged, and untracked changes
ocr delegate preview

# Branch comparison
ocr delegate preview --from main --to feature-branch

# Single commit
ocr delegate preview --commit abc123
```

The output lists all reviewable files with their change stats (+insertions/-deletions).

### Step 2: Get Review Rules

Retrieve the resolved review rules for the target files:

```bash
ocr delegate rule <file1> <file2> ...
```

This outputs grouped rules (by file pattern) that define what to look for during review.
Rules cover: dead code, boundary handling, error handling, security, performance, concurrency, etc.

### Step 3: Gather Business Context (Optional)

If the user provides background context, note it for improved review quality.
Use `--background "context"` or `-b "context"` flags when available.

### Step 4: Perform the Review

For each reviewable file:

1. Read the file's diff (use `git diff` or the change info from preview)
2. Read the full file content for context
3. Apply the rules from Step 2 to identify issues
4. Generate structured review comments with:
   - **path**: File path
   - **start_line / end_line**: Precise line range
   - **content**: Review comment text
   - **suggestion_code**: Optional fix suggestion
   - **existing_code**: Original code snippet

### Step 5: Classify and Report

For each issue found, classify by priority:

- **High**: Obvious bugs, security issues, clear mistakes, or well-founded suggestions with precise fix proposals
- **Medium**: Reasonable concerns but context-dependent, style/performance suggestions, or fixes that require manual implementation
- **Low**: Likely false positives, lacking sufficient context, nitpicks, or meaningless suggestions

Report all comments grouped by priority level.

### Step 6: Fix (If Requested)

Before applying fixes, check whether the user requested automatic fixes:

- If the user explicitly requested "review and fix" or similar, proceed with automatic fixes
- If the user only requested "review" without fix intent, ask for permission before applying any changes

When fixing issues:

- Focus on High and Medium priority items
- Apply fixes directly to the code when safe and well-defined
- For complex fixes requiring manual intervention, clearly describe what needs to be done

## Output Format

Present results using this template:

```markdown
## Code Review Results

**Files reviewed**: N
**Issues found**: X high priority / Y medium priority

### High Priority

- **`path/to/file.py:42`** — Brief description
  > Recommendation: How to fix

### Medium Priority

- **`path/to/file.ts:88`** — Brief description
  > Recommendation: How to fix (if applicable)
```

If the review found no issues after filtering, simply state: "Review complete — no issues found in N files."

## Alternative: OCR-Managed Review

If an LLM is configured for OCR (via `ocr config provider` or environment variables),
you can also run OCR's built-in review directly:

```bash
# Always use --audience agent to suppress progress UI
ocr review --audience agent -b "business context"

# Branch comparison
ocr review --audience agent --from main --to feature-branch

# Single commit
ocr review --audience agent --commit abc123

# Full-file scan (no git history needed)
ocr scan --path src/
```

## Custom Review Rules

OCR resolves rules in this priority order:

1. `--rule <path>` flag (highest)
2. `<repo>/.opencodereview/rule.json`
3. `~/.opencodereview/rule.json`
4. Built-in system defaults (lowest)

Rule file format:

```json
{
  "rules": [
    {
      "path": "**/*.py",
      "rule": "All new methods must validate required parameters for null",
      "merge_system_rule": true
    },
    {
      "path": "**/*mapper*.xml",
      "rule": "Check SQL for injection risks and missing closing tags"
    }
  ]
}
```

To preview which rule applies to a file:

```bash
ocr rules check src/main/java/com/example/Foo.java
```

## Gotchas

- **Working directory matters** — `ocr delegate` operates on the Git repo at the current directory. Use `--repo /path/to/repo` to run from elsewhere.
- **Untracked files are included** in workspace mode — running bare `ocr delegate preview` includes staged, unstaged, and untracked changes.
- **Don't pass --audience human** for OCR-managed mode — it streams progress UI that pollutes output. Always use `--audience agent`.
- **Comment language** follows config — set language config to English or Chinese (default: Chinese).

## References

- Full docs: https://github.com/alibaba/open-code-review
- NPM package: https://www.npmjs.com/package/@alibaba-group/open-code-review
- Issue tracker: https://github.com/alibaba/open-code-review/issues
