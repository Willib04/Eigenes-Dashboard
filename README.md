# Eigenes Dashboard – Phase 1 & 2: Garmin-Datenzugang

Dieses Projekt liest deine Garmin-Daten (Schlaf, HRV, Ruhepuls, Body Battery,
Stress, Aktivitäten, VO2max, Trainingsstatus, Wettkampfprognosen, Gewicht) aus
Garmin Connect, speichert sie lokal in einer SQLite-Datenbank und macht sie
über einen MCP-Server im Claude-Chat abfragbar.

Alles läuft **lokal auf deinem Mac** – deine Gesundheitsdaten verlassen deinen
Rechner nicht (ausser wenn du sie selbst später an die Claude-API schickst,
das kommt erst in Phase 4 für die Chat-Funktion des Trainingsplans).

## Was ist fertig (Phase 1 + 2)

- Login bei Garmin Connect mit Zwei-Faktor-Unterstützung (MFA), Tokens werden
  lokal gespeichert, damit du dich nicht bei jedem Sync neu einloggen musst.
- SQLite-Datenbank mit Tabellen für Tageswerte, Schlaf, Aktivitäten und
  Wettkampfprognosen.
- Ein Backfill-Skript, das die letzten 90 Tage importiert (für Baselines).
- Ein täglicher Sync (für 1–2x am Tag, z.B. per launchd).
- Ein MCP-Server, mit dem Claude direkt in deine lokale Datenbank schauen kann.
- Tests, die die Umrechnung der Garmin-Rohdaten prüfen.

**Noch nicht enthalten** (kommt in späteren Phasen, nach deinem OK): die
berechneten Kennzahlen (Recovery-Score, Strain, CTL/ATL/TSB, Schlafbedarf),
der Trainingsplan und das eigentliche Dashboard (Web-Oberfläche).

## Wichtiger Hinweis zu den Garmin-Feldnamen

Garmin veröffentlicht keine offizielle, dokumentierte API – die Bibliothek
`garminconnect` (und dieses Projekt) nutzt die internen Endpunkte, die auch
die Garmin-Connect-App verwendet. Die Feldnamen sind gut bekannt und stabil,
können sich aber je nach Uhr/App-Version leicht unterscheiden. Deshalb:

- Jede Rohantwort wird zusätzlich komplett als JSON in der Datenbank
  gespeichert (Spalte `raw_json`). Nichts geht verloren.
- Fehlt ein erwartetes Feld, wird in der Datenbank `NULL` ("keine Daten")
  eingetragen – es wird nichts geschätzt.
- Falls dir nach dem ersten Backfill Werte fehlen, die eigentlich da sein
  sollten (z.B. VO2max oder Trainingsstatus), sag mir das einfach – dann
  schaue ich mir dein `raw_json` an und passe das Mapping in `app/sync.py` an.

## Schritt-für-Schritt-Installation (macOS)

### 1. Python prüfen

Terminal öffnen (Cmd+Leertaste, "Terminal" eingeben) und:

```bash
python3 --version
```

Falls das einen Fehler gibt oder eine Version unter 3.10 zeigt: Python von
https://www.python.org/downloads/macos/ installieren.

### 2. Projekt herunterladen und vorbereiten

```bash
cd ~/Documents
git clone https://github.com/Willib04/Eigenes-Dashboard.git
cd Eigenes-Dashboard
```

(Falls du das Projekt schon hast, reicht `cd` in den Ordner.)

### 3. Virtuelle Umgebung anlegen und Pakete installieren

Eine "virtuelle Umgebung" ist ein abgeschotteter Ordner nur für dieses
Projekt, damit sich nichts mit anderen Python-Projekten auf deinem Rechner
in die Quere kommt.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Wichtig: `source .venv/bin/activate` musst du in jedem NEUEN Terminal-Fenster
wieder ausführen, bevor du eines der Skripte startest (du erkennst es daran,
dass vor deiner Eingabezeile `(.venv)` steht).

### 4. Zugangsdaten eintragen

```bash
cp .env.example .env
open -e .env
```

Trage dort deine Garmin-Connect-E-Mail und dein Passwort ein und speichere.
Die Datei `.env` wird NIE ins Git-Repository hochgeladen (steht in
`.gitignore`).

### 5. Einmaliger Login (mit MFA)

```bash
python3 scripts/login.py
```

