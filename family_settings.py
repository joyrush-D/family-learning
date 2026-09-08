"""Parent-only household configuration; no collection or model calls on save."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

import family_agent
import family_llm


class SettingsError(ValueError):
    def __init__(self, message, status=400, code='invalid_settings'):
        super().__init__(message); self.status=status; self.code=code


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def revision(value):
    return hashlib.sha256(value).hexdigest()


def raw_config(path):
    if path.is_symlink(): raise SettingsError('配置不能是符号链接',409)
    if not path.exists(): return b''
    if path.stat().st_size>32768: raise SettingsError('配置文件过大，请先核对',409)
    return path.read_bytes()


def atomic_json(path, value):
    raw_config(path)
    fd, name=tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(encoded(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


def check_revision(obj, current, wanted=None):
    expected=obj.get('revision')
    if not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected):
        raise SettingsError('请先读取当前配置再保存')
    if expected!=revision(current) and (wanted is None or current!=encoded(wanted)):
        raise SettingsError('配置已更新，请重新读取并核对后保存',409,'settings_version_conflict')


class Store:
    def __init__(self, app):
        self.app=app; self.agent=app.agent_store(); self.data=Path(app.DATA)

    def snapshot(self):
        config=self.agent._config(); state=self.agent.snapshot()
        return dict(children=self.app.profiles(),enabled=config['enabled'],sources=state['sources'],
                    revision=revision(raw_config(self.data/'agent.json')),
                    agent={key:state.get(key,'') for key in ['state','last_run','last_error']},
                    model=self.model_state())

    def create_child(self,obj):
        if set(obj)!={'name','grade','classroom','request_key'}:
            raise SettingsError('请填写孩子称呼、年级和班级')
        fields={k:self.app.clean(obj,k,80) for k in ['name','grade','classroom']}
        if not fields['name']: raise SettingsError('请填写孩子称呼')
        for value in fields.values():
            if '|' in value or any(ord(c)<32 or ord(c)==127 for c in value):
                raise SettingsError('档案字段不能含竖线、换行或控制字符')
        if '（' in fields['name'] or '）' in fields['name']: raise SettingsError('称呼不加全角括号备注')
        key=obj.get('request_key')
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',key):
            raise SettingsError('请求编号不正确，请重试')
        fingerprint=revision(encoded(fields))
        with self.app.connect() as c:
            c.execute('CREATE TABLE IF NOT EXISTS profile_creations (request_key TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, child_id TEXT NOT NULL)')
            c.execute('BEGIN IMMEDIATE')
            previous=c.execute('SELECT * FROM profile_creations WHERE request_key=?',(key,)).fetchone()
            children,owners=self.app.profile_state(c)
            if previous:
                if previous['fingerprint']!=fingerprint: raise SettingsError('该请求已用于其他档案，请重新核对',409)
                return dict(profile=next(p for p in children if p['id']==previous['child_id']))
            if len(children)>=20: raise SettingsError('当前家庭最多支持20个孩子档案')
            if fields['name'] in owners: raise SettingsError('称呼已被使用，包括历史称呼；请换一个称呼',409,'profile_alias_conflict')
            if c.execute('SELECT 1 FROM records WHERE child=?',(fields['name'],)).fetchone() or any(t['child']==fields['name'] for t in self.app.tasks(c)):
                raise SettingsError('该称呼已有归属未核对的记录，请先核对',409,'profile_alias_conflict')
            unclaimed=set()
            for filename in ['陪伴建议.json','采集状态.json']:
                path=self.data/filename
                if not path.exists(): continue
                try:
                    sources=json.loads(path.read_text())
                    if not isinstance(sources,(list,dict)): raise ValueError()
                    for source in sources if isinstance(sources,list) else sources.values():
                        if isinstance(source,dict) and isinstance(source.get('child'),str): unclaimed.add(source['child'])
                except (OSError,ValueError): raise SettingsError('来源归属无法核对，请先修复来源文件',409) from None
            if fields['name'] in unclaimed: raise SettingsError('该称呼已有未核对的来源归属',409,'profile_alias_conflict')
            used={p['id'] for p in children}|set(owners.values())
            ident='child-'+str(max([int(p[6:]) for p in used if re.fullmatch(r'child-[0-9]+',p)]+[0])+1)
            c.execute('INSERT INTO profile_overrides VALUES (?,?,?,?,?)',(ident,fields['name'],fields['grade'],fields['classroom'],1))
            for name,owner in [*owners.items(),(fields['name'],ident)]:
                c.execute('INSERT OR IGNORE INTO profile_aliases VALUES (?,?)',(name,owner))
            c.execute('INSERT INTO profile_history VALUES (?,?,?,?,?,?)',(ident,1,'{}',encoded(fields).decode(),'家长在家庭设置中创建档案',dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat()))
            c.execute('INSERT INTO profile_creations VALUES (?,?,?)',(key,fingerprint,ident))
            # Empty source documents keep the existing backup/import flow usable; never rewrite originals.
            for name in ['家庭运行规则','消息来源','跟踪台账','学习与成长']:
                path=Path(self.app.ROOT)/(name+'.md')
                try:
                    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                except FileExistsError: continue
                with os.fdopen(fd,'w') as stream: stream.write('# '+name+'\n\n家庭档案和网页记录保存在私有数据库；未录入内容保持未知。\n')
            return dict(profile=next(p for p in self.app.profiles(c) if p['id']==ident))

    def save_sources(self,obj):
        if set(obj)!={'revision','enabled','sources'} or type(obj.get('enabled')) is not bool:
            raise SettingsError('来源配置格式不正确')
        rows=obj['sources']
        if not isinstance(rows,list) or len(rows)>20: raise SettingsError('当前最多支持20个群来源')
        with self.agent._db() as c:
            c.execute('BEGIN IMMEDIATE')
            current=raw_config(self.data/'agent.json'); old=self.agent._config()
            known={row['id']:row for row in old['sources']}; children={p['id'] for p in self.app.profiles(c)}
            sources=[]; seen=set()
            for row in rows:
                if not isinstance(row,dict) or set(row)!={'id','platform','child_id','name','enabled'}:
                    raise SettingsError('来源字段不正确；游标由采集器维护')
                for key,limit in [('id',160),('name',200),('child_id',80)]:
                    family_agent._text(row,key,limit,True)
                ident=row['id']; platform=row['platform']
                if platform not in {'wechat','qq'} or row['child_id'] not in children or type(row['enabled']) is not bool:
                    raise SettingsError('请核对消息平台、孩子归属和启用状态')
                pattern=r'(?:wechat:)?[0-9]{5,32}@chatroom' if platform=='wechat' else r'(?:qq:)?[0-9]{5,20}'
                if not re.fullmatch(pattern,ident) or ident in seen: raise SettingsError('群标识不正确或重复，请填写CLI提供的真实群标识')
                canonical=(platform,ident.removeprefix(platform+':'))
                if canonical in seen: raise SettingsError('同一个群不能以不同前缀重复绑定')
                seen.add(ident); seen.add(canonical)
                previous=known.get(ident)
                if previous and (previous['platform'],previous['child_id'])!=(platform,row['child_id']):
                    raise SettingsError('已有群不能改绑平台或孩子；请停用并核对历史归属',409,'source_binding_conflict')
                saved=c.execute('SELECT * FROM agent_sources WHERE id=?',(ident,)).fetchone()
                binding=self.agent._binding(row,saved)
                cursor=saved['cursor'] if saved else previous['cursor'] if previous else '0' if platform=='wechat' else ''
                sources.append({**row,'cursor':cursor})
                if saved is None: c.execute('INSERT INTO agent_sources(id,binding,cursor) VALUES(?,?,?)',(ident,binding,cursor))
            if not set(known)<=seen: raise SettingsError('已有来源请停用，不能删除其历史绑定',409)
            wanted=dict(enabled=obj['enabled'],sources=sources)
            check_revision(obj,current,wanted)
            atomic_json(self.data/'agent.json',wanted)
        return self.snapshot()

    def model_state(self):
        try: raw=raw_config(self.data/'model.json')
        except (OSError,SettingsError):
            return dict(revision='',origin='file',base_url='',model='',has_api_key=False,reasoning_effort='',configured=False,error='模型配置无法读取；手动记录仍可使用，请先核对私有配置文件')
        try:
            config=family_llm.model_values(self.data)
            family_llm.validate_model(config,allow_empty=True)
            error=''
        except family_llm.LLMUnavailable as failure:
            config=dict(base_url='',model='',api_key='',reasoning_effort='',origin='file');error=str(failure)
        return dict(revision=revision(raw),origin=config['origin'],base_url=config['base_url'],model=config['model'],
                    has_api_key=bool(config['api_key']),reasoning_effort=config['reasoning_effort'],
                    configured=bool(config['base_url'] and config['model'] and not error),error=error)

    def save_model(self,obj):
        if not {'revision','base_url','model'}<=set(obj) or not set(obj)<={'revision','base_url','model','api_key','reasoning_effort','clear_api_key'}:
            raise SettingsError('模型配置字段不正确')
        if family_llm.environment_model(): raise SettingsError('当前模型由部署环境管理，请在部署配置中更改；网页未覆盖',409,'model_environment_managed')
        if type(obj.get('clear_api_key',False)) is not bool: raise SettingsError('清除密钥选项格式不正确')
        with self.agent._db() as c:
            c.execute('BEGIN IMMEDIATE')
            current=raw_config(self.data/'model.json')
            try: config=family_llm.model_values(self.data)
            except family_llm.LLMUnavailable: config={key:'' for key in family_llm.MODEL_ENV}
            old_base=config['base_url'].rstrip('/')
            old_key=config['api_key']
            for key in ['base_url','model','api_key','reasoning_effort']:
                if key in obj:
                    value=obj[key]
                    if not isinstance(value,str) or len(value)>(4096 if key=='api_key' else 2000 if key=='base_url' else 200) or any(ord(ch)<32 or ord(ch)==127 for ch in value):
                        raise SettingsError('模型配置字段格式或长度不正确')
                    if key!='api_key' or value.strip(): config[key]=value.strip()
            if obj.get('clear_api_key'): config['api_key']=''
            if config['base_url'].rstrip('/')!=old_base and old_key and not obj.get('api_key','').strip() and not obj.get('clear_api_key'):
                raise SettingsError('更改模型地址时请重新填写密钥或明确清除原密钥',409,'model_key_endpoint_changed')
            wanted={key:config[key] for key in ['base_url','model','api_key','reasoning_effort']}
            try: family_llm.validate_model(wanted,allow_empty=True)
            except family_llm.LLMUnavailable as error: raise SettingsError(str(error)) from None
            check_revision(obj,current,wanted)
            atomic_json(self.data/'model.json',wanted)
        return dict(model=self.model_state())
