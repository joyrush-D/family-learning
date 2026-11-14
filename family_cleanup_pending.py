#!/usr/bin/env python3
"""One-off cleanup of school rows that never became tasks: count first, write only with --apply.

Display and storage stay as they are for every other row. A written row only changes state to 'expired' and gains one
agent_item_events row; evidence, plan, agent_messages and manual_tasks are never edited. --undo reverses only the rows
this exact run wrote and that have not changed since.
"""
import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
from pathlib import Path

import family_agent

RULES = ('R0', 'R1', 'R2', 'R3', 'R4', 'R5')
REASONS = {'R1': 'noise', 'R2': 'reference', 'R3': 'placeholder', 'R4': 'stale', 'R5': 'duplicate'}
_OBJECT_KEYS = ('approved', 'school_change_of', 'school_duplicate_of', 'parent_goal_id', 'school_revision_of')
_EMOTE = re.compile(r'\[[^\[\]\n]{1,6}\]|[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]')
_ACK = r'(?:是的|好的?|收到|已上传|已提交|明白了?|知道了|谢谢(?:老师)?|(?:老师)?辛苦了?|OK|ok)'
_ACK_LINE = re.compile(r'(?:' + _ACK + r')(?:[\W_]*' + _ACK + r')*[\W_]*')
_ATTACHMENT = re.compile(r'^message:(.+):[^:]+$')


def _now(value=None):
    if value:
        return dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return dt.datetime.now(family_agent.TZ)


def _time(value):
    try:
        return dt.datetime.fromisoformat(str(value or '').replace('Z', '+00:00'))
    except ValueError:
        return None


