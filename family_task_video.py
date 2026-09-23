"""R14 task video observation draft: one task-attributed video per Agent tick, for the parent to check, read-only.

Reuses the Agent's enabled switch, the tick's model budget, agent_jobs (three attempts, backoff, retry) and
family_llm.video_feedback_draft. This repository has no separate model consent or daily quota, and none is added
here: what actually bounds the calls is enabled, the tick's three model calls shared with all other work, and one
job per (record, original, fingerprint) with three attempts, 5/10 minute backoff and then the parent's retry.
Nothing here writes a record, task, plan, goal, result or completion. No child entry reads the draft table;
learning evidence uses only the parent's currently effective selection. The parent's explicit review (review below) appends to record_video_reviews which observations
of one exact draft version were confirmed or revoked; it is shown back only for that version. `confirmed` below is the one
read-only path by which the linked learning goal's evidence (family_goals._context) reads the parent's current choice."""
import datetime as dt
import hashlib
import json
import math
import sqlite3
import subprocess
import os
import selectors
import time

import family_llm
import family_media
from family_agent import AgentError, _hash

SCAN_LIMIT = 50
PROBE_DEADLINE = 15  # Shared by the header probe and, for headerless WebM, the full-timeline fallback.
# The full packet dump is bounded; oversized streams are refused instead of silently reading a prefix.
MAX_PROBE_OUTPUT = 1 << 20
EXPLANATIONS = {
    'agent_disabled': '后台Agent未启用或授权已撤回；视频不会被读取，已有草稿不再显示，原视频保留。',
    'child_unknown': '这条记录的孩子归属无法核对；视频不会被读取。',
    'task_unlinked': '这条记录当前没有明确关联到事项；视频不会被后台读取。',
    'task_ambiguous': '这条记录同时指向不同事项，无法确定原任务；请先更正关联。',
    'task_mismatch': '关联事项不存在或孩子归属不一致；视频不会被读取。',
    'task_context_invalid': '原任务标题、科目或要求为空或过长，无法完整提供给模型；不会截断后分析。',
    'attachments_invalid': '这条记录的原件列表无法核对；视频不会被读取。',
    'original_missing': '这份视频不在这条记录的原件中。',
    'original_unavailable': '原视频文件缺失、不可读取或长度不符；请核对原件。',
    'original_other_child': '原视频同时关联另一位孩子的资料，归属无法证实；视频不会被读取。',
    'original_too_large': '原视频超过20MiB，不会截取片段后分析；请由家长查看原视频。',
    'original_changed': '原视频文件与保存时不一致；请核对原件。',
    'not_video': '这份原件不是已核验的MP4、MOV或WebM视频。',
    'probe_missing': '此电脑尚未安装ffprobe，无法核验视频时长；未发送给模型。',
    'probe_failed': '视频无法在本机核验（文件损坏或没有时长信息）；未发送给模型。',
    'no_video_track': '文件中没有可用的视频轨道；未发送给模型。',
    'duration_invalid': '视频时长无法确定或超过10分钟，不会截取片段后分析；未发送给模型。',
    'webm_duration_unsupported': '这份WebM缺少可核验的时长信息，且本机无法确定完整时间轴（文件损坏、不完整或处理超时）；不会猜测时长；未发送给模型，请由家长查看原视频。',
    'changed': '记录、事项关联、任务要求、授权或原视频在整理期间发生变化，本次结果已丢弃。',
    'saved_invalid': '已保存的草稿未通过时间位置复核，不予显示；请查看原视频。',
    'draft_missing': '当前没有可核对的有效视频观察草稿（记录、原件、授权或草稿已变化）；请刷新后再核对。',
    'token_stale': '页面上的视频观察已不是当前版本；请刷新后重新核对。',
    'review_not_confirmed': '这份视频观察当前没有有效的家长核对，没有可撤回的内容。',
}
REVIEW_LABEL = '家长已核对的视频观察'
REVIEW_NOTE = '家长选定了这些画面观察作为自己核对过的内容；未评估声音，不代表完成或掌握，不会自动改动任务、学习记录或计划。'
UNCONFIRMED = '家长尚未核对这份视频观察，或已撤回核对；只有家长明确选择后才算核对。'
MAX_OBSERVATIONS = 8  # family_llm.validate_video_feedback allows at most eight observations per draft.
REVIEW_KEYS = ('record_id', 'upload_id', 'expected_token', 'action', 'selected')


