"""Local due-review inspection; no delivery, inference, or family-record writes."""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile


TIMEZONE = dt.timezone(dt.timedelta(hours=8))  # Matches the current application.
REPORT_NAME = '回看检查.json'
INPUT_NAMES = ('陪伴建议.json', '陪伴提醒状态.json')
PAYLOAD_KEYS = ('status', 'candidate_coverage', 'candidates', 'errors')


def fingerprint(value):
    payload = {key: value[key] for key in PAYLOAD_KEYS}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def load_app(root, data):
    """Isolate the app globals; its import only mkdirs this existing data directory."""
    spec = importlib.util.spec_from_file_location('_family_review_app', Path(__file__).with_name('app.py'))
    app = importlib.util.module_from_spec(spec)
    old = os.environ.get('FAMILY_DATA')
    os.environ['FAMILY_DATA'] = str(data)
    try:
        spec.loader.exec_module(app)
    finally:
        if old is None:
            os.environ.pop('FAMILY_DATA', None)
        else:
            os.environ['FAMILY_DATA'] = old
    app.ROOT, app.DATA, app.DB = root, data, data / 'family.sqlite3'
    return app


def read_candidates(root, data, today):
    app = load_app(root, data)
    # Do not call app.connect(): it creates/migrates tables. Never use snapshot(),
    # which includes unrelated services and the parent API token.
    with closing(sqlite3.connect((data / 'family.sqlite3').as_uri() + '?mode=ro', uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')
        care = app.care_notes(connection)
        if care['error']:
            return [], [dict(code='care_state_unverified', message=care['error'])]
        if any(item.get('review_state_source')!='record' for item in care['items']) and not (data / INPUT_NAMES[1]).exists():
            return [], [dict(code='reminder_state_missing',
                message='已有陪伴建议，但提醒状态文件缺失；请核对停推或延期状态，不能按默认待提醒处理。')]
        profiles = app.profiles(connection)
        names = app.child_names(connection)
        child_ids = {child['name']: child['id'] for child in profiles}
        if not child_ids:
            raise ValueError('family_profile_missing')
        candidates = []
        columns={row['name'] for row in connection.execute('PRAGMA table_info(records)')}
        choice_columns=",care_choice,care_review_on" if {'care_choice','care_review_on'} <= columns else ",'' AS care_choice,'' AS care_review_on"
        for item in sorted(care['items'], key=lambda entry: entry['id']):
            state = item['review_status']
            review_on = dt.date.fromisoformat(item['review_on']).isoformat()
            expires_on = dt.date.fromisoformat(item['expires_on']).isoformat()
            feedback = []
            for row in connection.execute(
                    'SELECT id,child,day,title,note,source,created,attachments'+choice_columns+' FROM records WHERE source=? ORDER BY id',
                    ('陪伴建议:' + item['id'],)):
                if names.get(row['child']) == item['child']:
                    entry = dict(row)
                    entry['child'] = item['child']
                    entry['attachment_ids'] = json.loads(entry.pop('attachments'))
                    if not isinstance(entry['attachment_ids'], list) or not all(
                            isinstance(ident, str) for ident in entry['attachment_ids']):
                        raise ValueError('feedback_attachment_shape')
                    entry['attachment_content_read'] = False
                    feedback.append(entry)
            # A choice settles the arrangement, not the meaning of its text or
            # attachments. Without a review acknowledgement, keep all such facts
            # pending, including later corrections to earlier record IDs.
            unchecked_feedback=[entry for entry in feedback if entry['note'].strip() or entry['attachment_ids']]
            # Free-text feedback needs checking even while stopped or deferred.
            # It never overrides that explicit decision or advances its date.
            if state == 'declined' or state == 'deferred' and review_on > today:
                if not unchecked_feedback:
                    continue
                reason = 'feedback_needs_review'
            elif expires_on < today:
                reason = 'expired_needs_revalidation'
            elif review_on <= today:
                reason = 'due_review'
            elif unchecked_feedback:
                reason = 'feedback_needs_review'
            else:
                continue
            candidates.append(dict(id=item['id'], child_id=child_ids[item['child']],
                                   child=item['child'], topic=item['topic'], title=item['title'],
                                   reason=reason, review_status=state, review_on=review_on,
                                   care_choice=item.get('care_choice',''),choice_record_id=item.get('choice_record_id'),
                                   review_state_source=item.get('review_state_source','none'),
                                   expires_on=expires_on, evidence=item['evidence'], action=item['action'],
                                   action_is_reference_only=True, expired=expires_on < today,
                                   feedback=feedback, unchecked_feedback_ids=[entry['id'] for entry in unchecked_feedback],
                                   execution_status='unknown'))
    return candidates, []


def previous_report(path):
    if not path.exists():
        return None, []
    try:
        if path.is_symlink():
            raise ValueError('report_symlink')
        value = json.loads(path.read_text())
        if (not isinstance(value, dict) or value.get('schema_version') != 1 or
                not isinstance(value.get('candidates'), list) or
                not all(isinstance(item, dict) for item in value['candidates']) or
                not isinstance(value.get('errors'), list) or
                not isinstance(value.get('required_inputs', []), list) or
                any(name not in INPUT_NAMES for name in value.get('required_inputs', [])) or
                value.get('fingerprint') != fingerprint(value)):
            raise ValueError('report_shape')
        return value, []
    except (OSError, ValueError, TypeError, KeyError):
        return None, [dict(code='previous_report_unverified',
                           message='上次检查报告无法核对；本次重新检查，不视为已通知或已处理。')]


def write_report(path, report):
    descriptor, filename = tempfile.mkstemp(prefix='.review-', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(report, output, ensure_ascii=False, indent=2)
            output.write('\n')
            output.flush()
            os.fsync(output.fileno())
        os.replace(filename, path)
    finally:
        if os.path.exists(filename):
            os.unlink(filename)


def check(root, data, now=None):
    """Persist the complete local report, returning (report, materially_changed).

    A supplied clock is for isolated tests; the CLI always uses the actual clock.
    The report is derived inspection state, never an acknowledgement of delivery.
    """
    root, data = Path(root).resolve(), Path(data).resolve()
    if not root.is_dir() or not data.is_dir():
        raise OSError('family_directory_missing')
    now = now or dt.datetime.now(TIMEZONE)
    if now.tzinfo is None:
        raise ValueError('an aware clock is required')
    now = now.astimezone(TIMEZONE)
    old, errors = previous_report(data / REPORT_NAME)
    required = set(old.get('required_inputs', [])) if old else set()
    if old and old['candidates']:
        required.add(INPUT_NAMES[0])
        if any(item.get('review_status') for item in old['candidates']):
            required.add(INPUT_NAMES[1])
    present = {name for name in INPUT_NAMES if (data / name).exists()}
    required.update(present)
    missing = sorted(required - present)
    try:
        if missing:
            candidates, input_errors = [], [dict(code='configured_input_missing', files=missing,
                message='此前已配置的陪伴文件缺失，现有待回看状态无法核对；不能视为没有事项或恢复推荐。')]
        else:
            candidates, input_errors = read_candidates(root, data, now.date().isoformat())
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        candidates, input_errors = [], [dict(code='family_inputs_unavailable',
            message='家庭档案、建议或反馈数据库无法只读核对；请检查路径、权限与初始化状态，不能视为没有待回看事项。')]
    coverage = 'current_inputs_verified'
    if input_errors:
        coverage = 'current_inputs_unavailable'
        # Preserve unresolved items as explicitly stale evidence during an outage.
        candidates = old['candidates'] if old else []
    errors += input_errors
    report = dict(schema_version=1, checked_at=now.isoformat(), timezone='UTC+08:00',
                  status='needs_review' if errors else 'pending' if candidates else 'clear',
                  candidate_coverage=coverage, candidates=candidates, errors=errors,
                  required_inputs=sorted(required),
                  note='仅本地检查。候选未自动处理，反馈未自动解释；检查完成不表示通知送达、建议采纳或行动完成。')
    report['fingerprint'] = fingerprint(report)
    changed = old['fingerprint'] != report['fingerprint'] if old else bool(candidates or errors)
    write_report(data / REPORT_NAME, report)
    return report, changed


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent,
                        help='家庭运行规则.md 所在目录，默认为程序目录')
    parser.add_argument('--data', type=Path, help='私有目录，默认为 FAMILY_DATA 或家庭目录/private')
    args = parser.parse_args(argv)
    data = args.data or Path(os.environ.get('FAMILY_DATA', args.root / 'private'))
    try:
        report, changed = check(args.root, data)
        if changed:
            print(json.dumps(dict(status=report['status'], candidate_count=len(report['candidates']),
                                  candidate_coverage=report['candidate_coverage'],
                                  errors=report['errors'], report=str(data.resolve() / REPORT_NAME)),
                             ensure_ascii=False))
        return 1 if report['errors'] else 0
    except (OSError, ValueError):
        print(json.dumps(dict(status='needs_review', errors=[dict(code='report_not_saved',
            message='本地检查报告未能保存；请核对家庭目录和写入权限，原家庭记录未修改。')]), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
