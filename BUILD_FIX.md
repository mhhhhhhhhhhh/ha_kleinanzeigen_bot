# ARM64-Build-Fix 0.2.1

Dieses Paket ist ein kleiner Build-Fix, kein vollständiges Add-on.

Änderungen:
- Dockerfile: HA aarch64 / Debian arm64 werden auf das Bot-Asset linux-arm64 abgebildet.
- BUILD_VERSION und Add-on-Version werden auf 0.2.1 gesetzt.
- Sonstige Manifestwerte entsprechen dem abgerufenen GitHub-Stand.
- Keine GUI-, Backend-, Anzeigen- oder Nutzdaten werden durch dieses Paket ersetzt.

Anwendung:
1. Beide Dateien unter kleinanzeigen_bot/ im GitHub-Repository ersetzen.
2. In main committen.
3. In Home Assistant die Store-Quellen aktualisieren und Installation erneut versuchen.

Die HA-Architektur bleibt aarch64; nur der Name der heruntergeladenen
Binärdatei wird korrigiert. Der Release-Tag latest und die URL-Struktur
releases/download/latest bleiben unverändert.

Geprüft: Zuordnung amd64/aarch64/arm64, Abweisung armv7, Shell-Syntax und YAML-Manifest.
Nicht ausgeführt: Binärdownload, Docker-Build oder reale ARM64-Ausführung.
