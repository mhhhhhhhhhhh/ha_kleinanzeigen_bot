# Kleinanzeigen Bot – Home-Assistant-Add-on 0.2.0

Überarbeitete Add-on-Version mit Online-Anzeigenübersicht, Formular- und YAML/JSON-Editor,
Bildverwaltung und dauerhaft gespeicherter Automatik. Kein Push in das ursprüngliche Repository
wurde aus dieser Arbeitsumgebung vorgenommen. Dieses Verzeichnis ist zum Einspielen in das
bestehende Repository bzw. als lokales Add-on bestimmt.

## Enthalten

- Startansicht mit Online-Anzeigen aus der vollständigen `list`-Ausgabe des Original-Bots.
- Automatischer Erstimport fehlender Anzeigen samt Bildern nach Kontoeinrichtung.
- Suche, Statusfilter, Bildvorschau, Anzeigen-ID und Ablaufdatum.
- Formular für Titel, Beschreibung, Kategorie und Preis; erweiterter YAML/JSON-Editor für alle Felder.
- Unbekannte Anzeigenfelder bleiben beim Formularspeichern erhalten.
- Bild-Upload, Zuordnung, Reihenfolge und Entfernen von Bildzuordnungen. WEBP-Uploads werden zu JPG.
- Einzelaktionen: prüfen, aktualisieren, veröffentlichen/neu einstellen, verlängern, reservieren,
  aktivieren und online löschen.
- Explizites „Von online neu laden“ mit vorheriger Sicherung und Download in einen Zwischenordner.
- Regelmäßiger Online-Abgleich und opt-in Verlängerung vor Ablauf.
- Pro Anzeige opt-in Neuanlegen nach X vollständigen 24-Stunden-Tagen.
- Sperre gegen unbestätigte Wiederholungen nach unklarer Veröffentlichung oder Neustart.
- Ingress, noVNC-Browserdesktop, echte PTY-Eingabe, Live-Logs, Stoppen und Zeitlimit.
- Quellinstallation des Original-Bots einschließlich seines nodriver-Patches; keine ARM-Binärdatei-Verwechslung.

## Installation / Upgrade

Die Anleitung für bestehende Installationen und die Ersteinrichtung steht in
[kleinanzeigen_bot/DOCS.md](kleinanzeigen_bot/DOCS.md).

Als lokales Add-on muss der **Inhalt von `kleinanzeigen_bot/`** nach
`/addons/kleinanzeigen_bot/`. Direkt dort liegen dann `config.yaml`, `Dockerfile`,
`boot.py`, `bot-entry.sh`, `nginx.conf` und `app/`.

Bei einem Upgrade bestehende Add-on-Daten sichern und das Add-on stoppen. Die vorhandene
Installation mit gleichem `slug: ha_kleinanzeigen_bot` aktualisieren/neu bauen;
nicht deinstallieren oder `/data` löschen. Bestehende Konfiguration, Anzeigen und
Browserprofil werden nicht absichtlich zurückgesetzt.

## Prüfstatus

Die tatsächlich ausgeführten zehn Prüfdurchläufe stehen in [TEST_REPORT.md](TEST_REPORT.md).
Die Prüfungen verwenden eine lokale Offline-CLI als Ersatz für den Original-Bot.
Die Oberfläche wird zusätzlich in echtem headless Chromium getestet.

**Nicht lokal durchgeführt:** Docker-Build, Supervisor-Installation, echte Home-Assistant-
Ingress-/noVNC-Verbindung und echte Kleinanzeigen-Aktionen mit einem Konto.
Daher bleibt das Manifest auf `stage: experimental`.

## Basis und Lizenz

- Zielrepository: [mhhhhhhhhhhh/ha_kleinanzeigen_bot](https://github.com/mhhhhhhhhhhh/ha_kleinanzeigen_bot)
- Original-Bot: [Second-Hand-Friends/kleinanzeigen-bot](https://github.com/Second-Hand-Friends/kleinanzeigen-bot)
- Wrapper-Quellcode: AGPL-3.0-or-later. Siehe [LICENSE-NOTICE.md](LICENSE-NOTICE.md).
