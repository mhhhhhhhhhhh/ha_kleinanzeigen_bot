# Kleinanzeigen Bot mit Web-GUI

Lokales Home-Assistant-Add-on für den kleinanzeigen-bot von Second-Hand-Friends.

Enthalten: Anzeigeneditor für YAML/JSON, Bild-Upload, Konfigurationseditor,
separate Zugangsdatenverwaltung, Auftragsverlauf und Live-Protokolle sowie
ein Chromium-Desktop über noVNC für manuelle Anmeldung und Verifizierung.

Die Weboberfläche wird über Home Assistant Ingress geöffnet. Es sind keine
zusätzlichen Host-Ports und kein Zugriff auf die Supervisor-API nötig.
Bot und Desktop laufen als Benutzer mit UID 1000.

**Status: experimentelle Version 0.1.0.** Web-API-Tests mit simuliertem Bot
liegen bei; Docker-Build, Supervisor-Installation, noVNC-Verbindung und echte
Kleinanzeigen-Abläufe müssen auf dem Zielsystem getestet werden.

Installation und Bedienung: siehe `DOCS.md` bzw. den Dokumentation-Tab.
