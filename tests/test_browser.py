# SPDX-License-Identifier: AGPL-3.0-or-later
"""Actual headless Chromium against a local Flask server + offline CLI double."""
from pathlib import Path
import threading
import os
import time
import pytest
from werkzeug.serving import make_server

@pytest.fixture
def browser_page(api):
    playwright = pytest.importorskip('playwright.sync_api')
    http = make_server('127.0.0.1',0,api.app,threaded=True)
    thread = threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    errors=[]
    with playwright.sync_playwright() as p:
        try:
            browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
        except playwright.Error as exc:
            http.shutdown()
            pytest.skip('Chromium unavailable: '+str(exc))
        page=browser.new_page(viewport={'width':1440,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(f'http://127.0.0.1:{http.server_port}/')
        yield page,errors,api
        browser.close()
    http.shutdown()
    thread.join(timeout=3)
    assert not errors,errors


def test_browser_initial_online_ads_and_edit(browser_page):
    page,errors,api=browser_page
    page.locator('#adList article').first.wait_for(timeout=10000)
    if os.environ.get('UI_SCREENSHOT_DIR'):
        directory=Path(os.environ['UI_SCREENSHOT_DIR']);directory.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(directory/'anzeigen-ui.png'),full_page=True)
    page.get_by_role('button',name='Bearbeiten',exact=True).click()
    page.locator('#adTitle').fill('Browser edited title')
    page.locator('#description').fill('Browser edited description')
    page.locator('#saveAd').click()
    page.wait_for_function("document.querySelector('#toast').textContent.includes('lokal gespeichert')")
    assert api.store.files()[0]['title']=='Browser edited title'
    obj=api.store.read(api.store.files()[0]['path'])[0]
    assert obj['special_attributes']['condition_s']=='like_new'
    assert obj['contact']['zipcode']=='01234'
    page.locator('#closeEditor').click()
    assert page.locator('#adList').inner_text().find('Browser edited title')>=0


def test_browser_schedule_keeps_dirty_form_selection(browser_page):
    page,errors,api=browser_page
    page.locator('#adList article').first.wait_for(timeout=10000)
    page.get_by_role('button',name='Bearbeiten',exact=True).click()
    page.locator('#adTitle').fill('Dirty title and policy')
    page.locator('#repostEnabled').check()
    page.locator('#repostDays').fill('12')
    page.once('dialog',lambda dialog:dialog.accept())
    page.locator('#savePolicy').click()
    page.wait_for_function("document.querySelector('#toast').textContent.includes('Zeitplan gespeichert')")
    policy=list(api.engine.db['policies'].values())[0]
    assert policy['enabled'] and policy['days']==12
    assert api.store.files()[0]['title']=='Dirty title and policy'


def test_browser_mobile_layout_and_tabs(browser_page):
    page,errors,api=browser_page
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#adList article').first.wait_for(timeout=10000)
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.get_by_role('button',name='Automatik',exact=True).click()
    assert page.locator('#automation').is_visible()
    page.get_by_role('button',name='Meine Anzeigen',exact=True).click()
    assert page.locator('#ads').is_visible()


def test_browser_new_draft_and_form_image_upload(browser_page):
    page,errors,api=browser_page
    page.locator('#adList article').first.wait_for(timeout=10000)
    page.locator('#newBtn').click()
    page.locator('#adTitle').fill('New browser draft')
    page.locator('#description').fill('New item description')
    page.locator('#category').fill('161/278')
    page.locator('#price').fill('25')
    page.locator('#saveAd').click()
    page.wait_for_function("document.querySelector('#toast').textContent.includes('lokal gespeichert')")
    from io import BytesIO
    from PIL import Image
    image=BytesIO();Image.new('RGB',(16,16),'green').save(image,format='PNG')
    page.locator('#uploadFiles').set_input_files({'name':'photo.png','mimeType':'image/png','buffer':image.getvalue()})
    page.locator('#uploadBtn').click()
    page.wait_for_function("document.querySelector('#toast').textContent.includes('Bilder zugeordnet')")
    page.locator('#saveAd').click()
    page.wait_for_function("document.querySelector('#toast').textContent.includes('lokal gespeichert')")
    row=next(r for r in api.store.files() if r['title']=='New browser draft')
    obj,_=api.store.read(row['path'])
    assert obj['active'] is False
    assert obj['images'][0].startswith('images/')
    assert api.store.image_files(row['path'],obj,strict=True)
