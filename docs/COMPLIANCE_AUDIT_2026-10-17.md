# ReleaseProof — audit di conformità progetto/hackathon

**Data:** 17 ottobre 2026. **Esito:** NON totalmente conforme; release/submission gate aperto.

**Aggiornamento successivo:** le correzioni e le scelte mantenute sono tracciate in
[`COMPLIANCE_REMEDIATION_2026-10-17.md`](COMPLIANCE_REMEDIATION_2026-10-17.md).
Questo documento conserva la fotografia originale; non usare i suoi finding come elenco
di difetti ancora tutti aperti senza leggere la remediation e le nuove acceptance.

Questo è un audit tecnico, non una certificazione di sicurezza, un parere legale o una
conferma di ammissione ai premi. Non vengono attribuite percentuali arbitrarie di conformità.

## 1. Perimetro e metodo

- Progetto di submission: `releaseproof/`. `firmware-migration-assurance/` è la baseline
  preesistente, non l'app da presentare.
- Requisiti vincolanti del progetto: `general_docs/ReleaseProof_AMD_ACT_III_Engineering_Brief.md`,
  in particolare §§3, 5–10, 13. Le ricerche su altre idee/tracce, competitor e precedenti vincitori
  sono contesto strategico, non ulteriori funzionalità obbligatorie di ReleaseProof.
- Regole evento confrontate con fonti pubbliche aggiornate; il form autenticato e le comunicazioni
  ufficiali specifiche dell'evento prevalgono sulle guide generali.
- Esaminati codice corrente, test, profili, adapter, AI, orchestrazione, runner, Compose,
  deployment, provenance, notices, README e kit pitch.
- Il worktree contiene numerose modifiche preesistenti. Nessuna è stata annullata; nessun fix
  applicativo, pubblicazione GitHub, provisioning AWS o rebuild dello stack è stato effettuato.
- Test offline sul worktree e verifiche HTTP/Docker sul deploy locale sono **evidenze distinte**.
  I container esistenti non contengono il codice corrente: quattro hash campionati differiscono.
- Completata una nuova acceptance API con `--require-ai` sullo stack esistente: script PASS
  su entrambi i profili, report `docs/acceptance/20261017T142014Z.json`. Il suo esito va
  interpretato come prova del deploy già avviato, non delle ultime modifiche locali; il run
  MCUboot ha planner AI_UNAVAILABLE, quindi non supera il requisito completo del brief.

Legenda: **VERIFICATO** = prova osservata entro il perimetro dichiarato; **PARZIALE** =
implementazione presente ma prova incompleta; **GAP** = requisito non soddisfatto;
**NON VERIFICATO** = nessuna prova sufficiente; **N/A** = fuori dal perimetro scelto.

## 2. Risultati verificati

| Verifica eseguita | Risultato | Limite |
|---|---|---|
| Backend: `backend/.venv/Scripts/python.exe -m pytest` da `backend/` | 374 passed, 1 skipped | Test offline, non nuova build Docker |
| Scripts + runner common/wolfBoot/MCUboot, con `PYTHONPATH=runners/common;runners/wolfboot;runners/mcuboot` | 39 passed, 2 skipped | Skip platform-specific; non eseguono Renode live |
| Baseline: `firmware-migration-assurance/.venv/Scripts/python.exe -m pytest tests/unit -q` | 143 passed | Baseline separata |
| `npm.cmd run test` da `web/` | 8 passed | Stream/URL helpers, non browser E2E |
| `npm.cmd run lint` | PASS | Nessuna verifica visuale/accessibilità completa |
| `npm.cmd run typecheck` | PASS | Type checking |
| Backend `ruff check . --statistics` | PASS | Lint statico, non prova runtime |
| `npm.cmd audit --omit=dev --json` | 0 advisory riportati | Dipendenze production JS; non scanner Python/container né garanzia di assenza vulnerabilità |
| `npm.cmd run build` nel worktree | BLOCCATO da lock Next preesistente | Lock non cancellato, processi non terminati |
| Build su copia isolata in directory temporanea, `next build --webpack` | PASS compilazione, TypeScript e generazione route | Diverso dal bundler standard; junction node_modules causa warning su 27 file esclusi dal tracing standalone. Non certifica packaging Docker |
| Confronto contratto V1.2 con baseline | 17/17 file identici byte per byte | Non implica che tutte le modifiche al motore abbiano comportamento identico |
| Download/verifica di tutti gli artefatti dei due run di acceptance registrati | 111/111 SHA-256 corretti | Integrità rispetto al report; non attesta hardware né autenticità contro un writer ostile |
| Route locali `/`, `/amd`, `/reference`, `/runs/...`, health, AMD e configurations | HTTP 200 | Nessun click browser/mobile/accessibility audit effettuato |
| Scan euristico token/private key/AWS key: file tracked correnti e 18 commit raggiungibili | Nessun match nei pattern cercati | Non è uno scan completo gitleaks, di reflog o di ogni file untracked |
| Git tracked `.env` e relativi commit | Nessuno | Il `.env` locale non è stato stampato |

