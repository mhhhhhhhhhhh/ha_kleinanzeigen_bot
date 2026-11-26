# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run the installed upstream CLI with structured list output and bounded login.
No login is assumed successful without upstream verification.
"""
import asyncio
import json
import sys

MARKER = 'HA_ACCOUNT_ADS_V1='

def validate_ads(ads):
    if not isinstance(ads,list):
        raise ValueError('Online-Liste ist kein Array.')
    seen=set()
    output=[]
    for ad in ads:
        raw=ad.get('id') if isinstance(ad,dict) else None
        if isinstance(raw,bool) or not str(raw).isdigit() or int(raw)<=0:
            raise ValueError('Online-Liste enthält ungültige IDs.')
        key=str(raw)
        if key in seen:
            raise ValueError('Online-Liste enthält doppelte IDs.')
        if not isinstance(ad.get('state'),str):
            raise ValueError('Online-Status fehlt.')
        seen.add(key)
        output.append(dict(ad_id=key,title=str(ad.get('title') or '-'),
                           state='reserved' if ad['state']=='paused' else ad['state'],
                           expires=ad.get('endDate')))
    return output

async def bounded_login(original, web, **kwargs):
    from kleinanzeigen_bot import login_flow
    try:
        await asyncio.wait_for(original(web,**kwargs), timeout=120)
        return
    except (TimeoutError,AssertionError):
        print('\n[HA_LOGIN_REQUIRED] Anmeldung nicht automatisch bestätigt. '
              'Browserdesktop öffnen, Anmeldung/Gerätebestätigung abschließen und ENTER senden.',flush=True)
    # Keep the existing visible page: do not replace a pending MFA/CAPTCHA with another navigation.
    for attempt in range(3):
        await asyncio.to_thread(input)
        try:
            result=await asyncio.wait_for(login_flow.get_login_state(
                web,username=kwargs['username'],capture_diagnostics=False),timeout=30)
            if result.is_logged_in:
                print('[HA_LOGIN_CONFIRMED] Browsersitzung bestätigt.',flush=True)
                return
        except TimeoutError:
            pass
        print('[HA_LOGIN_REQUIRED] Sitzung noch nicht bestätigt. Im Browser prüfen und ENTER senden.',flush=True)
    raise RuntimeError('Anmeldung nach manueller Prüfung nicht bestätigt. Keine Anzeigenliste abrufbar.')

def main():
    from kleinanzeigen_bot import cli, published_ads, login_flow
    # Only replaces presentation, not account fetching or strict pagination.
    published_ads.render_published_ads=lambda ads: MARKER+json.dumps(validate_ads(ads),ensure_ascii=False)
    original_login=login_flow.login
    async def login(web,**kwargs):
        return await bounded_login(original_login,web,**kwargs)
    login_flow.login=login
    cli.main(sys.argv)

if __name__=='__main__':
    main()
