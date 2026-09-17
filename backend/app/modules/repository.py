import json
from uuid import uuid4
from fastapi import HTTPException
from app.core.database import Session, Record

def create(kind, owner, data, parent=""):
    identifier = str(uuid4())
    with Session.begin() as db:
        db.add(Record(id=identifier, kind=kind, owner=owner, parent=parent, payload=json.dumps(data)))
    return {**data, "id": identifier}

def get(identifier, owner=None, kind=None):
    with Session() as db:
        row = db.get(Record, identifier)
        if not row or (owner is not None and row.owner != owner) or (kind and row.kind != kind):
            raise HTTPException(404, "Resource not found")
        return {**json.loads(row.payload), "id": row.id, "_owner": row.owner}

def listing(kind, owner, parent=None):
    with Session() as db:
        query = db.query(Record).filter_by(kind=kind, owner=owner)
        if parent is not None:
            query = query.filter_by(parent=parent)
        return [{**json.loads(r.payload), "id": r.id} for r in query.all()]

def update(identifier, owner, changes):
    with Session.begin() as db:
        row = db.get(Record, identifier)
        if not row or row.owner != owner:
            raise HTTPException(404, "Resource not found")
        data = json.loads(row.payload)
        data.update(changes)
        row.payload = json.dumps(data)
    return get(identifier, owner)
