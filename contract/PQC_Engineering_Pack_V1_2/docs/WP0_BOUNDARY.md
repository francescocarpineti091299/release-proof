# WP0 boundary

Lo spike produce fatti. Non valida il reasoning layer: quello resta il semantic core.

Il motore accetta `authorization_path_states[].policy = UNKNOWN` e recovery `UNKNOWN`. Non hardcoda board, geometria wolfBoot, metodi E07/E10/E12 o un analyzer. Non accetta `full_verification` né un dossier ufficiale dal client. Se la policy transitoria non esiste nel target, il fatto entra nel decision log: non si inventa un hybrid nello schema.

Lo stato misurato è in [`WP0_STATUS.md`](WP0_STATUS.md), freeze `2026-10-01T07:09:31Z`. Quel JSON è locale e non versionato: la nota è il documento da condividere. Il Definition of Done sotto resta la sbarra. Il freeze non la chiude.

## Definition of Done

Lo spike termina con un Target Fact Pack congelabile, non con la frase «wolfBoot ML-DSA funziona». Il pack contiene almeno:

- target/board e modello Renode usati;
- commit wolfBoot, con tag;
- toolchain e versioni;
- implementazione wolfCrypt/PQC effettivamente compilata;
- build flags e config;
- geometria flash, partition e swap;
- artefatti e log di boot ECDSA;
- artefatti e log di boot ML-DSA-87;
- dimensioni misurate di header, payload non firmato, immagine firmata e bootloader;
- `IMAGE_HEADER_SIZE` dichiarata e header misurato sull'immagine;
- comportamento del self-update e chiave o policy che lo autorizza, oppure prova che non è supportato;
- risultato dell'interruzione deterministica e recovery osservata;
- modalità dual/secondary signature (`AND`, `OR`, altra, oppure non supportata), confermata da una prova comportamentale;
- metodo scelto per RAM/stack, con il limite del metodo;
- analyzer scelto, con almeno un segnale normalizzabile;
- matrice versioni, licenze e modalità d'uso.

Questi fatti diventano `PlatformModel`, `DeployedState`, `CandidateState`, `DeclaredTransitionPlan` ed `Evidence`. Il motore fa il resto. Il fact pack non contiene `migration_verdict` né stati I1–I4.

## Stato rispetto al Definition of Done

Freeze `2026-10-01T07:09:31Z`. Le misure stanno in [`WP0_STATUS.md`](WP0_STATUS.md).

| Voce del DoD | Nel freeze |
| --- | --- |
| Board, script Renode, toolchain | nRF52840, `nrf52840_wolfboot.resc`, gcc 14.2.1, Renode 1.16.1 |
| Commit wolfBoot con tag | SHA `4c79eee999b7083743811f37928322fe78b9fdb1`. Nessun tag di release coincide. `v2.9.0` è il semver pubblicato più vicino, non un antenato dimostrato |
| wolfCrypt compilato, flag, geometria, size | SHA `4aa1ad7a…`, GPL-3.0. Payload, header, partition e settore sono fatti per ECDSA e ML-DSA-87 |
| Boot ECDSA e ML-DSA-87 | G1 PASS, G2 PASS, tre run, `Factory img: OK` |
| Self-update | `supported = false` su nRF52840, CONCLUSIVE |
| Interruzione deterministica e recovery | Aperto. Pausa 0,2 s dopo il secondo start: le due UART non coincidono. Un follow-up sul secondo frame di versione è ripetibile e arriva dopo la verifica; non osserva la finestra |
| Dual AND/OR, oppure non supportata, da un boot | Aperto. Solo ECDSA e solo ML-DSA accettano. Il key mismatch va in panic. `SIGN=ECC256` con `SIGN_SECONDARY=ML_DSA` non compila. AND/OR non è nominato |
| RAM/stack, con il limite del metodo | Parziale. Regione linker 64K, non uso stack |
| Analyzer con un segnale normalizzabile | Parziale. `strings` su `Component`, `CryptoAsset`, `AuthorizationSurface` |
| Matrice versioni, licenze, modalità d'uso | Parziale. wolfBoot e wolfCrypt sono GPL-3.0 e pinnati. Il resto della matrice non è un SBOM |

## Sequenza e gate

1. Probe toolchain.
2. ECDSA su Renode, tre run, poi G1.
3. ML-DSA-87 e layout, tre run, poi G2.
4. T1 self-update, T2 interruzione, T3 semantica delle firme. Solo se G2 passa.
5. Metodo RAM/stack sul binario disponibile.
6. Analyzer, fuori dal critical path iniziale.
7. Matrice versioni e licenze.
8. Un solo freeze del fact pack, poi summary e decision log.

G1 non conclusivo sul boot: stop degli esperimenti sul target. Si chiudono probe, licenze e summary. RAM e analyzer restano `NOT_RUN` se non esiste un binario.

G2 non passa: stop di T1, T2 e T3. Si completano RAM e analyzer sul binario ECDSA, poi licenze, freeze e summary.

Un fallimento si classifica prima di diventare un fatto sul target: `ENVIRONMENT_SETUP`, `TOOLCHAIN_CONFIG`, `UNSUPPORTED_FEATURE`, `TARGET_LIMITATION`, `UNKNOWN`. I primi due si correggono e si ripetono. Non diventano evidenza di prodotto. Al primo fallimento di setup non si cambia board.

nRF52840 è il candidato provato. Un limite reale e riproducibile si classifica prima di cambiare target.

## Self-update

Tre esperimenti separati. L'esito è `CONCLUSIVE` o `INCONCLUSIVE`. `supported = false`, se riproducibile, è conclusivo.

- WP0-T1: self-update del bootloader classico da S0, e con quale firma.
- WP0-T2: interruzione in un punto dichiarato prima della prova. Il pack riporta strategia, punto, trigger e riproducibilità osservata.
- WP0-T3: ispezione statica più matrice comportamentale (solo ECDSA, solo ML-DSA, dual, key mismatch). Chiude O05 e determina S1.

## A4 e analyzer

A4 è un what-if. Si misura prima la geometria naturale. Poi, se serve `INCOMPATIBLE`, la release N+1 cresce di X KiB oltre il limite misurato Y. X e Y vengono da dati reali o da una modifica dichiarata sintetica. La baseline non si fa fallire apposta. Sul pin congelato il signer G2 rifiuta un payload che supera partition meno un settore e non emette il file: quel rifiuto non è una size.

L'analyzer risponde a una sola domanda: quale strumento produce almeno un segnale riproducibile normalizzabile in `Component`, `CryptoAsset`, `AuthorizationSurface` o `ArtifactRelation`. Una lista generica di stringhe non basta.

## Demo successiva

Il POC mostra il freeze e copie marcate, valutate da `evaluate`, con `official=false`. Il workspace è `web/`. Non serve un'altra pausa Renode per chiudere O06: la finestra non atomica resta un gap.

Run registrate e riproducibili per A1–A3 restano il riferimento storico. L'azione già eseguita sul pin è il rifiuto del signer A4, assessment separato. Ogni run ha `run_id`, input esatti, versioni dei tool, artefatti e log grezzi. Un pin wolfBoot nuovo, o un transfer MCUboot, è un assessment nuovo, non una riscrittura di questo freeze.

Riferimento storico, immutabile: `PQC_Engineering_Pack_V1_1/03_WP0_Spike_Tecnico_V1_1.md`.
