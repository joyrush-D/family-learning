import os, json, traceback, urllib.parse
os.environ['LOOPCHECK_SKIP_INGEST'] = '1'
import loopcheck_run as L
task = L.find_math_task(); child = task['child']
photo = L.WORK / 'evidence' / 'fake-homework-page.png'
st, up = L.http('POST', '/api/upload', raw_body=photo.read_bytes(), step='dbg-upload',
                headers={'X-File-Name': urllib.parse.quote(photo.name), 'X-Request-Key': L.rk(),
                         'Content-Type': 'image/png'})
attach = up['attachment']['id']
body = {'task_id': task['id'], 'child': child, 'complete': False,
        'completion_note': '数学练习册第12页第2至4题：第3、4题完成，第2题 2+3 写成了 6；拍照留档，待订正。',
        'note': '数学练习册第12页第2至4题：第3、4题完成，第2题 2+3 写成了 6；拍照留档，待订正。',
        'category': '学习进展', 'subject': '数学', 'attachments': [attach], 'request_key': L.rk()}
try:
    out = L.case.app.save_task_feedback(body)
    print('OK', json.dumps(out, ensure_ascii=False)[:500])
except Exception:
    traceback.print_exc()
    print('BODY', json.dumps(body, ensure_ascii=False))
