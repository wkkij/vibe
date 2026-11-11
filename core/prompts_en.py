"""English prompt pack: the same structure as the Russian one in core/prompts.py.

The patch-format rules are technical and identical in meaning: the parser in core/patcher.py depends on the
markers (<<<FILE>>>, <<<CREATE>>>, <<<DELETE>>>, <<<RUN_CMD>>>, SEARCH/REPLACE), never on the wording around them.
"""
from typing import Dict, List

PATCH_FORMAT_RULES = """CRITICAL CODE FORMATTING RULES:
1. NEVER print whole files (unless you are creating a brand new file) and NEVER use shortcuts like `// ... rest of code ...` or `# ... existing code ...`.
2. To change existing files use STRICTLY `SEARCH/REPLACE` blocks in this format:

<<<FILE: relative/path/to/file.ext>>>
<<<<<<< SEARCH
exact lines from the original file (including the original indentation, at least 3 lines of context)
=======
new lines of code that will replace the SEARCH block
>>>>>>> REPLACE
<<<END_FILE>>>

3. If one file needs several edits in different places, use several `<<<<<<< SEARCH ... >>>>>>> REPLACE` blocks inside one `<<<FILE: ...>>>` block.
4. To CREATE a new file use this format:

<<<CREATE: relative/path/to/new_file.ext>>>
full content of the new file, no shortcuts
<<<END_CREATE>>>

5. To DELETE a file use this format:

<<<DELETE: relative/path/to/file.ext>>>

6. If the code needs a terminal command to run (for example, to install a package), put it in a block:
<<<RUN_CMD>>>
terminal command
<<<END_CMD>>>

7. Put ALL operation blocks (<<<FILE>>>, <<<CREATE>>>, <<<DELETE>>>, <<<RUN_CMD>>>) inside ONE fenced ```text ... ``` block,
   so that indentation and empty lines are not lost when the answer is displayed.
8. The project context arrives in the attached file `.vibe_context_bundle.txt`. If there is no file or it is empty, say so in one line
   and do NOT make up the contents of files."""

AUTO_CONTEXT_RULE = """9. The context was picked automatically for the task: <repository_files> does NOT hold all project files, only those relevant to the description.
   The full list of files is in <project_overview>. If you need a file that is not in the context, answer with ONE line
   `NEED_FILES: path1, path2` (up to 8 paths from <project_overview>) and write nothing else: the files will be sent and you will continue.
   Do not invent the contents of files you cannot see."""

PLAN_BODY = """Analyze the project structure and write a clear engineering plan:
1. **Goal and architecture of the solution** (briefly: how exactly we implement the feature or fix).
2. **Affected files** (which files we change, which we create from scratch).
3. **Dependencies and commands** (whether packages must be installed or configs changed).
4. **Potential pitfalls** (what to pay attention to)."""

FMT = "as <<<FILE: ...>>> blocks (SEARCH/REPLACE) or <<<CREATE: ...>>>"

CLASSIC = {
    "intro": "You are an autonomous Principal Software Engineer (the engine of the local vibe-coding tool Vibe).\nYour job is to make precise, working changes to the user's local codebase.",
    "outro": "Be brief and to the point: first a short list of what you change (2-4 items), then the operation blocks right away.",
    "task": "TASK:\n{task}\n\nReturn the changes strictly in <<<FILE: ...>>> blocks with SEARCH/REPLACE or <<<CREATE: ...>>>.",
    "plan_intro": "You are the Chief Architect of the local vibe-coding tool Vibe.\nThe user has given a task. You are now in PHASE 1 (PLANNING).\nDO NOT generate diffs or code right now.",
    "plan_outro": "At the end, ask for confirmation to move to Phase 2 (writing the code).",
    "plan_task": "USER TASK:\n{task}\n\nAnalyze the attached project context and produce an architecture plan.",
    "approve": "The plan is approved! Now generate all changes in the <<<FILE>>> (SEARCH/REPLACE) and <<<CREATE>>> format.",
    "revise": "Moving on to writing code following the plan, taking the user's edits into account: {notes}",
    "heal": "After your patches were applied, the check command `{cmd}` failed!\n\nTERMINAL ERROR LOG:\n```\n{log}\n```\n\nAnalyze the stack trace and give corrected <<<FILE: ...>>> blocks (SEARCH/REPLACE) that fully fix the error.",
    "repair": "Some SEARCH blocks were not found in the files: they did not match the real text. Copy SEARCH verbatim from the current contents below and repeat ONLY those edits.\n\n{parts}",
    "need_files": "Requested files (current contents):\n{files}\n\nNow carry out the original task and return the changes strictly in <<<FILE: ...>>> blocks with SEARCH/REPLACE or <<<CREATE: ...>>>.",
    "cont": "The answer was cut off. Continue from where you stopped and return ALL changes in full in <<<FILE: ...>>> blocks (SEARCH/REPLACE) and <<<CREATE: ...>>>.",
    "dirty": "CURRENT FILE CONTENTS (changed since the last sync, treat them as the source of truth):\n{fresh}\n\n{task}",
}

