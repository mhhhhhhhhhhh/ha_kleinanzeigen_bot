# Einrichtung und Betrieb

## 1. Upgrade auf 0.2.0

1. Bestehende Add-on-Daten über Home Assistant sichern.
2. Add-on stoppen. Nicht deinstallieren; dabei könnten die Daten entfernt werden.
3. Die Dateien aus `kleinanzeigen_bot/` in den gleichnamigen bestehenden Add-on-Ordner übernehmen.
   Insbesondere die neue Datei `bot-entry.sh` und beide Module `app/storage.py` / `app/engine.py` mit übernehmen.
4. Lokale Add-on-Quellen neu laden und aktualisieren bzw. das Image neu erstellen.
5. Add-on starten und dessen Weboberfläche öffnen.

Der `slug` ist unverändert `ha_kleinanzeigen_bot`, damit die bestehende Add-on-Installation
und ihr Datenverzeichnis weiterverwendet werden können. Bereits vorhandene `config.yaml`,
Anzeigen und Browsersitzung werden beim Start behalten. Die neue Auftrags-/Automatikverwaltung
legt `/data/state/engine.json` an. Der alte 0.1.0-Auftragsverlauf wird nicht in diese neue
Historie übernommen; er bleibt im Datenverzeichnis verfügbar.

Bei einer frischen Installation nur `kleinanzeigen_bot/` nach `/addons/kleinanzeigen_bot/`
kopieren. Nicht das gesamte ZIP-Oberverzeichnis als Add-on-Ordner verwenden.

## 2. Konto und erste Anzeigen

1. Unter **Konto** E-Mail und Passwort speichern.
2. **Manuell anmelden** starten; im Browserdesktop Anmeldung und Gerätebestätigung abschließen.
3. Im Browserdesktop **ENTER senden**, damit der Original-Bot den Login prüft.
4. **Meine Anzeigen → Online synchronisieren** ausführen.

Danach zeigt die Startseite alle Anzeigen des vom Bot vollständig abgerufenen Online-Standes.
Fehlende lokale Anzeigen werden automatisch mit ihren Bildern importiert. Bereits gespeicherte
Anzeigen werden bei gewöhnlicher Synchronisierung nicht überschrieben.

Die Oberfläche startet bei aktiviertem Online-Abgleich einen Erstabgleich, wenn ein Konto
konfiguriert ist und der Stand nicht gerade frisch ist. Der Scheduler läuft unabhängig
von einem geöffneten Browser alle 30 Sekunden und entscheidet, ob ein Auftrag fällig ist.
Es läuft immer nur ein Bot-/Browserauftrag.

Falls ein Detaildownload fehlschlägt, bleibt die Online-Anzeige mit einem Hinweis sichtbar.
Bei fehlgeschlagener Online-Abfrage bleibt der letzte erfolgreiche Stand mit Fehlerhinweis
sichtbar; eine leere Erfolgsmeldung wird nicht vorgetäuscht.

## 3. Bearbeiten

**Bearbeiten** öffnet das Formular. Lokales Speichern verändert zunächst nur die Arbeitsdatei.
**Online aktualisieren** überträgt anschließend die gespeicherten Daten.

Kategorie, Kontakt, Versandoptionen und Sonderattribute lassen sich im YAML/JSON-Editor vollständig
bearbeiten. Das Formular erhält Felder, die es selbst nicht anzeigt. Zwischen Formular und
Rohtexteditor wechseln verwirft Änderungen nur nach Rückfrage.

Bilder werden im Unterordner `images/` direkt neben der gewählten Anzeigen-Datei gespeichert.
Dadurch stimmen die relativen Pfade auch bei importierten Anzeigen in Unterordnern.
Uploads werden tatsächlich decodiert und als JPG gespeichert; Dateiendung oder Signatur allein
reichen nicht. Pfeile ändern die Bild-Reihenfolge; Entfernen entfernt die Zuordnung, nicht die
Bilddatei. Danach **Lokal speichern**.