class VideoDraftError(ValueError):
    def __init__(self, code):
        super().__init__(EXPLANATIONS[code]); self.code = code


def _require(condition, code):
    if not condition:
        raise VideoDraftError(code)


def job_key(record_id, upload_id):
    return 'record-video:' + str(record_id) + ':' + upload_id


def _attribution(app, store, c, record_id):
    """The record's child and its one task as the database has them now; neither is ever guessed."""
    row = c.execute('SELECT * FROM records WHERE id=?', (record_id,)).fetchone()
    if row is None:
        raise AgentError('记录不存在，请刷新', 404, 'record_missing')
    names = app.child_names(c); owner = names.get(row['child'])
    profile = next((p for p in store.profiles(c) if p['name'] == owner), None) if owner else None
    _require(profile is not None, 'child_unknown')
    source = row['source'] or ''
    claimed = {source[3:]} if source.startswith('事项:') else set()
    if row['linked_task_id']:
        claimed.add(row['linked_task_id'])
    _require(claimed, 'task_unlinked'); _require(len(claimed) == 1, 'task_ambiguous')
    task_id = claimed.pop()
    try:
        task = app.record_task(c, task_id, owner)
    except (app.RecordError, app.TaskError):
        raise VideoDraftError('task_mismatch') from None
    context = dict(title=task['title'] or '', subject=row['subject'] or '', requirement=task.get('action') or '')
    _require(context['title'].strip() and len(context['title']) <= 200 and len(context['subject']) <= 80
             and len(context['requirement']) <= 2000, 'task_context_invalid')  # Never cut to fit.
    try:
        attachments = json.loads(row['attachments'] or '[]')
    except ValueError:
        attachments = None
    _require(isinstance(attachments, list) and all(isinstance(i, str) for i in attachments), 'attachments_invalid')
    basis = 'feedback' if source.startswith('事项:') else 'link'
    # The record as the parent last corrected it: save_record renews `created` and logs a revision on every correction
    # and a link change renews linked_task_at, so the whole row and its revision log are the version. The child's
    # spelling is left to child_id, which an alias rename of the same child does not change.
    revisions = c.execute('SELECT COUNT(*),COALESCE(MAX(id),0) FROM revisions WHERE record_id=?', (record_id,)).fetchone()
    version = dict(row={k: row[k] for k in row.keys() if k != 'child'}, revisions=list(revisions))
    return dict(record_id=record_id, child_id=profile['id'], owner=owner, names=names, task_id=task_id, basis=basis,
                linked_at=row['linked_task_at'] if basis == 'link' else '', version=version, task=context,
                attachments=attachments)


def _videos(c, base):
    for upload_id in base['attachments']:
        row = c.execute('SELECT mime FROM uploads WHERE id=?', (upload_id,)).fetchone()
        if row is not None and row['mime'] in family_llm.VIDEO_TYPES:
            yield upload_id


def _original(store, c, base, upload_id):
    """One video of that record, provably this child's, with its bytes read and hashed now."""
    _require(upload_id in base['attachments'], 'original_missing')
    try:
        row = store._message_upload(c, base['child_id'], upload_id)
    except AgentError as error:
        raise VideoDraftError('original_other_child' if error.code == 'attachment_child_conflict' else 'original_unavailable') from None
    _require(row['mime'] in family_llm.VIDEO_TYPES, 'not_video')
    for other in c.execute("SELECT child,attachments FROM records WHERE attachments LIKE '%'||?||'%'", (upload_id,)):
        try:
            shared = upload_id in json.loads(other['attachments'])
        except ValueError:
            shared = True  # An unreadable list cannot prove the original is not another child's.
        _require(not shared or base['names'].get(other['child'], other['child']) == base['owner'], 'original_other_child')
    sources = {s['id']: s['child_id'] for s in store._config(c)['sources']}
    for link in c.execute('SELECT source_id FROM agent_message_attachments WHERE upload_id=?', (upload_id,)):
        _require(sources.get(link['source_id']) == base['child_id'], 'original_other_child')
    _require(row['size'] <= family_llm.MAX_INPUT, 'original_too_large')
    try:  # Bounded, regular file only, no symlink anywhere in the path; never more than the limit is read.
        body = family_media.read_file(store.data / 'uploads' / upload_id, family_llm.MAX_INPUT)
    except family_media.MediaError as error:
        raise VideoDraftError('original_changed' if str(error) == 'media_file_changed' else 'original_unavailable') from None
    except OSError:
        raise VideoDraftError('original_unavailable') from None
    _require(len(body) == row['size'], 'original_changed')
    record_id = base['record_id']
    fingerprint = _hash([2, record_id, base['child_id'], base['basis'], base['task_id'], base['linked_at'], base['version'],
                         base['task'], upload_id, row['mime'], row['size'], hashlib.sha256(body).hexdigest()])
    return dict(record_id=record_id, upload_id=upload_id, task_id=base['task_id'], task=base['task'], mime=row['mime'],
                body=body, fingerprint=fingerprint)


