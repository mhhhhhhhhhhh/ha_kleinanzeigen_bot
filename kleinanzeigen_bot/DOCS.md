# Installation und Bedienung

## Voraussetzungen

Home Assistant OS mit App-/Add-on-Verwaltung (Supervisor). Die Add-on-Struktur
kann auch ein vorhandener Supervisor verwenden. Home Assistant Container
oder eine reine Core-Installation kann dieses Paket nicht als Add-on
installieren. Vorgesehen sind amd64 (x86-64) und aarch64 (64-Bit ARM).
32-Bit ARM wird nicht unterstützt.

Als praktische Planungsgröße etwa 2 GB freier RAM für Chromium plus
Desktop und ausreichend freien Speicher für Image, Anzeigen und Bilder
vorsehen. Das ist eine Schätzung, keine gemessene Mindestanforderung.

## Als lokales Add-on installieren

1. ZIP auf einem Rechner entpacken.
2. Den vollständigen Ordner `kleinanzeigen_bot` in das lokale
   Home-Assistant-Verzeichnis `/addons/` kopieren. Mit Samba entspricht das
   üblicherweise `addons/kleinanzeigen_bot`. Nicht unter `/config/addons/`
   ablegen. Wenn die addons-Freigabe nicht verfügbar ist, über einen geeigneten
   Datei-/Terminal-Zugang auf das lokale Add-on-Verzeichnis zugreifen.
3. Im App-/Add-on-Store die Quellen über das Drei-Punkte-Menü neu laden bzw.
   nach Updates suchen. Das Add-on erscheint unter den lokalen Apps/Add-ons.
4. **Kleinanzeigen Bot mit Web-GUI** installieren. Der Supervisor baut das
   Docker-Image auf dem Gerät. Der erste Build benötigt Internetzugang zu den
   Debian-Paketquellen und GitHub und kann mehrere Minuten dauern.
5. Add-on starten, Protokoll auf Startfehler prüfen und **Weboberfläche öffnen**
   auswählen. Optional die Seitenleistenanzeige aktivieren.

Der ZIP-Download ist keine URL, die direkt als Store-Repository eingetragen
werden kann. Für diese Installationsart zuerst den Ordner lokal kopieren.

## Ersteinrichtung

1. Unter **Konto** E-Mail/Benutzername und Passwort speichern.
2. Unter **Konfiguration** die automatisch angelegte `config.yaml` prüfen und
   bei Bedarf Kontaktdaten, Anzeigen-Defaults und weitere Bot-Optionen ergänzen.
   Die zwei login-Platzhalter verwenden die in der GUI gespeicherten Daten.
   Alternativ sind originale Bot-Konfigurationen mit eigenen Login-Werten
   möglich; dann werden die GUI-Zugangsdaten dort nicht verwendet.
3. **Manuelle Anmeldung starten**. Im Browserdesktop in Kleinanzeigen anmelden,
   CAPTCHA/SMS/E-Mail-Verifizierung bei Bedarf selbst durchführen. Danach
   **ENTER an Bot senden**. Der Bot prüft das konfigurierte Konto und beendet
   den Login-Auftrag. Das persistente Browserprofil bleibt erhalten.
4. Zunächst **Online-Anzeigen auflisten** oder **Online-Anzeigen herunterladen**
   mit Auswahl `new` ausführen. Alternativ eine eigene lokale Anzeige erstellen.
5. Mit **Konfiguration & Anzeigen prüfen** den Original-Bot prüfen lassen.
6. Erst danach gewünschte Online-Aktionen ausdrücklich starten.

Die Weboberfläche führt beim Speichern eine YAML/JSON-Syntaxprüfung und einige
Basisprüfungen durch. Das ist keine vollständige Upstream-Schema- oder
Kleinanzeigen-Formularprüfung; dafür dient `verify`.

## Anzeigen und Bilder

Neue Dateien sind zunächst `active: false`. Zum Veröffentlichen Titel,
Beschreibung, Kategorie, Preis, Kontaktdaten und Bilder vervollständigen und
`active: true` setzen. Die Beispielkategorie im Editor ist nur ein Platzhalter.

Eigene Anzeigen liegen unter `ads/`; heruntergeladene Dateien unter
`downloaded-ads/`. Die Standard-globs finden YAML/JSON-Dateien in beiden
Bäumen. Heruntergeladene Online-Drafts mit Dateiendung `.draft` bleiben Entwürfe
und werden von diesen globs nicht veröffentlicht. Soll daraus eine reguläre
Anzeige werden, als `.yaml` speichern und prüfen.

