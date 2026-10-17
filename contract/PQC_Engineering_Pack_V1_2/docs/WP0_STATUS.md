# Stato WP0 — freeze 2026-10-01T07:09:31Z

Nota da condividere. Il fact pack `wp0/facts/target_fact_pack.json` e `wp0/facts/WP0_SUMMARY.md` sono locali e non stanno nel git: questa pagina è la fotografia. Non è un verdict del semantic core e non chiude il Definition of Done dello spike: O05 e O06 restano aperti, O07–O09 restano parziali.

I log, sulla macchina che ha eseguito la run, stanno in `wp0/runs/<run_id>/`. Il confine e la sbarra del DoD sono in [`WP0_BOUNDARY.md`](WP0_BOUNDARY.md). La lettura breve nel decision log è la sezione «Lettura WP0 al 1 ottobre 2026» di `06_Decision_Log_V1_2.md`.

## Cosa si può dire

Il candidato nRF52840 ha fatto boot in Renode, sia con ECDSA P-256 sia con ML-DSA-87. Tre run per gate, stesso pin, stesso script, `functional_repeatability` vera. Marchio UART: `Factory img: OK`.

| | G1 ECDSA | G2 ML-DSA-87 |
| --- | --- | --- |
| Esito | PASS | PASS |
| Firma | `SIGN=ECC256` | `SIGN=ML_DSA`, `ML_DSA_LEVEL=5` |
| Header dichiarato | default della config | `IMAGE_HEADER_SIZE=12288` |
| Settore | 4096 byte | 12288 byte (`WOLFBOOT_SECTOR_SIZE=0x3000`) |
| Payload non firmato | 584 byte | 588 byte |
| Immagine firmata | 840 byte | 12876 byte |
| Span header misurato | 256 byte | 12288 byte |
| Bootloader `wolfboot.bin` | 23652 byte | 22840 byte |
| Partition | 262144 byte | 262144 byte |

Pin osservato, senza tag inventato:

- repository `https://github.com/wolfSSL/wolfBoot`
- branch `master`
- commit `4c79eee999b7083743811f37928322fe78b9fdb1`
- nessun tag di release coincide con quel commit (`release_tag_matches_commit = false`)
- tag semver pubblicato più vicino: `v2.9.0`. Non è dimostrato come antenato: il clone è shallow
- wolfCrypt / submodule `lib/wolfssl`: `4aa1ad7a5b4f7be86d88cc26fe3880a31ff7de9f`
- licenza wolfBoot e wolfCrypt: GPL-3.0

Toolchain della run: `arm-none-eabi-gcc` 14.2.1, GNU Make 4.4.1, Renode 1.16.1, Git 2.53.0.

T1, sulla sola piattaforma nRF52840: nessun config di self-update del bootloader e nessun path in `hal/nrf52.c`. Fatto `bootloader.self_update.supported = false`, classe `UNSUPPORTED_FEATURE`, stato CONCLUSIVE. Lo script di update applicativo `tools/scripts/renode-test-update.sh` c'è.

T3, matrice comportamentale della run `t3-20261001T070859Z-028f05b9`:

| Cella | Esito | Base |
| --- | --- | --- |
| solo ECDSA | ACCEPT | boot G1 |
| solo ML-DSA | ACCEPT | boot G2 |
| dual `SIGN=ECC256 SIGN_SECONDARY=ML_DSA` | BUILD_FAILED | log `dual_build.log` |
| key mismatch | REJECT | byte 32 dell'immagine factory invertito; UART termina con `wolfBoot: PANIC!` |

Il fallimento dual di questo commit non è l'assenza del flag secondario. `options.mk` aggiunge sia `-DWOLFBOOT_SIGN_SECONDARY_ML_DSA` sia `-DWOLFBOOT_SIGN_ML_DSA`. `include/image.h` mappa `WOLFBOOT_SIGN_ML_DSA` su `wolfBoot_verify_signature_primary`, che è già definito da `WOLFBOOT_SIGN_ECC256`. Il compilatore si ferma con redefinition e `-Werror`. AND/OR non è stato osservato: il fatto `authorization.secondary_signature.behavior` è nullo e INCONCLUSIVE. O05 resta aperto.

