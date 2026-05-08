---
name: kng-recall
description: |
  Load knowledge base details from KNG via a subagent when the conversation
  needs project-specific knowledge.

  Trigger conditions (any one):
  - The auto-retrieve hint indicated KB hits (line starting with `[KNG]
    项目 ... 命中 N 条`).
  - User asks about project business modules, bug patterns, test design,
    historical issues, code conventions, or domain terminology specific to
    the active project.
  - User explicitly invokes `/kng-recall <query>`.

  Do NOT invoke for general programming questions, generic tool usage, or
  conversations unrelated to the linked project.
argument-hint: "[query]"
allowed-tools: [Agent]
---

# KNG Knowledge Recall

Load KB content **via subagent**, not in the main thread.

## Why subagent

KB retrieval is mechanical work — run script → parse JSON → judge which
1-2 hits out of 5 are actually relevant → extract the useful points.
Doing this inline pollutes the main conversation with raw snippets (5 ×
up to 2KB each) that the user never sees in the final answer.

By delegating to a subagent in an isolated context, the main thread only
receives the subagent's focused summary (~500–800 words), keeping the
context window lean. Same design as `auto_evolve` — KNG's invariant is
that mechanical KB work doesn't bleed into the user-facing thread.

## How to invoke

Use the **Agent tool** with `subagent_type: "general-purpose"` and the
prompt template below. Fill in the placeholders from the conversation:

- `<USER_QUESTION>` — the user's most recent prompt or the question that
  motivated this recall.
- `<QUERY>` — derived from the user's prompt; if they passed
  `$ARGUMENTS` to `/kng-recall`, use that verbatim. Otherwise extract
  the topical keywords from the user's question.

### Subagent prompt template

```
You are running a knowledge retrieval task for the KNG plugin. Return
only a focused summary of relevant findings — no preamble, no
restatement of the question.

User's question: <USER_QUESTION>
Retrieval query: <QUERY>

Steps:

1. Resolve project & paths:
   - KNG_HOME = $KNG_HOME env, else $HOME/.kng-plugin
   - Read ${KNG_HOME}/kng.config.json — note db_path and kb_root
   - Determine project_id by priority:
     a. Walk up from CWD looking for `kng.project` marker; if found,
        read its `project` field
     b. Else use $KNG_PROJECT env var
     c. Else use config's active_project
   - If no project resolves, return: "No KNG project linked to this
     directory. Suggest /kng-select <project> or kng-plugin link <project>."

2. Run retrieval (prefer DB mode if db_path exists):

   DB mode:
   python "${CLAUDE_PLUGIN_ROOT}/scripts/retrieve_kb.py" \
     --query "<QUERY>" \
     --db "<db_path>" \
     --project "<project_id>" \
     --top-k 5

   File mode:
   python "${CLAUDE_PLUGIN_ROOT}/scripts/retrieve_kb.py" \
     --query "<QUERY>" \
     --capability-dir "<kb_root>/capability" \
     --project-dir "<kb_root>/projects/<project_id>" \
     --top-k 5

3. Parse JSON. For each hit in capability_hits + project_hits:
   - Read the snippet (up to 2000 chars)
   - Judge: does this entry help answer <USER_QUESTION>?
   - Skip clearly off-topic hits

4. For relevant hits, extract the specific points / sections / facts that
   apply to the question. Quote short passages (<200 chars each) only
   when the exact wording matters.

5. Return a summary under 800 words total:
   - Group findings by KB source (能力库 / 项目库) only if both have hits
   - Lead with what's relevant, not metadata
   - If no hit is genuinely relevant, say so plainly — don't pad
   - If detected_module is non-`general`, mention it briefly

Don't dump raw snippets. Don't summarize all 5 hits when 2 matter.
Don't restate the user's question.
```

## After the subagent returns

Use the summary as background knowledge to answer the user's original
question directly. Don't re-quote the entire summary verbatim —
synthesize it into the answer naturally. The user shouldn't see the
mechanics of the retrieval; they should see an informed answer.

If the subagent reports no relevant hits, answer the question without KB
context (the user's question may be off-domain, or the KB doesn't yet
cover this topic — both are fine, just answer normally).
