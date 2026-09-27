# TEMPRA · Gestionale prodotti

Gestionale per il brand TEMPRA (calcio · padel · sportswear): prezzi di acquisto, costi accessori,
personalizzazioni, prezzi di vendita, margini, spedizioni, fornitori, ordini e preventivi per squadre e circoli.
Grafica secondo il brandbook (Lama `#111113`, Pietra `#EEE8E2`, Forgia `#E5502A`, Acciaio `#2F3B45`;
Chakra Petch, Archivo, Space Mono).

## Come si usa

Apri `index.html` in un browser. È un file unico, senza installazioni.
Aperto dal file locale, i dati restano salvati nel browser di quel dispositivo: usa
**Impostazioni → Esporta backup (JSON)** per conservarli o spostarli su un altro dispositivo.

## Sezioni

| Sezione | A cosa serve |
|---|---|
| Dashboard | Fatturato, utile, preventivi aperti, valore del magazzino, margine di ogni modello rispetto al target, prodotti da riordinare |
| Catalogo | Le 17 categorie (FC·01–FC·12, PD·01–PD·12) con i modelli; per ogni modello: acquisto, lotto, trasporto, dazi, packaging, personalizzazioni di serie, prezzo, grado BASE/PRO/ELITE, giacenza |
| Personalizzazioni | Listino lavorazioni (stampa, ricamo, sublimazione, DTF, incisione…): costo al pezzo, impianto una tantum, prezzo al cliente, categorie su cui si applicano |
| Ordini e preventivi | Righe con modello, pezzi, prezzo squadra e personalizzazioni; spedizione, sconto, totale cliente, costi e utile in tempo reale |
| Fornitori | Paese, tempi di consegna, minimi d'ordine, pagamento, modelli collegati |
| Spedizioni | Tariffe: costo corriere e prezzo al cliente, soglia di spedizione gratuita |
| Impostazioni | IVA, margine target, commissioni di pagamento, soglia spedizione gratis, categorie aggiuntive, backup/import, export CSV |

## Come calcola

- **Costo pieno** = acquisto + trasporto del lotto ÷ pezzi + dazi % + packaging + personalizzazioni di serie (impianto diviso sul lotto)
- **Prezzo netto** = prezzo di vendita ÷ (1 + IVA)
- **Utile per pezzo** = prezzo netto − costo pieno − commissioni (% sul prezzo + quota fissa)
- **Margine** = utile ÷ prezzo netto; **ricarico** = prezzo netto ÷ costo pieno
- **Prezzo consigliato** = prezzo che raggiunge il margine target, arrotondato a ,90
- Negli ordini l'impianto delle personalizzazioni si conta una volta per riga; i pezzi degli ordini
  Confermato / In produzione / Spedito / Consegnato scalano la disponibilità di magazzino

I dati precaricati sono esempi (segnati come tali) da sostituire con i propri numeri o da eliminare con
un clic dal banner in alto.
