# QGIS Ledger

**QGIS Ledger** (nome plugin: `sketinel`) è un sistema di versionamento completo per QGIS. Trasforma il desktop GIS in una piattaforma collaborativa con storicizzazione Git-like, rollback, diff visuale, estrazione file, salvataggio automatico e **browser Nextcloud integrato** — tutto senza PostGIS né server dedicati.

---

## 🚀 Requisiti

- **QGIS 3.16** o superiore
- Nessuna dipendenza esterna. Funziona con Python standard + PyQGIS + SQLite integrato.
- **Supporto Cloud/USB**: Progetti completamente portabili tra Linux/Windows tramite percorsi relativi dinamici.

---

## 📦 Installazione

1. Copia la cartella `sketinel` in `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
2. Apri QGIS → **Plugin** → **Gestisci e Installa Plugin** → Abilita **sketinel**
3. Comparirà la toolbar **QGIS Ledger** con tutti i pulsanti descritti sotto.

---

## 🛠️ Funzionalità Complete

### 1. 💾 Commit Layer
**Pulsante:** `💾 Commit`

Salva uno snapshot completo del layer vettoriale o raster attivo nel database storico.

**Come usarlo:**
1. Seleziona un layer nella TOC di QGIS
2. Clicca `💾 Commit` nella toolbar
3. Inserisci un messaggio descrittivo (es. "Aggiunta nuova zona residenziale")
4. Il sistema salva tutte le feature, gli attributi e le geometrie nel database `.ledger.db`
5. Viene catturato automaticamente uno **screenshot** della mappa attuale

---

### 2. 💾 Commit Progetto
**Pulsante:** `💾 Commit Progetto`

Salva una copia completa dell'intero file di progetto `.qgz`.

**Come usarlo:**
1. Clicca `💾 Commit Progetto`
2. Inserisci il messaggio
3. Il file `.qgz` viene copiato nella cartella `.ledger_history/project/`

---

### 3. 🕓 Timeline
**Pulsante:** `🕓 Timeline` (toggle)

Pannello laterale in stile GitKraken che mostra la cronologia completa dei commit.

**Come usarlo:**
1. Clicca `🕓 Timeline` per aprire/chiudere il pannello
2. Usa il menu a tendina in alto per filtrare: **Tutti**, **Solo Progetto**, o un layer specifico
3. Ogni nodo mostra: ID, messaggio, utente, data
4. **Pulsanti su ogni nodo:**
   - `👁️ Preview` — Anteprima temporanea (annullabile con Ctrl+Z)
   - `⏪ Rollback` — Ripristina il layer a quello stato passato
   - `Δ Diff` — Confronto visivo con lo stato corrente
   - `🖼️ Vedi Mappa` — Apre lo screenshot catturato al momento del commit

---

### 4. Δ Diff (Confronto Visuale)
**Pulsante:** `Δ Diff`

Confronta due versioni qualsiasi di un layer e visualizza le differenze direttamente sulla mappa.

**Come usarlo:**
1. Clicca `Δ Diff` nella toolbar
2. Seleziona **Versione A** (vecchia) e **Versione B** (nuova) dai menu a tendina
3. Premi OK
4. Sulla mappa compariranno layer temporanei colorati:
   - 🟢 **Verde** — Feature aggiunte
   - 🔴 **Rosso** — Feature rimosse
   - 🟡 **Arancione** — Feature modificate (mostra lo stato finale)
5. Si aprirà una finestra di riepilogo con i conteggi e le azioni rapide:
   - `📥 Estrai Versione` — Salva la vecchia versione come file `.gpkg`
   - `🔄 Sostituisci corrente` — Rollback immediato alla versione selezionata

---

### 5. 📂 Esplora Storico (Browser File)
**Pulsante:** `📂 Esplora Storico`

Archivio completo di tutti i file salvati nella storia del progetto. Permette di estrarre o caricare qualsiasi versione passata **senza fare un rollback distruttivo**.

**Come usarlo:**
1. Clicca `📂 Esplora Storico`
2. Nella tabella vedrai tutti i commit: ID, Tipo (VECTOR/RASTER/PROJECT), Nome, Data, Utente
3. Seleziona una riga e usa i pulsanti in basso:
   - **⬇️ Estrai File / Salva con nome** — Salva quella versione in una cartella a scelta (Desktop, ecc.) come `.gpkg`, `.tif` o `.qgz`
   - **🗺️ Carica in QGIS come Layer isolato** — Aggiunge il file storico alla mappa come layer temporaneo scollegato, perfetto per confronti visivi senza alterare nulla


> 💡 **Funziona anche se il layer originale è stato eliminato dal progetto!** Il sistema ricostruisce lo schema dal database.

---

### 6. ⏱️ Auto-Save (Salvataggio Automatico)
**Pulsante:** `⏱️ Auto-Save` (toggle ON/OFF)

Attiva un timer che salva automaticamente tutti i layer e il progetto ad intervalli regolari.

**Come usarlo:**
1. Vai in **⚙ Settings** → imposta l'intervallo desiderato (1-120 minuti, default: 5)
2. Clicca `⏱️ Auto-Save` nella toolbar per attivare il timer
3. Ogni N minuti il sistema:
   - Committa automaticamente tutti i layer vettoriali aperti
   - Cattura uno screenshot della mappa
   - Salva il file di progetto `.qgz` su disco
4. Riceverai una notifica nella barra messaggi di QGIS ad ogni ciclo
5. Clicca di nuovo il pulsante per disattivare

---

### 7. ⏪ Rollback Intelligente
Disponibile dalla **Timeline** o dal **Diff**.

**Funzionalità avanzate:**
- Se il layer è ancora nel progetto → ripristino diretto dei dati
- Se il layer è stato **rimosso** dalla TOC → il sistema tenta di ricaricarlo dal path originale
- Se anche il **file fisico** è stato cancellato → QGIS Ledger **ricostruisce il layer dal database**, creando un nuovo `.gpkg` e caricandolo automaticamente in mappa
- Per i **Progetti** → sovrascrive il `.qgz` e ricarica il progetto QGIS

---

### 8. 🖼️ Screenshot per Commit
Ogni commit (layer, raster o progetto) cattura automaticamente un'istantanea della mappa attuale.

**Come visualizzarli:**
- Nella Timeline, clicca il pulsante `🖼️ Vedi Mappa` su qualsiasi nodo
- Si aprirà l'immagine nel visualizzatore predefinito del sistema operativo

---

### 9. ℹ️ Tab Informazioni e Attività
**Pulsante:** `ℹ️ Info`

Oltre a mostrare la versione e i contatti (SinoCloud), la finestra Info contiene un tab dedicato alle **🔔 Notifiche mod_user**. 
Permette di monitorare rapidamente tutte le modifiche fatte di recente da altre postazioni o da mod_user collegati allo stesso progetto via Nextcloud, Google Drive o cartella condivisa.

---

### 10. ⚙ Impostazioni
**Pulsante:** `⚙ Settings`

| Sezione | Opzione | Descrizione |
|---|---|---|
| **Generale** | Nome Utente | Chi è l'autore dei commit (default: login OS) |
| **Generale** | Auto-commit | Commit automatico quando salvi un layer |
| **Auto-Save** | Intervallo | Frequenza del salvataggio automatico (1-120 min) |
| **Cloud** | Tipo Archiviazione | Locale/LAN o Nextcloud (WebDAV) |
| **Cloud** | Nextcloud Server URL | Es. `https://nextcloud.example.com` |
| **Cloud** | Nextcloud Cartella Remota | Es. `/QGIS_Projects/` |
| **Cloud** | Nextcloud Utente | Nome utente Nextcloud |
| **Cloud** | Nextcloud Password App | Password o token applicazione |