Nello stesso log compare anche `keygen: not found` risolto sotto il mount `/mnt/c/...`. `Makefile` usa `WOLFBOOT_ROOT?=$(PWD)`, e `PWD` ereditato dal processo Python è la root del repo, non il workbench Linux. È un difetto del harness, non la causa dello stop: l'errore di `make` è la ridefinizione della macro. Il harness ora esporta `WOLFBOOT_ROOT` verso il workbench; quel cambiamento non è nella run congelata.

RAM: regione del linker `hal/nrf52.ld`, 64K, metodo `static_linker_ram_region`. Non è lo stack del compilatore e non è stack painting. O07 parziale.

Analyzer: `strings` sui due `wolfboot.bin` di G1 e G2 ha prodotto `Component`, `CryptoAsset`, `AuthorizationSurface`. È un'euristica, non Ghidra. O08 parziale.

## Cosa non si può dire

T2, run `t2-20261001T070826Z-0553fb86`. Punto dichiarato prima della prova: pausa di 0,2 s dopo il secondo `start` di Renode, con l'immagine di update già caricata a `0x60000`. Entrambe le run sono uscite 0, dopo `make keysclean` sulla prima. Le coppie UART non coincidono:

- run 1: factory vero, update falso
- run 2: factory vero, update vero

`reproducibility = NOT_REPEATABLE`, esperimento INCONCLUSIVE. O06 resta aperto. Non è un fatto di swap interrotto.

Non c'è un tag sul commit. Non c'è un comportamento AND/OR. Gli schema V1.2 e le fixture A1–A4 non si aggiornano su questa fotografia.

## Come riprodurre

Da Ubuntu in WSL, con il virtualenv descritto in `wp0/docs/install_windows_wsl.md`:

```bash
bash wp0/scripts/run_wsl.sh
```

Una nuova esecuzione riscrive il fact pack, il summary e la sezione automatica del decision log. Non riscrive questa nota.

## Proiezione nel semantic core

Lo snapshot committabile è `examples/wp0_freeze_snapshot_v1_2.json`. `src.projection.wp0` lo trasforma in un assessment V1.2. Il piano dichiarato cambia il bootloader da G1 a G2; non è un update della sola immagine applicativa.

Sul freeze, `evaluate` chiude così:

- Configurazione candidata: G2 boota. Il target può esistere in ML-DSA-87.
- `candidate_verdict`: `INDETERMINATE`. La policy di firma e il recovery restano `UNKNOWN`. Gli unknown non cancellano il negativo della transizione.
- `transition_verdict`: `INCOMPATIBLE`. `REQ-BOOT-S0S1` è solo in fase TRANSITION: il piano richiede il self-update del bootloader e T1 è `UNSUPPORTED`.
- `migration_verdict`: `INCOMPATIBLE`, perché la transizione lo è.
- I1 è soddisfatto. I2, I3 e I4 restano `UNKNOWN`.
- La immagine firmata G2 (12876 byte) sta nella partition da 262144 byte.

Il baseline G2 (12876 byte) resta l'unica size firmata del freeze. Un intero scritto a mano non entra in `LEQ`.

La stessa proiezione è golden: `examples/golden/wp0_result_hashes_v1_2.json`. `python -m src.demo` ristampa i tre verdict del freeze e dell'assessment signer-bound. Le copie demo stanno in `src/projection/scenarios.py` e non riscrivono questo snapshot. Il workspace legge `web/data/catalog.json`, rigenerato con `python -m src.demo.export_catalog`.

## Follow-up sullo stesso commit

Non riscrive il fact pack. Comando: `python -m wp0.harness.followup`, pin `4c79eee999b7083743811f37928322fe78b9fdb1`.

