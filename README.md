# QGIS Ledger v3.2.0

> Enterprise-Grade Version Control and Cloud Orchestration for the QGIS Ecosystem.

**QGIS Ledger** (plugin name: `qgis_ledger`) transforms the conventional QGIS desktop environment into a collaborative, fully distributed geospatial platform. Built for absolute data integrity, it seamlessly introduces a Git-like snapshot architecture, semantic differential geometry analysis, deterministic rollbacks, and integrated native Cloud synchronization.

### 🌟 Key Architecture & Principles
- **Zero External Python Dependencies:** Operates exclusively via the Python standard library, utilizing PyQGIS and native SQLite processing. No `pip install` required.
- **Universal Portability:** Employs dynamic relative path resolution, guaranteeing absolute operational fidelity when migrating projects across Windows, Linux, and MacOS environments.
- **Version Agnosticism:** Fully tested and compliant with **QGIS 3.x** and ready for the next-generation **QGIS 4 (Qt6)** framework.

## 🎥 Video Tutorial

<video src="https://github.com/sag1687/qgis_ledger/blob/tutorial_3.2/tutorial_3-2.m4v" width="320" height="240" controls></video>

> 🇮🇹 **[Guarda il Video Tutorial Completo e scopri come utilizzare QGIS Ledger in azione](https://me.sinocloud.it/index.php/apps/maps/s/RfSi99EWE6iT9ng)**
>
> 🇬🇧 **[Watch the Full Video Tutorial and discover how to use QGIS Ledger in action](https://me.sinocloud.it/index.php/apps/maps/s/RfSi99EWE6iT9ng)**


---

## 🇮🇹 ITALIANO — Descrizione Architetturale

QGIS Ledger è un motore di tracciamento storico e sincronizzazione cloud progettato per l'integrità dei dati spaziali, operante localmente senza l'ausilio di complessi database server (come PostGIS) o layer applicativi esterni.

### Funzionalità Core (Versionamento)
- **Architettura a Snapshot (Commit):** Salva copie esatte e contestuali dei layer vettoriali, raster, o dell'intero workspace (`.qgz`) all'interno di un database transazionale locale SQLite (`.ledger.db`).
- **Locale / LAN Nativo:** Lo storico e le iterazioni temporali sono memorizzate per impostazione predefinita in una cartella a fianco del file di progetto (`.qgz`). Lavorando su una porzione di rete condivisa (LAN), l'intero ecosistema storico è universalmente accessibile e sincronizzato per tutti i membri del team senza configurazioni aggiuntive.
- **Diff Semantico-Visuale:** Un algoritmo basato su logica a differenza simmetrica esplora topologicamente le entità spaziali, iniettando nella mappa layer temporanei che evidenziano visivamente feature *aggiunte* (🟢), *rimosse* (🔴), o *mutate* (🟡) tra due punti della storia.
- **Rollback Deterministico:** Ripristina l'infrastruttura dei metadati e il payload geometrico a qualsiasi iterazione temporale precedente, ricostruendo contestualmente le simbologie associate.
- **Interfaccia di Merge (Risoluzione Conflitti):** Modulo ad analisi split-screen per l'individuazione e la mitigazione di collisioni scaturite da editing asincrono in scenari network-shared.

### Orchestrazione e Sincronizzazione
- **Pannello Timeline Relazionale:** Interfaccia stile GitKraken per la navigazione intra-database dei commit, con supporto alle preview non-distruttive e log visivi istantanei (tramite snapshot PNG generati contestualmente ad ogni commit).
- **Automazione Trigger-Based (Auto-Commit & Auto-Save):** Polling thread-safe e injection negli eventi del Canvas per storicizzare file e vettori ad intervalli cronometrici, assicurando un paracadute costante contro i crash.

### Integrazione Multi-Cloud & File Browser
- **I/O Trasparente (Zero-Pip):** Pieno supporto nativo per Nextcloud, WebDAV generici (Box, Koofr, pCloud, NAS), Dropbox API v2, Microsoft Graph (OneDrive/SharePoint) e Google Drive API v3 (con rinnovo token automatico).
- **Orologio Cloud Nativo:** Dock-widget interno preposto alle operazioni CRUD direttamente su istanze remote Cloud.
- **GeoPackage Serialization On-the-Fly:** La manipolazione file (drag-and-drop da mappa a cloud) innesca un algoritmo di conversione dinamica e auto-encapsulation del layer in file GeoPackage, pre-caricando la logica di stile direzionale della tabella `layer_styles` per massima fedeltà visiva durante il re-import in altre stazioni.

---

## 🇬🇧 ENGLISH — Architectural Overview

QGIS Ledger is a comprehensive historical tracking and cloud synchronization engine engineered for definitive geospatial data persistence, operating entirely without the complexities of heavyweight server databases (e.g. PostGIS) or external application stacks.

### Core Architecture (Versioning)
- **Snapshot Infrastructure (Commit):** Safely persists atomic checkpoints of vector pipelines, raster topologies, or the entire composite `.qgz` workspace inside a robust transactional SQLite database (`.ledger.db`).
- **Native Local / LAN Tracking:** Versions and history are stored natively inside a `.ledger_history` sidecar folder directly alongside your `.qgz` project file. When operating from a shared network drive (LAN), this ensures the full historical state is universally synced and accessible to all team members out-of-the-box, with strictly zero configuration required.
- **Semantic Visual Diff Engine:** Utilizes advanced symmetric-difference geometry algorithms to isolate and spatialy highlight structural modifications—*added* (🟢), *removed* (🔴), or *mutated* (🟡) features—across diverging history branches.
- **Deterministic Rollback Verification:** Instantaneously reconstructs previous infrastructural data schemas and gracefully re-attaches style payloads to guarantee continuous map rendering limits.
- **Conflict Resolution Telemetry (Merge Wizard):** A real-time split-screen interface designed to mitigate and resolve asynchronous overwrite anomalies within inherently shared persistent storage zones.

### Observability & Automation
- **Relational Timeline Panel:** An intuitive, strictly ordered graphical navigator (akin to GitKraken) exposing the underlying database logic, featuring non-destructive layer preview routines backed by instantaneous map-state screen-capturing logic.
- **Silent Trigger Automation:** Hooks into native QGIS Canvas edit lifecycles to trigger silent foreground auto-commits on data writes, alongside asynchronous background polling auto-saves, completely nullifying data-loss vectors.

### Multi-Cloud I/O Integration
- **Dependency-Free Providers:** Implements raw `stdlib` pipelines seamlessly supporting Nextcloud, Generic WebDAV standards (Box, Koofr, NAS), Dropbox API v2, Microsoft Graph (OneDrive/SharePoint), and Google Drive API v3 implementations (capable of token auto-refresh callbacks).
- **Native Extensible Cloud Browser:** Interoperable dock widget empowering local users with fully-fledged CRUD capability over disparate file systems without engaging external internet browsers.
- **On-the-Fly GeoPackage Serialization:** Dragging and dropping dynamic layers off the local canvas directly onto cloud roots invokes immediate format translation into strictly encapsulated GeoPackages—embedding active `.qml` styling definitions seamlessly into its internal `layer_styles` table metadata payload.

---

## 📁 Repository Structure / Struttura File di Progetto

```text
📂 Project Root/
├── my_qgis_project.qgz          ← The QGIS binary project file
├── my_qgis_project.ledger.db    ← SQLite tracking DB for logs, references and versions
└── .ledger_history/             ← Isolated local version-control directory
    ├── project/                 ← Retained snapshots for `.qgz` project rollbacks
    ├── raster/                  ← Compressed archived states for heavy raster grids
    └── screenshots/             ← Automatically generated PNG tracking history contexts
```

---

## 🚀 Installation & Build

1. Clone or copy the entire repository into your local QGIS user profile plugins catalog:
   ```bash
   cp -r qgis_ledger ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
   ```
2. Open QGIS $\rightarrow$ **Plugins** $\rightarrow$ **Manage and Install Plugins** $\rightarrow$ enable **QGIS Ledger** (formerly *sketinel*).
3. The integrated toolbar will immediately hook into your GUI. Configure preferred Cloud providers via the `⚙ Settings` dialog module.

---

## 📄 License & Maintenance

Licensed strictly under the **GNU General Public License v2.0 or subsequent versions**.

Maintained by **Dott. Sarino Alfonso Grande**  
*(sino.grande@gmail.com)*  
[SinoCloud.it](https://sinocloud.it)
