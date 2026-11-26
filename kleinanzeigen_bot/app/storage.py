# SPDX-License-Identifier: AGPL-3.0-or-later
"""Local ad storage. Relative image paths always belong to the ad directory."""
from __future__ import annotations
import copy
from datetime import date, datetime
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import time
import yaml
from PIL import Image, UnidentifiedImageError

MAX_TEXT = 1024 * 1024
EXTENSIONS = {'.yaml', '.yml', '.json', '.draft'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif'}

class Invalid(ValueError):
    pass

def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp-' + secrets.token_hex(8))
    try:
        with temp.open('x', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)

def mapping(text: str) -> dict:
    if not isinstance(text, str) or len(text.encode()) > MAX_TEXT:
        raise Invalid('Text fehlt oder ist größer als 1 MiB.')
    try:
        result = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise Invalid('Ungültiges YAML/JSON.') from exc
    if not isinstance(result, dict):
        raise Invalid('Ein YAML/JSON-Objekt wird erwartet.')
    return result

def jsonable(value):
    """Normalize YAML timestamps for the JSON form editor without HTTP-date coercion."""
    if isinstance(value,(datetime,date)):
        return value.isoformat()
    if isinstance(value,dict):
        return {k:jsonable(v) for k,v in value.items()}
    if isinstance(value,list):
        return [jsonable(v) for v in value]
    return value


def numeric_id(value) -> str | None:
    if isinstance(value, bool):
        return None
    value = str(value) if value is not None else ''
    return value if re.fullmatch(r'[1-9][0-9]*', value) else None

class Store:
    def __init__(self, work: Path, state: Path):
        self.work, self.state = work.resolve(), state.resolve()
        for p in [self.work, self.state, self.work/'ads', self.work/'downloaded-ads', self.state/'backups', self.state/'archives']:
            p.mkdir(parents=True, exist_ok=True)

    def path(self, name: str, image: bool = False) -> Path:
        if not isinstance(name, str) or not name or '\\' in name:
            raise Invalid('Ungültiger Pfad.')
        p = Path(name)
        parts = p.parts
        if p.as_posix() != name:
            raise Invalid('Pfad muss eindeutig sein: keine ./ oder doppelten Schrägstriche.')
        if p.is_absolute() or len(parts) < 2 or parts[0] not in {'ads', 'downloaded-ads'} or any(x.startswith('.') for x in parts):
            raise Invalid('Nur Dateien unter ads/ oder downloaded-ads/ sind erlaubt.')
        walk = self.work
        for part in parts:
            walk /= part
            if walk.is_symlink():
                raise Invalid('Symbolische Links sind nicht erlaubt.')
        if not walk.resolve().is_relative_to(self.work):
            raise Invalid('Pfad außerhalb des Arbeitsverzeichnisses.')
        if walk.suffix.lower() not in (IMAGE_EXTENSIONS if image else EXTENSIONS):
            raise Invalid('Nicht unterstützter Dateityp.')
        return walk

    def read(self, name: str) -> tuple[dict, str]:
        p = self.path(name)
        if not p.is_file():
            raise FileNotFoundError(name)
        if p.stat().st_size > MAX_TEXT:
            raise Invalid('Anzeigen-Datei zu groß.')
        text = p.read_text(encoding='utf-8')
        return mapping(text), text

    def revision(self, name: str) -> str:
        return hashlib.sha256(self.path(name).read_bytes()).hexdigest()

    def backup(self, path: Path):
        if not path.exists():
            return
        key = hashlib.sha256(str(path.relative_to(self.work)).encode()).hexdigest()
        directory = self.state/'backups'/key
        directory.mkdir(exist_ok=True)
        atomic_write(directory/'path.txt', path.relative_to(self.work).as_posix())
        atomic_write(directory/f'{time.time_ns()}.bak', path.read_text())
        for old in sorted(directory.glob('*.bak'))[:-10]:
            old.unlink()

    def save(self, name: str, text: str, revision: str | None) -> dict:
        p = self.path(name)
        obj = mapping(text)
        if p.suffix == '.json':
            try:
                json.loads(text)
            except ValueError as exc:
                raise Invalid('Eine .json-Datei benötigt gültiges JSON.') from exc
        if not isinstance(obj.get('title'), str) or not obj['title'].strip():
            raise Invalid('Ein Titel ist erforderlich.')
        if p.exists() and revision != self.revision(name):
            raise FileExistsError('Anzeige wurde zwischenzeitlich geändert. Neu laden.')
        if not p.exists() and revision is not None:
            raise FileExistsError('Anzeige existiert nicht mehr. Neu laden.')
        if p.exists():
            old, _ = self.read(name)
            for key in ['id', 'created_on', 'updated_on', 'repost_count', 'price_reduction_count', 'content_hash']:
                if jsonable(obj.get(key)) != jsonable(old.get(key)):
                    raise Invalid(f'Das Bot-Feld {key} darf hier nicht geändert werden.')
        elif any(obj.get(k) is not None for k in ['id', 'created_on', 'updated_on', 'content_hash']):
            raise Invalid('Neue lokale Anzeigen dürfen keine Bot-ID/Zeitstempel enthalten.')
        self.backup(p)
        atomic_write(p, text)
        return obj

    def files(self) -> list[dict]:
        result = []
        for folder in ['ads', 'downloaded-ads']:
            for p in sorted((self.work/folder).rglob('*')):
                if not p.is_file() or p.suffix.lower() not in EXTENSIONS or p.name == 'ad_fields.yaml':
                    continue
                name = p.relative_to(self.work).as_posix()
                try:
                    obj, _ = self.read(name)
                    pictures = self.image_files(name, obj)
                    result.append(dict(path=name, title=str(obj.get('title', p.name)), ad_id=numeric_id(obj.get('id')),
                        price=obj.get('price'), active=obj.get('active', True), draft=p.suffix == '.draft',
                        created_on=obj.get('created_on'), updated_on=obj.get('updated_on'), error=None,
                        thumbnail=pictures[0].relative_to(self.work).as_posix() if pictures else None, image_count=len(pictures)))
                except (Invalid, OSError, UnicodeError):
                    result.append(dict(path=name, title=p.name, ad_id=None, error='Datei nicht lesbar'))
        return result

    def image_files(self, name: str, obj: dict, strict=False) -> list[Path]:
        p = self.path(name)
        patterns = obj.get('images', []) or []
        if not isinstance(patterns, list) or not all(isinstance(x, str) for x in patterns):
            raise Invalid('images muss eine Liste von Pfaden sein.')
        result = []
        for pattern in patterns:
            # Production uses the same brace/extglob engine as upstream.
            full = str(p.parent/pattern)
            try:
                from wcmatch import glob as wc
                found = wc.glob(full, flags=wc.GLOBSTAR | wc.BRACE | wc.EXTGLOB)
            except ImportError:
                # Offline tests only need ordinary globs and brace alternatives.
                def expand(s):
                    match = re.search(r'\{([^{}]+)\}', s)
                    if not match:
                        return [s]
                    return [y for x in match[1].split(',') for y in expand(s[:match.start()]+x+s[match.end():])]
                found = [x for part in expand(full) for x in glob.glob(part, recursive=True)]
            usable = []
            for candidate in sorted(set(found)):
                q = Path(candidate)
                try:
                    q = self.path(q.relative_to(self.work).as_posix(), image=True)
                except (ValueError, Invalid):
                    if strict:
                        raise Invalid('Bildpfad liegt außerhalb der erlaubten Anzeigenordner.')
                    continue
                if q.is_file():
                    usable.append(q)
            if strict and not usable:
                raise Invalid(f'Bild fehlt oder Muster ohne Treffer: {pattern}')
            result.extend(usable)
        return list(dict.fromkeys(result))

    def archive(self, name: str) -> Path:
        obj, text = self.read(name)
        pictures = self.image_files(name, obj, strict=True)
        key = hashlib.sha256(name.encode()).hexdigest()
        parent = self.state/'archives'/key
        target = parent/str(time.time_ns())
        target.mkdir(parents=True)
        atomic_write(target/'source.txt', name)
        atomic_write(target/'original.yaml', text)
        portable = copy.deepcopy(obj)
        portable['images'] = []
        for i, source in enumerate(pictures):
            dest = target/f'image_{i:03d}{source.suffix.lower()}'
            shutil.copyfile(source, dest)
            dest.chmod(0o600)
            portable['images'].append(dest.name)
        atomic_write(target/'restore.yaml', yaml.safe_dump(portable, allow_unicode=True, sort_keys=False))
        for old in sorted(x for x in parent.iterdir() if x.is_dir())[:-3]:
            shutil.rmtree(old)
        return target

    def upload(self, name: str, uploads) -> list[str]:
        p = self.path(name)
        if not p.is_file():
            raise FileNotFoundError(name)
        prepared = []
        for upload in uploads:
            try:
                with Image.open(upload.stream) as im:
                    im.verify()
                upload.stream.seek(0)
                with Image.open(upload.stream) as im:
                    if im.width * im.height > 40_000_000:
                        raise Invalid('Bild hat zu viele Pixel.')
                    im.load()
                    prepared.append(im.convert('RGB').copy())
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise Invalid('Keine gültige Bilddatei.') from exc
        if not prepared:
            raise Invalid('Keine Bilder ausgewählt.')
        directory = p.parent/'images'
        # Validate all ancestors, including an existing images symlink.
        self.path((directory/'check.jpg').relative_to(self.work).as_posix(), image=True)
        directory.mkdir(exist_ok=True)
        result = []
        for im in prepared:
            dest = directory/(secrets.token_hex(16)+'.jpg')
            with dest.open('xb') as stream:
                im.save(stream, format='JPEG', quality=94)
            dest.chmod(0o600)
            result.append('images/'+dest.name)
        return result
