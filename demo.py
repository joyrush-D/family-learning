"""Run a disposable, synthetic family demo: python3 demo.py --port 8766."""
import argparse
from pathlib import Path
import tempfile
import json
import app

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='family-demo-') as tmp:
        app.DATA=Path(tmp);app.DB=app.DATA/'family.sqlite3'
        # Keep static files in the source directory; all demo records are temporary.
        docs={
            '家庭运行规则.md':'| child-1 | 示例星星 | — | 9岁 | 三年级 |\n| child-2 | 示例小宇 | — | 12岁 | 六年级 |\n',
            '跟踪台账.md':'| T01 | 示例星星 | 阅读后，听听孩子的发现 | 本周任选一天 | 待跟进 | 虚构演示通知 | 问问孩子愿意分享哪一段。 |\n| T02 | 示例小宇 | 打印一份复习资料 | 下次学习前 | 待跟进 | 虚构演示安排 | 选择演示练习.pdf，核对页码与份数。 |\n| T03 | 示例星星 | 准备周末的自然观察 | 周末 | 待跟进 | 虚构演示安排 | 带上笔记本，画下感兴趣的植物。 |\n',
            '学习与成长.md':'这是虚构演示，不含真实家庭资料。关闭演示后数据清除。',
        }
        app.read=lambda name:docs.get(name,'')
        today=app.dt.datetime.now(app.dt.timezone(app.dt.timedelta(hours=8))).date()
        docs['跟踪台账.md']=docs['跟踪台账.md'].replace('本周任选一天',today.isoformat()).replace('下次学习前',today.isoformat())
        for who,days,category,title,note in [
            ('示例星星',3,'学习进展','把一道题讲给我听','孩子尝试画图解释分数；最后一步还需要提示。'),
            ('示例星星',2,'兴趣','发现叶片的不同纹路','在公园观察了两片叶子，画下自己的发现。'),
            ('示例星星',0,'学习进展','再试一次昨天的方法','能独立画图，但题意还需要一起读。'),
            ('示例小宇',3,'兴趣','练习了一小段吉他','自己选了一段旋律，慢慢练习换和弦。'),
            ('示例小宇',1,'学习进展','找到上次算错的那一步','重新检查了单位换算，写下提醒。'),
        ]:
            app.save_record(dict(child=who,day=(today-app.dt.timedelta(days=days)).isoformat(),category=category,title=title,note=note,subject='探索练习',source='家长观察'))
        app.save_record(dict(child='示例小宇',day=today.isoformat(),category='学习进展',title='隔一天，独立再试一题',note='关掉上次的解答，自己完成了相似练习。',subject='探索练习',source='试卷 / 作业核对',related_record_id=5,followup_kind='独立复测'))
        (app.DATA/'陪伴建议.json').write_text(json.dumps([dict(id='demo-reading',child='示例星星',topic='表达与好奇心',title='把讲解的时间交给孩子',evidence='虚构演示：最近记录了一次画图解释的尝试。',action='今晚用五分钟，请孩子挑一个最想分享的发现。先听完，再问一句“你是怎么想到的？”',review_on=(today+app.dt.timedelta(days=3)).isoformat(),expires_on=(today+app.dt.timedelta(days=7)).isoformat())],ensure_ascii=False))
        # A small original PDF for the demo; no household document or printer.
        drawing=b'BT /F1 24 Tf 50 775 Td (DEMO / Practice sheet) Tj 0 -42 Td /F1 13 Tf (1. Draw your idea. Explain it in your own words.) Tj 0 -48 Td (2. Try again without looking at the example.) Tj ET'
        objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',b'<< /Length '+str(len(drawing)).encode()+b' >>\nstream\n'+drawing+b'\nendstream']
        pdf=bytearray(b'%PDF-1.4\n');offsets=[0]
        for i,obj in enumerate(objects,1):offsets.append(len(pdf));pdf.extend(f'{i} 0 obj\n'.encode()+obj+b'\nendobj\n')
        xref=len(pdf);pdf.extend(f'xref\n0 6\n0000000000 65535 f \n'.encode()+b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets[1:])+f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
        (app.DATA/'attachments').mkdir();(app.DATA/'attachments'/'演示练习.pdf').write_bytes(pdf)
        app.prepare_assets()
        server=app.ThreadingHTTPServer(('127.0.0.1',args.port),app.Handler)
        print(f'虚构演示 http://127.0.0.1:{args.port} — 退出后清除演示记录',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()