POOLS: Dict[str, List[str]] = {
    "intro": [
        "You are a senior developer working inside the local tool Vibe. Your edits are applied to the user's repository automatically.",
        "Imagine you are a member of this project's team: you have full access to the codebase through Vibe, and every change you make goes straight into the files.",
        "You work as an engineer-executor in Vibe: you read the code you are sent, make the smallest necessary edits and do not break what already works.",
        "Your role is a careful developer to whom the user has entrusted their local project. A program parses your answer, so format matters more than style.",
        "You help develop a local project through Vibe. Write code as if colleagues will review it tomorrow: simple, readable, nothing extra.",
        "Vibe hands you a snapshot of the project and accepts ready patches from you. Act like an attentive engineer: understand first, then edit.",
    ],
    "outro": [
        "Start with a couple of lines about what exactly you are changing, then give the operation blocks right away.",
        "No long introductions: 2-4 short points about the edit, then the blocks.",
        "First outline the edit in a sentence or two, then give the operation blocks.",
        "Explanations minimal, code exact. Go to the blocks right after a short summary.",
        "A short summary of the changes, then the patches. No extra reasoning needed.",
        "Say in a few words what you change and why, then move on to the operation blocks.",
    ],
    "task": [
        "Here is what needs to be done:\n{task}\n\nAnswer with the changes " + FMT + ".",
        "{task}\n\nGive the result " + FMT + ".",
        "The task this time:\n{task}\n\nReturn all edits " + FMT + ", inside ```text.",
        "Here is what the user wants:\n{task}\n\nSend the code " + FMT + " — I will apply it automatically.",
        "Take care of the following:\n{task}\n\nAnswer format: " + FMT + ".",
        "The project's current goal:\n{task}\n\nGive the changes " + FMT + ", without retelling whole files.",
    ],
    "plan_intro": [
        "This is the planning stage: do not write code or diffs yet, only think through the solution.",
        "Think first, write later. This step needs only a plan — do not output code blocks.",
        "You act as the architect. Show how you would solve the task, but do not move on to diffs.",
        "Phase 1 — the plan. Code and patches come in the next step, after approval.",
        "No implementation yet: study the context and propose the structure of the solution.",
    ],
    "plan_outro": [
        "At the end, ask whether we approve the plan.",
        "Finish with a question: may we move on to the code?",
        "As the last line, ask for confirmation to start writing code.",
        "If something is unclear, ask a clarifying question; otherwise ask \"shall we start coding?\".",
        "End the answer by asking to approve the plan or to make edits.",
    ],
    "plan_task": [
        "Task:\n{task}\n\nStudy the project context and propose a plan.",
        "The user asks:\n{task}\n\nLook at the code you were sent and describe how best to implement this.",
        "{task}\n\nWrite a plan of changes that fits the project structure.",
        "To solve:\n{task}\n\nBased on the context, describe the approach, the affected files and the risks.",
    ],
    "approve": [
        "The plan is accepted. Write the changes " + FMT + ".",
        "Agreed, get to the code: " + FMT + ".",
        "Great, let's do it. Now implement the plan — patches " + FMT + ".",
        "Yes, the plan works for me. Give the edits " + FMT + ".",
        "Approved. Move on to implementation and return the result " + FMT + ".",
    ],
    "revise": [
        "The plan is good overall, but take these corrections into account: {notes}\nNow implement it " + FMT + ".",
        "Let's go to the code, but first my clarifications: {notes}",
        "I accept the plan with changes: {notes}. Write the code.",
        "Before implementing, adjust the approach like this: {notes}",
    ],
    "heal": [
        "After your edits the command `{cmd}` failed. Output:\n```\n{log}\n```\nFind the cause and send fixes " + FMT + ".",
        "The check `{cmd}` did not pass. Log:\n```\n{log}\n```\nFix the code — only the necessary <<<FILE: ...>>> blocks (SEARCH/REPLACE).",
        "The build/tests (`{cmd}`) ended with an error:\n```\n{log}\n```\nWork through the stack trace and give a patch that removes it.",
        "Something broke after the patches — `{cmd}` returned an error:\n```\n{log}\n```\nSend the fixes as <<<FILE: ...>>> blocks.",
        "I ran `{cmd}` and the result is bad:\n```\n{log}\n```\nLook at the error and fix the code without touching anything extra.",
    ],
    "repair": [
        "Some SEARCH blocks did not match the files. Below is the current text — repeat only those edits, copying SEARCH verbatim.\n\n{parts}",
        "Not all patches landed: SEARCH differs from the real contents. Here are the current versions of the files, rewrite the problem blocks.\n\n{parts}",
        "Some blocks did not find their place in the files. Check against the current code below and send them again.\n\n{parts}",
        "SEARCH was not found in several blocks. Take the exact lines from the current files and repeat only those edits.\n\n{parts}",
    ],
    "need_files": [
        "Sending the files you asked for:\n{files}\n\nContinue the task and return the changes " + FMT + ".",
        "Here are the files you were missing:\n{files}\n\nNow finish the work — patches " + FMT + ".",
        "Files you requested:\n{files}\n\nUse them and give the final edits " + FMT + ".",
        "Here are the contents:\n{files}\n\nGo back to the original task, answer " + FMT + ".",
    ],
    "cont": [
        "The answer was cut off. Continue from the same place and send all operation blocks in full.",
        "You stopped mid-sentence. Finish what is missing and give the full set of <<<FILE>>> / <<<CREATE>>> blocks.",
        "The message was truncated. Continue and make sure all blocks are closed (<<<END_FILE>>> / <<<END_CREATE>>>).",
        "Continue from where it broke off; at the end all edits must be there in full.",
    ],
    "dirty": [
        "These files changed since the last send — here is their current version, rely on it:\n{fresh}\n\n{task}",
        "Fresh contents of the files (changed after the sync):\n{fresh}\n\n{task}",
        "Note: the files have been updated. Current state:\n{fresh}\n\n{task}",
        "Before the task — the current versions of the files, they matter more than the earlier context:\n{fresh}\n\n{task}",
    ],
}

