"""One explicit CUPS queue, a loopback SSH tunnel, and a durable no-reprint journal.

Run manually with --once. This does not discover or configure printers.
FAMILY_PRINT_BRIDGE_TOKEN is independent of the family web session token.
"""
import argparse
import fcntl
import getpass
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import struct
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from family_print import MAX_PDF, PrintError, printer_name, page_selection, SIDES, COLORS


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def cups_submission_id(stdout, printer):
    # macOS may localize lp even with LC_ALL=C. The queue/job identifier itself
    # is stable; accept only one exact identifier for the selected queue.
    pattern=rb'(?<![A-Za-z0-9_.-])('+re.escape(printer.encode())+rb'-[1-9][0-9]*)(?![A-Za-z0-9_.-])'
    matches=re.findall(pattern,stdout)
    return matches[0].decode() if len(matches)==1 else None


def cups_state(job_id):
    """Read standard IPP Get-Job-Attributes on local CUPS; never send a print job."""
    number = job_id.rsplit('-', 1)[-1]
    if not number.isdigit(): return None
    def attribute(tag, name, value):
        name, value = name.encode(), value.encode()
        return bytes([tag])+struct.pack('>H',len(name))+name+struct.pack('>H',len(value))+value
    body = b'\x01\x01\x00\x09\x00\x00\x00\x01\x01'
    body += attribute(0x47,'attributes-charset','utf-8')
    body += attribute(0x48,'attributes-natural-language','en')
    body += attribute(0x45,'job-uri','ipp://localhost/jobs/'+number)
    body += attribute(0x42,'requesting-user-name',getpass.getuser())
    body += attribute(0x44,'requested-attributes','job-state')+b'\x03'
    conn = http.client.HTTPConnection('127.0.0.1', 631, timeout=10)
    try:
        conn.request('POST','/jobs/',body,{'Content-Type':'application/ipp'})
        response = conn.getresponse(); data = response.read(65537)
        if response.status != 200 or len(data)>65536 or len(data)<9 or data[4:8]!=b'\x00\x00\x00\x01' or int.from_bytes(data[2:4],'big')>7: return None
        pos, name = 8, b''
        while pos < len(data):
            tag=data[pos];pos+=1
            if tag == 3: break
            if tag < 16: continue
            length=int.from_bytes(data[pos:pos+2],'big');pos+=2
            if length: name=data[pos:pos+length]
            pos+=length
            length=int.from_bytes(data[pos:pos+2],'big');pos+=2
            value=data[pos:pos+length];pos+=length
            if name==b'job-state' and tag==0x23 and len(value)==4:
                return int.from_bytes(value,'big')
    except (OSError, http.client.HTTPException, ValueError): pass
    finally: conn.close()
    return None


