"""Synthetic QQ evidence checks; no real QQ, account, family data or model calls."""
import asyncio
import base64
import datetime as dt
import json
import plistlib
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import zlib

import family_agent as agent
import family_media as media
import family_qq_capture as qq
import family_qq_cua as host
from test_agent_http import AgentHTTPTests
from test_media import png


SOURCE = dict(id='qq:123456', platform='qq', child_id='child-1', name='虚构测试班级群', cursor='100', enabled=True)


def fixture():
    def e(i, role, text, box, parent=1, value=None):
        return dict(element_index=i, element_token=f's1:{i}', role=role, label=text,
                    value=value, parent_index=parent, frame=dict(zip(('x','y','w','h'), box)))
    elements = [e(1,'AXButton',SOURCE['name'],(310,50,230,22)),
        e(2,'AXToolbar','更多',(600,45,180,32)), e(3,'AXButton','更多',(746,45,32,32),2),
        e(4,'AXToolbar','会话',(300,450,350,40)), e(5,'AXTextArea',SOURCE['name'],(300,490,350,100)),
        e(6,'AXStaticText','群聊成员',(570,200,60,16)),
        e(7,'AXStaticText',SOURCE['name'],(600,120,160,16)),
        e(8,'AXStaticText','123456',(606,145,60,12)), e(9,'AXButton','分享',(700,124,64,28)),
        e(10,'AXStaticText','英语：完成课本练习',(305,230,180,20)),
        e(11,'AXStaticText','SIDE_CHAT_SECRET',(100,120,130,20)),
        e(12,'AXStaticText','MEMBER_SECRET',(575,260,90,20)),
        e(13,'AXStaticText','HIDDEN_SECRET',(320,300,100,1))]
    return dict(pid=1, window_id=2, window_bounds=dict(x=0,y=0,width=800,height=600),
                screenshot_frame_valid=True, screenshot_width=800,screenshot_height=600,elements=elements)