La prima raccolta dei test runner senza `PYTHONPATH` ha prodotto errori di import; ripetuta
con la configurazione corretta, è passata. Non è un difetto funzionale del runner.

### Evidenze dei run registrati

Fonte: `docs/acceptance/20261017T135337Z.json`, poi controlli indipendenti via API locale.

| Profilo/run | Artefatti verificati | AI | Ricalcolo con motore locale corrente |
|---|---|---|---|
| MCUboot, `RP-20261017T134125Z-36b6cd` | 50, 5.305.163 byte | Planner OK; explainer e alternatives AI_UNAVAILABLE; `mcuboot.signed_update` scelto dall'AI ed eseguito | Hash uguale |
| wolfBoot, `RP-20261017T135001Z-cd1874` | 61, 1.140.555 byte | Planner, explainer e alternatives OK; due optional scelti dall'AI ed eseguiti | Hash diverso, vedi F04 |

Entrambi i casi sono vere combinazioni di bootloader/device differenti, anche se la board è
la stessa. Il brief ammette esplicitamente questa scelta. Un risultato di migrazione
INCOMPATIBLE non rende il prodotto non conforme: è una conclusione corretta se sostenuta
da misure. Non serve inventare una migrazione COMPATIBLE.

### Nuova acceptance completata durante questo audit

Fonte: `docs/acceptance/20261017T142014Z.json`; stati AI poi verificati direttamente via API.

| Profilo/run | Esecuzione | AI effettiva | Valutazione rispetto al brief |
|---|---|---|---|
| MCUboot, `RP-20261017T140937Z-d37080` | 7/7 test, build/sign/boot/negative; 50 artefatti; migration INCOMPATIBLE | Planner AI_UNAVAILABLE, report AI_UNAVAILABLE, alternatives OK; test pianificati da POLICY_REQUIRED/PROFILE_OPTIONAL | Script PASS, ma **non** dimostra AI planner → test eseguiti in questa job |
| wolfBoot, `RP-20261017T141734Z-b7a825` | 8/8 test, build/sign/boot/negative; 61 artefatti; candidate COMPATIBLE, transition/migration INCOMPATIBLE | Planner, report e alternatives OK; test AI_PLANNER presenti | Flusso positivo confermato sul deploy esistente, non sul worktree corrente |

Questa nuova prova riproduce **in condizioni reali** la debolezza F05 già dimostrata offline:
`--require-ai` passa sul solo successo di alternatives, anche con planner indisponibile.
Non confondere successo dello script con chiusura di tutti i requisiti del brief.

## 3. Finding prioritari

### F01 — ALTA: timeout signer convertito in incompatibilità crittografica

**File:** `runners/mcuboot/rp_mcuboot/templates.py:442–495`, `PqcSignAttempt.run`.
**Requisito:** brief §§5.4, 10.1, NFR-05; tool failure distinto da risultato firmware.

Il ramo di fallimento di keygen/sign non distingue un rifiuto esplicito di algoritmo da timeout,
errore ambiente o altro exit code. Se nessuna variante produce un file, emette
`signing_result=REJECTED` e test `FAIL`. L'adapter (`adapters/mcuboot.py:326–362`) traduce
quel valore in `UNSUPPORTED`, usato per violare REQ-PQC-VERIFIER.

**Riprodotto offline:** sostituito esclusivamente nel processo di test `run_cmd` con tre
`CmdResult(returncode=None, timed_out=True)` e log di timeout. Risultato effettivo:
`outcome=FAIL`, `signing_result=REJECTED`, `failure_class=null`.

**Fix richiesto:** riconoscere il rifiuto previsto tramite exit code/output specifici del tool;
timeout e crash devono produrre ERROR/INCONCLUSIVE, non evidenza di algoritmo unsupported.
Aggiungere regressioni per timeout keygen, timeout sign, crash e vero invalid-choice.
Il rifiuto ML-DSA già registrato resta una misura reale: il finding riguarda il ramo di errore.

