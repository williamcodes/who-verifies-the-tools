# 5. Finding and fixing warped formatters

Our results support a starter checklist, not a complete theory of warped formatting. In the system we studied, four disclosures separated the warped wording from the clear one:

1. State what the tool actually searched, including any limit that left material unexamined.
2. Say when a result list was cut, or report the true total.
3. Mark every derived value as estimated or confirmed.
4. Give every identifier its namespace.

Section 4 measured what these disclosures bought us: +62 to +92 points for the first three, but only +6 for identifiers. It was not a panacea. Identifier namespaces needed enforcement through types or validation rather than clearer formatting alone.

Furthermore, our audits happened to find these four families, but they are not all that exist. New systems will have their own families. In fact, we ran into a warped formatter that didn't fit cleanly into any of our categories while writing the LaTeX for this research paper. Claude Code commented that, rather ironically, a tool it was using stated that it had successfully rendered a page that included bold text, when in fact the tool had truncated logs warning that the font library did not supply a bold face, so the rendering was done, but every bolded phrase came out regular.

Smart agents can sometimes compensate for warping with additional tool calls, but the real solution is to find and fix the warped formatters. And it might not be that difficult, now that we know what we are looking for.

For an anecdotal demonstration that finding them is practical, we wrote and froze a short audit prompt while already knowing the source system's defects, then gave it to the off-the-shelf coding-agent harnesses Codex and Claude Code.^[Both received the pre-fix source tree without version-control history, and the Codex runs had the agent's persistent memory disabled. Claude Code loads user-level instructions that cannot be disabled; we verified that they contain nothing about the system.]

Each harness independently rediscovered both defects that were live at that commit and did not flag the two already-fixed families. Together they reported twelve distinct additional instances of warped formatting outside our catalogue, including a formatter for the `semantic_search` tool that silently returned three of five results the tool retrieved. Adversarial model reviewers, models prompted to refute each finding, confirmed the discrepancies in substance, although two had a detail downgraded.

Thinking that we had something useful, we pointed it at the first two popular open source agentic systems we could think of: OpenClaw and Hermes. Excitingly, it worked on both. On OpenClaw, the prompt found that the `attachments_fetch` tool reports a message outside its bounded recent-history window as not found, and a project maintainer merged our fix before this paper was submitted. On Hermes, it found that the `search_files` tool truncates matched lines at 500 characters without a marker, and the issue and fix remain open upstream at time of writing.

The appendix supplies the verbatim prompt for practitioners to run on any codebase with an ordinary coding agent. The demonstration shows that these defects can be cheap to find. It does not claim that one sweep finds every violation. However, we advise anyone maintaining a production agentic system to consider trying the prompt for themselves.
