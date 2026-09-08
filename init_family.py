"""初始化持久化家庭资料（仅首次安装；不覆盖任何已有家庭资料）。

交互输入：python3 init_family.py
命令行：python3 init_family.py --child 示例甲 四年级 --child 示例乙 初一
--root 指向已解压或克隆的应用目录；真实姓名建议交互输入，避免进入终端历史。
"""
import argparse
from contextlib import contextmanager
import sqlite3
import os
from pathlib import Path
import tempfile


@contextmanager
def empty_private(private):
    """A first browser visit may have made an empty DB; never erase or replace it."""
    connection=None
    try:
        if private.is_symlink() or private.exists() and not private.is_dir(): raise ValueError('private 目录格式不正确')
        if private.exists():
            entries=list(private.iterdir())
            for path in entries:
                if path.is_symlink(): raise ValueError('private 不能包含符号链接')
                if path.name in {'uploads','attachments','print'} and path.is_dir() and not any(path.iterdir()): continue
                if path.name!='family.sqlite3' or not path.is_file(): raise ValueError('private 目录已有资料，初始化已停止；不会覆盖现有资料')
            database=private/'family.sqlite3'
            if database.exists():
                connection=sqlite3.connect(database)
                connection.execute('BEGIN IMMEDIATE')
                for name, in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                    if connection.execute('SELECT 1 FROM "'+name.replace('"','""')+'" LIMIT 1').fetchone():
                        raise ValueError('private 数据库已有资料，初始化已停止；不会覆盖现有资料')
        yield
    finally:
        if connection is not None: connection.rollback(); connection.close()


def initialize(root, children):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError('应用目录不存在')
    rows, seen = [], set()
    for name, grade in children:
        name, grade = name.strip(), grade.strip()
        for value in (name, grade):
            if not value or len(value) > 80 or '|' in value or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError('姓名和年级必须为 1–80 个字符，不能含竖线、换行或控制字符')
        if '（' in name or '）' in name:
            raise ValueError('请直接填写姓名或称呼，不加全角括号备注')
        if name in seen:
            raise ValueError('孩子姓名或称呼必须不同，以便准确关联记录')
        seen.add(name)
        rows.append(f'| child-{len(rows) + 1} | {name} | 未填写 | 未填写 | {grade} |')
    if not rows:
        raise ValueError('至少填写一个孩子')
    docs = {
        '家庭运行规则.md': '# 家庭运行规则\n\n资料由家长录入，学校消息来源需另行明确授权。年龄、性别等未知信息不推测。\n\n| ID | 姓名或称呼 | 性别 | 年龄 | 年级 |\n| --- | --- | --- | --- | --- |\n' + '\n'.join(rows) + '\n',
        '消息来源.md': '# 消息来源\n\n尚未配置学校消息来源。可先通过网页手动记录或导入文件；新增群聊来源时记录平台、归属孩子、授权范围和实际覆盖时间。\n',
        '跟踪台账.md': '# 跟踪台账\n\n暂无学校通知待办；录入实际通知时保留来源与截止时间。\n\n| 编号 | 孩子 | 事项 | 截止时间 | 状态 | 来源 | 下一步 |\n| --- | --- | --- | --- | --- | --- | --- |\n',
        '学习与成长.md': '# 学习与成长\n\n暂无成长记录。可在网页保存观察、成绩和学习进展；区分孩子自述、家长观察与老师反馈。\n',
    }
    private = root / 'private'
    if any((root / name).exists() or (root / name).is_symlink() for name in docs):
        raise ValueError('已有家庭 Markdown，初始化已停止；不会覆盖现有资料')
    with empty_private(private), tempfile.TemporaryDirectory(prefix='.family-init-', dir=root) as temp:
        stage = Path(temp)
        (stage / 'private').mkdir(mode=0o700)
        for name in ('attachments', 'uploads'):
            (stage / 'private' / name).mkdir(mode=0o700)
        for name, content in docs.items():
            (stage / name).write_text(content, encoding='utf-8')
            (stage / name).chmod(0o600)
        published = []
        try:
            for name in docs:
                os.link(stage / name, root / name)  # Exclusive publication refuses a concurrent file.
                published.append(name)
            if private.is_symlink():
                raise ValueError('private 不能是符号链接')
            if private.exists():
                for name in ('uploads','attachments'): (private/name).mkdir(mode=0o700,exist_ok=True)
            else:
                (stage / 'private').rename(private)
        except BaseException:
            for name in published:
                target = root / name
                if target.exists() and not target.is_symlink() and target.samefile(stage / name):
                    target.unlink()
            raise
    return root


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent, help='已安装应用的目录')
    parser.add_argument('--child', nargs=2, action='append', metavar=('姓名', '年级'), help='可重复指定；省略时交互输入')
    args = parser.parse_args()
    children = args.child
    try:
        if children is None:
            children = []
            while True:
                name = input('孩子姓名或称呼（留空结束）：').strip()
                if not name:
                    break
                grade = input('目前年级：').strip()
                children.append((name, grade))
        result = initialize(args.root, children)
    except (OSError, ValueError, EOFError) as error:
        parser.exit(1, f'初始化失败：{error}\n')
    print(f'家庭资料已保存到 {result}，可在该目录运行 python3 app.py。')