def _current(app, store, c, value):
    """Authorization, record, task, requirement, attachment and bytes re-read now; any difference refuses."""
    _require(store._config(c)['enabled'], 'agent_disabled')
    try:
        current = _original(store, c, _attribution(app, store, c, value['record_id']), value['upload_id'])
    except AgentError:
        raise VideoDraftError('changed') from None
    _require(current['fingerprint'] == value['fingerprint'], 'changed')
    return current


def _run_ffprobe(args, body, timeout):
    return subprocess.run(args, input=body, capture_output=True, check=True, timeout=timeout)


def _webm_packet_end(body, remaining):
    """End time of every packet ffprobe can parse from the supplied bytes.

    The dump is streamed into a bounded buffer and folded into one pts+duration maximum after EOF. A truncated
    container can exit 0 while printing e.g. "File ended prematurely" on stderr, so ANY non-empty -v error stderr
    (or a nonzero exit, timeout, oversize output or unparseable/nonfinite row) is refused: never a shorter partial
    success. Clean stderr and exit 0 prove only that the supplied bytes parse completely to their own end; a stream
    deliberately finished on a valid boundary cannot prove what unseen bytes the original recording may have had, so
    the value is the duration of the supplied complete parseable bytes, never a claim of source completeness."""
    _require(remaining > 0, 'webm_duration_unsupported')
    args = ['ffprobe', '-v', 'error', '-protocol_whitelist', 'pipe', '-f', 'matroska', '-i', 'pipe:0',
            '-select_streams', 'v:0', '-show_entries', 'packet=pts_time,duration_time', '-of', 'csv=p=0']
    deadline = time.monotonic() + remaining
    try:
        with subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            with selectors.DefaultSelector() as selector:
                for pipe, event in ((process.stdin, selectors.EVENT_WRITE), (process.stdout, selectors.EVENT_READ),
                                    (process.stderr, selectors.EVENT_READ)):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, event)
                offset = 0; output = bytearray()
                try:
                    while selector.get_map():
                        left = deadline - time.monotonic()
                        _require(left > 0, 'webm_duration_unsupported')
                        for key, _ in selector.select(left):
                            pipe = key.fileobj
                            if pipe is process.stdin:
                                try:
                                    offset += os.write(pipe.fileno(), body[offset:offset + 65536])
                                except BrokenPipeError:
                                    offset = len(body)
                                if offset == len(body):
                                    selector.unregister(pipe); pipe.close()
                            else:
                                chunk = os.read(pipe.fileno(), 65536)
                                if not chunk:
                                    selector.unregister(pipe); pipe.close()
                                elif pipe is process.stdout:
                                    _require(len(output) + len(chunk) <= MAX_PROBE_OUTPUT, 'webm_duration_unsupported')
                                    output.extend(chunk)
                                else:
                                    # -v error output means the supplied container was not completely parsed,
                                    # even if ffprobe later exits zero. Do not retain an unbounded error stream.
                                    raise VideoDraftError('webm_duration_unsupported')
                    process.wait(timeout=max(0, deadline - time.monotonic()))
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
                returncode = process.returncode; stdout = bytes(output)
    except FileNotFoundError:
        raise VideoDraftError('probe_missing') from None
    except (OSError, subprocess.SubprocessError):
        raise VideoDraftError('webm_duration_unsupported') from None
    try:
        if returncode != 0:
            raise VideoDraftError('webm_duration_unsupported')
        text = stdout.decode('utf-8', 'strict')
        end = 0.0; rows = 0
        for line in text.splitlines():
            fields = line.split(',')
            values = [float(v) for v in fields]  # 'N/A', '', inf all fail here.
            _require(len(fields) == 2 and all(math.isfinite(v) and v >= 0 for v in values) and values[1] > 0, 'webm_duration_unsupported')
            end = max(end, values[0] + values[1]); rows += 1
        _require(rows > 0 and end > 0, 'webm_duration_unsupported')
    except (UnicodeError, ValueError, OverflowError):
        raise VideoDraftError('webm_duration_unsupported') from None
    _require(time.monotonic() < deadline, 'webm_duration_unsupported')
    return end


