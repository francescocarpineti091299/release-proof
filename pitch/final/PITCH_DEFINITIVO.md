# ReleaseProof: pitch definitivo

**Contesto:** AMD Developer Hackathon ACT III, track Intelligent Industry. Pitch della **soluzione/demo** davanti a una giuria, non un pitch per investitori.
**Durata target:** 4:15 (sotto i 5 minuti, con 45 s di margine). Va confermata con l'organizzazione.
**Deliverable:**

| File | Contenuto |
|---|---|
| `pitch/final/PITCH_DEFINITIVO.md` | Questo documento: analisi, decisioni, script, regia demo, Q&A |
| `pitch/final/slides_final.html` / `.pdf` | Deck definitivo: 7 slide principali + 3 di backup |
| `pitch/final/previews/` | Anteprime PNG di ogni slide |
| `pitch/final/export_final.mjs` | Rigenera PDF e anteprime (`node pitch/final/export_final.mjs` dalla root del repo) |

> Analisi e decisioni sono in italiano. Testo delle slide e script sono in inglese, la lingua della giuria e della submission.
> Il deck precedente (`pitch/slides.html`, `slides.pdf`) **non è stato toccato**: i test in `scripts/tests/test_pitch.py` ne verificano gli hash.

---

## 1. Analisi dei due brainstorm

### 1.1 Brainstorm dei colleghi (`general_docs/ReleaseProof_Pitch_Redesign_Brainstorm.md`)

**Punti di forza:**
- **Diagnosi corretta del formato.** È un pitch della soluzione per una giuria. Va guidato dalla demo, non dal mercato.
- **Arco narrativo forte:** fiducia → sorpresa → indagine → prova → passo successivo consapevole. È una "detective story", non un elenco di feature.
- **Headline eccellente:** *"The firmware boots. The fleet can't upgrade."*
- **Tre direzioni ben combinate:** il test verde che non vede il problema (storia), il ponte mancante (metafora visiva), l'AI che sa quando non decidere (differenziatore tecnico).
- **`INDETERMINATE` diventa un momento drammatico**, non una debolezza.
- **Regia della demo concreta:** partire dal risultato, mostrare 3 click, avere un fallback registrato ed etichettato.
- **Rigore:** niente "nessun altro lo fa", niente claim su GPU o latenza non verificati.

**Debolezze:**
- **Business Value quasi azzerato.** Mercato, buyer e modello finiscono tutti nel Q&A, ma Business Value è uno dei 4 criteri ufficiali. Servono almeno 30 secondi su *chi soffre, perché costa e perché adesso*.
- **Manca il "why now".** Il pubblico non esperto non sa perché ECDSA vada sostituito.
- **Visione piccola.** "Release gate" chiude in modo corretto ma non lascia un'immagine memorabile del futuro.
- **Il ruolo di AMD resta difensivo.** Bisogna mostrarlo come parte attiva del prodotto (Application of Technology), non solo come "non decide".
- Lo script parla di "thousands of connected devices installed in factories and infrastructure" senza ancorarlo al caso reale (sensori di condition monitoring su nRF52840) che il progetto ha già documentato.

### 1.2 Il mio brainstorm (`pitch/IDEA_BRAINSTORM.md`)

**Punti di forza:**
- **Framing più ampio:** "can your fleet still be updated?", con il PQC come motivo d'urgenza. Il problema sembra un mercato, non una feature.
- **Fleet Generation Matrix:** un'immagine di visione forte e comprensibile. Una flotta reale è un insieme di generazioni, e le righe rosse sono i dispositivi bloccati.
- **"Why now" esplicito** e mappatura sul buyer.
- **Principio "tutta l'onestà in un posto solo"**, invece di 2–3 disclaimer per slide.
- One-liner e chiusura nitidi.

**Debolezze (autocritica):**
- **Sono scivolato verso un pitch da investitori**: moat, canali, TAM bottom-up, ask di funding, 10 slide. È esattamente ciò che il brief escludeva.
- **Troppo contenuto per 4–5 minuti.**
- **Il route planner AI e la matrice non esistono.** Possono stare solo come visione, per 15–20 secondi, chiaramente etichettati.
- Diversi claim (incidenti con chiavi trapelate, UN R156, FDA) **non sono verificati** e non devono entrare nel pitch.

### 1.3 Confronto e decisione

