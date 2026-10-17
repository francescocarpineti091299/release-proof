# 01 — Specifica Semantica V1.2

Normativa autosufficiente per assessment, evidenze, piano di transizione e verdict. V1.1 è solo riferimento storico.

## 1. Boundary

Valutazione di **CandidateState** e **DeclaredTransitionPlan** separata; aggregazione in **MigrationVerdict**. Nessuna ricerca di piani alternativi. Non certificazione né autorizzazione operativa.

## 2. Lifecycle

`DRAFT → READY → RUNNING → COMPLETED | BLOCKED | INCOMPLETE`

- **BLOCKED**: errore di contratto (input incoerente, I5, derived field contraffatto, scope illegale).
- **INCOMPLETE**: input valido ma evaluation incompleta (invariante/requirement critico applicabile senza result finalizzato).
- **COMPLETED**: verdict presente.

Verdict solo su `COMPLETED`.

## 3. Tre livelli di esito

| Livello | Esempio | Esito |
| --- | --- | --- |
| Contract error | delta non spiegato, path orfano | BLOCKED |
| Knowledge gap | UNKNOWN esplicito post-evaluator | INDETERMINATE / CONDITIONAL |
| Violation | misura bloccante | INCOMPATIBLE |

## 4. EvaluationScope

Ogni `RequirementEvaluationResult` e `InvariantEvaluationResult` è scoped:

- `phase`: `CURRENT | TRANSITION | TARGET`
- `subject_type`: `STATE | TRANSITION_STEP | PLAN`
- `subject_ref`: id stato, step o piano

Coppie ammesse: `CURRENT`/`TARGET` → solo `STATE`; `TRANSITION` → `STATE`, `TRANSITION_STEP`, `PLAN`.

## 5. Precedenza verdict

1. Violazione critical → INCOMPATIBLE  
2. Unknown critical → INDETERMINATE  
3. Open condition ammessa → CONDITIONAL  
4. Altrimenti → COMPATIBLE  

## 6. PlatformModel vs stato

- PlatformModel: identità path/surface, `recovery_modes` supportati.
- Stato: `authorization_path_states[path_id]` con `policy` e `accepted_schemes`.
- Policy ammesse: `CLASSICAL_ONLY`, `PQC_ONLY`, `HYBRID_AND`, `HYBRID_OR`, `UNKNOWN`.

## 7. Recovery (I2)

Profilo: `acceptable_recovery_modes`. Platform: modalità supportate incl. `UNKNOWN`. `NONE` non soddisfa I2.

## 8. I5 — Transition delta accountability

Campi accountable: `components[].configuration`, `authorization_path_states`. Delta non spiegato da action o `DerivedEffect` tipizzato → BLOCKED.

## 9. Evidence groups

`required_evidence_groups[]`: OR dentro gruppo, AND tra gruppi; `min_satisfied` per gruppo.

## 10. Condition

Il client invia solo la definizione della condition. `allowed_by_profile` non è un campo di input: lo schema lo rifiuta. Compare solo in `ConditionEvaluation`, calcolato dal motore a partire da `profile.allowed_operational_preconditions`.

## 11. Explanation

La famiglia si deduce da `evidence_kind`, non da un flag del client. Una conclusione critical senza il percorso della propria famiglia rende il result `INCOMPLETE`.

- Misura: Verdict → Requirement o Invariant → Rule → Evidence → Test → Run → Artifact. Senza Test, Run e Artifact il percorso non è completo.
- Dichiarazione o evidenza statica: Verdict → Requirement o Invariant → Rule → Evidence → Source o Artifact. Il nodo Test non è richiesto.
- Gap: Verdict → Requirement o Invariant → Rule → EvidenceGap → EvidenceRequirement.

Una violazione con `critical_for_verdict: false` resta un finding e non produce `INCOMPATIBLE`.

## 12. Evaluator

Un `evaluator_id` fuori whitelist, o un input target-specific assente, non esegue l'evaluator: lifecycle `INCOMPLETE`, nessun verdict. Un evaluator eseguito che restituisce `UNKNOWN` può produrre `INDETERMINATE`. `NONE` non soddisfa I2.

## 13. Hash

Tre campi, tre significati. Non sono intercambiabili.

- `canonical_hash`: identità calcolata. JCS (RFC 8785) sull'oggetto con solo questo campo top-level omesso, poi SHA-256 dei byte UTF-8, prefisso `sha256:`. Un `content_hash` annidato resta nel canonico. È il digest dell'output `SemanticAssessmentResult`.
- `hash`: pin di versione fornito dall'autore su `Profile`, `PlatformModel`, `TransitionPlan`, `RulesetRef` e ruleset. Il motore non lo ricalcola.
- `content_hash`: digest dei byte dell'artefatto o della sorgente. Resta dentro la canonicalizzazione.

## 14. Catalogo invarianti

I1, I2, I3 e I4 obbligatori stanno in `examples/ruleset_v1_2.json` (`required_invariants`). Il motore valuta quel catalogo. Ometterli dall'assessment non produce `COMPATIBLE`: un invariante applicabile senza input eseguito è `INCOMPLETE`.