def probe(body, mime):
    """Local ffprobe over a pipe only, no file or network protocol: a video track and a finite duration of the whole file."""
    demux = 'matroska' if mime == 'video/webm' else 'mov'
    deadline = time.monotonic() + PROBE_DEADLINE
    try:
        result = _run_ffprobe(['ffprobe', '-v', 'error', '-protocol_whitelist', 'pipe', '-f', demux, '-i', 'pipe:0',
                               '-show_entries', 'stream=codec_type:format=duration', '-of', 'json'],
                              body, PROBE_DEADLINE)
        info = json.loads(result.stdout); streams = info.get('streams'); raw = info.get('format', {}).get('duration')
    except FileNotFoundError:
        raise VideoDraftError('probe_missing') from None
    except (subprocess.SubprocessError, ValueError, TypeError, AttributeError):
        raise VideoDraftError('probe_failed') from None
    _require(isinstance(streams, list) and 0 < len(streams) <= 32 and all(isinstance(s, dict) for s in streams)
             and any(s.get('codec_type') == 'video' for s in streams), 'no_video_track')
    try:
        duration = float(raw) if type(raw) in (str, int, float) else math.nan
    except ValueError:
        duration = math.nan
    # Browser WebM often has no duration header. Scan every packet, including for seekable WebM,
    # so a valid header cannot conceal a truncated tail. This covers supplied bytes, not unseen source data.
    if mime == 'video/webm':
        _require(not getattr(result, 'stderr', None), 'webm_duration_unsupported')
        duration = _webm_packet_end(body, deadline - time.monotonic())
    _require(math.isfinite(duration) and 0 < duration <= family_llm.MAX_VIDEO_SECONDS, 'duration_invalid')
    _require(time.monotonic() < deadline, 'probe_failed')
    return duration


def _saved(c, value):
    """A stored draft counts only for the same fingerprint and while its times still pass the adapter's checks."""
    try:
        row = c.execute('SELECT * FROM record_video_drafts WHERE record_id=? AND upload_id=?',
                        (value['record_id'], value['upload_id'])).fetchone()
        if row is None or row['fingerprint'] != value['fingerprint']:
            return None
        payload = json.loads(row['payload'])
        if (not isinstance(payload, dict) or set(payload) != {'version', 'record_id', 'upload_id', 'task_id', 'duration_seconds', 'draft'}
                or [payload[k] for k in ('version', 'record_id', 'upload_id', 'task_id')] != [1, value['record_id'], value['upload_id'], value['task_id']]):
            return None
        draft = family_llm.validate_video_feedback(payload['draft'], payload['duration_seconds'])
        # The version the parent reviews: the record/original fingerprint and the saved draft itself, not its time.
        return dict(updated=row['updated'], duration_seconds=payload['duration_seconds'], draft=draft,
                    token=_hash([1, value['fingerprint'], payload]))
    except (sqlite3.OperationalError, ValueError, TypeError, family_llm.LLMDraftError):
        return None


