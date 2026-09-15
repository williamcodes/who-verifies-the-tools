# Audit prompt (frozen 2026-08-27)

This is the prompt under demonstration. It is frozen as of this date. If it changes
after the first Codex run, the demonstration restarts and this header records the
revision. The prompt was written by the study's authors, who knew the system's
defects; the paper must disclose that in the same breath as any result.

---

Inventory all the tool output formatters in this codebase: every place where a
tool's internal result is turned into the text an agent or model reads. For each
one, one by one, compare what the formatted output tells the model to what the
code actually did. If production logs or traces of real tool calls are available,
pull instances of real formatted output and review them; otherwise, construct
representative calls from the code and its tests and read the output they would
produce.

Look for cases where the formatted output omits or misstates something the code
knows: how much was actually searched or scanned, whether a result list was
truncated or capped, whether a value is computed or estimated rather than read
from a record, where an identifier comes from and what it can be confused with,
or anything else a reasonable reader would take more broadly than the code
licenses. For each finding, cite the file and line of the formatter, quote the
output text, state what the code actually does, and explain what an agent reading
the output would wrongly conclude.

Do not fix anything. Report findings only.