def check_layout_and_pixels():
    state=fixture(); _, viewport, text=qq.layout(state,SOURCE)
    assert text=='英语：完成课本练习' and viewport==[300,85,262,365]
    for mutate in [lambda s: s['elements'][7].update(label='654321'),
                   lambda s: s['elements'][4].update(value='用户正在写作业反馈'),
                   lambda s: s['elements'][0].update(label='另一个群'),
                   lambda s: s['elements'][7]['frame'].update(x=320,y=180),
                   lambda s: s['elements'][10]['frame'].update(h=float('nan'))]:
        changed=fixture(); mutate(changed)
        try: _,_,t=qq.layout(changed,SOURCE)
        except qq.CollectError: pass
        else: assert 'SECRET' not in t and changed['elements'][10]['frame']['h']!=changed['elements'][10]['frame']['h']
    with tempfile.TemporaryDirectory() as temporary:
        path=Path(temporary).resolve(); source=path/'window.png'
        def chunk(kind,body): return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
        pixels=b''.join(b'\0'+b''.join(bytes((0,255,0)) if 30<=x<130 and 20<=y<80 else bytes((255,0,0))
                      for x in range(300)) for y in range(200))
        source.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',300,200,8,2,0,0,0))+
                           chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b''))
        state=dict(screenshot_file_path=str(source),screenshot_width=300,screenshot_height=200,
                   window_bounds=dict(x=100,y=200,width=300,height=200))
        qq.crop_window(state,[130,220,100,60],path/'cropped.png')
        # Native BMP decoding proves all pixels came from the non-central green viewport.
        subprocess.run(['/usr/bin/sips','-s','format','bmp',str(path/'cropped.png'),'--out',str(path/'crop.bmp')],
                       check=True,capture_output=True,timeout=10)
        bitmap=(path/'crop.bmp').read_bytes(); offset=struct.unpack_from('<I',bitmap,10)[0]
        width,height=struct.unpack_from('<ii',bitmap,18); bits=struct.unpack_from('<H',bitmap,28)[0]
        assert width==100 and abs(height)==60 and bits in (24,32)
        stride=((width*bits+31)//32)*4
        assert all(bitmap[offset+y*stride+x*(bits//8):offset+y*stride+x*(bits//8)+3]==b'\0\xff\0'
                   for y in range(abs(height)) for x in range(width)), 'Crop included private surrounding pixels'
    print('PASS: group identity, visible-only text and actual off-centre crop pixels')


def check_http():
    case=AgentHTTPTests(); case.setUp()
    try:
        case.source=SOURCE.copy(); case.config=dict(enabled=True,sources=[case.source]); case.write_config(case.config)
        assert case.post('/api/agent/ingest',case.batch())[0]==200
        import app
        store=app.agent_store()
        def rows(table):
            with store._db() as c: return [dict(r) for r in c.execute('SELECT * FROM '+table)]
        before=rows('agent_sources')[0]; facts=rows('records')+rows('manual_tasks')
        obj=dict(source_id=SOURCE['id'],child_id=SOURCE['child_id'],captured_at='2026-02-10T08:06:00+08:00',
                 text='英语：完成课本练习。明天交。',png=base64.b64encode(png()).decode())
        assert case.post('/api/agent/fragment',obj,{})[0]==403
        child_headers=case.child_headers('child-1')|case.parent
        assert case.post('/api/agent/fragment',obj,child_headers)[0]==403
        for changes in [dict(child_id='child-2'),dict(source_id='qq:999999'),dict(png='broken'),
                        dict(captured_at='2026-02-10'),dict(captured_at='2099-01-01T00:00:00Z')]:
            assert case.post('/api/agent/fragment',obj|changes)[0] in (400,403)
        assert not rows('uploads')
        with patch.object(agent.Store,'_message_upload',side_effect=agent.AgentError('synthetic write failure')):
            assert case.post('/api/agent/fragment',obj)[0]==400
        assert not rows('uploads') and not list((store.data/'uploads').iterdir())
        status,result,_=case.post('/api/agent/fragment',obj); assert status==200,result
        assert result['inserted']==1 and result['cursor_advanced'] is False
        keys=dict(source_id=SOURCE['id'],child_id='child-1',message_id=result['message_id'])
        first=case.message_get(keys)[1]
        assert first['message']['kind']==qq.KIND and first['message']['time']=='' and first['message']['sender']==''
        assert first['message']['unread'] is True and len(first['attachments'])==1
        assert first['material_draft']['state']=='pending'
        assert rows('records')+rows('manual_tasks')==facts
        assert rows('agent_sources')[0] | {'unread_count':before['unread_count']} == before
        assert store.snapshot()['sources'][0]['fragment']['id']==result['message_id']
        status,retry,_=case.post('/api/agent/fragment',obj|dict(captured_at='2026-02-10T09:06:00+08:00'))
        assert status==200 and retry['replayed'] and retry['inserted']==0
        assert case.message_get(keys)[1]['message']==first['message'] and len(rows('uploads'))==1
        assert case.message_get(keys|dict(child_id='child-2'))[0]==403
        with patch.object(media,'read_file',wraps=media.read_file), patch('family_llm.extract_draft',return_value=dict(
                title='虚构课本练习',category='学习进展',subject='英语',score=None,total=None,note='仅窗口可见要求',uncertainties=['原件未读'])) as model:
            assert media.prepare_draft(store,agent._now())==dict(used=1,failed=0)
        assert qq.NOTICE in model.call_args.args[0] and 'captured_at' in model.call_args.args[0]
        assert case.message_get(keys)[1]['material_draft']['state']=='ready'
        assert rows('records')+rows('manual_tasks')==facts
        attachment=first['attachments'][0]['id']
        assert case.link({'id':attachment},'detach',keys)[0]==200
        assert case.post('/api/agent/fragment',obj)[1]['replayed']
        assert not case.message_get(keys)[1]['attachments']
        case.config['sources'][0]['enabled']=False; case.write_config(case.config)
        assert case.post('/api/agent/fragment',obj)[0]==403
        case.config['sources'][0]['enabled']=True; case.config['sources'][0]['child_id']='child-2'; case.write_config(case.config)
        assert case.post('/api/agent/fragment',obj|dict(child_id='child-2'))[0]==409
        assert 'fragment' not in store.snapshot()['sources'][0]
    finally: case.tearDown()
    print('PASS: HTTP auth, child/source binding, idempotency, native cursor preservation, model draft and no invented facts')


def check_worker():
    """Exercise the worker flow with a SDK-shaped fake, never a real desktop."""
    sdk=SimpleNamespace(**{name:lambda **kw:SimpleNamespace(**kw) for name in
        ['ListAppsInput','ListWindowsInput','GetWindowStateInput','ClickInput']},
        ActionTarget=SimpleNamespace(WINDOW=lambda pid,wid:(pid,wid)),
        ClickPosition=SimpleNamespace(ELEMENT=lambda token:token),
        ClickButton=SimpleNamespace(LEFT='left'),InputDeliveryMode=SimpleNamespace(BACKGROUND='background'))
    for panel in (True,False):
        first=fixture()
        if not panel: first['elements']=[e for e in first['elements'] if e['element_index'] not in (6,7,8,9)]
        driver=SimpleNamespace(
            list_apps=AsyncMock(return_value=SimpleNamespace(apps=[SimpleNamespace(running=True,bundle_id='com.tencent.qq',launch_path='/Applications/QQ.app',pid=1)])),
            list_windows=AsyncMock(return_value=SimpleNamespace(windows=[SimpleNamespace(pid=1,window_id=2,layer=0,bounds=SimpleNamespace(width=800,height=600))])),
            get_window_state=AsyncMock(side_effect=[SimpleNamespace(**s) for s in (first,fixture(),fixture())]),click=AsyncMock())
        with patch.dict(sys.modules,cua_driver=sdk),patch.object(host,'screen_locked',return_value=False),patch.object(qq,'crop_window',return_value=png()) as crop:
            text,body=asyncio.run(qq.capture(driver,SOURCE,Path('/synthetic')))
        assert text=='英语：完成课本练习' and body==png()
        assert driver.click.await_count==(0 if panel else 2)
        assert all(c.args[0].delivery_mode=='background' and c.args[0].position=='s1:3' for c in driver.click.await_args_list)
        assert crop.call_args.args[1]==[300,85,262,365]
        driver.list_apps.reset_mock()
        with patch.dict(sys.modules,cua_driver=sdk),patch.object(host,'screen_locked',return_value=True):
            try: asyncio.run(qq.capture(driver,SOURCE,Path('/synthetic')))
            except qq.CollectError as error: assert str(error)=='screen_locked'
            else: raise AssertionError('Locked desktop was read')
        driver.list_apps.assert_not_called()
    with tempfile.TemporaryDirectory() as temporary:
        data=Path(temporary).resolve(); config=data/'collector.json'
        config.write_text('{"app_url":"http://127.0.0.1:8765"}');config.chmod(0o600)
        assert qq.settings(data) is None
        local=data/'qq-cua.json';local.write_text(json.dumps(dict(enabled=True,source_id=SOURCE['id'])));local.chmod(0o600)
        with patch.object(host,'check_host',AsyncMock(return_value=dict(status='permission_required'))),patch.object(qq,'capture_once',AsyncMock()) as capture:
            assert host.main(['--config',str(config)])==1;capture.assert_not_called()
        with patch.object(host,'check_host',AsyncMock(return_value=dict(status='host_ready'))),patch.object(qq,'capture_once',AsyncMock(return_value=dict(status='fragment_saved',observations_inserted=1))) as capture:
            assert host.main(['--config',str(config)])==0;capture.assert_awaited_once()
        receipt=json.loads((data/'qq-cua-preflight.json').read_text())
        assert receipt['observations_inserted']==1 and receipt['messages_ingested']==0 and not receipt['cursor_advanced']
        local.chmod(0o644)
        try: qq.settings(data)
        except media.MediaError: pass
        else: raise AssertionError('Broad-readable capture config accepted')
    print('PASS: standalone worker dispatch, existing-group only, background toolbar action and locked/unauthorized gates')

    import family_collect
    local=dict(enabled=True,source_id=SOURCE['id'])
    for changed in (False,True):
        sent=[]
        def request(path, body=None, token='', **kwargs):
            if path=='/api/agent/fragment/plan': return dict(enabled=True,sources=[SOURCE])
            if path=='/api/state': return dict(token='synthetic-token')
            assert path=='/api/agent/fragment' and token=='synthetic-token'
            sent.append(body)
            return dict(ok=True,replayed=False,inserted=1,coverage='window_fragment',cursor_advanced=False,message_id='fragment-'+'a'*40)
        driver=SimpleNamespace(shutdown=AsyncMock(),call_tool=AsyncMock(return_value=SimpleNamespace(
            is_error=False,structured_json='{"accessibility":true,"screen_recording":true}')))
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules,cua_driver=SimpleNamespace(CuaDriver=SimpleNamespace(create=lambda:driver))), \
                patch.object(family_collect,'Client',return_value=SimpleNamespace(request=request)), \
                patch.object(qq,'capture',AsyncMock(return_value=('synthetic scoped text',png()))), \
                patch.object(qq,'settings',return_value=None if changed else local), \
                patch.object(host,'native_host_id',return_value=host.HOST_ID),patch.object(host,'screen_locked',return_value=False):
            try: result=asyncio.run(qq.capture_once(dict(app_url='http://127.0.0.1:8765'),Path(directory).resolve(),local))
            except qq.CollectError as error: assert changed and str(error)=='qq_capture_config_changed'
            else: assert not changed and result['status']=='fragment_saved'
        driver.shutdown.assert_awaited_once()
        assert len(sent)==(0 if changed else 1)
        if sent: assert base64.b64decode(sent[0]['png'])==png() and sent[0]['text']=='synthetic scoped text'
    print('PASS: cropped-only submission, rechecked authorization/configuration and explicit server acknowledgement')


def check_cadence():
    case=AgentHTTPTests();case.setUp()
    try:
        import app
        case.source=SOURCE.copy();case.config=dict(enabled=True,sources=[case.source]);case.write_config(case.config)
        store=app.agent_store();data=app.DATA;now=agent._now().replace(hour=10,minute=55,second=0,microsecond=0)
        native=app.ROOT/'Synthetic QQ Reader.app';(native/'Contents/MacOS').mkdir(parents=True)
        info=dict(CFBundleIdentifier=host.HOST_ID,CFBundleExecutable='FamilyCollector',FamilyQQPreflight=True,
                  FamilyRoot=str(app.ROOT),FamilyConfig=str(data/'collector.json'))
        (native/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        binary=native/'Contents/MacOS/FamilyCollector';binary.write_text('#!/bin/sh\nexit 1\n');binary.chmod(0o700)
        local=dict(enabled=True,source_id=SOURCE['id'],host_app=str(native));config=data/'qq-cua.json'
        config.write_text(json.dumps(local));config.chmod(0o600)
        calls=[]
        def run(moment,*,status='permission_required',locked=False,stale=False):
            def launch(args,env,timeout,max_stdout):
                assert args==[str(binary)] and timeout==50 and max_stdout==8192
                assert [k for k in env if k.startswith('FAMILY_')]==['FAMILY_QQ_WORKDIR']
                work=Path(env['FAMILY_QQ_WORKDIR']);assert work.parent==data and work.is_dir()
                (work/'synthetic-window.png').write_bytes(png())
                calls.append(args)
                receipt=dict(checked_at=(moment-dt.timedelta(minutes=1) if stale else moment).isoformat(),
                             host_bundle_id=host.HOST_ID,source_id=SOURCE['id'],status=status,messages_ingested=0,
                             cursor_advanced=False,coverage='window_fragment',observations_inserted=1)
                p=data/'qq-cua-preflight.json';p.write_text(json.dumps(receipt));p.chmod(0o600)
                if status=='permission_required':raise qq.MediaError('process_failed')
                return b''
            with patch.object(qq,'bounded_process',side_effect=launch),patch.object(host,'screen_locked',return_value=locked),patch.object(agent,'_now',side_effect=lambda value=None:value or moment):
                return qq.run_one(app,store,moment)
        result=run(now);assert result['state']=='permission_required' and result['next_at']==(now+dt.timedelta(minutes=30)).isoformat()
        result=run(now+dt.timedelta(minutes=5));assert result['state']=='not_due' and len(calls)==1
        result=run(now+dt.timedelta(minutes=30),status='fragment_saved');assert result['state']=='fragment_saved' and len(calls)==2
        result=run(now+dt.timedelta(minutes=60),stale=True);assert result['state']=='not_confirmed'
        count=len(calls);result=run(now+dt.timedelta(minutes=90),locked=True);assert result['state']=='screen_locked' and len(calls)==count
        # Native source attempts cannot starve the independent window schedule.
        batch=case.batch();batch['checked_at']=agent._now().isoformat();assert case.post('/api/agent/ingest',batch)[0]==200
        assert case.request('GET','/api/agent/collector')[1]['sources']==[]
        plan=case.request('GET','/api/agent/fragment/plan')[1];assert [s['id'] for s in plan['sources']]==[SOURCE['id']]
        assert case.request('GET','/api/agent/fragment/plan',headers=case.child_headers('child-1'))[0]==403
        # A QQ configuration failure leaves the ordinary independent Agent running.
        with store._db() as c:c.execute('UPDATE agent_messages SET processed=1')
        info['FamilyRoot']='/synthetic-other-family';(native/'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        with patch.object(qq,'bounded_process') as launch:
            result=agent.run_once(app)
        launch.assert_not_called();assert result['qq_fragment']['state']=='configuration_error' and result['state']=='ready'
        config.unlink();assert qq.run_one(app,store,now)['state']=='disabled'
        assert not list(data.glob('*.plist'))
        assert not list(data.glob('.qq-cycle-*'))
    finally:case.tearDown()
    print('PASS: independent 30/60 cadence, persisted retry wait, stale receipts, locked skip, exact installation and unaffected Agent work')


if __name__=='__main__':
    check_layout_and_pixels()
    check_http()
    check_worker()
    check_cadence()
