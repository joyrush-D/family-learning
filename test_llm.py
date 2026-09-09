"""Run python3 test_llm.py. Mock loopback HTTP only; never sends family data."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from email.parser import BytesParser
from email.policy import default
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import family_llm as llm

DRAFT=dict(title='虚构数学测验',subject='数学',score=85,total=100,note='虚构示例：订正情况未提供。',uncertainties=['订正情况未知'])
state={'mode':'ok','calls':[],'redirect_calls':0,'usage':None,'reported_model':None}

class Mock(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        state['redirect_calls']+=1;self.send_response(200);self.end_headers()
    def do_POST(self):
        audio=self.path=='/v1/audio/transcriptions'
        raw=self.rfile.read(int(self.headers['Content-Length']))
        state['calls'].append((self.path,raw if audio else json.loads(raw),self.headers.get('Authorization')))
        if audio: state['audio_type']=self.headers['Content-Type']
        mode=state['mode']
        if mode=='redirect':
            self.send_response(302);self.send_header('Location',f'http://localhost:{self.server.server_port}/leak');self.end_headers();return
        if mode=='http_error':
            self.send_response(500);self.end_headers();self.wfile.write(b'PRIVATE_RESPONSE synthetic-secret');return
        if mode=='http_error_json':
            self.send_response(500);self.send_header('Content-Type','application/json');self.end_headers()
            self.wfile.write(json.dumps({'error':'PRIVATE_RESPONSE','usage':state['usage'],'model':state['reported_model']}).encode());return
        if mode=='timeout': time.sleep(.15)
        if audio: result=state.get('asr_result',{'text':'  虚构录音转写，等待核对。  '})
        else:
            result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(DRAFT,ensure_ascii=False)}}]}
            if isinstance(mode,dict): result['choices'][0]['message']['content']=json.dumps(mode)
            elif mode=='bad_json': result['choices'][0]['message']['content']='PRIVATE_RESPONSE invalid JSON'
            elif mode=='empty': result['choices'][0]['message']['content']=''
            elif mode=='length': result['choices'][0]['finish_reason']='length'
            elif mode=='bad_outer': result=[]
            if self.path=='/v1/responses':
                result={'status':'completed','output':[
                    {'type':'reasoning','summary':[{'type':'summary_text','text':'PRIVATE_REASONING'}]},
                    {'type':'message','role':'assistant','status':'completed','content':[
                        {'type':'output_text','text':json.dumps(DRAFT,ensure_ascii=False)}]}]}
                if isinstance(mode,dict): result=mode
            if state['usage'] is not None: result['usage']=state['usage']
            if state['reported_model'] is not None: result['model']=state['reported_model']
        wire=json.dumps(result).encode()
        if audio and mode=='bad_json': wire=b'PRIVATE_RESPONSE invalid JSON'
        if mode=='large': wire=b'x'*(llm.MAX_RESPONSE+1)
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        try: self.wfile.write(wire)
        except BrokenPipeError: pass

server=ThreadingHTTPServer(('127.0.0.1',0),Mock)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with patch.dict(os.environ,{},clear=True):
        try: llm.extract_draft('虚构资料')
        except llm.LLMUnavailable: pass
        else: raise AssertionError('missing model configuration accepted')
    env=dict(FAMILY_LLM_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',FAMILY_LLM_MODEL='synthetic-model',FAMILY_LLM_API_KEY='synthetic-secret')
    with patch.dict(os.environ,env,clear=True):
        draft=llm.extract_draft('虚构数学卷85分，满分100；没有订正信息。')
        assert draft==DRAFT
        path,body,key=state['calls'][-1]
        assert path=='/v1/chat/completions' and key=='Bearer synthetic-secret'
        assert body['response_format']['type']=='json_schema' and body['response_format']['json_schema']['strict'] is True
        assert body['model']=='synthetic-model' and body['stream'] is False
        assert 'reasoning_effort' not in body
        assert len(body['messages'])==2 and body['messages'][1]['content'][0]['text'].startswith('虚构数学卷')
        try: llm._chat_json([dict(role='user',content='synthetic light connection')],llm.SCHEMA,
                            'family_light_connection_test')
        except llm.LLMUnavailable: pass
        else: raise AssertionError('light connection check fell back to the primary model')
        light_env={**env,'FAMILY_LLM_LIGHT_MODEL':'synthetic-light-model'}
        with patch.dict(os.environ,light_env,clear=True):
            state['mode']='ok'
            llm._chat_json([dict(role='user',content='synthetic selection text')],llm.SCHEMA,'family_agent_selection',data_path=None)
            assert state['calls'][-1][1]['model']=='synthetic-light-model'
            llm._chat_json([dict(role='user',content=[dict(type='text',text='synthetic image context'),
                                                       dict(type='image_url',image_url=dict(url='data:image/png;base64,eA=='))])],
                            llm.SCHEMA,'family_agent_selection')
            assert state['calls'][-1][1]['model']=='synthetic-model'
            llm._chat_json([dict(role='user',content='synthetic plan text')],llm.SCHEMA,'family_agent_plan')
            assert state['calls'][-1][1]['model']=='synthetic-model'
            llm._chat_json([dict(role='user',content='synthetic connection text')],llm.SCHEMA,'family_light_connection_test')
            assert state['calls'][-1][1]['model']=='synthetic-light-model'
        llm.extract_draft(images=[dict(data=b'synthetic-trusted-image',mime='image/png')])
        assert state['calls'][-1][1]['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        os.environ['FAMILY_LLM_REASONING_EFFORT']='none'
        llm.extract_draft('虚构资料')
        assert state['calls'][-1][1]['reasoning_effort']=='none'
        os.environ['FAMILY_LLM_REASONING_EFFORT']='invalid'
        try: llm.extract_draft('虚构资料')
        except llm.LLMUnavailable: pass
        else: raise AssertionError('invalid reasoning effort accepted')
        os.environ.pop('FAMILY_LLM_REASONING_EFFORT')
        before=len(state['calls'])
        for text,images in [('',[]),('a'*(llm.MAX_TEXT+1),[]),('',[dict(data=b'x',mime='image/svg+xml')]),
                            ('',[dict(data=b'x',mime='image/png')]*4),('',[dict(data=b'x'*(llm.MAX_INPUT+1),mime='image/png')]),
                            ('',[dict(data='not bytes',mime='image/png')])]:
            try: llm.extract_draft(text,images)
            except ValueError: pass
            else: raise AssertionError('invalid input accepted')
        assert len(state['calls'])==before
        for mode in ['bad_json','empty','length','bad_outer','http_error','redirect','timeout',
                     dict(DRAFT,score=True),dict(DRAFT,total=0),dict(DRAFT,score=101),dict(DRAFT,score=-1),
                     dict(DRAFT,total=float('inf')),dict(DRAFT,score='85'),dict(DRAFT,title=None),
                     dict(DRAFT,note=[]),dict(DRAFT,uncertainties='unknown'),dict(DRAFT,extra='unexpected')]:
            state['mode']=mode
            try: llm.extract_draft('虚构资料',timeout=.03 if mode=='timeout' else 2)
            except llm.LLMDraftError as error:
                assert 'synthetic-secret' not in str(error) and 'PRIVATE_RESPONSE' not in str(error)
            else: raise AssertionError('invalid model result accepted')
        assert state['redirect_calls']==0
        state['mode']=dict(DRAFT,score=None,total=None)
        assert llm.extract_draft('虚构无分数资料')['score'] is None
        os.environ['FAMILY_LLM_BASE_URL']='http://user:password@localhost/v1'
        try: llm.extract_draft('虚构资料')
        except llm.LLMUnavailable as error: assert 'password' not in str(error)
        else: raise AssertionError('URL credentials accepted')
    agreement=dict(book='虚构故事：纸船',edition='',scope='虚构第一段',method='任选语音或图画讲解',
                   criteria='说一说自己注意到的一个选择')
    feedback=dict(feedback=['你提到了纸船停下来的地方，可以沿着这个细节继续讲。'],
                  questions=['你会怎样画出这个地方？'],limits=[])
    with patch.dict(os.environ,{},clear=True):
        before=len(state['calls'])
        insufficient=llm.reading_feedback(agreement,'',excerpt='虚构篇目片段。')
        assert insufficient['feedback']==[] and insufficient['questions']==[]
        assert '尚无' in insufficient['limits'][0] and len(state['calls'])==before
    env=dict(FAMILY_LLM_BASE_URL=f'http://127.0.0.1:{server.server_port}/v1',
             FAMILY_LLM_MODEL='synthetic-model',FAMILY_LLM_API_KEY='synthetic-secret',
             FAMILY_LLM_REASONING_EFFORT='none',HTTP_PROXY='http://127.0.0.1:1',NO_PROXY='')
    with patch.dict(os.environ,env,clear=True):
        state['mode']=feedback
        work='虚构作品：我画了纸船停在石头旁边。'
        result=llm.reading_feedback(agreement,work)
        assert result['feedback']==feedback['feedback'] and result['questions']==feedback['questions']
        assert result['limits'][0].startswith('未提供篇目原文')
        path,body,key=state['calls'][-1]
        assert path=='/v1/chat/completions' and key=='Bearer synthetic-secret'
        assert body['response_format']['json_schema']['name']=='family_reading_feedback'
        assert body['response_format']['json_schema']['strict'] is True and body['reasoning_effort']=='none'
        assert 'tools' not in body and len(body['messages'])==2
        assert json.loads(body['messages'][1]['content'][0]['text'])==dict(agreement=agreement,work_text=work,excerpt='')
        assert '不得核验' in body['messages'][0]['content'] and '不发放印章' in body['messages'][0]['content']
        result=llm.reading_feedback(agreement,'',images=[dict(mime='image/png',data=b'synthetic-work-image',name='must-not-send-name')],
                                    excerpt='虚构原文：纸船停在石头旁。')
        assert result['limits'][0].startswith('仅依据本次提供的篇目片段')
        body=state['calls'][-1][1]
        assert len(body['messages'][1]['content'])==2
        assert body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
        assert 'must-not-send-name' not in json.dumps(body)
        before=len(state['calls'])
        bad_inputs=[dict(agreement=dict(agreement,child='虚构孩子甲')),
                    dict(agreement={}),dict(agreement=dict(agreement,scope=[])),
                    dict(agreement=dict(agreement,book=' ')),dict(work_text=[]),
                    dict(work_text='x'*(llm.MAX_TEXT+1)),dict(excerpt='x'*(llm.MAX_TEXT+1)),
                    dict(images=[dict(mime='image/svg+xml',data=b'x')]),
                    dict(images=[dict(mime='image/png',data=b'x')]*4),
                    dict(images=[dict(mime='image/png',data='not-bytes')]),
                    dict(images=[dict(mime='image/png',data=b'x'*llm.MAX_INPUT)]),
                    dict(timeout=0),dict(timeout=181),dict(timeout=True),dict(timeout=float('nan'))]
        for bad in bad_inputs:
            kwargs=dict(agreement=agreement,work_text=work);kwargs.update(bad)
            try: llm.reading_feedback(**kwargs)
            except ValueError: pass
            else: raise AssertionError('invalid reading feedback input accepted')
        assert len(state['calls'])==before
        for mode in [dict(feedback,award=1),dict(feedback,feedback='not a list'),
                     dict(feedback,feedback=['x']*4),dict(feedback,questions=[' ']),
                     dict(feedback,questions=['x'*301]),dict(feedback,limits=['x']*6),
                     dict(feedback,limits=[None]),'bad_json','empty','length','bad_outer',
                     'http_error','redirect','large','timeout']:
            state['mode']=mode
            try: llm.reading_feedback(agreement,work,timeout=.03 if mode=='timeout' else 2)
            except llm.LLMDraftError as error:
                assert 'synthetic-secret' not in str(error) and 'PRIVATE_RESPONSE' not in str(error)
            else: raise AssertionError('invalid reading feedback output accepted')
        state['mode']=dict(feedback,limits=['虚构限制'+str(i) for i in range(5)])
        bounded=llm.reading_feedback(agreement,work)
        assert len(bounded['limits'])==5 and bounded['limits'][0].startswith('未提供篇目原文')
        assert state['redirect_calls']==0
    with patch.dict(os.environ,{},clear=True):
        try: llm.transcribe_audio(b'synthetic-audio','audio/wav')
        except llm.LLMUnavailable: pass
        else: raise AssertionError('missing ASR configuration accepted')
    env=dict(FAMILY_ASR_URL=f'http://127.0.0.1:{server.server_port}/v1/audio/transcriptions',
             FAMILY_ASR_API_KEY='synthetic-secret',HTTP_PROXY='http://127.0.0.1:1',NO_PROXY='')
    with patch.dict(os.environ,env,clear=True):
        state['mode']='ok'
        assert llm.transcribe_audio(b'synthetic-audio','audio/wav')=='虚构录音转写，等待核对。'
        path,body,key=state['calls'][-1]
        assert path=='/v1/audio/transcriptions' and key=='Bearer synthetic-secret'
        def audio_parts(body):
            message=BytesParser(policy=default).parsebytes(('Content-Type: '+state['audio_type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
            return {part.get_param('name',header='content-disposition'):part for part in message.iter_parts()}
        parts=audio_parts(body)
        assert set(parts)=={'file','model','language','response_format','temperature'}
        assert parts['file'].get_filename()=='recording.wav' and parts['file'].get_payload(decode=True)==b'synthetic-audio'
        assert parts['file'].get_content_type()=='audio/wav'
        assert {name:parts[name].get_payload(decode=True).decode() for name in parts if name!='file'}==dict(model='base',language='zh',response_format='json',temperature='0')
        os.environ.pop('FAMILY_ASR_API_KEY');os.environ['FAMILY_ASR_MODEL']='synthetic-small'
        llm.transcribe_audio(b'synthetic-audio','audio/webm')
        assert state['calls'][-1][2] is None
        parts=audio_parts(state['calls'][-1][1])
        assert parts['file'].get_filename()=='recording.webm' and parts['model'].get_payload(decode=True)==b'synthetic-small'
        before=len(state['calls'])
        for audio,mime,timeout in [(b'','audio/wav',90),('text','audio/wav',90),
                                   (b'x'*(llm.MAX_INPUT+1),'audio/wav',90),
                                   (b'x','text/plain',90),(b'x',[],90),(b'x','audio/webm;codecs=opus',90),
                                   (b'x','audio/wav',0),(b'x','audio/wav',181),(b'x','audio/wav',True),
                                   (b'x','audio/wav',float('nan'))]:
            try: llm.transcribe_audio(audio,mime,timeout)
            except ValueError: pass
            else: raise AssertionError('invalid ASR input accepted')
        assert len(state['calls'])==before
        for mode in ['bad_json','large','http_error','redirect','timeout']:
            state['mode']=mode
            try: llm.transcribe_audio(b'x','audio/wav',timeout=.03 if mode=='timeout' else 2)
            except llm.LLMDraftError as error:
                assert 'synthetic-secret' not in str(error) and 'PRIVATE_RESPONSE' not in str(error)
            else: raise AssertionError('unsafe ASR response accepted')
        assert state['redirect_calls']==0
        state['mode']='ok'
        for value in [[],{},None,{'text':None},{'text':123},{'text':' '},{'text':'x'*6001}]:
            state['asr_result']=value
            try: llm.transcribe_audio(b'x','audio/wav')
            except llm.LLMDraftError: pass
            else: raise AssertionError('invalid transcription accepted')
        for url in ['http://user:password@localhost/transcriptions','file:///tmp/transcriptions',
                    'http://localhost:0/transcriptions','http://localhost/transcriptions?key=synthetic-secret']:
            os.environ['FAMILY_ASR_URL']=url
            try: llm.transcribe_audio(b'x','audio/wav')
            except llm.LLMUnavailable as error:
                assert 'password' not in str(error) and 'synthetic-secret' not in str(error)
            else: raise AssertionError('unsafe ASR endpoint accepted')
    with patch.dict(os.environ,{'FAMILY_LLM_MODEL':'synthetic-model','FAMILY_LLM_API_KEY':'synthetic-secret',
                               'FAMILY_LLM_BASE_URL':f'http://127.0.0.1:{server.server_port}/v1/responses',
                               'FAMILY_LLM_REASONING_EFFORT':'low'},clear=True):
        state['mode']='ok'
        assert llm.extract_draft('虚构数学测验85/100',images=[dict(data=b'synthetic-image',mime='image/png')])==DRAFT
        path,body,key=state['calls'][-1]
        assert path=='/v1/responses', 'A full Responses endpoint must not gain /chat/completions'
        assert body['store'] is False and body['stream'] is False and body['max_output_tokens']==3000
        assert body['reasoning']=={'effort':'low'} and 'reasoning_effort' not in body
        assert body['text']['format']==dict(type='json_schema',name='family_learning_draft',strict=True,schema=llm.SCHEMA)
        assert body['input'][0]['role']=='system' and body['input'][0]['content']==llm.PROMPT
        assert body['input'][1]['content']==[
            dict(type='input_text',text='虚构数学测验85/100'),
            dict(type='input_image',image_url='data:image/png;base64,c3ludGhldGljLWltYWdl')]
        assert not {'messages','tools','previous_response_id','max_tokens','response_format'} & body.keys()
        assert key=='Bearer synthetic-secret'
        valid_message=dict(type='message',role='assistant',status='completed',content=[dict(type='output_text',text=json.dumps(DRAFT))])
        for invalid in [dict(status='incomplete',output=[valid_message]),dict(status='failed',output=[valid_message]),
                        dict(status='completed',output=[]),dict(status='completed',output=[dict(valid_message,role='user')]),
                        dict(status='completed',output=[dict(valid_message,status='in_progress')]),
                        dict(status='completed',output=[dict(valid_message,content=[dict(type='refusal',refusal='PRIVATE_RESPONSE')])]),
                        dict(status='completed',output=[valid_message,dict(type='function_call',name='unsafe_tool')])]:
            state['mode']=invalid
            try: llm.extract_draft('虚构资料')
            except llm.LLMDraftError as error:
                assert 'PRIVATE_RESPONSE' not in str(error) and 'PRIVATE_REASONING' not in str(error)
            else: raise AssertionError('An incomplete, refused or unexpected Responses output was accepted')
        state['mode']='redirect';before_calls=len(state['calls'])
        try: llm.extract_draft('虚构资料')
        except llm.LLMDraftError: pass
        else: raise AssertionError('Responses redirect accepted')
        assert state['redirect_calls']==0 and len(state['calls'])==before_calls+1
finally:
    server.shutdown();server.server_close()

material=dict(title='虚构分数题',subject='数学',question_text='1/2加1/3，先考虑什么？',
              reference_text='先通分为六分之三加六分之二，结果六分之五。',reference_checked=True)
attempts=[dict(kind='first',text='我把分子分母各自相加了。',assistance='')]
hint=dict(hint='先让每一份的大小相同，再考虑相加。',question='两个分母的公倍数可以选哪个？',uncertainties=[])
with patch.object(llm,'_chat_json',return_value=dict(hint,reference_status='consistent',reference_check='虚构参考核对说明',response_kind='hint')) as model:
    assert llm.guided_hint(material,attempts,[])==hint
    args=model.call_args.args
    assert args[2]=='family_guided_hint' and args[1]['additionalProperties'] is False
    content=json.loads(args[0][1]['content'][0]['text'])
    assert content==dict(material=material,attempts=attempts,hints=[])
    assert 'parent_observations' not in content
    assert '不宣布作业完成' in args[0][0]['content'] and '不复述或引用家长参考原文' in args[0][0]['content']
    model.reset_mock()
    result=llm.guided_hint(dict(material,reference_checked=False),attempts,[])
    assert not result['hint'] and result['uncertainties'] and not model.called
    for changed in [dict(material=dict(material,parent_note='PRIVATE_CANARY')),
                    dict(attempts=[]),dict(attempts=[dict(attempts[0],child_id='other')]),
                    dict(images=[dict(mime='image/png',data=b'synthetic-image',label='家长参考')])]:
        kwargs=dict(material=material,attempts=attempts,hints=[]);kwargs.update(changed)
        try:llm.guided_hint(**kwargs)
        except ValueError:pass
        else:raise AssertionError('guided material boundary accepted invalid context')
    for bad in [dict(hint,mastered=True),dict(hint,hint='x'*501),dict(hint,uncertainties=['x']*4),
                dict(hint='',question='',uncertainties=[]),dict(hint,hint=None)]:
        model.return_value=dict(bad,reference_status='consistent',reference_check='虚构参考核对说明',response_kind='hint')
        try:llm.guided_hint(material,attempts,[])
        except llm.LLMDraftError:pass
        else:raise AssertionError('unchecked guided model output accepted')
    model.return_value=dict(hint,reference_status='conflict',reference_check='PRIVATE_REFERENCE_CHECK',response_kind='clarify')
    halted=llm.guided_hint(material,attempts,[])
    assert not halted['hint'] and '冲突' in halted['uncertainties'][0]
    assert 'PRIVATE_REFERENCE_CHECK' not in json.dumps(halted)

plan=dict(goal='解释为什么先通分',success_criteria='能说清每一份大小相同才能相加，记录实际帮助。',
          start='先请孩子自己说思路。',ask='这两种分数中的每一份一样大吗？',
          help='卡住时用分割图提示；必要时示范相似的一步，再请孩子继续。',
          stop='能表达本次理由或想休息时结束，保留真实尝试。',retry='商量后隔一段时间，不看讲解试相近新题。')
raw_plan=dict(reference_status='consistent',reference_check='虚构参考与题目相符',plan=plan,uncertainties=[])
with patch.object(llm,'_chat_json',return_value=raw_plan) as model:
    proposal=llm.guided_plan(material,[],[],goal='家长明确目标',success_criteria='家长明确观察条件')
    assert proposal['plan']['goal']=='家长明确目标' and proposal['plan']['success_criteria']=='家长明确观察条件'
    args=model.call_args.args
    assert args[2]=='family_guided_plan' and args[1]['additionalProperties'] is False
    assert args[1]['properties']['plan']['additionalProperties'] is False
    content=json.loads(args[0][1]['content'][0]['text'])
    assert content==dict(material=material,attempts=[],hints=[],parent_goal='家长明确目标',parent_success_criteria='家长明确观察条件')
    assert '不硬编码1/3/7天' in args[0][0]['content'] and '先独立尝试' in args[0][0]['content']
    observation=dict(record_id=17,day='2026-09-08',title='虚构家长观察',
                     text='孩子在第二步停下来，说分母还没有看清。',assistance='少量提示',comparison_note='孩子自述与家长观察待核对')
    model.reset_mock()
    proposal=llm.guided_plan(material,[],[],parent_observations=(observation,),older_observations_count=2)
    assert proposal['plan']==plan
    args=model.call_args.args
    observed=json.loads(args[0][1]['content'][0]['text'])
    assert observed['parent_observations']==[observation] and observed['older_observations_count']==2
    assert '不是孩子在本题中的亲述' in args[0][0]['content']
    assert '私人观察原句或评价' in args[0][0]['content']
    model.reset_mock()
    invalid_observations=[
        {}, dict(observation,record_id=True), dict(observation,day='2026-02-30'),
        dict(observation,title='x'*201), dict(observation,text='x'*20001),
        dict(observation,comparison_note='x'*2001), dict(observation,assistance='未知'),
        dict(observation,private='不允许'),
    ]
    for bad in invalid_observations:
        try: llm.guided_plan(material,[],[],parent_observations=[bad])
        except ValueError: pass
        else: raise AssertionError('invalid parent observation accepted')
    for count in (-1,True,1.5):
        try: llm.guided_plan(material,[],[],older_observations_count=count)
        except ValueError: pass
        else: raise AssertionError('invalid older observation count accepted')
    assert not model.called
    for changed in [dict(material=dict(material,parent_note='PRIVATE_CANARY')),dict(goal='x'*301),
                    dict(success_criteria=False),dict(attempts=[dict(attempts[0],child_id='other')]),
                    dict(images=[dict(mime='image/png',data=b'synthetic-image',label='家长参考')])]:
        kwargs=dict(material=material,attempts=[],hints=[]);kwargs.update(changed)
        try:llm.guided_plan(**kwargs)
        except ValueError:pass
        else:raise AssertionError('parent guide accepted unbounded or unrelated input')
    model.reset_mock()
    missing=llm.guided_plan(dict(material,reference_checked=False),[],[],goal='明确目标')
    assert missing['plan']['goal']=='明确目标' and not missing['plan']['start'] and missing['uncertainties'] and not model.called
    missing=llm.guided_plan(dict(material,question_text=''),[],[])
    assert not missing['plan']['goal'] and missing['uncertainties'] and not model.called
    for bad in [dict(raw_plan,mastered=True),dict(raw_plan,plan=dict(plan,goal='x'*301)),
                dict(raw_plan,plan=dict(plan,help=None)),dict(raw_plan,plan=dict(plan,score=10)),
                dict(raw_plan,uncertainties=['x']*4),dict(raw_plan,reference_status='approved')]:
        model.return_value=bad
        try:llm.guided_plan(material,attempts,[])
        except llm.LLMDraftError:pass
        else:raise AssertionError('unchecked parent teaching output accepted')
    model.return_value=dict(raw_plan,reference_status='conflict',reference_check='虚构参考算式与原题不一致')
    conflict=llm.guided_plan(material,attempts,[],goal='家长目标')
    assert conflict['plan']['goal']=='家长目标' and not conflict['plan']['start'] and '冲突' in conflict['uncertainties'][0]

with patch.object(llm,'_chat_json',return_value=dict(hint,reference_status='consistent',reference_check='核对相符',response_kind='hint')) as model:
    shared_goal=dict(goal='家长核对的目标',success_criteria='能解释这一步并记录帮助程度')
    assert llm.guided_hint(material,attempts,[],learning_goal=shared_goal)==hint
    assert json.loads(model.call_args.args[0][1]['content'][0]['text'])['learning_goal']==shared_goal
    try:llm.guided_hint(material,attempts,[],learning_goal=dict(shared_goal,parent_guide='PRIVATE_CANARY'))
    except ValueError:pass
    else:raise AssertionError('parent-only plan leaked into child hint context')

server=ThreadingHTTPServer(('127.0.0.1',0),Mock)
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
  with TemporaryDirectory() as legacy:
    legacy_path=Path(legacy)
    legacy_config=dict(base_url='http://127.0.0.1:1/v1',model='synthetic-primary',api_key='',reasoning_effort='')
    (legacy_path/'model.json').write_text(json.dumps(legacy_config))
    with patch.dict(os.environ,{},clear=True):
        loaded=llm.model_values(legacy_path)
        assert loaded['light_model']=='' and loaded['model']=='synthetic-primary'
        (legacy_path/'model.json').write_text(json.dumps({**legacy_config,'light_model':'synthetic-light'}))
        assert llm.model_values(legacy_path)['light_model']=='synthetic-light'
        (legacy_path/'model.json').write_text(json.dumps({**legacy_config,'model':'','light_model':'synthetic-light'}))
        try: llm.model_values(legacy_path)
        except llm.LLMUnavailable: pass
        else: raise AssertionError('light model accepted without primary configuration')
    with patch.dict(os.environ,{
            'FAMILY_LLM_BASE_URL':'http://127.0.0.1:1/v1','FAMILY_LLM_MODEL':'synthetic-primary',
            'FAMILY_LLM_LIGHT_MODEL':'x'*201},clear=True):
        try: llm.configuration()
        except llm.LLMUnavailable: pass
        else: raise AssertionError('oversized light model accepted')
    try: llm.validate_model(dict(base_url='http://127.0.0.1:1/v1',model='synthetic-primary',
                                 light_model='',api_key='bad\x00key',reasoning_effort=''))
    except llm.LLMUnavailable: pass
    else: raise AssertionError('control character in environment configuration accepted')
  with TemporaryDirectory() as temporary:
    data_path=Path(temporary)
    endpoint=f'http://127.0.0.1:{server.server_port}/v1'
    env=dict(FAMILY_LLM_BASE_URL=endpoint,FAMILY_LLM_MODEL='configured-chat-model',
             FAMILY_LLM_API_KEY='PRIVATE_KEY_CANARY',FAMILY_LLM_LIGHT_MODEL='configured-light-model')
    state['mode']='ok';state['usage']={'prompt_tokens':11,'completion_tokens':7,'total_tokens':18}
    state['reported_model']='provider-chat-model'
    with patch.dict(os.environ,env,clear=True):
        llm.extract_draft('PRIVATE_PROMPT_CANARY',data_path=data_path)
        summary=llm.usage_summary(data_path)
        assert summary['calls']==1 and summary['returned']==1 and summary['failed']==0
        assert summary['input_tokens']==11 and summary['output_tokens']==7 and summary['total_tokens']==18
        assert summary['unknown_usage']==0 and summary['groups'][0]['protocol']=='chat'
        state['mode']='http_error_json';state['usage']={'prompt_tokens':13,'completion_tokens':2,'total_tokens':15}
        try: llm.extract_draft('虚构资料',data_path=data_path)
        except llm.LLMDraftError: pass
        else: raise AssertionError('HTTP error accepted')
        state['mode']=dict(DRAFT,extra='unexpected')
        state['usage']={'prompt_tokens':17,'completion_tokens':3,'total_tokens':20}
        try: llm.extract_draft('虚构资料',data_path=data_path)
        except llm.LLMDraftError: pass
        else: raise AssertionError('invalid result accepted')
        summary=llm.usage_summary(data_path)
        assert summary['failed']==1 and summary['returned']==2 and summary['total_tokens']==53
        state['mode']='ok';state['usage']={'prompt_tokens':True,'completion_tokens':-2,'total_tokens':2**63}
        llm.extract_draft('虚构资料',data_path=data_path)
        summary=llm.usage_summary(data_path)
        assert summary['unknown_usage']==1 and summary['input_tokens']==41 and summary['output_tokens']==12
        state['mode']='ok';state['usage']={'input_tokens':23,'output_tokens':9,'total_tokens':32}
        state['reported_model']='provider-responses-model'
        os.environ['FAMILY_LLM_BASE_URL']=endpoint+'/responses'
        os.environ['FAMILY_LLM_MODEL']='configured-responses-model'
        llm.extract_draft('虚构资料',data_path=data_path)
        state['usage']={}
        llm.extract_draft('虚构资料',data_path=data_path)
        summary=llm.usage_summary(data_path)
        assert summary['groups'][-1]['protocol']=='responses'
        assert summary['groups'][-1]['input_tokens']==23 and summary['groups'][-1]['output_tokens']==9
        assert summary['groups'][-1]['unknown_usage']==1
        assert llm.usage_summary(Path(os.path.relpath(data_path)))==summary
        with sqlite3.connect(data_path/'family.sqlite3') as connection:
            rows=connection.execute(
                'SELECT task,model,reported_model,protocol,state,input_tokens,output_tokens,total_tokens '
                'FROM llm_usage_ledger').fetchall()
        dump=repr(rows)
        assert 'PRIVATE_KEY_CANARY' not in dump and 'PRIVATE_PROMPT_CANARY' not in dump
        assert 'provider-chat-model' in dump and 'provider-responses-model' in dump
        state['mode']='ok';state['usage']={'prompt_tokens':5,'completion_tokens':2,'total_tokens':7}
        os.environ['FAMILY_LLM_BASE_URL']=endpoint
        os.environ['FAMILY_LLM_MODEL']='configured-chat-model'
        os.environ['FAMILY_LLM_LIGHT_MODEL']='configured-light-model'
        llm._chat_json([dict(role='user',content='synthetic light ledger call')],llm.SCHEMA,
                       'family_agent_selection',data_path=data_path)
        assert any(group['task']=='family_agent_selection' and group['model']=='configured-light-model'
                   for group in llm.usage_summary(data_path)['groups'])
        state['mode']='http_error';before=len(state['calls'])
        try: llm._chat_json([dict(role='user',content='synthetic light failure')],llm.SCHEMA,
                            'family_agent_selection',data_path=data_path)
        except llm.LLMDraftError: pass
        else: raise AssertionError('light model failure unexpectedly fell back')
        assert len(state['calls'])==before+1 and state['calls'][-1][1]['model']=='configured-light-model'
        state['mode']='ok';state['usage']={'input_tokens':3,'output_tokens':1,'total_tokens':4}
        os.environ['FAMILY_LLM_BASE_URL']=endpoint+'/responses'
        llm._chat_json([dict(role='user',content='synthetic responses light call')],llm.SCHEMA,
                       'family_agent_selection',data_path=data_path)
        assert state['calls'][-1][1]['model']=='configured-light-model'
        before=len(state['calls'])
        try: llm.extract_draft('虚构资料',data_path=data_path/'missing-parent')
        except llm.LLMDraftError: pass
        else: raise AssertionError('ledger failure accepted')
        assert len(state['calls'])==before
    with TemporaryDirectory() as empty:
        absent=Path(empty)/'no-create'
        assert llm.usage_summary(absent)['calls']==0 and not absent.exists()
    with TemporaryDirectory() as pending_only:
        # Abrupt exit at the transport boundary must leave a committed, unknown attempt.
        script='''import os, sys, family_llm
from unittest.mock import patch
class Crash:
    def open(self, request, timeout): os._exit(17)
with patch.object(family_llm, 'build_opener', return_value=Crash()):
    family_llm.extract_draft('synthetic crash check', data_path=sys.argv[1])
'''
        crashed=subprocess.run([sys.executable,'-c',script,pending_only],env=env,timeout=10)
        assert crashed.returncode==17
        pending=llm.usage_summary(Path(pending_only))
        assert pending['calls']==pending['pending']==pending['unknown_usage']==1
        assert pending['elapsed_ms'] is None and pending['total_tokens'] is None
finally:
    server.shutdown();server.server_close()

print('PASS: draft, reading feedback, guided hints, audio and bounded usage ledger; isolated HTTP, redaction, failure and interruption checks')
