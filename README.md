# Eigenes Dashboard – Phase 1–5

Dieses Projekt liest deine Garmin-Daten (Schlaf, HRV, Ruhepuls, Body Battery,
Stress, Aktivitäten, VO2max, Trainingsstatus, Wettkampfprognosen, Gewicht) aus
Garmin Connect, speichert sie lokal in einer SQLite-Datenbank und macht sie
über einen MCP-Server im Claude-Chat abfragbar.

Alles läuft **lokal auf deinem Mac** – deine Gesundheitsdaten verlassen deinen
Rechner nicht (ausser wenn du die Chat-Funktion nutzt: dann gehen dein aktueller
Bericht + Trainingsplan als Kontext an die Claude-API, siehe Phase 4 unten).

## Was ist fertig (Phase 1 + 2)

- Login bei Garmin Connect mit Zwei-Faktor-Unterstützung (MFA), Tokens werden
  lokal gespeichert, damit du dich nicht bei jedem Sync neu einloggen musst.
- SQLite-Datenbank mit Tabellen für Tageswerte, Schlaf, Aktivitäten und
  Wettkampfprognosen.
- Ein Backfill-Skript, das die letzten 90 Tage importiert (für Baselines).
- Ein täglicher Sync (für 1–2x am Tag, z.B. per launchd).
- Ein MCP-Server, mit dem Claude direkt in deine lokale Datenbank schauen kann.
- Tests, die die Umrechnung der Garmin-Rohdaten prüfen.

## Was ist fertig (Phase 3)

- **Baselines**: gleitender 28-Tage-Durchschnitt + Standardabweichung für
  HRV (als ln rMSSD) und Ruhepuls – schliesst den aktuellen Tag selbst aus,
  damit die Baseline nicht durch den zu bewertenden Tag verzerrt wird.
- **Recovery-Score (0–100 %)**: gewichtet aus HRV-, Ruhepuls-,
  Schlafleistungs- und Atemfrequenz-Abweichung zur Baseline. Ampel: grün
  ≥ 67, gelb 34–66, rot < 34. Gewichtungen stehen in `app/metrics_config.py`
  und sind frei anpassbar (Standard: HRV 50 %, Ruhepuls 20 %, Schlaf 20 %,
  Atmung 10 %).
- **Strain (0–21)**: TRIMP nach Banister aus Herzfrequenz + Dauer je
  Aktivität, logarithmisch auf 0–21 abgebildet (WHOOP-ähnlich). Garmins
  eigener Training Load wird zusätzlich angezeigt.
- **CTL/ATL/TSB**: Fitness (42-Tage-Mittel), Ermüdung (7-Tage-Mittel), Form
  = CTL − ATL. **ACWR** (akut:chronisch, 7:28 Tage) mit Warnung > 1,5 und
  Hinweis < 0,8.
- **Schlafbedarf heute Nacht**: Grundbedarf (Start: 8 h) + Aufschlag nach
  dem Strain des Tages + anteiliger Abbau der Schlafschuld der letzten 7
  Nächte. Dazu eine empfohlene Zubettgehzeit (Weckzeit werktags 06:30,
  Wochenende 08:30 – ebenfalls in `app/metrics_config.py` anpassbar).
- **Tagesempfehlung**: Ziel-Strain-Korridor + konkreter Vorschlag aus
  Recovery-Ampel, TSB und ACWR.
- **Warnsignal** (vorsichtig formuliert, keine Diagnose): wenn HRV und
  Ruhepuls mehrere Tage in Folge gemeinsam in die ungünstige Richtung
  abweichen.
- Alle Formeln sind in `app/metrics.py` als kleine, einzeln testbare
  Funktionen umgesetzt (33 Tests), die Verknüpfung mit der Datenbank steckt
  in `app/report.py` (2 weitere Tests mit realistischen Beispieldaten).

**Dein HFmax** steht aktuell auf **195** (dein bisher höchster gemessener
Puls, 17.09., Laufen – höher als die Tanaka-Schätzformel 208−0,7×Alter=193).
Falls du später höher kommst, einfach `HF_MAX` in `app/metrics_config.py`
erhöhen.

### Bericht ansehen

```bash
python3 scripts/report.py           # heute
python3 scripts/report.py 2026-09-20   # ein bestimmtes Datum
```

Im Claude-Chat (nach MCP-Einbindung, siehe unten) kannst du fragen: "Wie ist
mein Recovery-Score heute?" – Claude ruft dann `get_computed_report` auf.

