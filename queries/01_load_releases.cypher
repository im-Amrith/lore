// 01 load: Release nodes. SHIPPED_IN (PR -> Release) is not derived yet.
UNWIND $rows AS row
MERGE (r:Release {id: row.id})
SET r.tag = row.tag, r.repo = row.repo, r.name = row.name, r.url = row.url, r.at = row.at,
    r.is_prerelease = row.is_prerelease
