"""Run python3 test_llm.py. Mock loopback HTTP only; never sends family data."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from email.parser import BytesParser
from email.policy import default
import json
import os
import threading
import time
from unittest.mock import patch

import family_llm as llm

DRAFT=dict(title='虚构数学测验',subject='数学',score=85,total=100,note='虚构示例：订正情况未提供。',uncertainties=['订正情况未知'])
state={'mode':'ok','calls':[],'redirect_calls':0}

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
        if mode=='timeout': time.sleep(.15)
        if audio: result=state.get('asr_result',{'text':'  虚构录音转写，等待核对。  '})
        else:
            result={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(DRAFT,ensure_ascii=False)}}]}
            if isinstance(mode,dict): result['choices'][0]['message']['content']=json.dumps(mode)
            elif mode=='bad_json': result['choices'][0]['message']['content']='PRIVATE_RESPONSE invalid JSON'
            elif mode=='empty': result['choices'][0]['message']['content']=''
            elif mode=='length': result['choices'][0]['finish_reason']='length'
            elif mode=='bad_outer': result=[]
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

print('PASS: draft, reading feedback, requested guided hint and audio; bounded context/output, auth, timeout and error redaction')