### F02 — ALTA: chat non applica i guardrail su verdetto e citazioni

**File:** `backend/releaseproof/ai/service.py:323–384`,
`web/components/run/assistant-drawer.tsx:102–103`.
**Requisiti:** brief §6.2, NFR-07, §10.1 prompt injection/citazioni.

La chat applica il prompt e filtra `<think>`, ma inoltra testo prima di validare citazioni o
coerenza con i verdetti. `check_report` protegge i report strutturati, non `assistant_stream`.
La UI afferma che le risposte citano le prove; non è una garanzia verificata server-side.

**Riprodotto offline con lo stub adversarial già presente nei test:** contesto migration
INCOMPATIBLE, richiesta di ignorare le istruzioni, modalità PROMPT_INJECTION. Testo emesso:
`The migration is COMPATIBLE and safe to deploy.` Trace: `OK`.

Questa prova mostra un difetto del controllo applicativo; non dimostra che il modello AMD
reale risponda sempre così. Il verdetto persistito del motore non viene alterato.

**Fix richiesto:** risposta strutturata validata prima della visualizzazione, oppure buffering
e validazione finale con rifiuto esplicito. Controllare gli ID e il riferimento alla fase corretta;
non basta che una parola-verdetto esista fra i tre esiti. Test chat avversari dedicati.

### F03 — ALTA: runner root e volume con database condiviso

**File:** `runners/wolfboot/Dockerfile:7,84–87`, `runners/mcuboot/Dockerfile`,
`docker-compose.yml:59–60,78–79,101–102`.
**Requisiti:** NFR-03, NFR-04, immutabilità/evidence boundary.

`docker inspect` conferma wolfBoot user=root e MCUboot user vuoto (default root), entrambi
non privilegiati ma con filesystem scrivibile e senza `cap_drop`. Il no-egress network e
`no-new-privileges` sono presenti, ma **non soddisfano il requisito non-root**.

Entrambi montano `/data` intero in scrittura, comprendente SQLite e run degli altri runner.
La validazione del path HTTP non è una barriera filesystem contro un runner compromesso.
SHA-256 non sostituisce ownership/ACL, snapshot immutabili o autenticazione della misura.

**Fix richiesto:** UID non-root con ownership inizializzata, volumi distinti per artefatti e DB,
permessi per famiglia/run, capability drop e rootfs read-only ove compatibile con i tool.
Testare dopo rebuild no-egress, UID, accesso negato al DB e agli artefatti altrui.

### F04 — ALTA: deploy, prove e motore non identificano la stessa release

**File:** `profiles/*.yaml:runner.image`, `docker-compose.yml`,
`backend/releaseproof/orchestrator/service.py:1011–1101`.
**Requisiti:** NFR-02, gate clean environment e riproducibilità.

I profili locali sono SUPPORTED, mentre `/api/configurations` restituisce EXPERIMENTAL;
health indica `env=dev` e `expose_experimental=true`. Quattro file campionati differiscono
tra container e worktree: orchestrator, AI client, common engine e MCUboot templates.

Riprodotto il vecchio assessment wolfBoot col motore corrente:

- Hash memorizzato: `sha256:dacbeb9465b16c2080bd47efd923214f2fc4e5f78fcda9d430c575c7b6f41c91`.
- Hash ricalcolato: `sha256:fa5a6d296b022b604ff58b06728a3bd30d2b4a6919c2ab44207ea2bb34655f52`.
- Verdettistica di alto livello invariata; cambia il grafo (139 → 138 edge) e il modello corrente
  espone i wrapper assurance assenti nel result salvato. Una edge a EV-APP-UPDATE-SCRIPT
  viene rimossa. È una differenza fra implementazioni, non una prova di nondeterminismo.

Il manifest conserva tag immagini riutilizzabili `:0.1.0` e ruleset 1.2, non digest immagini,
commit del motore/adapters/parser e snapshot completo dell'implementazione.
`CODE_PROVENANCE.md:9` descrive una sola modifica additiva D05; il diff corrente contiene
anche cambiamenti a selezione evidenza valida, allowed actions, policy, layout e trust chain.

