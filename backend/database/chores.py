from sqlalchemy import insert, select, update

from .models import chores, occurrences


def all_chores(db):
    return db.execute(select(chores).order_by(chores.c.title, chores.c.id)).mappings()


def active_chores(db):
    return db.execute(select(chores).where(chores.c.retired == 0)
                      .order_by(chores.c.title)).mappings()


def active_chore(db, chore_id):
    statement = select(chores).where(chores.c.id == chore_id, chores.c.retired == 0)
    return db.execute(statement).mappings().first()


def create_chore(db, values):
    db.execute(insert(chores).values(**values))


def update_chore(db, chore_id, values):
    db.execute(update(chores).where(chores.c.id == chore_id, chores.c.retired == 0)
               .values(**values))


def retire_chore(db, chore_id):
    db.execute(update(chores).where(chores.c.id == chore_id).values(retired=1))


def occurrences_between(db, first, last):
    return db.execute(select(occurrences).where(occurrences.c.day.between(first, last))).mappings()


def occurrence_key(chore_id, day):
    return (occurrences.c.chore_id == chore_id, occurrences.c.day == day)


def find_occurrence(db, chore_id, day):
    return db.execute(select(occurrences).where(*occurrence_key(chore_id, day))).mappings().first()


def save_occurrence(db, chore_id, day, assignee, completed, *, exists):
    # The surrounding SQLite write transaction locks before the first read.
    values = dict(assignee=assignee, completed=completed)
    if exists:
        db.execute(update(occurrences).where(*occurrence_key(chore_id, day)).values(**values))
    else:
        db.execute(insert(occurrences).values(chore_id=chore_id, day=day, **values))