def view(app, store, record_id):
    """Parent-only read of a record's task-video drafts as they are valid now: no model, no probe, no write."""
    if type(record_id) is not int or not 0 < record_id <= 9223372036854775807:
        raise AgentError('记录编号不正确')
    result = dict(record_id=record_id, task_id='', basis='', audience='parent', read_only=True, explanation='', videos=[])
    with store._db() as c:
        enabled = store._config(c)['enabled']
        try:
            base = _attribution(app, store, c, record_id)
        except VideoDraftError as error:
            return dict(result, explanation=str(error))
        result.update(task_id=base['task_id'], basis=base['basis'])
        for upload_id in _videos(c, base):
            key = job_key(record_id, upload_id); item = dict(upload_id=upload_id, job_id=key)
            try:
                _require(enabled, 'agent_disabled')
                value = _original(store, c, base, upload_id)
            except VideoDraftError as error:
                result['videos'].append(dict(item, state='unavailable', explanation=str(error))); continue
            saved = _saved(c, value)
            job = c.execute('SELECT * FROM agent_jobs WHERE id=?', (key,)).fetchone()
            same = job is not None and job['fingerprint'] == _hash({'video': value['fingerprint']})
            if saved is not None:
                item.update(state='ready', explanation='仅供家长对照原视频核对；未评估声音，不代表完成或掌握。', **saved,
                            review=_effective(_latest(c, value, saved['token']), base, value, saved))
            elif same and job['done']:
                item.update(state='unavailable', explanation=EXPLANATIONS['saved_invalid'])
            elif same and job['error']:
                item.update(state='error', explanation=job['error'], attempts=job['attempts'], exhausted=not job['next_try'])
            else:
                item.update(state='pending', explanation='Agent将在后台整理这份任务视频的画面观察；结果只供家长核对，不会改动任务或学习记录。')
            result['videos'].append(item)
    return result


def prepare(app, store, now):
    """At most one task video and one model call per tick, out of the tick's existing budget; jobs bound the retries."""
    with store._db() as c:
        if not store._config(c)['enabled']:
            return dict(used=0, failed=0)
        # ponytail: only the 50 newest task-attributed records with originals are inspected per tick.
        ids = [r['id'] for r in c.execute("""SELECT id FROM records WHERE attachments<>'[]' AND
            (source LIKE '事项:%' OR linked_task_id<>'') ORDER BY id DESC LIMIT ?""", (SCAN_LIMIT,))]
    selected = None
    for record_id in ids:
        values = []
        try:
            with store._db() as c:
                base = _attribution(app, store, c, record_id)
                for upload_id in _videos(c, base):
                    try:
                        value = _original(store, c, base, upload_id)
                    except VideoDraftError:
                        continue
                    value.pop('body')
                    if _saved(c, value) is None:
                        values.append(value)
        except Exception:
            continue  # No model receives an unattributed, foreign or unreadable original.
        for value in values:
            key = job_key(record_id, value['upload_id'])
            fp = store._job(key, {'video': value['fingerprint']}, now, model=True)
            if fp:
                selected = (value, key, fp); break
        if selected:
            break
    if selected is None:
        return dict(used=0, failed=0)
    value, key, fp = selected; called = False
    try:
        with store._db() as c:
            current = _current(app, store, c, value)
        duration = probe(current['body'], current['mime'])
        with store._db() as c:  # The probe may have taken seconds; what is sent is what the database says now.
            current = _current(app, store, c, value)
        called = True
        draft = family_llm.video_feedback_draft(current['body'], current['mime'], duration, current['task'], data_path=store.data)
        payload = dict(version=1, record_id=value['record_id'], upload_id=value['upload_id'], task_id=value['task_id'],
                       duration_seconds=duration, draft=draft)
        with store._db() as c:
            c.execute('BEGIN IMMEDIATE')
            _current(app, store, c, value)  # A result for a withdrawn, corrected, moved or replaced input is dropped.
            job = c.execute('SELECT fingerprint FROM agent_jobs WHERE id=?', (key,)).fetchone()
            _require(job is not None and job['fingerprint'] == fp, 'changed')
            c.execute('INSERT OR REPLACE INTO record_video_drafts VALUES(?,?,?,?,?)',
                      (value['record_id'], value['upload_id'], value['fingerprint'],
                       json.dumps(payload, ensure_ascii=False, allow_nan=False), now.isoformat()))
            c.execute("UPDATE agent_jobs SET done=1,error='',next_try='' WHERE id=? AND fingerprint=?", (key, fp))
        return dict(used=1, failed=0)
    except Exception as error:
        store._fail(key, now, fingerprint=fp,
                    reason=str(error) if isinstance(error, (VideoDraftError, family_llm.LLMDraftError)) else '')
        return dict(used=int(called), failed=1)


def _now():
    return dt.datetime.now().isoformat(timespec='seconds')


