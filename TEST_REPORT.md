# Prüfbericht – Version 0.1.0

## Tatsächlich ausgeführt

- 23 automatisierte API-/Prozesssteuerungs-Tests, alle bestanden.
- Python-Syntaxprüfung für Backend, Boot-Supervisor und Testprogramme.
- YAML-Syntaxprüfung und Abgleich von Add-on-Optionen mit ihrem Schema.
- Statische Prüfung von Ingress-Port, Supervisor-ACL und WebSocket-Direktiven.
- Syntaxprüfung der Shell-Fragmente beider Docker-RUN-Anweisungen mit `bash -n`.
- Rendering der Jinja-Weboberfläche über den Flask-Testclient.

Die API-Tests prüfen unter anderem Datei-CRUD, Bild-Upload, Syntaxfehler,
CSRF, Path-Traversal, Symlinks, Befehlsbegrenzung, Bestätigungspflicht,
Passwortfilterung inklusive geteilten PTY-Ausgaben, Login/ENTER,
parallele Auftragssperre, Stoppen, Zeitlimit und gespeicherte Protokolle.
Der simulierte Bot spricht keine externen Systeme an.

## Nicht ausgeführt

- Docker-Image-Build / echte Bot-Binärdatei aus GitHub.
- `nginx -t` mit den installierten Debian-Paketen.
- JavaScript-Engine-/Browsertest (kein Node/Browser in der Testumgebung).
- Home-Assistant-Supervisor-Installation und Ingress-Sitzung.
- noVNC-WebSocket-Verbindung und Chromium-Start.
- Kleinanzeigen-Anmeldung, CAPTCHA oder tatsächliche Online-Aktionen.

Das Paket ist deshalb als **experimentell** markiert. Die bestandenen
Offline-Tests sind kein Nachweis einer erfolgreichen Zielsystem-Installation.

## Testausgabe

```text
test_ad_crud (__main__.ApiTests.test_ad_crud) ... ok
test_command_injection (__main__.ApiTests.test_command_injection) ... ok
test_confirmation_required (__main__.ApiTests.test_confirmation_required) ... ok
test_credentials_private (__main__.ApiTests.test_credentials_private) ... ok
test_csrf (__main__.ApiTests.test_csrf) ... ok
test_file_listing (__main__.ApiTests.test_file_listing) ... ok
test_finished_job_persisted (__main__.ApiTests.test_finished_job_persisted) ... ok
test_homepage (__main__.ApiTests.test_homepage) ... ok
test_job_failure (__main__.ApiTests.test_job_failure) ... ok
test_job_success_and_log (__main__.ApiTests.test_job_success_and_log) ... ok
test_json_file_invalid (__main__.ApiTests.test_json_file_invalid) ... ok
test_json_object_required (__main__.ApiTests.test_json_object_required) ... ok
test_login_pty_lock_and_enter (__main__.ApiTests.test_login_pty_lock_and_enter) ... ok
test_password_preserved (__main__.ApiTests.test_password_preserved) ... ok
test_path_traversal (__main__.ApiTests.test_path_traversal) ... ok
test_png_upload (__main__.ApiTests.test_png_upload) ... ok
test_publish_arguments (__main__.ApiTests.test_publish_arguments) ... ok
test_split_secret_redacted (__main__.ApiTests.test_split_secret_redacted) ... ok
test_stop (__main__.ApiTests.test_stop) ... ok
test_symlink (__main__.ApiTests.test_symlink) ... ok
test_timeout (__main__.ApiTests.test_timeout) ... ok
test_upload_invalid (__main__.ApiTests.test_upload_invalid) ... ok
test_yaml_invalid (__main__.ApiTests.test_yaml_invalid) ... ok

----------------------------------------------------------------------
Ran 23 tests in 1.203s

OK
```

## Offline-Validierung

```text
Python syntax OK: kleinanzeigen_bot/boot.py
Python syntax OK: tests/test_api.py
Python syntax OK: tests/validate_project.py
Python syntax OK: kleinanzeigen_bot/app/server.py
YAML syntax OK: kleinanzeigen_bot/config.yaml
YAML syntax OK: kleinanzeigen_bot/translations/de.yaml
Ingress manifest, ACL and WebSocket directives: OK (static only)
UI template and relative API paths: OK (static only)
SKIPPED: JavaScript engine not installed; UI browser execution remains untested.
Not run: Docker build, nginx -t, Home Assistant Supervisor, real Chromium/noVNC or Kleinanzeigen.
```
