# Kleinanzeigen Bot – Home-Assistant-Add-on

**Downloadpaket mit vollständigem Quellcode, Weboberfläche und lokaler
Add-on-Struktur. Experimentelle Erstfassung 0.1.0.**

## Schnellinstallation

1. Den Ordner `kleinanzeigen_bot` nach `/addons/kleinanzeigen_bot` auf dem
   Home-Assistant-System kopieren.
2. Im App-/Add-on-Store lokale Quellen neu laden.
3. Add-on installieren, starten und Weboberfläche öffnen.
4. Unter Konto Zugangsdaten speichern, manuell anmelden und Konfiguration prüfen.

Nicht den gesamten ZIP-Oberordner nach `/addons/` kopieren. Direkt in
`/addons/kleinanzeigen_bot/` müssen `config.yaml`, `Dockerfile` und `app/` liegen.

Die vollständige Anleitung steht in `kleinanzeigen_bot/DOCS.md`.
Dieses ZIP ist kein bereits gehostetes GitHub-Add-on-Repository.

## Enthalten

- Ingress-GUI ohne separate Host-Ports.
- YAML/JSON-Anzeigeneditor, Bild-Upload und lokale Dateisicherungen.
- GUI-Verwaltung der Zugangsdaten und Original-Bot-Konfiguration.
- Einzeln ausführbare Bot-Aufträge mit Live-Logs, Stoppen, Zeitlimit und Verlauf.
- Chromium-Desktop via noVNC mit PTY/ENTER für manuelle Anmeldung.
- Dockerfile für amd64/aarch64 sowie Offline-API-Tests.

## Prüfstatus

Web-API und Jobsteuerung werden mit einem simulierten Bot geprüft. Kein
Kleinanzeigen-Konto wird durch die Tests angesprochen. Docker/Chromium,
Supervisor-Installation, Ingress/WebSocket und reale Bot-Aktionen müssen
auf dem Zielsystem noch getestet werden. Siehe `TEST_REPORT.md`.

## Aufbau

```text
kleinanzeigen_bot/
  config.yaml
  Dockerfile
  boot.py
  nginx.conf
  app/server.py
  app/templates/index.html
  DOCS.md
  README.md
  CHANGELOG.md
  translations/de.yaml
tests/
  test_api.py
  validate_project.py
LICENSE-NOTICE.md
TEST_REPORT.md
```

Original-Bot und Debian-Systempakete werden beim Container-Build aus ihren
Quellen bezogen; sie sind nicht als Binärdateien im ZIP enthalten.
Lizenz des neuen Wrapper-Quellcodes: AGPL-3.0-or-later.