Falls du bei Garmin Zwei-Faktor-Anmeldung (MFA) aktiviert hast, fragt das
Skript nach dem Code, den Garmin dir per E-Mail/App schickt. Nach
erfolgreichem Login liegen die Tokens im Ordner `garmin_tokens/` – dieser
Ordner ist bewusst NICHT im Git-Repository (persönliche Zugangsdaten).

### 6. Die letzten 90 Tage importieren

```bash
python3 scripts/backfill.py
```

Das kann ein paar Minuten dauern (bewusst mit kleinen Pausen zwischen den
Anfragen, um Garmins Rate-Limits zu respektieren). Danach liegt deine
Datenbank unter `data/dashboard.db`.

### 7. Tests ausführen (optional, aber empfehlenswert)

```bash
pytest tests/ -v
```

Alle Tests sollten grün sein – sie prüfen die Umrechnung der Garmin-Rohdaten
in die Datenbank-Struktur mit Beispieldaten (nicht deine echten Daten).

### 8. Täglichen Sync automatisieren (launchd)

Damit deine Daten 1–2x täglich automatisch aktualisiert werden, ohne dass du
das Skript von Hand starten musst, richten wir einen launchd-Job ein (macOS'
Version von Cron):

```bash
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.eigenesdashboard.sync.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.eigenesdashboard.sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>REPLACE_WITH_VENV_PYTHON</string>
        <string>REPLACE_WITH_PROJECT_PATH/scripts/sync_daily.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>19</integer><key>Minute</key><integer>0</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/data/sync.log</string>
    <key>StandardErrorPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/data/sync.log</string>
</dict>
</plist>
EOF
```

Danach `REPLACE_WITH_VENV_PYTHON` (Ausgabe von `which python3` bei
aktivierter `.venv`) und `REPLACE_WITH_PROJECT_PATH` (Ausgabe von `pwd` im
Projektordner) in der Datei ersetzen, dann laden mit:

```bash
launchctl load ~/Library/LaunchAgents/com.eigenesdashboard.sync.plist
```

Das synct morgens um 7 Uhr und abends um 19 Uhr – zweimal täglich, wie in
den Vorgaben gewünscht.

### 9. MCP-Server mit Claude verbinden

Damit du im Claude-Chat direkt über deine Daten sprechen kannst, trage den
Server in die MCP-Konfiguration ein (z.B. für Claude Desktop unter
`~/Library/Application Support/Claude/claude_desktop_config.json`, für
Claude Code über `claude mcp add`):

```bash
claude mcp add garmin-dashboard REPLACE_WITH_VENV_PYTHON REPLACE_WITH_PROJECT_PATH/mcp_server/server.py
```

Oder manuell in der JSON-Konfiguration:

```json
{
  "mcpServers": {
    "garmin-dashboard": {
      "command": "REPLACE_WITH_VENV_PYTHON",
      "args": ["REPLACE_WITH_PROJECT_PATH/mcp_server/server.py"]
    }
  }
}
```

Nach einem Neustart von Claude kannst du z.B. fragen: "Wie war mein Schlaf
letzte Nacht laut meinem Dashboard?" – Claude ruft dann `get_sleep` auf und
liest direkt aus deiner lokalen Datenbank (kein neuer Garmin-Login nötig).

## Projektstruktur

```
app/
  config.py       - liest .env
  garmin_client.py - Login, Token-Speicherung, Rate-Limit-Schutz
  db.py           - SQLite-Helfer
  schema.sql       - Tabellen-Definition
  sync.py         - Garmin-Rohdaten -> Datenbank-Zeilen
scripts/
  login.py        - einmaliger Login mit MFA
  backfill.py     - 90-Tage-Import
  sync_daily.py   - täglicher Sync (für launchd)
mcp_server/
  server.py       - MCP-Server für den Claude-Chat
tests/            - Tests mit Beispieldaten (keine echten Garmin-Zugänge nötig)
data/dashboard.db - deine lokale Datenbank (nicht in Git)
garmin_tokens/    - deine Login-Tokens (nicht in Git)
.env              - deine Zugangsdaten (nicht in Git)
```

## Nächste Schritte

Sag mir, wenn Login und Backfill bei dir funktioniert haben (und ob dabei
Felder als "keine Daten" auftauchen, die eigentlich vorhanden sein sollten).
Danach geht es mit **Phase 3** weiter: Recovery-Score, Strain, CTL/ATL/TSB,
Schlafbedarf und die anderen berechneten Kennzahlen – inklusive der
Gewichtungs-Konfiguration, die du selbst anpassen kannst.