def _latest(c, value, token):
    """The newest review event recorded for exactly this draft version; a database without the table has none."""
    try:
        return c.execute('SELECT * FROM record_video_reviews WHERE record_id=? AND upload_id=? AND token=? ORDER BY id DESC LIMIT 1',
                         (value['record_id'], value['upload_id'], token)).fetchone()
    except sqlite3.OperationalError:
        return None


def _snapshot(row, base, value, saved):
    """A confirmation row counts only if its snapshot is exactly the current draft's observations at its indices."""
    try:
        payload = json.loads(row['payload']); selected = payload['selected']; observations = saved['draft']['observations']
        if (row['action'] != 'confirm' or set(payload) != {'version', 'label', 'action', 'record_id', 'upload_id', 'child_id', 'task_id',
                'token', 'selected', 'observations', 'uncertainties', 'duration_seconds', 'audio_assessed', 'reviewed_at'}
                or [payload[k] for k in ('version', 'action', 'record_id', 'upload_id', 'child_id', 'task_id', 'token', 'audio_assessed')]
                != [1, 'confirm', value['record_id'], value['upload_id'], base['child_id'], value['task_id'], saved['token'], False]
                or not isinstance(selected, list) or not selected or len(set(selected)) != len(selected)
                or any(type(i) is not int or not 0 <= i < len(observations) for i in selected)
                or payload['observations'] != [observations[i] for i in selected]
                or payload['uncertainties'] != saved['draft']['uncertainties'] or payload['duration_seconds'] != saved['duration_seconds']):
            return None
        return payload
    except (ValueError, TypeError, KeyError):
        return None


def _effective(row, base, value, saved):
    """What the parent has confirmed for this exact version now: nothing, a revocation, or the listed observations."""
    review = dict(state='unconfirmed', label=REVIEW_LABEL, explanation=UNCONFIRMED, audio_assessed=False)
    if row is None:
        return review
    if row['action'] != 'confirm':
        return dict(review, revoked_at=row['created'])
    payload = _snapshot(row, base, value, saved)
    if payload is None:
        return review
    return dict(state='confirmed', id=row['id'], reviewed_at=row['created'], label=REVIEW_LABEL, explanation=REVIEW_NOTE,
                audio_assessed=False, selected=payload['selected'], observations=payload['observations'],
                uncertainties=payload['uncertainties'], duration_seconds=payload['duration_seconds'])


def confirmed(app, store, c, record_id):
    """The parent's currently effective confirmations of this record's task videos, read on the caller's connection.

    family_goals calls this only for a record the goal already lists through its own explicit links; nothing here picks
    records. It repeats exactly the checks of view and review: the Agent switch, the record's one task and child, the
    original's bytes and sharing, the saved draft's fingerprint and the newest review row for that draft version. No
    model, no probe, no write and no table is created; a database without the draft or review tables, a corrected,
    relinked, foreign or unreadable record, a changed original, a withdrawn switch, a stale token or a revocation all
    read as no confirmation. Only the parent's selected observations leave: never unselected ones, the draft's other
    text or the video bytes. A confirmation is the parent's reading of the picture with sound unassessed; it changes no
    record, task, plan or completion."""
    try:
        _require(store._config(c)['enabled'], 'agent_disabled')
        base = _attribution(app, store, c, record_id)
    except (AgentError, VideoDraftError, sqlite3.OperationalError):
        return []
    out = []
    for upload_id in _videos(c, base):
        try:
            value = _original(store, c, base, upload_id)
            saved = _saved(c, value)
            if saved is None:
                continue
            review = _effective(_latest(c, value, saved['token']), base, value, saved)
        except (AgentError, VideoDraftError, sqlite3.OperationalError):
            continue
        if review['state'] != 'confirmed':
            continue
        out.append(dict(kind='parent_checked_video', label=REVIEW_LABEL, upload_id=upload_id, review_id=review['id'],
                        token=saved['token'], reviewed_at=review['reviewed_at'], selected=review['selected'],
                        observations=review['observations'], uncertainties=review['uncertainties'],
                        duration_seconds=review['duration_seconds'], audio_assessed=False))
    return out