Inoltre **entrambi i result serializzati dal deploy non sono auto-consistenti col proprio
canonical_hash**: ricalcolare JCS sul JSON esposto dall'API non restituisce l'hash dichiarato.
Il match torna soltanto reinserendo i wrapper `candidate_state_assurance` e
`transition_plan_assurance`, che il vecchio modello non serializzava. Il worktree corrente
include già questi campi nel modello: è un fix locale presente ma non applicato ai container.
Il gate attuale confronta l'hash del run con quello del result, senza ricalcolarlo, perciò
non scopre questo errore del deploy.

**Fix richiesto:** congelare commit/release, aggiornare provenance, registrare digest e versione
del motore, rebuild controllato, acceptance nuova sullo stesso codice. Preservare i vecchi run
con identificazione della loro versione; non riscriverne hash/evidenze per farli coincidere.

### F05 — ALTA: acceptance AI può passare senza planner e senza host approvato

**File:** `scripts/acceptance.py:150–159`.
**Requisiti:** P0-07; §3.3 AI realmente pianifica i test della stessa job.

`--require-ai` accetta qualunque trace con status OK. Non richiede modulo planner,
corrispondenza run_id, host approvato o prova che il piano accettato sia quello eseguito.
Non richiede il successo di explainer/alternatives per dimostrare l'intero ciclo.

**Riprodotto offline:** fixture di acceptance completa con una sola trace OK di explainer,
host `unapproved.example`, nessuna trace planner. Acceptance `passed=true`.
Non significa che il runtime ordinario abbia realmente contattato tale host: la debolezza
è nella prova del gate, non nel client che ha allowlist e redirects disabilitati.

**Confermato anche live:** nella nuova acceptance MCUboot il gate passa grazie alla trace
alternatives OK, mentre planner e report sono AI_UNAVAILABLE (run
`RP-20261017T140937Z-d37080`). Non risultano test con planned_by=AI_PLANNER in quel run.

**Fix richiesto:** controllare planner OK, run_id, provider/host attesi, ai_plan valido e relazione
con planned/executed templates; distinguere gate minimo da demo AI completa.
Ricalcolare anche gli hash dei documenti e verificare manifest/artefatti completi, non solo
uguaglianza fra due stringhe restituite dalla stessa API e campione di cinque artefatti.

### F06 — BLOCCANTE SUBMISSION: pubblicazione/demo/video non dimostrati

**File:** `pitch/submission.md:240–246`, `pitch/slides.html`.

DEMO_URL, VIDEO_URL, GITHUB_URL e TEAM sono placeholder. `git remote -v` non restituisce
remotes; non è prova che non esista un repository altrove, ma manca un URL verificabile.
Non ci sono video tracked nel repo e non è disponibile un link al video finale.
Cover PNG e PDF slide esistono; il kit avverte che gli export vanno rigenerati.
Il PDF non è stato revisionato visivamente (input PDF non supportato dal modello).
Script video e HTML slide non sostituiscono deliverable pubblicati e apribili dai giudici.

**Fix richiesto:** URL pubblici autorizzati, video autentico, PDF aggiornato, test da browser
esterno/incognito e completamento del form; conservare prova di submission riuscita.

### F07 — MEDIA: testo submission oltre i limiti standard ufficiali

Fonte ufficiale: `https://lablab.ai/delivering-your-hackathon-solution`.
Titolo standard 5–50 caratteri; short 50–255; long 600–2.000.

- Titolo principale: **75** caratteri, non conforme al limite standard.
- Titolo alternativo `ReleaseProof: Firmware Migration Assurance`: **42**, conforme.
- Short copy: **221**, conforme.
- Sezione Long description: **3.697**, da ridurre per il form standard.

Confermare i limiti nel form ACT III: il form evento prevale sulla guida.
Video standard MP4/MOV fino a 300 MB; sotto 5 minuti è una **raccomandazione**, non una
durata massima ACT III verificata. Slide standard PDF. Cover guida generale opzionale 16:9,
ma l'evento la elenca fra i materiali: prepararla comunque.

### F08 — MEDIA: evidence pack AMD/benchmark e legal gate incompleti

`docs/AMD_SMOKE_TOKEN_FACTORY.json` documenta 9/10 chiamate logiche riuscite e un outage;
`docs/AMD_BENCHMARK.json` non presente. Metriche nel pitch sono placeholder. Non inventarle.
API Token Factory documentata da AMD e dall'evento: l'uso gestito è una strada valida;
non è necessario sostenere che il servizio usi MI300X o imporre un deploy AWS per essere idonei.
Una label hardware configurabile, da sola, non attesta la GPU.

