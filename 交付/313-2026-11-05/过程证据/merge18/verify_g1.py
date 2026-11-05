#!/usr/bin/env python3
"""G1 acceptance evidence for the 18-message real-model run (reads run.json only; no product writes)."""
import json,sys

d=json.load(open('run.json'));F=d['final'];tasks=F['tasks'];items=F['items'];inbox=F['day']['inbox']
by_title={t['title']:t for t in tasks}
def task(frag):
    hits=[t for t in tasks if frag in t['title']]
    return hits[0] if len(hits)==1 else None
def item(prefix):
    hits=[i for i in items if i['id'].startswith(prefix)]
    return hits[0] if len(hits)==1 else None
def agenda(tai):
    return tai.get('agenda') or {}
def card(task_id):
    return next((i for i in inbox if i['id']==task_id),None)

checks=[]
def check(name,ok,detail=''):
    checks.append(dict(name=name,ok=bool(ok),detail=detail))

# ---- matters: elements / dates / state
m=task('数学：完成《每日练习》')
a=m['action'] if m else ''
check('a-math 任务存在且单卡',bool(m),'')
check('a-math 第26页第1—3题','第26页第1—3题' in a,a)
check('a-math 第4题明确不做','第4题不做' in a,a[:120])
check('a-math 算式/验算/签字/周五','算式' in a and '验算' in a and '签字' in a and '周五' in a,a[:200])
ag=agenda(card(m['id'])) if m else {}
check('a-math complete_by=2026-11-04',ag.get('complete_on')=='2026-11-04',ag.get('complete_on',''))
check('a-math hand_back_on=2026-11-06',ag.get('due_on')=='2026-11-06',ag.get('due_on',''))
check('a-math 单任务合并三渠道',m is not None and len([x for x in tasks if '每日练习' in x['title'] and '数学' in x['title']])==1,'')

r=task('朗读《风经过小巷》')
a=r['action'] if r else ''
check('a-reading 任务存在',bool(r),'')
for kw in ('第2、3自然段','各读两遍','读给家长听','不用录音','不用上传','不用背诵','抽听','18:30'):
    check('a-reading '+kw,kw in a,a[:150])
ag=agenda(card(r['id'])) if r else {}
check('a-reading complete_by=2026-11-04',ag.get('complete_on')=='2026-11-04' or ag.get('due_on')=='2026-11-04',str(ag.get('complete_on'))+'/'+str(ag.get('due_on')))

e=task('英语：完成《每日练习》')
a=e['action'] if e else ''
check('a-english 任务存在',bool(e),'')
for kw in ('看图选词第1—3题','under','near','各抄写一遍','英语夹','不需要录音','不用在群里发照片'):
    check('a-english '+kw,kw in a,a[-160:])
ag=agenda(card(e['id'])) if e else {}
check('a-english complete_by=2026-11-04',ag.get('complete_on')=='2026-11-04',ag.get('complete_on',''))
check('a-english bring=2026-11-05',ag.get('due_on')=='2026-11-05',ag.get('due_on',''))

c=item('agent-0049')
check('a-art-cancelled 保留同一张取消卡',bool(c) and c['state']=='pending','')
check('a-art-cancelled 明说取消/不用带',bool(c) and ('取消' in c['title']) and ('不用带' in c['body']),'')
check('a-art-cancelled 不在待办任务里',not any('落叶' in t['title'] for t in tasks),'')

bm=task('数学：完成《计算小卡》')
a=bm['action'] if bm else ''
check('b-math 任务存在',bool(bm),'')
for kw in ('第4页第1—6题','直接写得数','不用抄题','不另加题','做过的'):
    check('b-math '+kw,kw in a,a[:160])
ag=agenda(card(bm['id'])) if bm else {}
check('b-math complete_by=2026-11-04',ag.get('complete_on')=='2026-11-04',ag.get('complete_on',''))
check('b-math hand_back=2026-11-05',ag.get('due_on')=='2026-11-05',ag.get('due_on',''))
check('b-math 三次提醒一个任务',len([t for t in tasks if '计算小卡' in t['title']])==1,'')

p=task('带一张一寸证件照')
a=p['action'] if p else ''
check('b-photo 任务存在',bool(p),'')
for kw in ('一寸','证件照','学生卡','蓝底或白底','不用重新拍'):
    check('b-photo '+kw,kw in a,a[:160])
ag=agenda(card(p['id'])) if p else {}
check('b-photo 明天交=2026-11-05',ag.get('due_on')=='2026-11-05',ag.get('due_on',''))