| Dimensione | Colleghi | Mio | Decisione finale |
|---|---|---|---|
| Formato | Demo-led, 6 scene | Investor-like, 10 slide | **Demo-led, 7 slide + 3 backup** (colleghi) |
| Headline | "The firmware boots. The fleet can't upgrade." | "Every device has a cryptographic expiry date" | **Colleghi**: più concreta e già provata dalla demo |
| Metafora | Missing bridge | Google Maps / percorsi | **Missing bridge** (colleghi); i "percorsi" diventano la visione |
| Why now | Assente | Elenco regolatorio lungo | **Una frase sola**: ECDSA vulnerabile al quantum, ML-DSA standard NIST 2024 |
| Business value | Spostato nel Q&A | Slide intera + business model | **Una slide condivisa con la visione** (buyer + modello marcato come ipotesi); i numeri vanno nel backup |
| Ruolo AI | "AI that knows when not to decide" | AI come esploratore di percorsi | **"AI investigates. Evidence decides."** Pianifica ed esplora; non decide mai |
| Momento clou | `INDETERMINATE` | Matrice | **`INDETERMINATE`** nella demo; matrice come immagine finale di visione |
| Visione | Release gate | Matrice + route planner + onboarding AI | **Release gate (esiste) → matrice di flotta (visione etichettata)** |
| Onestà | Rigorosa, sparsa | Concentrata in appendice | **Una riga di footer per slide + slide di backup "what's real / not claimed"** |
| Chiusura | "Don't just test where you're going…" | "…can deployed devices get there" | **"Don't just test where you're going. Test whether you can get there."** |

**In una frase:** la struttura e il tono vengono dai colleghi; dal mio brainstorm prendo il "why now" in una frase, la presenza del business value, la matrice di flotta come visione e il principio dell'onestà concentrata. Scarto tutta la parte da investitori.

---

## 2. Il pitch definitivo in sintesi

- **Headline:** *The firmware boots. The fleet can't upgrade.*
- **One-liner:** *ReleaseProof checks that the devices you already shipped can actually reach your next firmware, with executed evidence, before rollout.*
- **Metafora:** il **ponte mancante** tra il bootloader già installato (il "gatekeeper") e il nuovo firmware.
- **Differenziatore:** *AI investigates. Evidence decides.* Quando le prove non bastano, ReleaseProof dice *"not proven yet"*.
- **Chiusura:** *Don't just test where you're going. Test whether you can get there.*
- **Arco emotivo:** fiducia (test verde) → sorpresa (upgrade rifiutato) → perché (il ponte) → prova (demo) → fiducia nel metodo (`INDETERMINATE`) → non è un caso isolato (MCUboot) → dove va (dalla release alla flotta) → invito.

### Copertura dei 4 criteri ufficiali

| Criterio | Dove si vince | Prova mostrata |
|---|---|---|
| **Application of Technology** | Slide 3–4 + demo | Build reali, Renode, test negativi, motore deterministico; AI AMD che pianifica, spiega e propone, con trace per run |
| **Business Value** | Slide 2 + 6 | Chi soffre (OEM di sensori industriali), cosa costa (intervento manuale dispositivo per dispositivo), modello per profilo (ipotesi) |
| **Originality** | Slide 1, 4, 6 | Verdetto candidate ≠ transition; `INDETERMINATE` invece di un falso verde; visione della matrice di flotta |
| **Presentation** | Tutto | Una sola storia, 3 click di demo, nessun hash sulle slide parlate, chiusura memorabile |

---

## 3. Struttura delle slide e tempi

| # | Titolo slide | Tempo | Messaggio unico | Visual |
|---|---|---|---|---|
| 1 | **The firmware boots. The fleet can't upgrade.** | 0:00–0:25 | Il test verde non vede il problema | Pannello verde "New firmware boots" vs pannello rosso "Upgrade rejected" |
| 2 | **The missing bridge** | 0:25–1:05 | Il bootloader in campo è il gatekeeper; nessuno testa il ponte | Bootloader ECDSA → **?** rosso → firmware ML-DSA; 3 card: why now / who / cost |
| 3 | **Let's test the bridge** (demo) | 1:05–2:05 | La transizione è incompatibile, ed ecco la prova | 3 passi + verdetto + evidenze X01 / E11 (o app live) |
| 4 | **AI investigates. Evidence decides.** | 2:05–2:55 | L'AI indaga e propone, il motore decide, l'umano sceglie | Plan → Execute → Decide → Explain → Choose; INCOMPATIBLE → INDETERMINATE |
| 5 | **Different bootloader. Different blocker. Same engine.** | 2:55–3:20 | Non è una demo cablata | Card wolfBoot vs MCUboot |
| 6 | **From one check to every release** | 3:20–3:55 | Oggi preflight + release gate; domani la matrice di flotta | Today / Next / Vision + buyer e modello |
| 7 | **Don't just test where you're going.** | 3:55–4:15 | Chiusura + invito ai design partner | Frase finale, link a demo e codice |
| B1–B3 | Backup | Q&A | Architettura + AMD; cosa è reale e cosa no; mercato e landscape | Solo su domanda |

