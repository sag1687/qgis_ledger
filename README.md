🇮🇹 Italiano
QGIS Ledger (sketinel)

QGIS Ledger (nome del plugin: sketinel) è un sistema di versionamento completo per QGIS. Trasforma il tuo desktop GIS in una piattaforma collaborativa offrendo storicizzazione in stile Git, rollback, diff visivo, salvataggio automatico e un browser Nextcloud integrato. Tutto questo funziona nativamente senza la necessità di PostGIS o server dedicati.
🚀 Requisiti

    Versione QGIS: 3.16 o superiore.

    Dipendenze: Nessuna dipendenza esterna. Utilizza Python standard, PyQGIS e SQLite integrato.

    Portabilità: Progetti completamente portabili tra Linux e Windows grazie all'uso di percorsi relativi dinamici (supporto Cloud/USB).

📦 Installazione

    Copia la cartella sketinel nel percorso: ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/

    Apri QGIS e vai su Plugin → Gestisci e Installa Plugin.

    Abilita sketinel dalla lista.

    La toolbar QGIS Ledger comparirà nell'interfaccia principale.

🛠️ Funzionalità Principali

    💾 Commit Layer: Salva uno snapshot completo (feature, attributi, geometrie) del layer attivo nel database .ledger.db, includendo uno screenshot automatico della mappa.

    💾 Commit Progetto: Salva una copia dell'intero file .qgz all'interno della cartella nascosta .ledger_history/project/.

    🕓 Timeline: Pannello laterale che mostra la cronologia completa dei commit. Permette di filtrare i nodi e utilizzare azioni rapide come Anteprima, Rollback, Diff e Visualizzazione Mappa.

    Δ Diff (Confronto Visuale): Evidenzia le differenze tra due versioni sulla mappa (Verde = Aggiunte, Rosso = Rimosse, Arancione = Modificate). Consente di estrarre la versione o sostituire quella corrente.

    📂 Esplora Storico: Un file browser per navigare tutte le versioni passate. Permette di salvare estrazioni in .gpkg/.tif/.qgz o caricare versioni storiche come layer isolati, anche se il layer originale è stato cancellato.

    ⏱️ Auto-Save: Timer configurabile (1-120 minuti) per salvare automaticamente layer aperti, progetto e screenshot, notificando l'utente a ogni ciclo completato.

    ⏪ Rollback Intelligente: Ripristina i dati in modo dinamico. Ricostruisce persino interi layer dal database se i file fisici originali sono stati eliminati.

    🖼️ Screenshot per Commit: Ogni salvataggio cattura un'istantanea visiva, visualizzabile direttamente dalla Timeline.

    ℹ️ Info e Notifiche: Monitoraggio in tempo reale delle modifiche effettuate da altri utenti (mod_user) sullo stesso progetto condiviso.

    ⚙ Impostazioni: Configurazione utente, intervalli di salvataggio, chiavi API per IA e credenziali Cloud (Locale, Nextcloud/WebDAV, Google Drive).

    🚦 Barra di Stato LED: Indicatore visivo istantaneo (Verde = Sincronizzato, Giallo = Modifiche in sospeso, Rosso = Conflitto). Cliccandolo si apre la Timeline.

    🔀 Merge Wizard: Interfaccia a schermo diviso per risolvere agevolmente i conflitti di editing tra più utenti.

☁️ Sincronizzazione Nextcloud (Workflow Cloud-Native)

Dalla versione 2.5.0, QGIS Ledger integra un Workspace Locale Sincronizzato per gestire dati pesanti senza latenza di rete.

    📥 Check-out Rapido: Fai doppio clic su un file dal pannello Nextcloud. Il sistema scarica il file e tutto il suo ecosistema in ~/QGIS_Cloud_Workspace/ aprendolo in mappa.

    📤 Auto-Sync in Background: Qualsiasi commit o salvataggio fatto su un file Cloud viene caricato in remoto in background, mantenendo l'interfaccia di QGIS fluida e reattiva.

    🚀 Esportazione Diretta: Clicca col tasto destro su un layer nella TOC e scegli "Invia a Nextcloud" per impacchettarlo e caricarlo online.

    🖱️ Drag & Drop (v2.6.0): Trascina file direttamente dal browser Nextcloud alla mappa di QGIS per un download e inserimento istantaneo.

📁 Struttura dei File

La gerarchia dei file generata dal plugin mantiene il tuo progetto pulito e organizzato:

    progetto.qgz: Il tuo file di progetto QGIS.

    progetto.ledger.db: Database SQLite contenente tutti i commit.

    .ledger_history/: Cartella nascosta.

    .ledger_history/project/: Storico dei file di progetto.

    .ledger_history/raster/: Copie di backup dei layer raster.

    .ledger_history/screenshots/: Immagini generate ai salvataggi.