Wenn eine Anzeige außerhalb des Add-ons geändert wurde: **Von online neu laden**. Dabei wird
lokaler Inhalt nach Bestätigung durch einen vollständig heruntergeladenen Online-Stand ersetzt.
Zuerst entsteht ein Backup einschließlich Bildern. Arbeitsdateipfad, Zeitplan und lokale
Wiederveröffentlichungs-/Preisreduktionszähler bleiben erhalten.

Bot-ID, Zeitstempel und Zähler können im Webeditor nicht verändert werden. Gleichzeitige
Änderungen werden über eine Dateirevision erkannt; statt stillen Überschreibens erscheint ein
Konflikt. Während eines Bot-Auftrags sind Speicheraktionen gesperrt.

## 4. Automatisch verlängern

Unter **Automatik** die Option **Aktive Anzeigen automatisch verlängern** einschalten und
bestätigen. Standardmäßig ist diese Online-Schreibautomatik aus. Standard-Prüfintervall: sechs Stunden.

Bei Fälligkeit wird der Online-Stand abgerufen, fehlende Anzeigen werden importiert, und geeignete
aktive Anzeigen innerhalb von acht Tagen vor Ablauf werden in einem Browserauftrag an `extend`
übergeben. Bei fehlendem Ablaufdatum entscheidet der Original-Bot. Reservierte Anzeigen bleiben
unberührt. Eine Verlängerung erhält die ID; sie ist kein Neuveröffentlichen.

Eine bereits abgelaufene Anzeige lässt sich nicht zuverlässig wie eine noch aktive Anzeige
verlängern. Diese Automatik setzt deshalb vor dem Ablauf an.

## 5. Nach X Tagen neu anlegen

1. Aktive importierte Anzeige öffnen.
2. **Automatisch neu einstellen** einschalten.
3. Gewünschte ganze Anzahl von 1 bis 365 Tagen eintragen.
4. **Zeitplan speichern** und die Wiederveröffentlichung bestätigen.

Die erste Frist beginnt mit dem gespeicherten letzten Veröffentlichungszeitpunkt
(`updated_on`, sonst `created_on`). Fehlt ein brauchbarer Zeitpunkt, beginnt sie bei Aktivierung.
Bei einer älteren Anzeige kann der erste Neuauftrag daher bereits fällig sein.
Danach zählt ein volles Intervall ab der zuletzt bestätigten Neuveröffentlichung.
Eine Verlängerung startet den Neuveröffentlichungszeitplan nicht neu.

Der Zeitplaner nimmt nur ausdrücklich aktivierte Anzeigen. Er übergibt genau die betreffende
Arbeitsdatei mit ihren Daten und Bildern an `publish`, nicht global `--ads=due` für alle Dateien.
`publish` erzeugt eine neue ID. Alte Anzeigen werden über `AFTER_PUBLISH` erst nach erfolgreicher
Veröffentlichung gelöscht; titelbasierte Löschsuche ist für die Einzelaufträge abgeschaltet.
Die neue ID wird in derselben Arbeitsdatei gespeichert. Die Ordner müssen nicht umbenannt werden.

Bei aktivierter Original-Bot-Preisreduktionsoption kann dieser den Veröffentlichungspreis ändern.
Ohne diese separat konfigurierte Option werden die gespeicherten Preisdaten verwendet.

Reservierte, fehlende, lokal deaktivierte oder doppelt gespeicherte Anzeigen-IDs werden nicht
automatisch neu veröffentlicht. Fehlende Bilder verhindern den Start einer Veröffentlichung.
Automatik braucht einen aktuellen Online-Stand. Den regelmäßigen Online-Abgleich deshalb anlassen.

## 6. Unklare Veröffentlichung / Neustart

Vor einer Veröffentlichung wird ein dauerhaftes Journal gespeichert. Erst eine erfolgreich
beendete Aktion mit neuer gespeicherter Anzeigen-ID hebt die Sperre auf. Bei Fehler, Zeitlimit,
Stoppen oder Neustart während unbestätigter Veröffentlichung wird nicht automatisch erneut publiziert.