---

## 4. Script parlato (≈ 4:15)

> Parlare lentamente. Le parti in *[corsivo tra parentesi]* sono regia, non vanno lette.
> Sostituire *[name]* con il nome reale del presentatore o del team.

### Slide 1 · The firmware boots. The fleet can't upgrade. · 0:00–0:25

"Imagine you make wireless sensors that monitor machines in factories. Thousands are already installed. Your team has a new security firmware ready, with post-quantum signatures. It builds. It boots. Every test is green.

*[pausa, indicare il pannello rosso]*

And the devices already in the field can't install it.

That's not a hypothetical: we measured it. I'm *[name]*, and this is ReleaseProof."

### Slide 2 · The missing bridge · 0:25–1:05

"Here's why. On every device, the bootloader is a gatekeeper: it checks the signature of every update before accepting it.

Today those signatures are mostly ECDSA, and ECDSA is expected to fall to future quantum computers. So the industry is moving to post-quantum signatures like ML-DSA, standardised by NIST in 2024.

But the gatekeeper already in the field only knows the old algorithm. If it rejects the new signature and can't update itself, the only way across is manual: a technician, a cable, a visit, device by device.

Most tests check the destination. ReleaseProof tests the bridge."

### Slide 3 · Let's test the bridge · 1:05–2:05