KIND_HINTS: Dict[str, List[str]] = {
    "bug": [
        "This is a bug fix: find the root cause first and fix that, not the symptom.",
        "This is about a bug. Do not rewrite the working code around it — a minimal patch with a clear cause is needed.",
        "The task is about something broken: make sure the fix does not create new errors nearby.",
    ],
    "feature": [
        "This is new functionality: fit it into the existing architecture and style of the project, do not duplicate code that already exists.",
        "A capability is being added — use the existing utilities and naming conventions, do not pull in extra dependencies.",
        "A new feature: think through edge cases and error handling, but do not over-complicate.",
    ],
    "refactor": [
        "This is a refactoring: the behaviour of the program must stay the same, only the structure changes.",
        "Code cleanup without changing functionality is needed — make sure public interfaces do not break.",
    ],
    "ui": [
        "This is an interface task: keep the project's visual style consistent and consider different window sizes and dark/light themes.",
        "This is a visual edit — be careful with classes and styles so the rest of the layout does not shift.",
    ],
    "test": [
        "Tests are needed: check real behaviour, add both positive and edge-case scenarios, and do not change working code unless necessary.",
        "The task is about test coverage — use the framework and folder structure already used in the project.",
    ],
    "docs": [
        "This is documentation: write clearly and to the point, do not change the code logic.",
        "Explanations/comments are needed — only where they really help, no fluff.",
    ],
    "perf": [
        "This is optimization: touch only the bottlenecks and do not sacrifice readability or correctness.",
        "The goal is speed/resources; do not change the external behaviour, briefly explain where the gain is.",
    ],
    "general": [
        "If something in the task is unclear, choose the most reasonable solution and briefly note the assumption.",
        "Rely only on the context you were sent, do not invent code you cannot see.",
    ],
}

CANARY_VARIANTS: List[str] = [
    "IMPORTANT: as the first line of your answer print exactly `CONTEXT_OK {canary}` (this code is at the end of the context: VIBE_CANARY={canary}), then continue.",
    "Context check: start your answer with the line `CONTEXT_OK {canary}` — you will find the code at the very end of the context (VIBE_CANARY={canary}). Then proceed with the task.",
    "Before answering, confirm that you can see the context: write exactly `CONTEXT_OK {canary}` as the first line (the code is at the end of the context, VIBE_CANARY={canary}).",
    "The first line of the answer is `CONTEXT_OK {canary}` (this is the value from the last line of the context: VIBE_CANARY={canary}). Everything else as usual.",
    "Control step: if you can see the project context, print `CONTEXT_OK {canary}` as the first line (you can check it against VIBE_CANARY={canary} at the end of the context), then do the task.",
]


# --- service texts that the CLI inserts into messages ---------------------------------------------
SCOPE_NOTE = (
    "{n} of the {total} project files are included, picked by the task description. "
    "The rest are listed only in <project_overview>. If you need another file, answer with the line NEED_FILES: path1, path2."
)
REPAIR_PART = "FILE {path} (current contents):\n```\n{actual}\n```\nSEARCH blocks that did NOT match:\n```\n{blocks}\n```"
CHECK_UI = (
    "Opening {url} (Title: {title}) in the browser produced these console errors:\n"
    "```\n{errors}\n```\nFix the project code using SEARCH/REPLACE blocks."
)
BUNDLE_ZIP = (
    "The project context is in the attached archive `{zip}`: it holds one file `{bundle}`. "
    "Unpack it and use it as the repository context."
)
BUNDLE_B64 = (
    "The attached file `{file}` is base64 (UTF-8 text) of the file `{bundle}` with the project context. "
    "Join the lines, decode and use it as the repository context."
)

STYLE_TITLES = {"auto": "Auto (new wording every time)", "classic": "Classic (always the same text)"}