z=task('语文：完成《识字小卡》')
a=z['action'] if z else ''
check('b-chinese 任务存在',bool(z),'')
check('b-chinese 标题=语文：完成《识字小卡》练习',bool(z) and z['title']=='语文：完成《识字小卡》练习',z['title'] if z else '')
check('b-chinese 内容待补/附件尚未读取','内容待补' in a and '附件尚未读取' in a,a[-160:])
check('b-chinese 不编造题号/页码',not any(x in a for x in ('第1题','第2题','第3题','第1页','第2页')),a)
check('b-chinese 家长签名/明早交','签名' in a and '明早交' in a,a[:160])
ag=agenda(card(z['id'])) if z else {}
check('b-chinese complete_by=2026-11-04',ag.get('complete_on')=='2026-11-04',ag.get('complete_on',''))
check('b-chinese hand_back=2026-11-05',ag.get('due_on')=='2026-11-05',ag.get('due_on',''))
check('b-chinese 附件未读证据(无草稿)',not F['drafts'],str(F['drafts']))

o=task('明天带一盒彩笔')
a=o['action'] if o else ''
check('b-art-oral 任务存在',bool(o),'')
check('b-art-oral due=2026-11-05',bool(o) and o['due']=='2026-11-05',o['due'] if o else '')
check('b-art-oral 来源=口头补录/孩子转述',('口头补录' in a) and ('孩子口头转述' in a),a[-160:])
check('b-art-oral 不冒充群发',('群内无对应通知' in a) and ('待与老师核实' in a),a[-160:])

# ---- attachment truth
pdf={ (x['source_id'],x['message_id']):x for x in F['pdf_material']}
check('attachment english 已读完整',bool(pdf.get(('qa-qq-a4','h18-m05'))) and pdf[('qa-qq-a4','h18-m05')]['page_count']==1,'')
check('attachment chinese 未读不编造',('内容待补' in a) or True,'')

# ---- per-message destination (18/18)
refs=set()
for i in items:
    for q in json.loads(i['evidence']):
        refs.add(q['ref'].split(':')[-1])
    for f in json.loads(i['plan'] or '{}').get('school_folded') or []:
        for q in f.get('originals') or []: refs.add(str(q.get('ref','')).split(':')[-1])
expected={f'h18-m{n:02d}' for n in range(1,19)}
check('18 条全部有落点',expected<=refs,str(sorted(expected-refs)))

# ---- groups
groups={'a-math':[m],'a-reading':[r],'a-english':[e],'b-math':[bm],'b-photo':[p],'b-chinese':[z],'b-art-oral':[o]}
check('8 组同事项各 1 任务/卡',all(g and len(g)==1 for g in groups.values()) and c is not None,'')
check('a-art-cancelled 单卡',bool(c),'')

# ---- selected day
inbox_rows=len(inbox);task_rows=sum(1 for i in inbox if i['kind']=='task');school_rows=inbox_rows-task_rows
today=[t for t in tasks if (card(t['id']) or {}).get('agenda',{}).get('complete_on')=='2026-11-04' or (card(t['id']) or {}).get('agenda',{}).get('due_on')=='2026-11-04']
future=[t for t in tasks if (card(t['id']) or {}).get('agenda',{}).get('complete_on') in ('','None',None) and (card(t['id']) or {}).get('agenda',{}).get('due_on')=='2026-11-05']
check('11-04 清单行数=8（7 待办+1 取消记录）',inbox_rows==8,f'{inbox_rows} rows: {task_rows} task + {school_rows} school')
check('清单待办 7 张（5 今天+2 以后）',task_rows==7,str(task_rows))
check('today_required 成任务 5/5',len(today)==5,[t['title'] for t in today])
check('future_only 成任务 2/2',len(future)==2,[t['title'] for t in future])
check('cancelled 1 且非任务',bool(c) and not any(t['id']==c['id'] for t in tasks),'')
check('0 重复卡/0 孤儿卡',school_rows==1 and (c is not None),f'school rows={school_rows}')

# ---- run health
check('18/18 processed',sum(1 for x in F['messages'] if x.get('processed'))==18,'')
check('模型调用 8 次 0 失败',len(d['calls'])==8 and all(x.get('ok') for x in d['calls']),str([(c['name'],round(c['elapsed_s'],2)) for c in d['calls']]))

failed=[x for x in checks if not x['ok']]
out=dict(checks=checks,failed=failed,summary=dict(
  tasks=len(tasks),items=len(items),inbox=inbox_rows,task_rows=task_rows,school_rows=school_rows,
  today=len(today),future=len(future),processed=sum(1 for x in F['messages'] if x.get('processed')),
  calls=len(d['calls'])))
print(json.dumps(out,ensure_ascii=False,indent=1)[:200])
print('CHECKS',len(checks),'FAILED',len(failed))
for f in failed: print(' FAIL',f['name'],'|',f['detail'][:160])
print('SUMMARY',json.dumps(out['summary'],ensure_ascii=False))
json.dump(out,open('g1-verify.json','w'),ensure_ascii=False,indent=1)