Im eigenen Kleinanzeigen-Konto prüfen, ob eine neue Anzeige erstellt wurde. Anschließend
synchronisieren und nötigenfalls doppelte Anzeigen bzw. lokale Duplikate bereinigen. Erst danach
im Anzeigeneditor **Sperre nach Prüfung aufheben** bestätigen. Dieser Schritt startet bewusst ein
neues volles Intervall ab jetzt. Eine einzelne zurückgegebene Exit-0-Meldung ohne neue ID gilt
nicht als bestätigte Wiederveröffentlichung.

## 7. Pfade und Backups

| Pfad | Inhalt |
| --- | --- |
| `/data/workspace/config.yaml` | Original-Bot-Konfiguration |
| `/data/workspace/.credentials.json` | Zugangsdaten, privat gespeichert, nicht verschlüsselt |
| `/data/workspace/browser-profile/` | Standard-Browsersitzung einer neuen Installation |
| `/data/workspace/ads/` | Eigene lokale Arbeitsdateien |
| `/data/workspace/downloaded-ads/` | Importierte Arbeitsdateien und Bilder |
| `/data/state/engine.json` | Zeitpläne, Sicherheitsjournale, Online-Snapshot, Verlauf |
| `/data/state/backups/` | Letzte zehn Textversionen bearbeiteter Dateien |
| `/data/state/archives/` | Letzte drei Bild-/Datensicherungen je bearbeiteter Online-Anzeige |

In einem Archiv liegt `original.yaml` als Originaltext sowie `restore.yaml` mit relativ zu
mitgesicherten Bildern auflösbaren Pfaden. Für eine Wiederherstellung Daten sichern und Add-on
stoppen; den Archivinhalt in einen Arbeitsordner unter `ads/` übernehmen. Eine bereits veraltete
Online-ID nicht ohne Abgleich erneut verwenden. Textbackups behalten die Originalendung im
Separatverweis `path.txt`; auch JSON-Quellen bleiben im Archiv inhaltlich erkennbar.

## 8. Original-Bot-Build

Das Dockerfile installiert den Original-Bot aus Git-Quellcode und führt dessen
`fix_nodriver.py` aus. `BOT_REF` ist standardmäßig `main`. Für nachvollziehbare Builds eine volle
Commit-SHA übergeben. `/opt-bot-commit.txt`, `/opt-bot-version.txt` und
`/opt-bot-dependencies.txt` dokumentieren das tatsächlich gebaute Image.

```bash
docker build --build-arg BUILD_ARCH=amd64 --build-arg BOT_REF=main   -t ha-kleinanzeigen-bot:0.2.0 kleinanzeigen_bot/
```

`main` und nicht exakt fixierte Python-/Debian-Abhängigkeiten können sich ändern. Die UI liest
die englische `list`-Blockausgabe des ausgewählten Bots. Ein verändertes oder unvollständiges
Format führt zu einem sichtbaren Fehler statt einer vermeintlich leeren Anzeigenliste.

Bei Anzeigen mit einer Paketauswahl kann die Original-Bot-Standardeinstellung `MANUAL`
eine Bestätigung im Browser erfordern. Für automatische Auswahl des vom Bot verifizierten
kostenlosen Basispakets die Original-Option `publishing.package_selection: BASIS` ausdrücklich
in der Konfiguration setzen. Gerätebestätigung und CAPTCHA können weiterhin eine manuelle
Browseraktion erfordern; das wird nicht durch die lokale Automatik beseitigt.

Der Build prüft, ob `list` und `extend` in der Bot-Hilfe vorhanden sind. Diese Build-Prüfung
ersetzt keinen echten Login-/Anzeigentest.

## 9. Tests wiederholen

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt playwright
python -m playwright install --with-deps chromium
python tests/run_ten.py
```

Ohne installiertes Playwright/Chromium werden Browsertests explizit übersprungen.
Die hier dokumentierten Chromium-Tests wurden tatsächlich ausgeführt, nicht übersprungen.
Alle Tests sprechen nur die lokale Offline-CLI an. Docker und echter Home-Assistant-Ingress
müssen auf einem geeigneten Zielsystem geprüft werden.