---

### 11. 🚦 Barra di Stato LED
Indicatore visivo nella barra di stato di QGIS:
- 🟢 **Verde** — Tutto sincronizzato
- 🟡 **Giallo** — Modifiche locali non committate
- 🔴 **Rosso** — Conflitto rilevato

Cliccando sul LED si apre/chiude il pannello Timeline.

---

### 12. 🔀 Merge Wizard
Interfaccia split-screen per risolvere conflitti quando due utenti modificano lo stesso layer su una cartella condivisa.

---

### 13. ☁️ Sincronizzazione Cloud Nextcloud (Workflow Integrato, NOVITÀ v2.5.0)
**Pulsanti:** `☁️ Nextcloud` (Toolbar) e `☁️ Invia a Nextcloud` (Tasto destro sui layer)

QGIS Ledger v2.5.0 trasforma il tuo workflow GIS in un ecosistema **Cloud-Native** appoggiato su Nextcloud. Poiché i database SQLite (`.ledger.db`) e i progetti GIS pesanti non possono essere manipolati stabilmente in streaming sul web, il plugin adotta in automatico un meccanismo invisibile di **Workspace Locale Sincronizzato**.

**Configurazione Iniziale:**
1. Apri **⚙ Settings** $\rightarrow$ seleziona **Tipo Archiviazione: Nextcloud**.
2. Compila **Server URL**, **Utente**, **Password App** e **Cartella Remota** di default.

