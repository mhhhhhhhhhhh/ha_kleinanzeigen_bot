# Tatsächlicher Prüfbericht – Version 0.2.0

Stand: 26. November 2026. Zehn lokale Prüfdurchläufe wurden tatsächlich ausgeführt.
Die Testsuite wurde während der Bearbeitung um weitere Fehlerfälle erweitert.
Die letzten drei vollständigen Durchläufe bestanden jeweils **115 Tests**, ohne übersprungene Tests.

## Ergebnisse

| Durchlauf | Bestanden | Fehlgeschlagen | Schwerpunkt |
| --- | ---: | ---: | --- |
| 1 | 57 | 1 | API, Online-Import, Dateisicherheit, Bildzuordnung und echte PTY-Prozesse mit Offline-CLI |
| 2 | 82 | 0 | Template-Pfad korrigiert; Scheduler, Intervallgrenzen, Neustart und Veröffentlichungssperren ergänzt |
| 3 | 86 | 0 | Manuelle Veröffentlichung abgesichert; JavaScript-Syntax und echte Chromium-UI-Tests ergänzt |
| 4 | 90 | 0 | Verlängerung als ein Browserauftrag; Ablaufgrenzen, manuelle Unsicherheitsfälle und Neustart-Backoff |
| 5 | 98 | 1 | Expliziter Online-Neuimport, Fehler ohne Datenverlust, Projekt-/Ingress-/Docker-Verträge und UI-ID-Prüfung |
| 6 | 102 | 0 | Download-Konfiguration im CLI-Test korrigiert; echte Bilddaten, Prozessgruppen und Token-Isolation geprüft |
| 7 | 106 | 0 | Native YAML-Zeitstempel, beschädigter Zustand, Umgebungs-Konto, Dokumentation und CI-Builddefinition |
| 8 | 115 | 0 | Zusätzliche Randfälle: Pfad-Aliase, CRLF-Dateien, API-Typen und veralteter Online-Stand vor fälliger Automatik |
| 9 | 115 | 0 | Stabilitätswiederholung der vollständigen 115 Tests mit verändertem Python-Hashseed |
| 10 | 115 | 0 | Finaler vollständiger Regressionstest: API, Automatik, echte Chromium-UI und Projektprüfungen |

### Gefundene und korrigierte Fehler

- Durchlauf 1: Flask fand beim dynamischen Testimport die Vorlage nicht. Der Templateordner
  wird jetzt ausdrücklich relativ zur Serverdatei bestimmt.
- Durchlauf 5: Der Offline-CLI-Ersatz ignorierte `download.dir`. Der Testersatz wurde korrigiert;
  anschließend bestand der Test für Download in einen Zwischenordner mit Erhalt der Originaldatei.
- Zusätzlich bei Review/Regression abgesichert: native YAML-Zeitstempel im JSON-Formular,
  CRLF-Konfigurationsrevisionen, eindeutige Dateipfade, API-Eingabetypen, Intervallgrenzen,
  dauerhafte Veröffentlichungssperren sowie aktuelle Online-Abfragen für fällige Zeitpläne.

Die Rohprotokolle liegen unter `test-evidence/round-01.log` bis `round-10.log`.
`tested-source.json` enthält SHA-256-Fingerabdrücke der geprüften Programmdateien.

## Tatsächlich geprüft

- Python-Syntax aller Projektdateien und JavaScript-Syntax über den verfügbaren Node-Prozess.
- HTTP-API: JSON-/CSRF-Prüfung, Dateipfade, Symlinks, Revisionskonflikte und private Zugangsdaten.
- Vollständiger Import einer Offline-Testliste mit 37 Anzeigen in mehreren Downloadbatches.
- Gemeinsame Darstellung von Online-Snapshot und lokalen Arbeitsdateien.
- Beibehaltung lokaler Änderungen beim normalen Abgleich; expliziter Online-Neuimport über Staging.
- Daten-, Bild- und Sonderattributerhalt beim Bearbeiten/Wiederveröffentlichen.
- Decode-Prüfung von Uploads und WEBP-zu-JPG-Konvertierung im tatsächlich vorhandenen Pillow.
- Echte Linux-PTYs und echte Unterprozesse: Login-ENTER, Sperre paralleler Jobs, Stoppen,
  Prozessgruppen inklusive Nachkommen, Zeitlimit und geschwärzte Protokolle.