💡 Suggerimenti Rapidi

    Premi sempre Ctrl+S dopo un rollback per rendere permanenti le modifiche nel file di progetto.

    Utilizza la funzione Esplora Storico per caricare layer passati in isolamento senza distruggere il tuo lavoro attuale.

    Attiva Auto-Save nelle sessioni di lavoro più intense per prevenire la perdita di dati.

📄 Licenza

Rilasciato sotto licenza GNU General Public License v2.0 o successiva.
🇬🇧 English
QGIS Ledger (sketinel)

QGIS Ledger (plugin name: sketinel) is a comprehensive versioning system for QGIS. It transforms your desktop GIS into a collaborative platform, offering Git-like history, rollbacks, visual diffs, auto-saving, and an integrated Nextcloud browser. All of this operates locally without requiring PostGIS or dedicated servers.
🚀 Requirements

    QGIS Version: 3.16 or higher.

    Dependencies: No external dependencies. Uses standard Python, PyQGIS, and built-in SQLite.

    Portability: Fully portable projects across Linux and Windows via dynamic relative paths (Cloud/USB support).

📦 Installation

    Copy the sketinel folder to: ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/

    Open QGIS and navigate to Plugins → Manage and Install Plugins.

    Enable sketinel from the list.

    The QGIS Ledger toolbar will appear in your interface.

🛠️ Core Features

    💾 Commit Layer: Saves a complete snapshot (features, attributes, geometries) of the active layer to the .ledger.db database, including an automatic map screenshot.

    💾 Commit Project: Saves a backup copy of your entire .qgz file into the hidden .ledger_history/project/ folder.

    🕓 Timeline: A side panel displaying the full commit history. Allows node filtering and quick actions like Preview, Rollback, Diff, and View Map.

    Δ Diff (Visual Comparison): Highlights differences between two versions directly on the map (Green = Added, Red = Removed, Orange = Modified). Allows version extraction or current state replacement.

    📂 History Explorer: A file browser for navigating past versions. Extract commits as .gpkg/.tif/.qgz or load historical versions as isolated layers, even if the original layer was deleted.

    ⏱️ Auto-Save: Configurable timer (1-120 minutes) to auto-commit open layers, capture screenshots, and save the project, with notifications upon completion.

    ⏪ Smart Rollback: Dynamically restores data. It can even rebuild entire layers from the database if the original physical files are missing.

    🖼️ Commit Screenshots: Every save captures a visual snapshot, accessible directly from the Timeline nodes.

    ℹ️ Info & Notifications: Real-time monitoring of edits made by other users (mod_user) on the same shared project.

    ⚙ Settings: Configure username, auto-save intervals, AI API keys, and Cloud credentials (Local, Nextcloud/WebDAV, Google Drive).

    🚦 LED Status Bar: Instant visual indicator (Green = Synced, Yellow = Pending changes, Red = Conflict). Clicking it toggles the Timeline panel.

    🔀 Merge Wizard: A split-screen interface designed to smoothly resolve editing conflicts between multiple users.

☁️ Nextcloud Synchronization (Cloud-Native Workflow)

Starting from v2.5.0, QGIS Ledger integrates a Synchronized Local Workspace to handle heavy data without network latency.

    📥 Quick Check-out: Double-click a file in the Nextcloud panel. The system downloads the file and its entire ecosystem to ~/QGIS_Cloud_Workspace/ and opens it.

    📤 Background Auto-Sync: Any commit or save on a Cloud file is uploaded remotely in the background, keeping the QGIS interface fast and responsive.

    🚀 Direct Export: Right-click a layer in the Table of Contents and select "Send to Nextcloud" to package and upload it online.

    🖱️ Drag & Drop (v2.6.0): Drag files directly from the Nextcloud browser onto the QGIS map canvas for instant downloading and loading.

📁 File Structure

The plugin generates a clean hierarchy to keep your project organized:

    progetto.qgz: Your main QGIS project file.

    progetto.ledger.db: SQLite database storing all commits.

    .ledger_history/: Hidden history directory.

    .ledger_history/project/: Project file history.

    .ledger_history/raster/: Raster layer backups.

    .ledger_history/screenshots/: Generated visual snapshots.

💡 Quick Tips

    Always press Ctrl+S after a rollback to make the changes permanent in your project file.

    Use the History Explorer to safely load past layers for comparison without disrupting your current work.

    Enable Auto-Save during heavy editing sessions to prevent accidental data loss.

📄 License

Released under the GNU General Public License v2.0 or later.