Hochgeladene Bilder liegen unter `ads/images/` und erhalten eindeutige Namen.
Die GUI zeigt YAML-Pfade zum Kopieren an. Für Anzeigen direkt unter `ads/`
passen Pfade wie `images/<name>.jpg`; in anderen Unterordnern absolute
Containerpfade verwenden, etwa `/data/workspace/ads/images/<name>.jpg`.
Das Add-on schreibt Bilder nicht automatisch in die Anzeige und löscht sie
nicht beim Löschen einer Anzeigendatei.

## Bot-Aufträge

Verfügbar sind `verify`, `status`, `list`, `download`, `publish`, `update`,
`extend`, `reserve`, `activate`, `delete`, `login`, `diagnose`, `version` und
`help`. Die CLI-Aufrufe sind auf diese Befehle und erlaubte Selektoren begrenzt.
Es gibt keine freie Shell-Eingabe.

Die Auswahl akzeptiert je nach Befehl `all`, `due`, `new`, `changed`, `drafts`
oder kommaseparierte Online-Anzeigen-IDs. Für `publish` sind Kombinationen wie
`changed,due` möglich. `status` bezieht sich auf lokale Dateien, `list` auf das
Online-Konto. `extend` verlängert nur geeignete Anzeigen im vom Bot festgelegten
Zeitfenster.

Bei `publish` ist **Alte Anzeigen behalten** standardmäßig aktiv. Ohne diese
Option kann der Original-Bot alte Anzeigen beim Neueinstellen entfernen.
Verändernde Aktionen benötigen die Bestätigung in der Weboberfläche.
Ein Auftrag wird nie automatisch gestartet oder nach Fehlern wiederholt.
Die Bot-eigenen Intervalle werden nur ausgewertet, wenn ein Auftrag gestartet
wird. Ein zusätzlicher Zeitplaner/MQTT- oder HA-Automationsdienst gehört nicht
zu dieser Version.

Während eines Auftrags sind Änderungen an Konfiguration, Zugangsdaten und
Anzeigendateien sowie weitere Aufträge gesperrt. Bei Login-Prompts mit
**ENTER an Bot senden** bestätigen. **Stoppen** beendet den Prozess; bereits
übermittelte Änderungen werden dadurch nicht zurückgenommen.

## Add-on-Optionen

| Option | Standard | Bedeutung |
| --- | --- | --- |
| `job_timeout_minutes` | 30 | Zeitlimit je Auftrag, 1–240 Minuten; danach Abbruch. |
| `desktop_width` | 1440 | Desktop-Breite, 800–2560 Pixel. |
| `desktop_height` | 900 | Desktop-Höhe, 600–1600 Pixel. |

Nach Änderung der Add-on-Optionen neu starten. Die Optionen befinden sich im
Home-Assistant-Konfiguration-Tab; Bot-Einstellungen dagegen in der Web-GUI.

## Persistente Daten und Sicherungen

Alle Nutzdaten liegen im privaten Add-on-Datenverzeichnis `/data/`:

| Containerpfad | Inhalt |
| --- | --- |
| `/data/workspace/config.yaml` | Original-Bot-Konfiguration |
| `/data/workspace/.credentials.json` | GUI-Zugangsdaten, Rechte 0600 |
| `/data/workspace/browser-profile/` | Persistente Chromium-Sitzung |
| `/data/workspace/ads/` | Eigene Anzeigen und hochgeladene Bilder |
| `/data/workspace/downloaded-ads/` | Heruntergeladene Anzeigen und Bilder |
| `/data/state/history.json` | Letzte 50 Aufträge |
| `/data/state/*.log` | Gekürzte, gefilterte Auftragsprotokolle |
| `/data/state/backups/` | Letzte zehn editorseitige Sicherungen je Datei |

Home-Assistant-Sicherungen müssen das Add-on einschließen, um diese Daten
mitzusichern. Nutzdaten werden nicht in `/config/` oder in das Quellcodepaket
kopiert. Der Editor erlaubt keine Zugriffe auf andere Verzeichnisse.

Live-Ausgaben sind auf etwa 128 KiB begrenzt, gespeicherte Auftragsausgaben
auf etwa 1 MiB. Zugangsdaten werden nach Möglichkeit aus diesen Ausgaben
gefiltert. Der separate CLI-Logfile wird nach dem Auftrag entfernt. Anzeigen,
Bilder, Browserprofile und Bot-Diagnosedateien können trotzdem private Daten
enthalten; die Zugangsdaten sind dateirechtlich geschützt, nicht verschlüsselt.