def _table(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def _count(c, name, where=''):
    if not _table(c, name):
        return 0
    return c.execute('SELECT COUNT(*) FROM ' + name + (' WHERE ' + where if where else '')).fetchone()[0]


def _tier(row, plan):
    tier = getattr(family_agent, 'school_tier', None)
    if tier is not None:
        return tier(dict(row), plan)
    brief = plan.get('school_task') or {}
    title = str(row['title'] or '').strip()
    if brief.get('state') == 'reference':
        return 'ref'
    if (family_agent._needs_task_details(title) or title == '待整理：学校资料'
            or not str(brief.get('title') or '').strip() or not str(brief.get('goal') or '').strip()
            or brief.get('purpose') == 'unknown'):
        return 'hold'
    if brief.get('purpose') == 'optional':
        return 'ref'
    policy = brief.get('policy', (plan.get('school_learning') or {}).get('policy'))
    if brief.get('state') == 'ready' and policy == family_agent.SCHOOL_TASK_POLICY \
            and brief.get('change') == 'new' and not brief.get('target_id'):
        return 'todo'
    if brief.get('change') in ('update', 'append', 'same', 'cancel') and brief.get('target_id'):
        return 'confirm'
    return 'confirm'


def _refs(evidence):
    out = []
    for entry in evidence if isinstance(evidence, list) else []:
        if isinstance(entry, dict) and isinstance(entry.get('ref'), str) and entry['ref'].startswith('message:'):
            out.append(entry['ref'])
    return out


def _message(c, ref):
    try:
        source_id, message_id = ref[8:].rsplit(':', 1)
    except ValueError:
        return None
    row = c.execute('SELECT payload FROM agent_messages WHERE source_id=? AND id=?', (source_id, message_id)).fetchone()
    if not row:
        return None
    try:
        payload = json.loads(row['payload'])
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _source(ref):
    match = _ATTACHMENT.match(ref)
    return match.group(1) if match else ''


def _has_upload(c, ref):
    try:
        source_id, message_id = ref[8:].rsplit(':', 1)
    except ValueError:
        return False
    return bool(c.execute('SELECT 1 FROM agent_message_attachments WHERE source_id=? AND message_id=? LIMIT 1',
                          (source_id, message_id)).fetchone())


def _teacher_names(c):
    if not _table(c, 'teachers'):
        return set()
    try:
        return {str(row[0]).strip() for row in c.execute('SELECT display_name FROM teachers') if str(row[0]).strip()}
    except sqlite3.Error:
        return set()


def _school_noise(c, ref, teacher_names):
    """The same narrow noise test the collector now uses: only a message that certainly asks for nothing."""
    entry = _message(c, ref)
    if entry is None:
        return ''
    if entry.get('attachments') or _has_upload(c, ref):
        return ''
    if entry.get('kind') == 'recalled':
        return 'kind'
    text = str(entry.get('text') or '').strip()
    if family_agent._COLLECTOR_PLACEHOLDER.search(text):
        return 'recalled' if '已撤回' in text and not family_agent._COLLECTOR_PLACEHOLDER.sub('', text).strip() else ''
    if entry.get('content_incomplete', entry.get('unread', False)):
        return ''
    bare = _EMOTE.sub('', text)
    if not re.sub(r'[\W_]+', '', bare):
        return 'emote'
    if _ACK_LINE.fullmatch(bare):
        return 'ack'
    sender = str(entry.get('sender') or '')
    teacher = bool(family_agent._SCHOOL_TEACHER_NAME.search(sender)) or sender in teacher_names
    if (not teacher and len(bare) <= 20 and not family_agent._SCHOOL_SPLIT_REQUIREMENT.search(bare)
            and not family_agent._SCHOOL_DATE_MENTION.search(bare) and not re.search(r'[0-9？?《]', bare)):
        return 'chatter'
    return ''


def _r0(row, plan):
    if row['task_id'] or row['record_id'] is not None or row['care_id']:
        return True
    return any(plan.get(key) for key in _OBJECT_KEYS)


def _decide(c, row, plan, now, teacher_names):
    if _r0(row, plan):
        return 'R0', ''
    refs = _refs(json.loads(row['evidence'] or '[]'))
    if refs and all(_school_noise(c, ref, teacher_names) for ref in refs):
        return 'R1', REASONS['R1']
    tier = _tier(row, plan)
    if tier == 'ref':
        return 'R2', REASONS['R2']
    created = _time(row['created'])
    due = str(row['due'] or '').strip()[:10]
    today = now.date().isoformat()
    if tier == 'hold' and created is not None and created < now - dt.timedelta(hours=24):
        return 'R3', REASONS['R3']
    if tier == 'confirm' and created is not None and created < now - dt.timedelta(hours=48) \
            and (not due or due < today):
        return 'R4', REASONS['R4']
    return '', ''


def _key(row):
    return (str(row['child_id']), str(row['title'] or '').strip(), str(row['body'] or '').strip(), str(row['due'] or '').strip())


def _create_events(c):
    c.executescript('''
        CREATE TABLE IF NOT EXISTS agent_item_events (
          id INTEGER PRIMARY KEY, item_id TEXT NOT NULL, at TEXT NOT NULL,
          kind TEXT NOT NULL, actor TEXT NOT NULL, before TEXT NOT NULL DEFAULT '',
          after TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
          prev_updated TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS agent_item_events_item ON agent_item_events(item_id,id);
    ''')
    columns = {row['name'] for row in c.execute('PRAGMA table_info(agent_item_events)')}
    if 'prev_updated' not in columns:
        c.execute("ALTER TABLE agent_item_events ADD COLUMN prev_updated TEXT NOT NULL DEFAULT ''")


def _rows(c):
    return c.execute("SELECT * FROM agent_items WHERE kind='school' AND state='pending' ORDER BY created,id").fetchall()


def _report(c, decisions, now, applied=0, header=''):
    lines = [header or '清存量统计（未写入）', 'now=' + now.isoformat()]
    pending = _count(c, 'agent_items', "kind='school' AND state='pending'")
    lines.append('school pending=%d' % pending)
    for rule in RULES:
        rows = [item for item in decisions if item['rule'] == rule]
        lines.append('%s %-10s %d' % (rule, REASONS.get(rule, 'skip'), len(rows)))
    kept = [item for item in decisions if not item['rule']]
    lines.append('keep        %d' % len(kept))
    if applied:
        lines.append('written=%d' % applied)
    lines.append('')
    groups = {}
    for item in decisions:
        if item['rule'] not in ('R1', 'R2', 'R3', 'R4', 'R5'):
            continue
        groups.setdefault((item['rule'], item['child'], item['source']), []).append(item)
    for key in sorted(groups):
        rule, child, source = key
        rows = groups[key]
        lines.append('%s %s %s: %d' % (rule, child, source or 'unknown', len(rows)))
    return lines


def _print(decisions, show_titles):
    for item in decisions:
        rule = item['rule'] or 'keep'
        label = item['title'] if show_titles else item['id']
        print('  %-4s %-9s %s  %s' % (rule, item['child'], label, item['id']))


def _snapshot_counts(c):
    return dict(pending=_count(c, 'agent_items', "kind='school' AND state='pending'"),
                accepted=_count(c, 'agent_items', "kind='school' AND state='accepted'"),
                dismissed=_count(c, 'agent_items', "kind='school' AND state='dismissed'"),
                manual=_count(c, 'manual_tasks'))


def _connect(path, read_only=False):
    if read_only:
        return sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)
    return sqlite3.connect(str(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True, help='data directory (contains family.sqlite3)')
    parser.add_argument('--apply', action='store_true', help='write expired states and one event row per item')
    parser.add_argument('--run-id', help='required with --apply')
    parser.add_argument('--undo', metavar='RUN_ID', help='restore the rows written by this run id')
    parser.add_argument('--show-titles', action='store_true', help='print real titles (default prints ids only)')
    parser.add_argument('--now', help='override the clock for tests (ISO timestamp)')
    args = parser.parse_args(argv)
    if args.apply and not args.run_id:
        parser.error('--apply requires --run-id')
    if args.run_id and not args.apply and not args.undo:
        parser.error('--run-id only applies with --apply')
    if args.apply and args.undo:
        parser.error('choose --apply or --undo')
    data = Path(args.data)
    db = data / 'family.sqlite3'
    if not db.exists():
        print('database not found: ' + str(db), file=sys.stderr)
        return 2
    now = _now(args.now)
    with family_agent._lock(data / '.agent.lock') as locked:
        if not locked:
            print('another agent run holds the lock; nothing done', file=sys.stderr)
            return 3
        read_only = not (args.apply or args.undo)
        c = _connect(db, read_only=read_only)
        c.row_factory = sqlite3.Row
        try:
            if args.undo:
                return _undo(c, now, args.undo, args.show_titles)
            teacher_names = _teacher_names(c)
            decisions = []
            seen = {}
            for row in _rows(c):
                plan = json.loads(row['plan'] or '{}')
                rule, reason = _decide(c, row, plan, now, teacher_names)
                refs = _refs(json.loads(row['evidence'] or '[]'))
                key = _key(row)
                if not rule and key in seen:
                    rule, reason = 'R5', REASONS['R5']
                if not rule:
                    seen[key] = row['id']
                decisions.append(dict(id=row['id'], child=row['child_id'], title=row['title'], rule=rule,
                                      reason=reason, updated=row['updated'],
                                      source=_source(refs[0]) if refs else ''))
            before = _snapshot_counts(c)
            print('\n'.join(_report(c, decisions, now,
                                     header='清存量执行（写入前统计）' if args.apply else '清存量统计（未写入）')))
            print('')
            _print(decisions, args.show_titles)
            if not args.apply:
                print('\naccepted=%d dismissed=%d manual_tasks=%d pending=%d（只统计，未写入）'
                      % (before['accepted'], before['dismissed'], before['manual'], before['pending']))
                return 0
            actor = 'script:' + args.run_id
            _create_events(c)
            if c.execute("SELECT 1 FROM agent_item_events WHERE kind='cleanup' AND actor=? LIMIT 1", (actor,)).fetchone():
                print('run id already used: ' + args.run_id, file=sys.stderr)
                return 4
            c.execute('BEGIN IMMEDIATE')
            written = 0
            stamp = now.isoformat()
            for item in decisions:
                if item['rule'] not in ('R1', 'R2', 'R3', 'R4'):
                    continue
                changed = c.execute("UPDATE agent_items SET state='expired',updated=? WHERE id=? AND state='pending'",
                                    (stamp, item['id'])).rowcount
                if not changed:
                    continue
                c.execute('INSERT INTO agent_item_events(item_id,at,kind,actor,before,after,note,prev_updated) '
                          'VALUES(?,?,?,?,?,?,?,?)',
                          (item['id'], stamp, 'cleanup', actor, 'pending', 'expired', item['reason'],
                           item['updated']))
                written += 1
            after = _snapshot_counts(c)
            if (after['accepted'], after['dismissed'], after['manual']) != (before['accepted'], before['dismissed'], before['manual']):
                c.rollback()
                print('reconciliation failed: accepted/dismissed/manual changed; rolled back', file=sys.stderr)
                return 5
            if before['pending'] - after['pending'] != written:
                c.rollback()
                print('reconciliation failed: pending delta does not match events; rolled back', file=sys.stderr)
                return 5
            c.commit()
            print('\n写入完成 run=%s written=%d' % (args.run_id, written))
            print('reconciled accepted=%d dismissed=%d manual_tasks=%d pending %d→%d'
                  % (after['accepted'], after['dismissed'], after['manual'], before['pending'], after['pending']))
            return 0
        finally:
            c.close()


def _undo(c, now, run_id, show_titles):
    if not _table(c, 'agent_item_events'):
        print('no agent_item_events table; nothing to undo', file=sys.stderr)
        return 2
    actor = 'script:' + run_id
    events = c.execute("SELECT * FROM agent_item_events WHERE kind='cleanup' AND actor=? ORDER BY id", (actor,)).fetchall()
    if not events:
        print('no cleanup events for run ' + run_id, file=sys.stderr)
        return 2
    before = _snapshot_counts(c)
    stamp = now.isoformat()
    restored = skipped = 0
    skipped_ids = []
    c.execute('BEGIN IMMEDIATE')
    for event in events:
        row = c.execute('SELECT id,state,updated,title FROM agent_items WHERE id=?', (event['item_id'],)).fetchone()
        if row is None or row['state'] != 'expired' or row['updated'] != event['at']:
            skipped += 1
            skipped_ids.append(event['item_id'])
            continue
        c.execute("UPDATE agent_items SET state='pending',updated=? WHERE id=? AND state='expired' AND updated=?",
                  (event['prev_updated'] or stamp, row['id'], event['at']))
        restored += 1
        if show_titles:
            print('  restored %s  %s' % (row['id'], row['title']))
        else:
            print('  restored %s' % row['id'])
    after = _snapshot_counts(c)
    c.commit()
    print('撤销 run=%s restored=%d skipped=%d' % (run_id, restored, skipped))
    if skipped_ids:
        print('skipped (changed since cleanup): ' + ' '.join(skipped_ids))
    print('accepted=%d dismissed=%d manual_tasks=%d pending %d→%d（事件表保留）'
          % (after['accepted'], after['dismissed'], after['manual'], before['pending'], after['pending']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
