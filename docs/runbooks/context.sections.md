# context.sections

**What it means:** Chat's context is missing a section or carries an error line, so IRIS answers without part of what it should know.

**Confirm:** Build `PersonalAICompanion(user_id, session_id='probe')._get_aggregated_context('…')` locally and read the journal.

**Safe fix:** Fix the section's builder; the error line names which one failed.

**Never:** Do not print the context: it holds the owner's text.

See [README](README.md) for action classes and the rules every check follows.