A4, run `a4-20261001T082614Z-047ee1bc`. Dopo `make keysclean`, il flusso G2 ha prodotto `test-app/image.bin`; il payload è stato portato a 250112 byte con `0xff` e passato a `tools/keytools/sign --ml_dsa` con header 12288, partition `0x40000` e settore `0x3000`. Il tool ha rifiutato, senza emettere il file:

`Image size 262400 (header 12288 + firmware 250112) exceeds max 249856 (WOLFBOOT_PARTITION_SIZE 262144 - 1 x sector 12288)`

Lo snapshot ha `sign_refused: true`, `signing_result: REJECTED`, `requested_image_size_bytes: 262400`, `max_signable_image_size_bytes: 249856` e `measured_from_artifact: false`. Non c'è una lunghezza firmata. Quei due operandi, presi dalla riga del signer, alimentano l'assessment separato `WP0-A4-SIGNER-BOUND-20261001`: `REQ-SIGN-BOUND` in fase TARGET è `VIOLATED`, quindi quel candidato what-if è `INCOMPATIBLE`. Il baseline non contiene questa evidenza: `REQ-LAYOUT` resta soddisfatto su 12876 ≤ 262144 e il candidato del freeze resta `INDETERMINATE`.

O05, run `o05-20261001T082614Z-20827409`. Stesso stop del freeze: `wolfBoot_verify_signature_primary` ridefinita in `include/image.h`, `make` esce 1 su `src/string.o`. Etichetta del freeze: `UNSUPPORTED_CONFIGURATION_ON_FROZEN_COMMIT`. Non è un giudizio su wolfBoot in generale. AND/OR resta ignoto e fuori dalla evidence chain. `policy` resta `UNKNOWN`.

O06, run `t2-20261001T082614Z-11ae80a6`. Punto dichiarato prima della prova: kill di Renode sul secondo frame UART completo (`*` più 4 byte di versione), con l'update già caricato a `0x60000`. Due ripetizioni, frame `[1, 2]` e `[1, 2]`, `reproducibility = REPEATABLE`. La coda del capture contiene `version: 0x2`, `Verifying signature...done` e poi il frame versione 2. Il marker scatta quando l'applicazione di update è già partita. La finestra di erase/write non è osservata.

O06, una cella successiva, run `t2-20261001T090819Z-3f080e11`. Trigger dichiarato prima della run dalla printf `Copy sector` di `wolfBoot_copy_sector` in `src/update_flash.c`: al primo match, `pause`, `cpu Reset`, `start`. Due ripetizioni, entrambe con la riga vista e frame di reboot `[2]`. Nel capture la verifica dell'update precede la copia (`Versions: Current 0x1, Update 0x2`, poi tre `Copy sector 0`), e nello stesso burst compaiono già `Booting version: 0x2` e `Verifying signature...done`. Lo swap dell'immagine di test (584 byte) finisce prima che il comando di pausa abbia effetto. Il frame 2 è l'update completato, non un recovery da scrittura interrotta. I4 resta `UNKNOWN`. Non si cerca un'altra pausa.

## Ancora aperto

1. O06 resta aperto sul recovery. La cella su `Copy sector` è ripetibile e mostra l'update già completato. Il gap della finestra non atomica è esplicito: su questa emulazione la copia finisce prima della pausa. Stop.
2. AND/OR resta ignoto. Sul freeze la cella dual è chiusa come `UNSUPPORTED_CONFIGURATION_ON_FROZEN_COMMIT`. Un altro commit, se servirà, è un assessment nuovo.
3. Il metodo RAM non misura l'uso dello stack.
4. Il semantic core continua a ricevere `UNKNOWN` dove il fatto non è conclusivo.
5. Il `LEQ` su una size firmata inventata resta solo un test in memoria. Il fatto A4 è il rifiuto del signer, nell'assessment separato.