class Bridge:
    def __init__(self, url, token, printer, directory, bridge_id='local-family-print', lp='/usr/bin/lp', lpstat='/usr/bin/lpstat'):
        parsed=urllib.parse.urlsplit(url)
        if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise PrintError('桥接地址必须是现有SSH隧道的本机HTTP回环地址')
        if not token or len(token)<24: raise PrintError('请设置独立桥接凭据')
        if not re.fullmatch(r'[A-Za-z0-9_-]{8,128}',bridge_id): raise PrintError('桥接标识不正确')
        self.url,self.token,self.printer,self.bridge_id=url.rstrip('/'),token,printer_name(printer),bridge_id
        self.lp,self.lpstat=lp,lpstat
        self.directory=Path(directory).expanduser().resolve();self.directory.mkdir(mode=0o700,parents=True,exist_ok=True);self.directory.chmod(0o700)
        self.lock=(self.directory/'bridge.lock').open('a+b');os.chmod(self.directory/'bridge.lock',0o600)
        try:fcntl.flock(self.lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close();raise PrintError('同一打印桥接已在运行，未重复领取任务') from None
        self.db=sqlite3.connect(self.directory/'journal.sqlite3');self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS journal (id TEXT PRIMARY KEY, body TEXT NOT NULL, state TEXT NOT NULL, cups TEXT NOT NULL DEFAULT \'\')')
        self.db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY,value TEXT NOT NULL)');self.db.commit()
        (self.directory/'journal.sqlite3').chmod(0o600)
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())

    def close(self):
        self.db.close();self.lock.close()

    def request(self, path, body=None, claim=None, pdf=False):
        headers={'Authorization':'Bearer '+self.token}
        if claim: headers['X-Print-Claim']=claim
        if body is not None: headers['Content-Type']='application/json'
        request=urllib.request.Request(self.url+path,data=None if body is None else json.dumps(body).encode(),headers=headers)
        try:
            with self.opener.open(request,timeout=20) as response:
                limit=MAX_PDF if pdf else 100000
                payload=response.read(limit+1)
                if len(payload)>limit: raise PrintError('桥接响应过大')
                return payload if pdf else json.loads(payload)
        except (OSError, ValueError, urllib.error.URLError):
            raise PrintError('打印后台暂不可达，已保留桥接记录；不会重发打印') from None

    def _report(self, job, status, cups='', note=''):
        return self.request('/api/print/bridge/report',dict(job_id=job['id'],claim_token=job['claim_token'],status=status,cups_job_id=cups,note=note))

    def _save(self, job, state, cups=''):
        with self.db:
            self.db.execute('INSERT INTO journal VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,cups=excluded.cups', (job['id'],json.dumps(job),state,cups))

    def _configured(self):
        try:
            result=subprocess.run([self.lpstat,'-h','localhost','-p',self.printer],capture_output=True,timeout=10,env={**os.environ,'LC_ALL':'C'})
            # An explicit unknown queue exits nonzero; localized prose is not a protocol.
            return result.returncode==0
        except (OSError,subprocess.TimeoutExpired): return False

    def run_once(self):
        row=self.db.execute("SELECT * FROM journal WHERE state NOT IN ('done','review') ORDER BY rowid LIMIT 1").fetchone()
        if row:
            job=json.loads(row['body']);state=row['state'];cups=row['cups']
            if state=='submitting':
                self._save(job,'uncertain')
                state='uncertain'
            if state=='uncertain':
                self._report(job,'uncertain',cups,'提交结果不确定，必须先核对打印队列和纸张，禁止自动重印')
                self._save(job,'review',cups)
                return 'uncertain'
            if state=='submitted':
                self._report(job,'submitted',cups,'CUPS已接收，尚未确认纸张输出')
                status=cups_state(cups)
                if status==9:
                    self._report(job,'spooler_completed',cups,'CUPS报告作业完成，仍需家长确认取纸')
                    self._save(job,'done',cups)
                    return 'spooler_completed'
                if status in (7,8):
                    self._report(job,'failed',cups,'CUPS报告作业取消或中止，请核对纸张后再决定是否新建任务')
                    self._save(job,'review',cups)
                    return 'failed'
                return 'submitted'
        else:
            if not self._configured(): return 'printer_unavailable'
            old=self.db.execute("SELECT value FROM meta WHERE key='claim_request'").fetchone()
            request_key=old['value'] if old else secrets.token_hex(16)
            with self.db:self.db.execute("INSERT OR IGNORE INTO meta VALUES ('claim_request',?)",(request_key,))
            reply=self.request('/api/print/bridge/claim',dict(bridge_id=self.bridge_id,printer=self.printer,request_key=request_key))
            job=reply.get('job')
            if job:
                if not re.fullmatch(r'[a-f0-9]{32}',job.get('id','')) or job.get('printer')!=self.printer or job.get('pdf_url')!='/api/print/bridge/pdf/'+job['id']:
                    raise PrintError('领取任务不正确，未发送打印')
                self._save(job,'claimed')
            with self.db:self.db.execute("DELETE FROM meta WHERE key='claim_request'")
            if not job: return 'idle'
            # A claimed key may return an old terminal job after a network interruption.
            if job.get('status')!='claimed':
                self._save(job,'review',job.get('cups_job_id',''))
                return 'review_required'
        if not self._configured(): return 'printer_unavailable'
        # Validate again locally before any physical side effect.
        if type(job.get('copies')) is not int or not 1<=job['copies']<=10 or not isinstance(job.get('sides'),str) or job['sides'] not in SIDES or not isinstance(job.get('color'),str) or job['color'] not in COLORS:
            raise PrintError('打印参数不正确，未发送打印')
        normalized,selected=page_selection(job.get('pages'),job.get('page_count'))
        if normalized!=job['pages'] or selected*job['copies']>500: raise PrintError('打印页码不正确，未发送打印')
        pdf=self.request(job['pdf_url'],claim=job['claim_token'],pdf=True)
        if not pdf.startswith(b'%PDF-') or hashlib.sha256(pdf).hexdigest()!=job['pdf_sha256']:
            self._report(job,'failed',note='PDF校验失败，未发送打印')
            self._save(job,'review')
            return 'failed'
        path=self.directory/(job['id']+'.pdf')
        with path.open('wb') as f:
            os.chmod(path,0o600);f.write(pdf);f.flush();os.fsync(f.fileno())
        # Commit BEFORE invoking lp. A crash after this point must never invoke lp again.
        self._save(job,'submitting')
        args=[self.lp,'-h','localhost','-d',self.printer,'-n',str(job['copies']),'-t','family-'+job['id'],
              '-o','page-ranges='+job['pages'],'-o','sides='+job['sides'],'-o','print-color-mode='+job['color'],
              '-o','media=A4','-o','fit-to-page','-o','number-up=1','-o','collate=true','-o','job-sheets=none',str(path)]
        try:
            result=subprocess.run(args,capture_output=True,timeout=30,env={**os.environ,'LC_ALL':'C'})
            cups=cups_submission_id(result.stdout,self.printer)
        except (OSError,subprocess.TimeoutExpired):result=None;cups=None
        if result is None or result.returncode or not cups:
            self._save(job,'uncertain')
            return self.run_once()
        self._save(job,'submitted',cups)
        self._report(job,'submitted',cups,'CUPS已接收，尚未确认纸张输出')
        return 'submitted'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True,help='本机SSH转发地址，例如http://127.0.0.1:18765')
    parser.add_argument('--printer',required=True,help='家长明确选定且已配置的CUPS队列名')
    parser.add_argument('--directory',default='~/.local/share/family-learning/print-bridge')
    parser.add_argument('--once',action='store_true',required=True)
    args=parser.parse_args()
    bridge=None
    try:
        bridge=Bridge(args.url,os.environ.get('FAMILY_PRINT_BRIDGE_TOKEN',''),args.printer,args.directory)
        print(json.dumps({'status':bridge.run_once()},ensure_ascii=False))
    except PrintError as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False));raise SystemExit(1)
    finally:
        if bridge:bridge.close()


if __name__=='__main__':main()
