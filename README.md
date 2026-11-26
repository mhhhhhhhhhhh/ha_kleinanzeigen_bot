# Hotfix 0.2.4 für die bestehende 0.2.x-Anzeigenverwaltung

Dieses Paket ist ein gezielter Patch, kein vollständiges Add-on und kein Docker-Image.
Es braucht die zuvor bereitgestellte 0.2.x-Serverversion mit `engine = Engine(...)`.

## Anwenden

Add-on stoppen. ZIP außerhalb des Add-on-Ordners entpacken. Auf dem System, auf dem
sich die Add-on-Quelldateien befinden, ausführen:

```bash
python3 apply_hotfix.py /addons/kleinanzeigen_bot
```

Den Pfad bei Bedarf anpassen. Im angegebenen Ordner müssen Dockerfile, config.yaml,
app/server.py und app/engine.py liegen. Der Installer sichert die betroffenen Dateien
in einen benachbarten Ordner und ändert keine /data-Dateien oder Browsersitzungen.
Er prüft vor Änderungen die Serverstruktur. Wenn dort noch der alte 0.1.x-Server mit
`current = None` statt `engine = Engine(...)` liegt, bricht er ab: Dann müssen erst die
zusammengehörigen Dateien der 0.2.x-Version übernommen werden.

Danach lokale Add-on-Quellen neu laden, Image neu bauen/aktualisieren und Add-on starten.
Nur ein Neustart reicht nicht, da Python-Dateien beim Build ins Image kopiert werden.
Die Oberfläche neu laden und Online synchronisieren.

## Änderungen

- Automatische Anmeldung für list/download wird auf 120 Sekunden begrenzt. Bei Timeout
  bleibt die Browserseite mit ihrer eventuell offenen Gerätebestätigung erhalten.
  Im Browserdesktop anmelden/bestätigen und ENTER senden. Die Sitzung wird danach durch
  die Login-Erkennung des Original-Bots überprüft; ein Login wird niemals nur angenommen.
- list liefert strukturierte JSON-Daten aus dem Renderer des installierten Original-Bots.
  Seine echte Kontoabfrage und strikte Pagination werden nicht ersetzt.
- Online-Snapshot wird vor Detail-/Bilddownloads gespeichert. Die Startseite fragt den
  Anzeigenstand auch während laufender Jobs neu ab. Somit müssen nicht sämtliche Bilder
  geladen sein, bevor die Anzeigen sichtbar werden.
- Fehlgeschlagene Detailimporte entfernen keinen bereits geladenen Online-Snapshot.
- Runtime-Konfiguration verwendet einen sichtbaren persistenten Browser, setzt
  suppress_unsupported_flag_warning auf false und fixiert die Fenstergröße.
  Der vorhandene Browserprofilpfad und die Benutzerkonfiguration werden beibehalten.
- Alte Fehlermeldungen werden beim Start eines Login-/Sync-Auftrags zurückgesetzt.
- Dockerfile, Add-on-Manifest und sichtbare UI-Versionsanzeige werden auf 0.2.4 gesetzt.

## Grenzen

12 lokale Tests zu Datenauswertung, manueller Login-Verifikation, Snapshot bei Detailfehlern,
UI-Aktualisierung und Installation wurden ausgeführt. Der Original-Bot wurde dabei nicht
gegen ein echtes Konto getestet. Der Patch löst keine IP-Sperre und umgeht keine Geräte-
oder CAPTCHA-Bestätigung. Bleibt bereits der Browserstart hängen, kann auch dieser Patch
keine Anzeigenliste bereitstellen.

Die Brücke verwendet interne Python-Funktionen des installierten Original-Bots. Wenn dessen
API geändert wurde oder das Image nur eine eingefrorene Bot-Binärdatei statt /opt/venv enthält,
muss ein kompatibles Source-Image gebaut werden. Für deine gepostete Python-/Source-Konfiguration
ist diese Brücke vorgesehen.

Tests lokal: Python mit Flask und PyYAML, danach `python3 test_hotfix.py`.
Die GitHub-Dateien wurden nicht direkt verändert.