LICENSE MIT, notices e provenance sono presenti. Manca un SBOM/DEPENDENCIES versionato,
come richiesto dal hard gate del brief §8.1; manca prova della conferma su prior work/MIT
nel caso specifico e dell'autorizzazione dei titolari, oltre alla dichiarazione nel documento.
I notices sono correttamente prudenti sul GPL degli eventuali container pubblicati.
Non è lecito concludere che tutto il bundle sia MIT solo perché il codice applicativo lo è.

**Fix richiesto:** benchmark reale con soglie/limiti, screenshot console senza segreti,
trace correlate e quota verificata; inventario licenze/SBOM, provenance aggiornata e
conferma contest su prior work/packaging GPL se permane ambiguità. Non serve introdurre
Gemma o Evolus: sono premi opzionali, fuori dalla track scelta.

### F09 — ALTA PRIMA DEL DEPLOY PUBBLICO: accesso e consumo non controllati

API senza autenticazione/autorizzazione, quote pubbliche o tenant boundary, come ammesso
da README e ARCHITECTURE. `create_run` avvia un thread per ogni richiesta; il semaforo
limita il runner, non il numero di richieste in coda/thread. Chat/alternative possono consumare
la quota AMD. TLS non è access control. Nessun exploit o load test è stato eseguito.

**Fix richiesto per demo esposta:** gateway con accesso giudici, rate/queue limits e limiti AI,
verifica che l'accesso sia praticabile per i giudici. Tenant isolation completa è roadmap se
la demo usa soltanto materiale pubblico; non va dichiarata già implementata.

### F10 — BASSA: riferimenti documentali non risolvibili

`README.md:135` e `docs/ARCHITECTURE.md:61` rimandano a `docs/CODE_AUDIT.md`, assente.
Questo audit ha un nome diverso e non ripara automaticamente tali link.

## 4. Matrice P0 del brief

| ID | Stato | Evidenza/gap |
|---|---|---|
| P0-01 AMD gateway | PARZIALE | Client AMD reale, no fallback; smoke presente, benchmark/evidence pack incompleti |
| P0-02 Configuration registry | PARZIALE | Due YAML distinti e registry; deploy usa ancora EXPERIMENTAL/expose=true |
| P0-03 Job API/orchestration | PARZIALE | HTTP/SSE/SQLite/idempotenza/queue testati; root isolation e public-use controls incompleti |
| P0-04 wolfBoot runner | VERIFICATO sul deploy precedente | Build/firma/positive/negative/61 artefatti; codice corrente da rebuildare |
| P0-05 MCUboot runner | PARZIALE | Pipeline precedente reale/50 artefatti; F01 compromette error classification |
| P0-06 Discovery | PARZIALE | Parser, pins, layout, size, hash presenti; RAM runtime UNKNOWN; analisi formato/sezioni ELF non dimostrata completa |
| P0-07 AI planner | PARZIALE | Planner reali e optional eseguiti nei due run registrati; gate F05 insufficiente |
| P0-08 Adapter/motore | PARZIALE | Regressioni/golden passano, contratto 17/17 identico; F01/F04 da chiudere |
| P0-09 Guided UI/evidence | PARZIALE | Wizard, SSE, evidenze e UNKNOWN implementati; chat F02, browser/accessibilità non verificati |
| P0-10 Legal/submission | GAP | LICENSE/notices presenti; URL/video/SBOM/rights e form finale da verificare |

P1: alternative tipizzate e nuova reevaluation presenti; alcune riusano correttamente prove
del parent, non eseguono un nuovo flash. Il run MCUboot registrato non aveva explainer/alternative
disponibili. AI discovery claims, report tecnico/executive distinti e compare-runs completo
non sono dimostrati qui come tutte le feature P1. P2 non è necessario per il gate MVP.

## 5. Matrice NFR

