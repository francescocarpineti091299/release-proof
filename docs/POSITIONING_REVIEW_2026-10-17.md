# ReleaseProof — valutazione critica e implementazione del riposizionamento

Documento valutato: `general_docs/ReleaseProof_Riposizionamento_Mercato_Pitch_2026-10-17.md`.
Il documento originale e i report storici non sono stati riscritti. La PoC nel repository
`firmware-migration-assurance` non è stata modificata da questo intervento.

## Decisione tecnica/commerciale

**Accolto:** Intelligent Industry, industrial IoT / OEM di sensori wireless di condition monitoring,
buyer embedded engineering/firmware/product security. Il vantaggio dimostrabile è separare la
validità del candidato dalla raggiungibilità tramite il bootloader installato. PQC è il primo
cambio supportato, non una promessa di verifica universale degli aggiornamenti.

Il riposizionamento è utile perché collega una misura reale al problema di manutenzione del
prodotto. Non dimostra però domanda pagante, customer fit o difendibilità commerciale:
la condivisione del SoC con NI/Lynxemi/Atomation non equivale a supportarne firmware e policy;
l'emulazione non copre gli stati reali di ogni dispositivo; i profili commerciali richiedono
onboarding e acceptance propri. Non aggiungere quei marchi al registry come configurazioni supportate.

**Corretto:** CRA è contesto per aggiornamenti/evidenze, non mandato generale ML-DSA; CNSA 2.0
ha perimetro US NSS; NIST IR 8547 è draft. La competizione non va ridotta a una matrice di feature
assenti: Finite State documenta già AI evidence-linked e policy gates; Binarly anche reachability/CI.
La pagina Finite State è stata consultata durante la revisione; la fonte Nordic ha restituito HTTP
403 al fetch automatico. I riferimenti hardware restano quelli citati dal documento, non nuove
prove di interoperabilità o test dei prodotti commerciali.

**Non assunto come fatto:** TAM aggregato, prezzi, clienti, ROI, incidenza di fallimenti,
GPU gestita, cloud deploy. €62.500 = 5.000 × 5% × €250 è solo esposizione ipotetica, non risparmio.

## Cosa è stato implementato

| Proposta utile | Implementazione e confine |
|---|---|
| Categoria/buyer più precisi | Homepage, metadata, README, cover, submission, copioni e deck coerenti sul preflight industriale |
| Contrasto candidate/transition | Decision panel: “Works in the lab ≠ can migrate in the field”; niente autorizzazione dal solo candidato verde |
| Pitch essenziale e rigoroso | 8 slide, caso industriale documentato, metrica tecnica storica identificata, unico scenario economico ipotetico, confronto competitivo per focus |
| Evidence pack | API `GET /api/assessments/{id}/evidence-pack`, pulsante ZIP in UI; manifest originale, dossier, assessment/result, AI traces e artefatti verificati durante la copia |
| Release gate reale | CLI e workflow GitHub Actions manuale per run esplicito: verifica byte/hash/binding, engine replay, identità configuration/change/plan, LIVE, SUPPORTED, tre verdetti COMPATIBLE, copertura e assenza di critical UNKNOWN/condizioni |
| Fiducia AI | Report prose ora controllata per fase: candidato COMPATIBLE non può diventare migrazione COMPATIBLE solo perché il verdetto esiste in un'altra fase. Regressione su phase-swap, lowercase e Markdown |
| Verifiche avversarie | ZIP corrotto, indice ricalcolato ma manifest incoerente, path traversal, limiti, fallimento runner, prove parent riusate, errori/unknown e nessuna sovrascrittura del report precedente |

Il workflow CI è implementato e testato offline; non è stato eseguito su GitHub e non prova un
deployment pubblico. Opera su un assessment già completato e **non** controlla ogni immagine
commerciale di una pipeline OEM. Non avvia OTA, non usa l'AI per decidere e non cambia l'engine.
I due profili attuali devono correttamente bloccare il preflight; nessun “green” artificiale.

## Fix preesistenti preservati, non attribuiti a questa revisione

Nel worktree erano già presenti la classificazione signer timeout/crash distinta da rifiuto
algoritmo, chat buffered/citation-checked, UID non-root e mount limitato a `runs/`, identity hash
del codice, acceptance AI più rigorosa, gateway autenticato, limiti POST/job e dependency inventory.
Non sono stati annullati né reimplementati. I test correnti verificano il codice; non attestano
che i container già avviati contengano tali fix. Il volume artefatti resta condiviso fra runner:
non è isolamento ostile per tenant/famiglia. Le citazioni provano esistenza degli ID, non entailment.

## Roadmap deliberatamente non simulata

1. Test hardware-in-the-loop e interrupted update: occorrono hardware, controllo alimentazione,
   protocolli di acquisizione e adapter. I4 rimane UNKNOWN fino a osservazione valida.
2. STM32/NXP e fork commerciali: non basta aggiungere YAML o riusare nRF52840.
3. Import fleet/varianti: servono stato bootloader affidabile e copertura di ogni variante.
4. OTA/SBOM/CBOM integrations: complementi futuri, non client fittizi o feature dichiarate.
5. Pilot economico: misurare blocker, ore risparmiate, visite confermate evitate, costo/profile/run;
   nessuna cifra osservata è stata fabbricata.

## Gate esterni ancora aperti

Rebuild controllato e nuova acceptance strict della stessa release, inference AMD live/benchmark,
deploy pubblico e test browser esterno, video autentico/link/team, diritti/prior work/licenze e
submission richiedono prove operative. Nessun provisioning, pubblicazione, reset Git, modifica
di `.env`, paid inference o restart di stack è stato effettuato da questo intervento.
Vedere `docs/HACKATHON_READINESS.md` e `docs/RELEASE_GATE.md` per comandi e confini.

## Export e verifica della presentazione

`node scripts/export_pitch.mjs` usa Chromium installato (oppure `RELEASEPROOF_BROWSER`), rigenera
`pitch/slides.pdf` e `pitch/cover.png`, verifica otto slide senza placeholder/overflow o invasione
del footer e registra gli hash HTML/PDF/PNG in `pitch/export-manifest.json`. Produce anteprime nella
directory temporanea approvata, senza cambiare gli screenshot storici. Gli export correnti sono
stati rigenerati e le otto anteprime/cover controllate visivamente; i test rilevano export non
allineati ai sorgenti e descrizioni oltre i limiti standard del form.

## Verifiche effettuate su questa revisione

| Verifica | Esito e limite |
|---|---|
| Backend pytest completo | 416 passed, 1 skipped (Windows symlink); test offline |
| Scripts + runner, con PYTHONPATH configurato | 77 passed, 2 skipped platform-specific; nessuna emulazione live o AWS |
| Regressioni pack/gate e AI dopo gli ultimi controlli di binding | 117 passed; trasporti/fixture esclusivamente di test |
| Backend e nuovi script Ruff; git diff --check | PASS |
| Frontend lint / typecheck / test | PASS; 8 test frontend |
| Frontend production build (Turbopack) | PASS |
| Standalone HTTP smoke | 6 pagine HTTP 200; verifica copy industriale, nessun assessment avviato |
| Pitch export e anteprime | 8 slide, zero placeholder visibili/overflow; PDF/PNG con hash registrati; controllo visuale completo |

Questi risultati non attestano autenticazione esterna dei giudici, hardware reale, un workflow
GitHub eseguito, benchmark live o acceptance dei container correnti. Le modifiche locali
preesistenti sono incluse nel codice testato, non attribuite a questa implementazione.
