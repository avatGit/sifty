## What does this PR do?

<!-- A sentence or two. Link the issue if there is one. -->

## Safety checklist

Sifty deletes files, so every PR keeps these promises:

- [ ] `pytest` is green, including `tests/test_safety.py`
- [ ] No new direct deletions (`os.remove`, `shutil.rmtree`, `Path.unlink`); everything goes through `safety.trash()`
- [ ] New destructive paths default to dry-run and ask before applying
- [ ] New core functions have a matching test

## Notes for the reviewer

<!-- Anything you're unsure about, trade-offs, or things to look at closely. -->