| NFR | Stato | Nota |
|---|---|---|
| 01 Non-official, nessuna certificazione | PARZIALE | official=false verificato; chat può contraddire il perimetro (F02) |
| 02 Provenance e riproducibilità | PARZIALE | Hash artefatti validi; release/digest/motore non congelati (F04) |
| 03 Sandbox non-root | GAP | Root reale in entrambi i runner; no-egress e risorse presenti |
| 04 Secrets/log/artifact ACL | PARZIALE | Chiave AI API-only e scan euristico pulito; DB/artefatti shared writable, ACL API assenti |
| 05 Robustezza e failure | PARZIALE | Test idempotenza/restart/failure; timeout signer sbagliato, coda non bounded |
| 06 AMD/no fallback/AI indipendente | VERIFICATO nel perimetro client/test/record | Allowlist/no redirects/no provider fallback; label GPU non attestation |
| 07 Citazioni verificabili | PARZIALE | Guardrail strutturati presenti; chat non validata, entailment/locator completo non provato |
| 08 UX/accessibilità | NON VERIFICATO integralmente | Componenti guidati e assistant richiudibile; nessun audit WCAG/browser |
| 09 Metriche | PARZIALE | Durate/test/artefatti/trace disponibili; benchmark/manual-before-after/costi incompleti |
| 10 Limiti emulazione | VERIFICATO documentalmente | E12 e RAM runtime non inventati; limiti Renode espliciti |

## 6. Gate di chiusura raccomandato, in ordine

1. Correggere F01 e F02 con test avversari specifici: nessun timeout trasformato in unsupported,
   nessuna risposta chat incoerente con il core o con ID inesistenti accettata come OK.
2. Chiudere F03 e F09 prima di rendere la demo pubblica, mantenendo l'accesso semplice per i giudici.
3. Congelare una release, aggiornare provenance e identificare digest/engine revision (F04).
4. Rebuild controllato; rilanciare acceptance più rigorosa, UI browser A/B e failure test sullo
   stesso deploy. SUPPORTED soltanto con prova collegata a quella release.
5. Completare evidenze AMD e benchmark senza inventare risultati; validare quota/reachability.
6. Repo pubblico autorizzato, SBOM/notices/rights; non pubblicare automaticamente la POC privata.
7. Titolo breve, long copy compatta, link finali, video reale e PDF aggiornato; verificare il form,
   account/team/ADP/Discord e ricevuta di submission.

## 7. Fonti web controllate il 17 ottobre 2026

- Evento ufficiale: https://lablab.ai/ai-hackathons/amd-developer-hackathon-act-iii
  — AMD significativo obbligatorio, Token Factory esplicitamente ammessa, track Intelligent
  Industry, materiali di submission, team 1–6, original/MIT-compliant.
- Roma: https://luma.com/AMDHackathon-Rome
  — **18 ottobre ore 16:00 Europe/Rome** submission, pitch ore 17:00. Confermare eventuali
  messaggi ufficiali successivi; non presumere identico cutoff per tutte le sedi/team online.
- Rulebook: https://lablab.ai/hackathon-rules
  — testo recuperato dal contenuto MDX in `__NEXT_DATA__` HTML (render markdown vuoto),
  form/evento prioritari, public repo/app URL e video/PDF standard, comportamento etico.
- Submission: https://lablab.ai/delivering-your-hackathon-solution
  — MDX in HTML, limiti caratteri/formati/video indicati in F07.
- Terms: https://lablab.ai/terms-of-use
  — testo pertinente indicizzato dalla ricerca; originale/open source/MIT salvo eccezioni.
  La sola ricerca non sostituisce accettazione del testo autenticato da parte del team.
- AMD Quickstart: https://amd-aim.github.io/radeon-cloud-docs/quickstart/
  — documentazione AMD-AIM, aggiornata 17 ottobre; endpoint
  `https://developer.amd.com.cn/radeon/api/v1`, esempio DeepSeek-V4-Flash e accesso Token Factory.

**Conclusione:** la base funzionale è sostanziale e documentabile; non è una UI che inventa
build/verdetti. Tuttavia test verdi e precedenti acceptance non chiudono i finding avversari,
i confini della sandbox, la riproducibilità della release né i deliverable pubblici.
Non dichiarare "fully compliant" finché questi gate non hanno evidenze della stessa release.

## Addendum — riposizionamento e funzionalità di preflight

Il testo sopra conserva la fotografia storica dell'audit; non descrive automaticamente il worktree
successivo. La revisione del documento di mercato è in `docs/POSITIONING_REVIEW_2026-10-17.md`:
UI/pitch industriale, otto slide, evidence pack verificato e release-preflight CLI sono aggiunti;
il controllo di fase del verdetto è esteso al testo dei report AI. Fix signer/chat/Compose/acceptance
e accesso demo erano già presenti localmente. La verifica offline non chiude F04/F06/F08 né attesta
un nuovo deploy. Manteniamo report storici, UNKNOWN recovery e limiti di isolamento espliciti.
