---
model: claude-haiku-4-5-20251001
---

Stage all changes, commit with a short generated message, push, then clean up the branch.

## Steps

1. Run `git branch --show-current` and capture the current branch name as `BRANCH`.

2. Run `git add -A` to stage everything.

3. Run `git diff --cached --stat` to get the file names and line-count summary.
   - Do NOT read any file contents — the stat output is sufficient.

4. If the stat output is empty (nothing staged), print "Nothing to commit." and stop.

5. From the stat output alone, write a commit message:
   - Subject line ≤ 72 characters.
   - No body.
   - Imperative mood, lowercase after the first word.
   - Keep inference minimal — describe what changed, not why.

6. Run `git commit -m "<message>"`.

7. Push the branch:
   - Run `git push 2>&1`.
   - If it fails because there is no upstream tracking branch, run `git push --set-upstream origin <BRANCH>` instead.
   - Never force-push.

8. Print one line: the commit subject and the push result (e.g. branch URL or "up to date").

9. If `BRANCH` is not `main` or `master`:
   a. Run `git checkout main`. If that fails, run `git checkout master`.
   b. Run `git branch -d <BRANCH>` to delete the local branch.
   c. Run `git pull` to fast-forward the default branch.
   d. Print: "Switched to main, deleted <BRANCH>, pulled latest."
