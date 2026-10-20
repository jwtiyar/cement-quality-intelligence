# Assistant evaluation scenarios for plant review

These are the 16 scenario combinations retained after review. The draft questions below turn them into repeatable checks. No private laboratory values belong in this file.

The three dimensions target observed risks in this app:

- **Task** names what the user wants: plant data, strength guidance, raw-mix advice, or a technical reference.
- **Evidence** describes what the assistant receives: one clear source, several sources, missing evidence, or a possible conflict.
- **Scope** identifies the cement type or time period that can change the answer.

| # | Task | Evidence | Scope and review intent |
| --- | --- | --- | --- |
| 1 | Plant data | Recent result present | Latest OPC 2-day and 28-day status. |
| 2 | Plant data | Result missing | Older SRC sample without a recorded 28-day result. |
| 3 | Plant data | Several records | SBC 28-day monthly comparison across two months. |
| 4 | Plant data | Several records | OPC highest and lowest 28-day result in a named period. |
| 5 | Plant data | Freshness uncertain | Latest record date versus last successful refresh. |
| 6 | Strength guidance | Two estimates disagree | OPC model estimate versus recent average. |
| 7 | Strength guidance | Weak validation | Explain low model R² without calling the estimate a lab result. |
| 8 | Strength guidance | Input missing | Missing 2-day strength for SRC. |
| 9 | Strength guidance | Insufficient evidence | SBC type with too few valid validation folds. |
| 10 | Raw-mix advice | One clear source | Lime saturation factor definition in the FLS raw-mix course. |
| 11 | Raw-mix advice | Several related facts | Explain silica and alumina modulus together. |
| 12 | Raw-mix advice | Calculation plus chemistry | High LSF result and a chemically consistent adjustment. |
| 13 | Raw-mix advice | Several sources | Role of HFO sulfur in the clinker calculation. |
| 14 | Raw-mix advice | Infeasible result | Solver cannot meet the requested targets with the given materials. |
| 15 | Technical reference | Source absent | User asks for a rule or limit not present in the indexed documents. |
| 16 | Technical reference | Sources may conflict | Two standards or editions appear to give different requirements. |

## Draft questions

1. What are the latest OPC 2-day and 28-day strength results? If the 28-day result is missing, say whether it is still curing or unrecorded.
2. The SRC sample dated 2026-07-18 has no recorded 28-day strength. Is that still curing, or is the result missing?
3. Compare the average SBC 28-day strength in July and August 2026. Give both averages, sample counts, and the difference in MPa.
4. Which OPC samples had the highest and lowest recorded 28-day strength in July 2026? Give the dates and values.
5. What is the latest sample date in the laboratory data, and when did the last successful data refresh happen? If one date is unavailable, say so.
6. I have an OPC model estimate and a different recent-average estimate in the Strength Estimate tab. Which should I rely on, and what do the validation results say? (Send the tab's actual prediction context with this question.)
7. The model's validation R² is low. Does that mean this strength estimate is a measured 28-day laboratory result? Explain what it does and does not mean.
8. If an SRC sample has no 2-day strength result, can the model still make a valid 28-day estimate? Explain the limitation without inventing an input value.
9. If SBC has too few valid time-series validation folds, how should the Strength Estimate tab describe the model evidence and the recent-average estimate?
10. How does the FLS raw-mix course define lime saturation factor (LSF), and what oxides appear in its formula? Cite the source.
11. What do silica modulus and alumina modulus mean, and how are they calculated? Cite the relevant raw-mix reference.
12. A solved raw mix has an LSF above its target. Which direction should the raw materials be adjusted, and why? State what information you need before giving feeder settings.
13. In this raw-mix solver, how does HFO sulfur affect the clinker calculation? Distinguish the calculation from general kiln chemistry.
14. The solver says the requested LSF, SM, and AM cannot all be met with the available materials. What should the operator check or change before using any feeder settings?
15. What is our plant's approved upper limit for OPC 28-day strength? If the indexed documents do not contain a plant-specific limit, say so instead of guessing.
16. Two available cement standards appear to set different requirements. How should I decide which applies to this product and test? Identify the edition and scope needed before choosing a limit.

For each run, keep the query, exact input context, retrieved chunks, provider answer, and source list. Review full traces before defining failure labels. Do not use an LLM judge until a plant expert labels both passing and failing answers and a held-out set validates the judge.

## Local preflight (2026-09-23)

This is a context-availability check, not a score for answer quality. The app injects a live dataset summary separately from the five retrieved reference chunks.

- Questions 1–9 primarily need live plant or model context; reference-document top-five results are not the correct evidence measure for them.
- Question 2's older dated SRC row is in the dataset but outside the live summary's 60 most recent rows. Question 4 asks for the dates of July's extrema, while the live summary supplies monthly minimum and maximum values without their dates. These answers are not fully grounded by the current prompt.
- Question 3 has both months in the live summary, but it reports total records rather than the number with recorded 28-day strength. The question needs counts of recorded results.
- Question 5 has the latest sample date in the live summary, but the last successful refresh timestamp is not injected into chat context.
- For question 10, the first `fl-smith-calculation-of-raw-mix.txt` chunk ranks 7th in TF-IDF retrieval, outside the app's top five. For questions 11, 12, and 13 it ranks 8th, 2nd, and 4th respectively. These ranks do not alone prove an answer is wrong; other relevant references may be present.

## Codex run and fixes (2026-09-24)

The user approved sending the plant summary and up to five retrieved passages to the signed-in Codex account. All 16 questions returned HTTP 200 from the app using `gpt-5.6-luna (medium)`. The first run exposed three answer errors and several context limits:

The initial app-path run also invoked its configured TypeSafe reranker, which sends the query and retrieved candidate passages to TypeSafe. The targeted reruns set `TYPESAFE_API_KEY` empty so only Codex received the test context. This distinction matters when repeating privacy-sensitive evaluations.

- Question 3 used total sample rows as the count of recorded 28-day tests. Question 9 also used a total-row count in an unasked example. The monthly summary now states recorded-test counts separately; the affected Codex answers were rerun with the correct counts.
- Question 4 could not give extrema dates because they were missing from the prompt. The monthly summary now includes the high and low sample dates; the rerun supplied the right dates.
- Question 10 substituted a different LSF formula for the named FLS course. Question 13 guessed about the solver's HFO sulfur treatment. The app now supplies the verified FLS formula and its own solver calculation rules; both reruns matched those facts.
- Question 1 initially blurred the latest sample and the latest recorded test. The summary now provides the latest recorded 2-day and 28-day result for each cement type. The final Codex rerun distinguished both from the newest sample.

Question 2 still relies on the user's statement that an older row lacks a result; arbitrary historical row lookup is not available in chat context. Question 5 correctly said the last successful refresh time was unavailable. The reference panel now says "Retrieved references" because the listed passages are matches, not verified citations. This run is a manual sample, not a measured accuracy rate or plant-expert acceptance test.
