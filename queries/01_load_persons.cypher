// 01 load: Person nodes. id is person:<login>, or person:name:<slug> for commit
// authors with no GitHub account (login is then null). No emails, ever.
UNWIND $rows AS row
MERGE (p:Person {id: row.id})
SET p.login = row.login, p.name = row.name, p.is_bot = row.is_bot,
    p.first_seen = row.first_seen, p.last_active = row.last_active