## Netzwerk und Browser

Nur Nginx lauscht für Ingress auf Port 8099; es akzeptiert ausschließlich
Verbindungen des Supervisors von `172.30.32.2`. Kein Host-Port wird geöffnet.
Backend, VNC und WebSocket-Brücke binden nur an Loopback. Der gesamte
Browserzugang nutzt den angemeldeten Home-Assistant-Ingress-Zugang.

Chromium läuft als UID 1000. `--no-sandbox` ist wegen des eingeschränkten
Add-on-Containers in der Erstkonfiguration gesetzt; der Container benötigt
keinen deaktivierten Schutzmodus. `--disable-dev-shm-usage` verwendet
Container-Temporärspeicher, statt einen großen gemeinsamen Host-Speicher
vorauszusetzen. GPU-Passthrough ist nicht eingerichtet.

## Fehlerbehebung und Grenzen

- **Add-on fehlt im Store:** `/addons/kleinanzeigen_bot/config.yaml` und
  `/addons/kleinanzeigen_bot/Dockerfile` müssen direkt an diesen Pfaden liegen.
  Quellen neu laden. Ein zusätzlicher ZIP-Oberordner verhindert die Erkennung.
- **Build scheitert:** Supervisor-Build-Protokoll prüfen. Paketdownloads und
  GitHub-Release-Downloads benötigen Internet; eine vorhandene 32-Bit-Installation
  wird nicht unterstützt. Die Bot-Datei wird im Build mit `version` und `help`
  geprüft, sodass ein fehlender oder nicht lauffähiger Download den Build stoppt.
- **Browser leer:** Desktop zeigt den Bot-Browser erst während browserbasierter
  Aufträge. Einen Login-Auftrag starten und gegebenenfalls Desktop neu laden.
- **Anmeldung wird nicht gespeichert:** `browser.use_private_window: false`
  und `browser.user_data_dir: /data/workspace/browser-profile` beibehalten;
  keine private/guest/headless-Browseroption verwenden.
- **Formularprüfung schlägt fehl:** Live-Ausgabe lesen, Datei korrigieren und
  `verify` erneut ausführen. CAPTCHA wird manuell gelöst.
- **Zeitlimit:** Für manuelle Verifizierung mehr Zeit in den Add-on-Optionen
  setzen und das Add-on neu starten.

Die Integration wurde hier mit einem simulierten CLI-Prozess auf API-Ebene
geprüft. Das tatsächliche Containerimage, Supervisor-Ingress, VNC-WebSocket,
Chromium-Start und Kleinanzeigen-Abläufe wurden nicht end-to-end getestet.
Die Hardware-/Laufzeitkompatibilität muss daher auf dem Zielgerät bestätigt
werden. Änderungen am Upstream-Bot oder an der Website können Anpassungen
nötig machen.

## Upstream-Version und Entwicklung

Der Docker-Build lädt standardmäßig den GitHub-Release-Kanal `latest` herunter.
Es gibt keine automatische Bot-Aktualisierung beim Start. Für reproduzierbare
Builds einen konkreten verfügbaren Release-Tag mit dem Docker-Build-Argument
`BOT_RELEASE` festlegen und das Image neu bauen. Die Architekturabbildung folgt
den Upstream-Binärnamen `amd64` und `aarch64`.

Das Paket enthält `tests/test_api.py` sowie eine offline ausführbare
Validierung. Tests benötigen Python 3.12+ mit Flask und PyYAML:

```bash
python3 tests/test_api.py
python3 tests/validate_project.py
```

Ein optionaler Docker-Build auf einem Rechner mit Docker:

```bash
docker build --build-arg BUILD_ARCH=amd64 --build-arg BUILD_VERSION=0.1.0   -t kleinanzeigen-ha-addon:0.1.0 ./kleinanzeigen_bot
```

Dieser Build allein ist kein Nachweis einer erfolgreichen HA-Installation.

## Projekt- und Lizenzhinweis

Eigenständiger neuer Wrapper für das Second-Hand-Friends-Projekt,
AGPL-3.0-or-later. Siehe `LICENSE-NOTICE.md` im Paket. Das ursprüngliche Projekt
weist darauf hin, dass die Bot-Nutzung gegen die Kleinanzeigen-Nutzungsbedingungen
verstoßen kann. Es ist kein offizielles Home-Assistant- oder Upstream-Add-on.
