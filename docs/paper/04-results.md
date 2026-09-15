# 4. Results

The results answer Section 3’s two questions for each defect family: whether clear wording changes what agents claim and what verifiers accept. They also show whether those answers survive the grading, holdout, and construction checks.

## Agent overclaim

Clear wording sharply reduced agent overclaim for scope, completeness, and uncertainty, while identifier provenance changed little (Table \ref{tab:overclaim}). Under the warped wording, agents overclaimed on 62-100% of answers depending on family; the clear wording cut scope, completeness, and uncertainty to 8%, 0%, and 20%, while provenance stayed at 94%. The effects are +62 to +92 percentage points for the three repaired families against +6 for provenance, with 95% cluster bootstrap intervals in Table \ref{tab:overclaim}.

\input{tables}

Agents sometimes repaired an incomplete count themselves, but they also stripped qualifications from estimates. Completeness remained at 62% under A because some answers limited the count to "the search returned 20". Uncertainty retained a 20% overclaim rate under the clear wording through estimate laundering. The tool line labels its guess ("ESTIMATED page 8 of 14 ... proportional estimate, NOT a confirmed page") but the same line also names the matching archive page (149), derived from the same guess; answers hedged the labeled number and stated the archive page as fact (wording in Appendix \ref{app:wordings}).

Provenance was the family the clear wording could not repair. Its cases ask a question the tool output cannot answer: the user wants a scan ID for the scan viewer, and the output contains only a document ID and an archive link. The correct answer is that no scan ID is present. Instead, agents presented the document ID as a scan ID even when the clear wording tagged it as [doc:...], and some presented the archive link's handle instead; just 7/120 clear-condition answers correctly said the output contains no scan ID.

## Verifier acceptance

Clear wording reversed verifier judgments for scope, completeness, and uncertainty. In the fixed-answer measure the answer stays fixed and only the formatter's wording differs, so any verdict change is caused by the wording. Verifiers accepted the false answer 30/30 under the warped wording and 0/30 under the clear wording in each of the three families: 90/90 flips. Provenance again moved little, from 18/30 (60%) to 14/30 (47%).

Verifiers rejected the overclaims only when they had both the missing facts and the correctness question (Table \ref{tab:control}). The control judged 46 warped-wording false answers from the scope and completeness families, using each model's first answer per case, each judged by two cross-vendor verifiers. Changing the question alone did nothing, and the facts alone helped only partly; together they eliminated false acceptance, which indicates that the verifiers lacked information rather than ability.

\input{table2}

The frequency measure showed verifiers accepting most warped-wording overclaim answers in the scope, completeness, and uncertainty families and half in provenance (Table \ref{tab:freq}). These rates do not support a causal comparison because the conditions select different answers and a verifier may reject an answer for another defect.

## Grading reliability, robustness, and cost

The two model graders usually agreed on whether an answer overclaimed. The different-vendor judge and meta-judge agreed on 1,147/1,199 dually graded answers (96%). Human adjudication resolved 53 answers: 52 disagreements and one answer with a single valid grade after the other grader’s output failed validation. Rulings were resolved against the pre-written label sheets. No run from the reported models met the preregistered exclusion rules. Section 3 reports the calibration agreement and identifies its AI and human sources.

The paired pattern held under the preregistered robustness checks. Strict document-level holdout left scope at 105/105 (100%) under A and 9/105 (9%) under B. Restricting the fixed-answer measure to the 32 holdout cases left its result unchanged. The construction checker flagged 40/40 warped texts and produced 0/40 false positives.

Total API spend across all pilots and the full run was $74.44.
