# Quellenbasis

Die CLI-Befehle, Selektoren, portable Arbeitsverzeichnisse, Login-Platzhalter
und Anzeigen-Dateiformate basieren auf der README und der Konfigurations-
bzw. Browser-Dokumentation des Originalprojekts. Die Web-GUI, der
Home-Assistant-Wrapper und die noVNC-Dienste dieses Pakets wurden neu erstellt.
<ctn>0-web-10,0-web-29,0-web-30</ctn>

Das Ingress-Manifest und die Beschränkung des Webzugangs auf den Supervisor
basieren auf der offiziellen Home-Assistant-Dokumentation. Die dort
beschriebene Ingress-Schnittstelle bietet HTTP und WebSockets und verlangt
relative Webpfade. <ctn>0-web-6,0-web-8</ctn>

Die Architektur- und tatsächliche Laufzeitkompatibilität dieses konkreten
Add-ons ist eine Implementierungsannahme und noch nicht durch einen
Container-/Supervisor-Test bestätigt. Die API-Prüfergebnisse stammen
hingegen aus den beiliegenden, tatsächlich ausgeführten Offline-Tests.