- Scheduler: opt-in, vollständige Tagesintervalle, neue ID, fehlende/reservierte Anzeigen,
  gebündelte Verlängerung, Neustart, Backoff und kein blindes Wiederholen unklarer Veröffentlichungen.
- Vier echte headless-Chromium-Tests gegen einen lokalen Flask-Server: initiale Anzeigen,
  Formularbearbeitung, Zeitplan trotz ungespeicherter Formularänderung, mobile Ansicht,
  neue lokale Anzeige und Bild-Upload. Es wurden keine JavaScript-Seitenfehler festgestellt.
- Home-Assistant-Manifest und Proxy-/Dockerfile-Verträge als statische Prüfungen.

## Grenzen der Prüfung

Der Original-Bot wurde aus seinen verfügbaren Repository-Dateien und dokumentierten CLI-Verträgen
analysiert, aber in dieser Arbeitsumgebung nicht installiert oder gegen ein echtes Konto gestartet.
Bot-Aufrufe in Tests verwenden ausschließlich `tests/fake_bot.py`. Dessen Ausgaben und Verhalten
bilden die erwartete Schnittstelle ab; das ist kein Nachweis der aktuellen Kleinanzeigen-Website.

Die verfügbaren Browser wurden tatsächlich verwendet. Dagegen stand hier kein Docker- bzw.
Home-Assistant-Supervisor-System zur Verfügung. **Nicht durchgeführt:**

- Docker-Build auf amd64 und aarch64 samt Installation der realen Upstream-Abhängigkeiten.
- Startprüfung von nginx, Xvfb, Chromium und noVNC innerhalb des gebauten Add-on-Containers.
- Anmeldung, CAPTCHA/Gerätebestätigung und Online-Aktionen im eigenen Kleinanzeigen-Konto.
- Echte Home-Assistant-Ingress-/WebSocket-Verbindung.
- End-to-End-Prüfung des echten Original-Bots: mehrseitige Liste, Bilddownload, Update,
  Verlängerung, Reservierung, Löschung und Wiederveröffentlichung.

Die fehlenden Integrationsprüfungen sind auch im Manifest durch `stage: experimental` berücksichtigt.
Die neue GitHub-Actions-Datei definiert Tests und Docker-Builds für beide Architekturen,
**wurde hier jedoch weder gepusht noch auf GitHub ausgeführt**.

`wcmatch` war in der lokalen Python-Testumgebung nicht installiert. Die Offline-Tests nutzten
für Bildglobs die mitgelieferte Standardglob-/Brace-Alternative. Im Docker-Build wird das vom
Original-Bot benötigte `wcmatch` installiert; der Produktionspfad nutzt dessen Glob-Engine.

## Nach dem Einspielen auf dem Zielsystem

1. Image bauen und Add-on-Protokoll auf erfolgreichen Start prüfen.
2. Browserdesktop über Ingress öffnen, manuell anmelden und ENTER senden.
3. Online synchronisieren; Anzahl und fehlende Detaildownloads mit dem Konto vergleichen.
4. An einer einzelnen geeigneten Anzeige Prüfung und Update ausführen.
5. Verlängerung einer Anzeige im Verlängerungsfenster bestätigen.
6. Nach Freigabe eine einzelne Wiederveröffentlichung prüfen: neue ID, vollständige Bilder/Daten,
   alte Anzeige erst nach Bestätigung entfernt, aktualisierte Arbeitsdatei und weiterlaufender Zeitplan.

Erst diese Zielsystemprüfungen können den realen Betrieb bestätigen.