🔥 **IL Workflow Cloud in 3 Fasi:**

1. 📥 **Check-out (Auto-Download e Import):**
   - Apri il pannello Nextcloud. Fai **doppio clic** su un file (es. `mappa.shp` o `progetto.qgz`).
   - Il plugin replicherà la struttura della cartella cloud sul tuo computer in `~/QGIS_Cloud_Workspace/`.
   - Verrà scaricato non solo il file cliccato, ma **anche tutto il suo ecosistema** (i file ausiliari `.dbf/.shx` per gli shapefile, oppure l'intero database storico del Ledger per i progetti).
   - Il layer o il progetto viene automaticamente aperto in QGIS pronto per l'editing!

2. 📤 **Check-in (Auto-Sync in Background):**
   - Quando il progetto proviene da Nextcloud (o Nextcloud è impostato come attivo), **qualsiasi salvataggio o Commit** tu faccia in QGIS verrà registrato sul disco locale quasi istantaneamente.
   - Subito dopo, un'attività nascosta in **background caricherà i pacchetti modificati, i file di progetto e il database SQLite sul server Nextcloud**. QGIS non subisce rallentamenti e il Cloud resta sempre una copia 1:1 perfetta!

3. 🚀 **Esportazione Rapida (TOC Context Menu):**
   - Fai clic col **Tasto Destro** su un qualunque layer attivo nella barra dei livelli (TOC).
   - Seleziona *☁️ Invia a Nextcloud (QGIS Ledger)*.
   - Scegli la cartella remota (verrà creata se non esiste) e il layer verrà impacchettato e caricato sul tuo Cloud.

4. 🖱️ **Drag & Drop (NOVITÀ v2.6.0):**
   - Apri il pannello **☁️ Browser Nextcloud** a sinistra.
   - **Trascina** un qualsiasi file (shapefile, raster, GeoPackage, progetto) direttamente dalla lista del browser Nextcloud **sulla mappa di QGIS** (area del canvas).
   - Il plugin scaricherà automaticamente il file (e tutti i file associati, come `.dbf`/`.shx` per gli shapefile) nella cartella locale `~/QGIS_Cloud_Workspace/` e lo aggiungerà come layer attivo nel progetto corrente.
   - **Nota:** le cartelle non possono essere trascinate, solo i file. Per navigare nelle cartelle usa il doppio clic nel browser.

**Browser Nextcloud Classico:**
Resta sempre disponibile la toolbar all'interno del dock laterale per eseguire operazioni manuali come: 📁 *Nuova Cartella*, ✏️ *Rinomina*, 🗑️ *Elimina file*, ⬆ *Carica* e ⬇ *Scarica individualmente*.

---

## 📁 Struttura dei File

```
📂 Il Tuo Progetto/
├── progetto.qgz              ← Il tuo file di progetto QGIS
├── progetto.ledger.db         ← Database SQLite con tutti i commit e snapshot
└── .ledger_history/           ← Cartella nascosta con i file storici
    ├── project/               ← Copie dei file .qgz per commit di progetto
    ├── raster/                ← Copie dei file raster per commit raster
    └── screenshots/           ← Screenshot della mappa per ogni commit
```

---

## 💡 Suggerimenti

- **Ctrl+S** dopo ogni rollback o sostituzione per rendere permanenti le modifiche
- Usa l'**Esplora Storico** per confrontare vecchie versioni senza rischiare il lavoro attuale
- Attiva l'**Auto-Save** e dimentica il rischio di perdere dati
- Usa il **Browser Nextcloud** per caricare GeoPackage esportati direttamente sul server condiviso
- Ogni operazione mostra un alert con istruzioni e promemoria di salvataggio

---

## 📄 Licenza

GNU General Public License v2.0 o successiva.


---

## 🚀 Requisiti

- **QGIS 3.16** o superiore
- Nessuna dipendenza esterna. Funziona con Python standard + PyQGIS + SQLite integrato.
- **Supporto Cloud/USB**: Progetti completamente portabili tra Linux/Windows tramite percorsi relativi dinamici.

---

## 📦 Installazione

1. Copia la cartella `sketinel` in `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
2. Apri QGIS → **Plugin** → **Gestisci e Installa Plugin** → Abilita **sketinel**
3. Comparirà la toolbar **QGIS Ledger** con tutti i pulsanti descritti sotto.

---

## 🛠️ Funzionalità Complete

### 1. 💾 Commit Layer
**Pulsante:** `💾 Commit`

Salva uno snapshot completo del layer vettoriale o raster attivo nel database storico.

**Come usarlo:**
1. Seleziona un layer nella TOC di QGIS
2. Clicca `💾 Commit` nella toolbar
3. Inserisci un messaggio descrittivo (es. "Aggiunta nuova zona residenziale")
4. Il sistema salva tutte le feature, gli attributi e le geometrie nel database `.ledger.db`
5. Viene catturato automaticamente uno **screenshot** della mappa attuale

---

### 2. 💾 Commit Progetto
**Pulsante:** `💾 Commit Progetto`

Salva una copia completa dell'intero file di progetto `.qgz`.

**Come usarlo:**
1. Clicca `💾 Commit Progetto`
2. Inserisci il messaggio
3. Il file `.qgz` viene copiato nella cartella `.ledger_history/project/`

---

### 3. 🕓 Timeline
**Pulsante:** `🕓 Timeline` (toggle)

Pannello laterale in stile GitKraken che mostra la cronologia completa dei commit.

**Come usarlo:**
1. Clicca `🕓 Timeline` per aprire/chiudere il pannello
2. Usa il menu a tendina in alto per filtrare: **Tutti**, **Solo Progetto**, o un layer specifico
3. Ogni nodo mostra: ID, messaggio, utente, data
4. **Pulsanti su ogni nodo:**
   - `👁️ Preview` — Anteprima temporanea (annullabile con Ctrl+Z)
   - `⏪ Rollback` — Ripristina il layer a quello stato passato
   - `Δ Diff` — Confronto visivo con lo stato corrente
   - `🖼️ Vedi Mappa` — Apre lo screenshot catturato al momento del commit

---

### 4. Δ Diff (Confronto Visuale)
**Pulsante:** `Δ Diff`

Confronta due versioni qualsiasi di un layer e visualizza le differenze direttamente sulla mappa.

**Come usarlo:**
1. Clicca `Δ Diff` nella toolbar
2. Seleziona **Versione A** (vecchia) e **Versione B** (nuova) dai menu a tendina
3. Premi OK
4. Sulla mappa compariranno layer temporanei colorati:
   - 🟢 **Verde** — Feature aggiunte
   - 🔴 **Rosso** — Feature rimosse
   - 🟡 **Arancione** — Feature modificate (mostra lo stato finale)
5. Si aprirà una finestra di riepilogo con i conteggi e le azioni rapide:
   - `📥 Estrai Versione` — Salva la vecchia versione come file `.gpkg`
   - `🔄 Sostituisci corrente` — Rollback immediato alla versione selezionata

---

### 5. 📂 Esplora Storico (Browser File)
**Pulsante:** `📂 Esplora Storico`

Archivio completo di tutti i file salvati nella storia del progetto. Permette di estrarre o caricare qualsiasi versione passata **senza fare un rollback distruttivo**.

**Come usarlo:**
1. Clicca `📂 Esplora Storico`
2. Nella tabella vedrai tutti i commit: ID, Tipo (VECTOR/RASTER/PROJECT), Nome, Data, Utente
3. Seleziona una riga e usa i pulsanti in basso:
   - **⬇️ Estrai File / Salva con nome** — Salva quella versione in una cartella a scelta (Desktop, ecc.) come `.gpkg`, `.tif` o `.qgz`
   - **🗺️ Carica in QGIS come Layer isolato** — Aggiunge il file storico alla mappa come layer temporaneo scollegato, perfetto per confronti visivi senza alterare nulla

> 💡 **Funziona anche se il layer originale è stato eliminato dal progetto!** Il sistema ricostruisce lo schema dal database.

---

### 6. ⏱️ Auto-Save (Salvataggio Automatico)
**Pulsante:** `⏱️ Auto-Save` (toggle ON/OFF)

Attiva un timer che salva automaticamente tutti i layer e il progetto ad intervalli regolari.

**Come usarlo:**
1. Vai in **⚙ Settings** → imposta l'intervallo desiderato (1-120 minuti, default: 5)
2. Clicca `⏱️ Auto-Save` nella toolbar per attivare il timer
3. Ogni N minuti il sistema:
   - Committa automaticamente tutti i layer vettoriali aperti
   - Cattura uno screenshot della mappa
   - Salva il file di progetto `.qgz` su disco
4. Riceverai una notifica nella barra messaggi di QGIS ad ogni ciclo
5. Clicca di nuovo il pulsante per disattivare

---

### 7. ⏪ Rollback Intelligente
Disponibile dalla **Timeline** o dal **Diff**.

**Funzionalità avanzate:**
- Se il layer è ancora nel progetto → ripristino diretto dei dati
- Se il layer è stato **rimosso** dalla TOC → il sistema tenta di ricaricarlo dal path originale
- Se anche il **file fisico** è stato cancellato → QGIS Ledger **ricostruisce il layer dal database**, creando un nuovo `.gpkg` e caricandolo automaticamente in mappa
- Per i **Progetti** → sovrascrive il `.qgz` e ricarica il progetto QGIS

---

### 8. 🖼️ Screenshot per Commit
Ogni commit (layer, raster o progetto) cattura automaticamente un'istantanea della mappa attuale.

**Come visualizzarli:**
- Nella Timeline, clicca il pulsante `🖼️ Vedi Mappa` su qualsiasi nodo
- Si aprirà l'immagine nel visualizzatore predefinito del sistema operativo

---

### 9. ℹ️ Tab Informazioni e Attività
**Pulsante:** `ℹ️ Info`

Oltre a mostrare la versione e i contatti (SinoCloud), la finestra Info contiene un tab dedicato alle **🔔 Notifiche mod_user**. 
Permette di monitorare rapidamente tutte le modifiche fatte di recente da altre postazioni o da mod_user collegati allo stesso progetto via Nextcloud, Google Drive o cartella condivisa.

---

### 10. ⚙ Impostazioni
**Pulsante:** `⚙ Settings`

| Sezione | Opzione | Descrizione |
|---|---|---|
| **Generale** | Nome Utente | Chi è l'autore dei commit (default: login OS) |
| **Generale** | Auto-commit | Commit automatico quando salvi un layer |
| **Auto-Save** | Intervallo | Frequenza del salvataggio automatico (1-120 min) |
| **AI** | API Key | Per funzionalità future di intelligenza artificiale |
| **Cloud** | Tipo Archiviazione | Locale, Nextcloud/WebDAV, Google Drive |
| **Cloud** | Percorso/URL | Cartella condivisa o indirizzo WebDAV |
| **Cloud** | Credenziali | Utente e password per l'accesso remoto |

---

### 11. 🚦 Barra di Stato LED
Indicatore visivo nella barra di stato di QGIS:
- 🟢 **Verde** — Tutto sincronizzato
- 🟡 **Giallo** — Modifiche locali non committate
- 🔴 **Rosso** — Conflitto rilevato

Cliccando sul LED si apre/chiude il pannello Timeline.

---

### 12. 🔀 Merge Wizard
Interfaccia split-screen per risolvere conflitti quando due utenti modificano lo stesso layer su una cartella condivisa.

---

## 📁 Struttura dei File

```
📂 Il Tuo Progetto/
├── progetto.qgz              ← Il tuo file di progetto QGIS
├── progetto.ledger.db         ← Database SQLite con tutti i commit e snapshot
└── .ledger_history/           ← Cartella nascosta con i file storici
    ├── project/               ← Copie dei file .qgz per commit di progetto
    ├── raster/                ← Copie dei file raster per commit raster
    └── screenshots/           ← Screenshot della mappa per ogni commit
```

---

## 💡 Suggerimenti

- **Ctrl+S** dopo ogni rollback o sostituzione per rendere permanenti le modifiche
- Usa l'**Esplora Storico** per confrontare vecchie versioni senza rischiare il lavoro attuale
- Attiva l'**Auto-Save** e dimentica il rischio di perdere dati
- Ogni operazione mostra un alert con istruzioni e promemoria di salvataggio

---

## 📄 Licenza

GNU General Public License v2.0 o successiva.