def _request(body):
    """Exactly the parent's choice: which listed observations, of which version. No text, times or sound claims."""
    if not isinstance(body, dict) or not set(body) <= set(REVIEW_KEYS):
        raise AgentError('核对请求格式不正确')
    record_id = body.get('record_id'); upload_id = body.get('upload_id'); token = body.get('expected_token')
    action = body.get('action'); selected = body.get('selected', [])
    if type(record_id) is not int or not 0 < record_id <= 9223372036854775807:
        raise AgentError('记录编号不正确')
    if not isinstance(upload_id, str) or not 0 < len(upload_id) <= 200 or any(ord(ch) < 33 for ch in upload_id):
        raise AgentError('原件编号不正确')
    if not isinstance(token, str) or len(token) != 64 or any(ch not in '0123456789abcdef' for ch in token):
        raise AgentError('核对版本标识不正确')
    if action not in ('confirm', 'revoke'):
        raise AgentError('核对动作不正确')
    if (not isinstance(selected, list) or len(selected) > MAX_OBSERVATIONS
            or any(type(i) is not int or not 0 <= i < MAX_OBSERVATIONS for i in selected)
            or len(set(selected)) != len(selected)):
        raise AgentError('所选观察编号不正确')
    if action == 'confirm' and not selected:
        raise AgentError('请至少选择一条画面观察')
    if action == 'revoke' and selected:
        raise AgentError('撤回不能附带所选观察')
    return dict(record_id=record_id, upload_id=upload_id, expected_token=token, action=action, selected=sorted(selected))


def _result(row, base, value, saved, repeated):
    return dict(record_id=value['record_id'], upload_id=value['upload_id'], task_id=value['task_id'], token=saved['token'],
                id=row['id'], action=row['action'], reviewed_at=row['created'], repeated=repeated,
                review=_effective(row, base, value, saved))


def review(app, store, body):
    """The parent's explicit confirmation or revocation of listed current observations; appended, never rewritten.

    No model and no probe: inside one BEGIN IMMEDIATE the switch, child, task, record revision, link, original bytes,
    saved draft and the caller's expected token are re-read, and a row is written only if they still describe the
    version the parent looked at (otherwise 409). An identical retry of the latest event returns that event's id
    without a new row; a different request appends. A confirmation is the parent's reading of the picture with
    sound unassessed; it is not completion, mastery or a learning record, and nothing consumes it yet."""
    request = _request(body); now = _now()
    with store._db() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            _require(store._config(c)['enabled'], 'agent_disabled')
            base = _attribution(app, store, c, request['record_id'])
            value = _original(store, c, base, request['upload_id'])
            saved = _saved(c, value)
            _require(saved is not None, 'draft_missing')
            _require(saved['token'] == request['expected_token'], 'token_stale')
        except (AgentError, VideoDraftError) as error:
            raise AgentError(str(error), 409, error.code) from None
        observations = saved['draft']['observations']
        if any(i >= len(observations) for i in request['selected']):
            raise AgentError('所选观察编号不存在')
        latest = _latest(c, value, saved['token']); digest = _hash([1, request])
        if latest is not None and latest['request'] == digest:
            return _result(latest, base, value, saved, True)
        if request['action'] == 'revoke' and (latest is None or _snapshot(latest, base, value, saved) is None):
            raise AgentError(EXPLANATIONS['review_not_confirmed'], 409, 'review_not_confirmed')
        payload = dict(version=1, label=REVIEW_LABEL, action=request['action'], record_id=value['record_id'],
                       upload_id=value['upload_id'], child_id=base['child_id'], task_id=value['task_id'], token=saved['token'],
                       selected=request['selected'], observations=[observations[i] for i in request['selected']],
                       uncertainties=saved['draft']['uncertainties'], duration_seconds=saved['duration_seconds'],
                       audio_assessed=False, reviewed_at=now)
        if request['action'] == 'revoke':
            payload.update(revokes=latest['id'])
        cursor = c.execute('INSERT INTO record_video_reviews(record_id,upload_id,token,action,request,payload,created) VALUES(?,?,?,?,?,?,?)',
                           (value['record_id'], value['upload_id'], saved['token'], request['action'], digest,
                            json.dumps(payload, ensure_ascii=False, allow_nan=False), now))
        row = c.execute('SELECT * FROM record_video_reviews WHERE id=?', (cursor.lastrowid,)).fetchone()
        return _result(row, base, value, saved, False)