## Dashboard (Web-Oberfläche, Phase 5 – Startseite "Heute")

```bash
python3 scripts/dashboard.py
```

Startet einen Server und öffnet automatisch `http://127.0.0.1:8000` im
Browser auf deinem Mac. Beenden mit `Ctrl+C` im Terminal.

Alle acht Reiter sind fertig und klickbar:

- **Heute**: Recovery (Ampel-Ring), Recovery-Teilwerte im Detail, Strain,
  Schlafbedarf + Zubettgehzeit, Tagesempfehlung, CTL/ATL/TSB/ACWR. Jede Karte
  hat einen ⓘ-Button mit Formel + deinen echten Ausgangswerten (z.B. "HRV
  45 ms, Baseline 46 ms").
- **Schlaf**: Schlafphasen der letzten Nacht, Dauer-/Score-Verlauf,
  Schlafkonsistenz.
- **Erholung**: Recovery-Score-Verlauf, HRV/Ruhepuls mit Baseline, Body
  Battery, Stress.
- **Belastung**: CTL/ATL-, TSB-, Strain- und ACWR-Chart mit Zeitraum-Filter.
- **Trainingsplan**: dein periodisierter Plan als Wochenliste mit
  Soll/Ist-Ampel, Erfüllungsquote und "An Garmin senden"-Button je Einheit
  (siehe Phase 4 unten).
- **Aktivitäten**: Liste mit Dauer, Distanz, Pace, Puls, Trainingsbelastung.
- **Trends**: VO2max-Verlauf, aktuelle Wettkampfprognosen, Schlafkonsistenz.
- **Chat**: mit Claude über deine Daten/deinen Plan sprechen (Phase 4).

Alle Charts sind eigene, leichte SVG-Grafiken (kein Framework): dünne Linien,
Baseline zum Vergleich, Hover-Tooltip mit Fadenkreuz, 4/12/26 Wochen bzw.
7/30/90 Tage/1 Jahr umschaltbar.

Die Seite liest nur aus deiner lokalen Datenbank (kein Garmin-Login nötig),
du kannst sie also jederzeit neu laden, auch offline.

### Auf dem Handy ansehen (im selben WLAN)

`scripts/dashboard.py` gibt beim Start zwei Adressen aus:

```
Dashboard auf diesem Mac:              http://127.0.0.1:8000
Dashboard vom Handy (im selben WLAN):  http://192.168.x.x:8000
```

Die zweite Adresse auf dem Handy im Browser öffnen (Safari/Chrome) –
Voraussetzung: Handy und Mac sind im selben WLAN. Beim allerersten Start
fragt macOS eventuell "Eingehende Netzwerkverbindungen zulassen?" – das mit
**Erlauben** bestätigen (sonst blockiert die macOS-Firewall den Zugriff vom
Handy). Einen Shortcut/ein Lesezeichen auf dem Handy-Homescreen anlegen
("Zum Home-Bildschirm hinzufügen" in Safari), dann fühlt es sich fast wie
eine eigene App an.

**Einschränkung:** das funktioniert nur, wenn dein Mac an ist, im selben
WLAN wie das Handy hängt und `scripts/dashboard.py` läuft. Für Zugriff von
unterwegs (mobiles Netz, nicht zuhause) bräuchte es zusätzlich ein
VPN-Tool wie Tailscale – sag Bescheid, falls du das später willst.

### Dashboard automatisch im Hintergrund starten (optional)

Damit du nicht jedes Mal `scripts/dashboard.py` von Hand starten musst,
kannst du es analog zum Sync-Job (Schritt 8 oben) per launchd beim Login
automatisch im Hintergrund starten lassen:

```bash
cat > ~/Library/LaunchAgents/com.eigenesdashboard.web.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.eigenesdashboard.web</string>
    <key>ProgramArguments</key>
    <array>
        <string>REPLACE_WITH_VENV_PYTHON</string>
        <string>REPLACE_WITH_PROJECT_PATH/scripts/dashboard.py</string>
        <string>--no-browser</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/data/dashboard-web.log</string>
    <key>StandardErrorPath</key>
    <string>REPLACE_WITH_PROJECT_PATH/data/dashboard-web.log</string>
</dict>
</plist>
EOF
```

`REPLACE_WITH_VENV_PYTHON`/`REPLACE_WITH_PROJECT_PATH` wie in Schritt 8
ersetzen, dann laden mit
`launchctl load ~/Library/LaunchAgents/com.eigenesdashboard.web.plist`.
Danach läuft das Dashboard immer im Hintergrund (auch nach einem Neustart
des Mac), du musst morgens nur noch die Handy-Adresse im Browser öffnen.

## Trainingsplan + Chat (Phase 4)

**Trainingsplan**: Im Reiter "Trainingsplan" kannst du (falls noch keiner
existiert) einen Plan erstellen – Standard: 4 Wochen, 5 km, unter 20:00 Minuten
(anpassbar im Formular oder dauerhaft in `app/plan_config.py`). Der Plan ist
ein einfacher, transparenter Schärfungs-/Taper-Block (80/20-Verteilung, max.
10 % Umfangssteigerung pro Woche, Zielpace/Intervall-/Schwellenpace aus deiner
Zielzeit berechnet, letzte Woche = Taper mit Wettkampf/Zeitfahren am Ende).
Der Soll/Ist-Abgleich läuft automatisch: sobald eine passende Aktivität an
einem geplanten Tag synchronisiert ist, zeigt die Zeile "erledigt".

**An Garmin senden**: Jede Einheit hat einen eigenen Button – nichts wird
automatisch gesendet. ⚠️ **Diese Funktion konnte nicht gegen einen echten
Garmin-Account getestet werden** (kein Testzugang verfügbar). Probier sie
zuerst mit einer unkritischen, lockeren Einheit aus und prüfe danach in der
Garmin-Connect-App, ob der Workout korrekt ankommt, bevor du dich darauf
verlässt.

**Chat**: Trag deinen Claude-API-Key in die `.env` ein (`ANTHROPIC_API_KEY=...`,
einen Key bekommst du unter https://console.anthropic.com/), dann Dashboard
neu starten. Claude sieht deinen aktuellen Bericht + Plan und kann z.B. auf
"Ich bin Dienstag krank, verschieb die Einheit" reagieren – Änderungen werden
NIE automatisch übernommen, sondern erst nach Klick auf "Übernehmen" im Chat.
Claude kann nur bestehende Plan-Einheiten verschieben, streichen oder
inhaltlich anpassen, keine komplett neuen Tage hinzufügen.

**Noch nicht enthalten**: der wöchentliche Bericht (jeden Montag), der laut
Aufgabenstellung eine Zusammenfassung + Ausblick geben soll.

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
  config.py         - liest .env
  garmin_client.py  - Login, Token-Speicherung, Rate-Limit-Schutz
  db.py             - SQLite-Helfer
  schema.sql        - Tabellen-Definition
  sync.py           - Garmin-Rohdaten -> Datenbank-Zeilen
  metrics.py        - Berechnungsformeln (Recovery, Strain, CTL/ATL/TSB, ...)
  metrics_config.py - Gewichtungen/Schwellenwerte, anpassbar
  report.py         - verbindet DB + Formeln zu Berichten/Trends
  plan.py           - Trainingsplan-Generator, Soll/Ist, Garmin-Upload
  plan_config.py    - Ziel/Wochen/Trainingstage, anpassbar
  chat.py           - Claude-API-Anbindung fuer den Chat-Reiter
  web.py            - FastAPI-Backend (JSON-API + statisches Frontend)
scripts/
  login.py        - einmaliger Login mit MFA
  backfill.py     - 90-Tage-Import
  sync_daily.py   - täglicher Sync (für launchd)
  report.py       - Kommandozeilen-Bericht
  dashboard.py    - startet das Web-Dashboard
mcp_server/
  server.py       - MCP-Server für den Claude-Chat
web/              - Frontend (HTML/CSS/vanilla JS, kein Framework)
tests/            - Tests mit Beispieldaten (keine echten Garmin-Zugänge nötig)
data/dashboard.db - deine lokale Datenbank (nicht in Git)
garmin_tokens/    - deine Login-Tokens (nicht in Git)
.env              - deine Zugangsdaten (nicht in Git)
```

## Nächste Schritte

Alle fünf Phasen aus der ursprünglichen Aufgabenstellung stehen jetzt (bis auf
den wöchentlichen Bericht). Probier vor allem den Trainingsplan und - falls du
einen Claude-API-Key hast - den Chat aus, und sag mir, was noch fehlt oder
nicht passt (z.B. andere Trainingstage im Plan, andere Formulierungen, ein
Garmin-Sende-Test der schiefgegangen ist).
