# owner.questionnaire

**What it means:** Questionnaire answers are drafted but not added, so chat and patterns cannot use them.

**Confirm:** `SELECT question_id FROM questionnaire_answers WHERE status = 'draft'`.

**Safe fix:** Tell the owner; adding a section is their click, with the cost shown.

**Never:** Never add a section for the owner, and never print answers or question text.

See [README](README.md) for action classes and the rules every check follows.
