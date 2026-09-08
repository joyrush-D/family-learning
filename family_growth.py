"""Read-only product rewards derived from current records, never learning scores."""
import datetime as dt


SOURCES = frozenset({'家长观察', '孩子自述', '试卷 / 作业核对'})
KINDS = {
    'learning': ('学习探索', '记下一次学习探索；不表示作业完成或知识掌握。'),
    'retest': ('复测尝试', '留下有关联来源的复测记录；不评价复测成绩或掌握程度。'),
    'interest': ('兴趣记录', '记下一次兴趣探索；不判断活动完成、表现或熟练程度。'),
}
RULE_NOTE = (
    '能量和徽章是鼓励记录与尝试的产品规则，不是学习能力或教育评价。'
    '只按学习进展、兴趣及指定来源等结构字段计算，不解读正文判断是否完成。'
    '每个来源最多奖励一次，每个孩子每天每类最多10能量；重复记录保留但不加分。'
    '成绩、情绪、普通家长观察、老师反馈、陪伴建议回应及待办勾选不计分。'
    '不比较兄弟，不按成绩加分，没有连续打卡或断签扣分。'
    '纠正或移除原记录后会重新计算，不保留已被纠正事实的奖励。'
)


def _day(value):
    try:
        return dt.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _valid_link(record, by_id):
    """Require an existing same-child chain, rejecting self-links and cycles."""
    seen = {record['id']}
    related = record.get('related_record_id')
    if related is None:
        return False
    while related is not None:
        if type(related) is not int or related in seen or related not in by_id:
            return False
        seen.add(related)
        parent = by_id[related]
        if parent.get('child') != record.get('child'):
            return False
        related = parent.get('related_record_id')
    return True


def summarize(children, records, tasks, today):
    """Return {rules_version, note, children}; inputs follow app.snapshot().

    Each child has id/name/energy/level/progress/next_level_at/badges/events.
    progress is an integer percentage within a 50-energy band. No records means
    level 0; the first reward unlocks level 1, then 50 energy unlocks level 2.
    Events identify the original record; same-day/category overflow has 0 points.
    Tasks deliberately do not award energy: completion may be parent logistics.
    No input is mutated, no clock is read, and no reward balance is persisted.
    """
    cutoff = today if type(today) is dt.date else _day(today)
    if cutoff is None:
        raise ValueError('today must be an ISO date or datetime.date')
    by_id = {}
    for record in records:
        ident = record.get('id')
        if type(ident) is int and ident > 0:
            by_id.setdefault(ident, record)
    results = []
    for child in children:
        events, awarded = [], set()
        for record in sorted(by_id.values(), key=lambda r: r['id']):
            day = _day(record.get('day'))
            if (record.get('child') != child['name'] or day is None or day > cutoff
                    or record.get('source') not in SOURCES
                    or record.get('category') not in {'学习进展', '兴趣'}):
                continue
            if record.get('followup_kind') in {'复测', '独立复测'}:
                if record['category'] != '学习进展' or not _valid_link(record, by_id):
                    continue
                kind = 'retest'
            else:
                kind = 'learning' if record['category'] == '学习进展' else 'interest'
            key = (day, kind)
            points = 0 if key in awarded else 10
            awarded.add(key)
            reason = KINDS[kind][1] if points else '当日这类记录已获得能量；保留这条来源，不重复加分。'
            events.append(dict(source_type='record', source_id=record['id'],
                               title=record.get('title', ''), day=day.isoformat(),
                               kind=kind, reason=reason, points=points))
        events.sort(key=lambda e: (e['day'], e['source_id']))
        energy = sum(e['points'] for e in events)
        badges = []
        for kind, (name, description) in KINDS.items():
            first = next((e for e in events if e['kind'] == kind and e['points']), None)
            if first:
                badges.append(dict(id=kind, name=name, description=description,
                                   source_id=first['source_id'], unlocked_on=first['day']))
        results.append(dict(id=child['id'], name=child['name'], energy=energy,
                            level=1 + energy // 50 if energy else 0,
                            progress=(energy % 50) * 2,
                            next_level_at=(energy // 50 + 1) * 50 if energy else 10,
                            badges=badges, events=events))
    return dict(rules_version='growth-v1', note=RULE_NOTE, children=results)
