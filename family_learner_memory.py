"""Correctable, bi-temporal learner memory for confirmed judgments (R26).

Each time a parent confirms a plan, the assistant's judgment at that moment
(assessment + up to four hypotheses with their evidence refs) is appended here,
so a later re-evaluation can read what we already believed instead of cold-starting
from only the last 24 records. Two time axes, following the same idea as a
bi-temporal knowledge graph:

  confirmed_on  the day the judgment was decided (domain/decision time)
  valid_from    when this row began to be believed (transaction time)
  invalid_from  when it stopped being believed: NULL while current, set to the
                moment a newer confirmation for the same goal supersedes it

Judgment text is never deleted or overwritten: a superseded row only gains its
validity end and replacement link, and stays readable as history. This module owns only its own table and never imports the goal/app code,
so it adds no new service and minimal coupling; writes run inside the caller's
existing transaction cursor.
"""
import datetime as dt
import json

# What a cited record says, and which task the parent attached it to; a save that leaves these unchanged
# (or only adds an original) is not a correction.
MATERIAL = ('day', 'category', 'subject', 'title', 'note', 'score', 'total', 'related_record_id',
            'followup_kind', 'assistance', 'practice_relation', 'comparison_note', 'transcript', 'transcript_state',
            'linked_task_id')


def _ensure(c):
    c.execute("""CREATE TABLE IF NOT EXISTS learner_memory (
        id INTEGER PRIMARY KEY,
        child_id TEXT NOT NULL,
        goal_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT '',
        support TEXT NOT NULL DEFAULT '[]',
        against TEXT NOT NULL DEFAULT '[]',
        subject TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        confirmed_on TEXT NOT NULL,
        recorded_at TEXT NOT NULL,
        valid_from TEXT NOT NULL,
        invalid_from TEXT,
        superseded_by INTEGER,
        evidence_hash TEXT NOT NULL DEFAULT ''
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS learner_memory_child_valid ON learner_memory(child_id, invalid_from)")
    c.execute("CREATE INDEX IF NOT EXISTS learner_memory_goal ON learner_memory(goal_id, invalid_from)")


def _refs(value):
    """Keep only clean string refs; never trust free text as an evidence pointer."""
    return [r for r in value if isinstance(r, str) and r][:20] if isinstance(value, list) else []


def record_confirmation(c, now, *, child_id, goal_id, subject, title, confirmed_on,
                        assessment, hypotheses, evidence_hash):
    """Append the judgment confirmed now; supersede the goal's previous still-valid rows.

    Idempotent only for an exact replay of the same judgment and evidence. Returns the
    number of rows inserted (0 on replay or when there is nothing to record).
    """
    _ensure(c)
    stamp = now.isoformat()
    current = c.execute(
        "SELECT id,kind,text,status,support,against,evidence_hash FROM learner_memory "
        "WHERE goal_id=? AND child_id=? AND invalid_from IS NULL ORDER BY id",
        (goal_id, child_id)).fetchall()
    rows = []
    if isinstance(assessment, str) and assessment.strip():
        rows.append(('assessment', assessment.strip(), '', [], []))
    for h in (hypotheses or []):
        if not isinstance(h, dict):
            continue
        reason = h.get('reason')
        if not isinstance(reason, str) or not reason.strip():
            continue
        status = h.get('status') if isinstance(h.get('status'), str) else ''
        rows.append(('hypothesis', reason.strip(), status, _refs(h.get('support')), _refs(h.get('against'))))
    if not rows:
        return 0
    serialized = [(kind, text, status, json.dumps(support, ensure_ascii=False),
                   json.dumps(against, ensure_ascii=False))
                  for kind, text, status, support, against in rows]
    current_payload = [(r['kind'], r['text'], r['status'], r['support'], r['against']) for r in current]
    if current and current_payload == serialized and all(r['evidence_hash'] == (evidence_hash or '') for r in current):
        return 0  # Exact replay; the same evidence with a changed judgment is a new confirmation.
    # Only invalidate the prior belief once we know we have a new one to write in its place.
    if current:
        c.execute("UPDATE learner_memory SET invalid_from=? WHERE goal_id=? AND child_id=? AND invalid_from IS NULL",
                  (stamp, goal_id, child_id))
    first_id = None
    for kind, text, status, support, against in rows:
        cur = c.execute(
            "INSERT INTO learner_memory(child_id,goal_id,kind,text,status,support,against,subject,title,"
            "confirmed_on,recorded_at,valid_from,invalid_from,superseded_by,evidence_hash) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,NULL,?)",
            (child_id, goal_id, kind, text, status, json.dumps(support, ensure_ascii=False),
             json.dumps(against, ensure_ascii=False), subject or '', title or '',
             confirmed_on, stamp, stamp, evidence_hash or ''))
        first_id = first_id or cur.lastrowid
    # Point the superseded rows at the assessment/first row of the batch that replaced them.
    if current and first_id is not None:
        ids=[r['id'] for r in current]
        c.execute(f"UPDATE learner_memory SET superseded_by=? WHERE id IN ({','.join('?' for _ in ids)})",
                  (first_id,*ids))
    return len(rows)


def _row(r):
    return dict(id=r['id'], goal_id=r['goal_id'], kind=r['kind'], text=r['text'], status=r['status'],
                support=json.loads(r['support']), against=json.loads(r['against']), subject=r['subject'],
                title=r['title'], confirmed_on=r['confirmed_on'], recorded_at=r['recorded_at'],
                valid_from=r['valid_from'], invalid_from=r['invalid_from'])


def _has_table(c):
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='learner_memory'").fetchone() is not None


def learner_card(c, child_id, *, limit_goals=12):
    """Currently-believed judgments for one child, grouped by goal, newest confirmation first.

    This is the compact long-term memory a re-evaluation can read without the 24-record
    window: it survives beyond any single round. Superseded history is excluded here.
    """
    if not _has_table(c):
        return []
    # id ASC keeps each goal's assessment before its hypotheses and hypotheses in insertion order;
    # goals themselves are re-sorted by confirmation date below.
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM learner_memory WHERE child_id=? AND invalid_from IS NULL ORDER BY id ASC",
        (child_id,)).fetchall()]
    goals = {}
    for r in rows:
        g = goals.setdefault(r['goal_id'], dict(goal_id=r['goal_id'], subject=r['subject'], title=r['title'],
                                                confirmed_on=r['confirmed_on'], _valid_from=r['valid_from'], assessment='', hypotheses=[]))
        if r['kind'] == 'assessment' and not g['assessment']:
            g['assessment'] = r['text']
        elif r['kind'] == 'hypothesis':
            g['hypotheses'].append(dict(reason=r['text'], status=r['status'],
                                        support=json.loads(r['support']), against=json.loads(r['against'])))
    ordered = sorted(goals.values(), key=lambda g: (g['confirmed_on'], g['_valid_from']), reverse=True)
    for g in ordered: g.pop('_valid_from')
    return ordered[:limit_goals]


def _local(stamp):
    """Compare decision and edit times on one clock: aware stamps move to local time, naive ones already are."""
    return dt.datetime.fromisoformat(stamp).astimezone().replace(tzinfo=None)


def corrected_refs(c, refs, since, owned):
    """Cited records that no longer say what they said at `since` (a confirmation time).

    A `record:<id>` counts when it was materially edited afterwards — the revision log keeps the content
    as of then, so a save that changed nothing does not count — or when it is gone or no longer belongs
    to this child (`owned(stored child name)`). Other refs (task feedback, school messages, goal
    background) are checked by their own flows. Deterministic; returns refs in citation order.
    """
    if not since or c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='records'").fetchone() is None:
        return []
    since = _local(since)
    has_log = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='revisions'").fetchone() is not None
    out = []
    for ref in dict.fromkeys(r for r in refs if isinstance(r, str) and r.startswith('record:') and r[7:].isdigit()):
        row = c.execute('SELECT * FROM records WHERE id=?', (int(ref[7:]),)).fetchone()
        if row is None or not owned(row['child']):
            out.append(ref); continue
        then = None
        for rev in (c.execute('SELECT previous,changed FROM revisions WHERE record_id=? ORDER BY id', (row['id'],)) if has_log else []):
            try:
                if _local(rev['changed']) > since:
                    then = json.loads(rev['previous']); break
            except (TypeError, ValueError):
                continue
        # Older revisions predate some columns; only fields recorded then can show a change.
        if then is not None and any(k in then and then[k] != row[k] for k in MATERIAL if k in row.keys()):
            out.append(ref)
    return out


def prior_confirmations(c, child_id, goal_id, *, limit=5, owned=None):
    """Past (already superseded) confirmed judgments for one goal, newest first, as events.

    The current confirmation (invalid_from IS NULL) is excluded; this shows how the belief
    evolved before now so a re-evaluation can see what was already tried and refined instead
    of cold-starting. Each event groups the rows written in one confirmation (shared valid_from).
    With `owned`, each event and hypothesis also lists `corrected`: cited records edited or
    reassigned after that confirmation, so neither the parent nor a re-evaluation leans on it.
    """
    if not _has_table(c):
        return []
    rows = [dict(r) for r in c.execute(
        "SELECT * FROM learner_memory WHERE child_id=? AND goal_id=? AND invalid_from IS NOT NULL ORDER BY id ASC",
        (child_id, goal_id)).fetchall()]
    events = {}
    for r in rows:
        e = events.setdefault(r['valid_from'], dict(confirmed_on=r['confirmed_on'], assessment='', hypotheses=[]))
        if r['kind'] == 'assessment' and not e['assessment']:
            e['assessment'] = r['text']
        elif r['kind'] == 'hypothesis':
            h = dict(reason=r['text'], status=r['status'])
            if owned is not None and (refs := corrected_refs(c, json.loads(r['support']) + json.loads(r['against']), r['valid_from'], owned)):
                h['corrected'] = refs
            e['hypotheses'].append(h)
    ordered = sorted(events.items(), key=lambda item: (item[1]['confirmed_on'], item[0]), reverse=True)
    if owned is not None:
        for _, e in ordered:
            e['corrected'] = list(dict.fromkeys(ref for h in e['hypotheses'] for ref in h.get('corrected', [])))
    return [event for _,event in ordered[:limit]]


def timeline(c, child_id, goal_id=None):
    """Full readable history for audit, including superseded judgments, newest first."""
    if not _has_table(c):
        return []
    if goal_id:
        rows = c.execute("SELECT * FROM learner_memory WHERE child_id=? AND goal_id=? ORDER BY id DESC",
                         (child_id, goal_id)).fetchall()
    else:
        rows = c.execute("SELECT * FROM learner_memory WHERE child_id=? ORDER BY id DESC", (child_id,)).fetchall()
    return [_row(r) for r in rows]


TRANSCRIPT_CHECKED = '已核对'


def media_evidence(row):
    """Keys a record's media may add to its one evidence item ({} for a plain text record, which stays as it was).

    A transcript the parent checked is their checked wording of the original media: not something the system
    heard the child do, and on its own no proof of mastery or of a cause. An unchecked transcript or a bare
    original is unknown content, so its words are withheld and the record only says that it is unread.
    """
    state = row.get('transcript_state') or ''
    if state == TRANSCRIPT_CHECKED and row.get('transcript'):
        return dict(transcript=row['transcript'], transcript_state=state)
    if state: return dict(transcript_state=state, media_unread=True)
    bare = not (row.get('note') or '').strip() and row.get('score') is None and (row.get('attachments') or '[]') != '[]'
    return dict(media_unread=True) if bare else {}


VIDEO_CHECKED = '家长核对的画面观察'


def video_evidence(row, confirmed):
    """Keys the parent's confirmed picture observations add to the record's one evidence item ({} when there are none).

    `confirmed` is what family_task_video.confirmed read for the record's originals: per video the confirmation id,
    token, original id and time, the parent's selected observations with their time positions and the draft's listed
    unknowns, sound unassessed. It is the parent's checked reading of the picture: not something the system saw or
    heard the child do, no proof of completion, mastery or a cause, and it leaves the record's own text, score, task
    and plan untouched. Unselected observations never arrive here. An original the parent did not confirm, or an
    unchecked transcript, stays unknown and is named as `other_media_unread` instead of the whole record being unread.
    """
    if not confirmed:
        return {}
    covered = {v['upload_id'] for v in confirmed}
    try:
        attachments = json.loads(row.get('attachments') or '[]')
    except (TypeError, ValueError):
        attachments = None
    state = row.get('transcript_state') or ''
    checked_words = state == TRANSCRIPT_CHECKED and bool(row.get('transcript'))
    remaining = (attachments is None or (not checked_words and any(a not in covered for a in attachments))
                 or bool(state and not checked_words))
    out = dict(video_observations=confirmed, video_observations_label=VIDEO_CHECKED, audio_assessed=False)
    if remaining:
        out['other_media_unread'] = True
    return out


def media_unreadable(row):
    """A record with nothing to read but unchecked media: it can be listed, never support or contradict a cause.

    The parent's confirmed video observations are readable content, so a record carrying them is not unread even if
    its other media still is."""
    return (bool(media_evidence(row).get('media_unread')) and not row.get('video_observations')
            and not (row.get('note') or '').strip() and row.get('score') is None)