*[Passare all'app, oppure restare sulla slide se la demo è registrata o se la rete è a rischio.]*

"Let me show you. A Nordic nRF52840, a chip used in real industrial sensors, with the open-source wolfBoot bootloader. The change: ECDSA to ML-DSA-87. Run.

This really executes. It builds the real bootloaders with pinned toolchains, signs with fresh keys, then boots and updates them in the Renode emulator, including negative tests.

*[mostrare il verdetto]* Two answers. **Candidate: compatible.** The new firmware boots. **Transition: incompatible.**

*[click 1: evidenza X01]* Here's why. The deployed bootloader receives the ML-DSA update, answers *'Update type invalid'*, and version 1 keeps running. *[evidenza E11]* And this port has no way for the bootloader to replace itself.

A green boot test would have shipped this. And every line here links to a hashed artifact. It's evidence, not an opinion."

### Slide 4 · AI investigates. Evidence decides. · 2:05–2:55

"So where's the AI? An AMD-hosted model, on AMD Token Factory, plans the investigation: it adds checks from a registered catalog, and it can't remove the required ones. After the run, it explains the result citing real evidence, and proposes next steps.

What it can never do is decide. The verdict comes from a deterministic engine: same evidence, same verdict, same hash.

*[click 2: Evaluate this plan]* Watch this. The engineer picks a proposal: re-flash the bootloader in a service window. It runs as a new assessment, and the original stays untouched. The blocker goes away. But the result is not green. It's **indeterminate**, because recovery from an interrupted update was never observed.

An assistant built to please would say yes. ReleaseProof says: not proven yet."

### Slide 5 · Different bootloader. Different blocker. · 2:55–3:20

"And this isn't a hard-coded demo. Same chip, MCUboot on Zephyr: here the failure comes earlier. The pinned signing tool refuses to produce an ML-DSA signature at all. We measured that by running it. And single-stage MCUboot can't replace itself in the field. Different bootloader, different blocker, same engine."

### Slide 6 · From one check to every release · 3:20–3:55

"Who is this for? Firmware and product-security teams at industrial IoT manufacturers, who have to keep shipped devices updatable for years.

Today, ReleaseProof answers this question for two supported configurations, exports an evidence pack, and runs as a strict release gate: only a fully compatible migration passes. Next: real hardware and power-loss tests, then more chips and bootloaders.

And where it goes: every new release checked against every generation of devices you've already shipped, with a proven route for each one, or a clear warning that some would be stranded."

### Slide 7 · Close · 3:55–4:15

"Don't just test where you're going. Test whether you can get there.

We're looking for industrial design partners with a real migration on their roadmap. ReleaseProof. Thank you."

**Lunghezza:** circa 600 parole parlate, cioè 4:05–4:20 a 145–150 parole al minuto. Provare con il cronometro, demo inclusa.

### Piano di taglio se si sfora

1. **Prima** si accorcia la slide 5 a una frase: *"On MCUboot, a different blocker: the pinned tool can't even sign ML-DSA."* (−15 s)
2. **Poi** si toglie la frase "Next: real hardware…" dalla slide 6. (−8 s)
3. **Poi** si toglie la spiegazione "same evidence, same verdict, same hash". (−5 s)
4. **Mai** si tagliano: il momento rosso/verde, l'evidenza X01, `INDETERMINATE`, il ruolo AMD, la chiusura.

---

## 5. Regia della demo

**Principio:** non è un tour del prodotto. È **una scoperta**, mostrata con 3 prove.

### Preparazione

- Una run LIVE wolfBoot già completata, aperta in una scheda e **verificata**: verdetto, evidenze e trace AMD devono appartenere a quella stessa run.
- La re-evaluation `field_service_reflash` pronta o da lanciare con un click (è veloce: rivaluta le evidenze esistenti, senza nuova emulazione).
- La run MCUboot aperta in una seconda scheda.
- Il video di fallback registrato, con il badge **RECORDED DEMO** e gli ID delle run in sovrimpressione.
- Opzionale: lanciare una run LIVE nuova all'inizio del pitch e tornarci alla slide 3, ma solo se è già stato provato che finisce in tempo. In caso contrario, usare la run pronta.

### I 3 click

1. **Evidenza X01 / E11** sulla run wolfBoot: il bootloader ECDSA rifiuta l'update ML-DSA; nessun percorso di self-update.
2. **"Evaluate this plan"** sulla proposta di re-flash: nasce una nuova run `INDETERMINATE`, e il banner conferma che la run madre è invariata.
3. **Tab "AMD AI"** della run (5 secondi, durante la slide 4): le chiamate di planner ed explainer, con modello, stato e latenza.

### Se l'endpoint AMD non risponde

Dirlo esplicitamente: *"The AMD endpoint is unavailable right now. The UI shows AI_UNAVAILABLE, the deterministic plan still runs, and no other provider is called."* Mostrare le trace della run preparata solo se sono davvero di quella run. Non presentare mai il fallback deterministico come un passo AI.

---

## 6. Q&A: le 8 risposte da avere pronte

**1. "Isn't this just wolfBoot's CI?"**
No. La CI upstream testa ogni algoritmo da solo e un update v1→v2 con lo stesso schema: è proprio il test che qui risulta verde. ReleaseProof aggiunge il caso cross-generation (bootloader ECDSA già installato + update ML-DSA), la capacità di self-update, i test negativi e un verdetto separato per candidate e transition. Lo fa su due famiglie di bootloader con lo stesso motore.

**2. "What's real and what's simulated?"**
Reali: codice dei bootloader ai commit fissati, toolchain, chiavi, firme e binari. Emulato: l'hardware (Renode 1.16.1 su nRF52840). Non modellati: timing della flash, perdita di alimentazione, finestra di update interrotto. Per questo quel punto resta `UNKNOWN`. → Backup B2.

**3. "Why AMD?"**
Tutte le chiamate AI (planner, explainer, alternative, assistente) vanno a un unico endpoint AMD Token Factory (DeepSeek-V4-Flash), con host in allow-list e nessun provider di fallback. La GPU gestita non è dichiarata dal provider, quindi non la nominiamo. La demo pubblica gira su AWS EC2 c7a (AMD EPYC), come verificato nell'audit infrastrutturale; quell'audit non attesta che le immagini deployate corrispondano all'ultimo sorgente. → Backup B1.

**4. "What if the LLM hallucinates?"**
Non può cambiare l'esito: il verdetto esiste prima che l'explainer parli. Le spiegazioni devono citare ID di evidenza esistenti e ripetere i verdetti del motore; altrimenti vengono rifiutate. Il planner sceglie solo da un catalogo registrato. I log sono trattati come dati non fidati. Limite onesto: questi controlli verificano ID ed etichette dei verdetti, non la verità di ogni frase. La revisione umana resta necessaria.

**5. "Can I trust an emulator?"**
Solo entro ciò che è stato osservato. Per questo il re-flash risulta `INDETERMINATE` e non `COMPATIBLE`. Il prossimo passo è un runner hardware-in-the-loop su dev kit reali.

**6. "Who pays, and how?"**
Firmware lead e product security dei produttori di dispositivi industriali. Ipotesi da validare: onboarding a pagamento per profilo (chip + bootloader + toolchain), poi abbonamento per profilo, non per dispositivo. Nessun cliente o ROI dichiarato. Lo scenario illustrativo (5.000 sensori × 5% × €250 = €62.500 di esposizione) è nel Backup B3, solo se richiesto.

**7. "How is this different from Binarly, ONEKEY or Finite State?"**
Gli scanner trovano *cosa* è vulnerabile al quantum; noi *eseguiamo* la migrazione e verifichiamo se la flotta installata può arrivarci. Sono complementari: un finding CBOM è un trigger naturale per una run ReleaseProof. Finite State è il concorrente adiacente più vicino. Non dichiariamo superiorità né esclusività. → Backup B3.

**8. "Why ML-DSA if CNSA 2.0 prefers LMS/XMSS for firmware?"**
È vero. ML-DSA-87 è comunque un algoritmo CNSA 2.0 ed è quello supportato da wolfBoot al commit fissato. Il motore è indipendente dall'algoritmo, e il problema del ponte è lo stesso con qualunque schema post-quantum. LMS è in roadmap.

---

## 7. Regole di onestà (valgono per slide, voce e video)

**Si può dire:**
- "measured in emulation", "real builds at pinned commits", "deterministic verdict"
- "historical LIVE run" con l'ID, se si mostra una run passata
- "AMD-hosted inference on AMD Token Factory, no fallback provider"
- "illustrative concept" per la matrice di flotta, "hypothesis" per il modello di business

**Non si può dire:**
- "certified", "compliant", "proves the firmware is secure", "safe migration"
- "nobody else does this", "the only tool"
- MI300X / Instinct / modello di GPU specifico per l'inferenza gestita
- "42 seconds end to end": i 42 s riguardano solo build + emulazione
- numeri di benchmark AI, clienti, risparmi o ROI
- che la matrice di flotta o il route planner esistano oggi

---

## 8. Checklist prima della consegna

- [ ] Durata massima del pitch confermata con gli organizzatori.
- [ ] Run della demo, verdetto mostrato e trace AMD appartengono **alla stessa run** (verificare l'ID nell'URL).
- [ ] Acceptance rigorosa rieseguita sulla release corrente (`scripts/acceptance.py --require-ai`), come richiesto da `submission.md`.
- [ ] Endpoint AMD verificato sulla demo pubblica il giorno stesso.
- [ ] Video di fallback registrato, con tagli e accelerazioni etichettati.
- [ ] Prova completa a voce alta, demo inclusa, cronometrata almeno 2 volte.
- [ ] Nome del presentatore/team inserito nello script.
- [ ] Deck aggiornato: se si modifica `slides_final.html`, rieseguire `node pitch/final/export_final.mjs` e controllare che `overflow` sia vuoto.
- [ ] Se questo deck diventa quello ufficiale della submission: copiarlo in `pitch/slides.html`, aggiornare `scripts/export_pitch.mjs` e `scripts/tests/test_pitch.py` (oggi si aspettano 8 slide) e rieseguire l'export.

---

## 9. Allineamento con gli altri materiali (suggerito, non applicato)

- **`pitch/video_script.md`:** la struttura è già compatibile. Basta sostituire la battuta dello Shot 1 con l'headline *"The firmware boots. The fleet can't upgrade."* e chiudere con *"Don't just test where you're going. Test whether you can get there."*
- **`pitch/submission.md`:** titolo e descrizioni restano validi. Si può usare la nuova one-liner nella short description, rispettando il limite di 255 caratteri verificato dai test.
- **Homepage dell'app:** l'hero attuale ("A firmware can boot and still be impossible to upgrade safely") resta coerente. Volendo, si allinea all'headline nuova.
