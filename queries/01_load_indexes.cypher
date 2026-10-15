// 01 load: indexes. Statements are split on ';' by load.py.
// Creating an index that already exists fails; load.py ignores that error.
// Range indexes on every id, login, number and at (PLAN.md "Indexes").
CREATE INDEX FOR (n:Repo) ON (n.id);
CREATE INDEX FOR (n:Person) ON (n.id);
CREATE INDEX FOR (n:Person) ON (n.login);
CREATE INDEX FOR (n:Team) ON (n.id);
CREATE INDEX FOR (n:Module) ON (n.id);
CREATE INDEX FOR (n:Commit) ON (n.id);
CREATE INDEX FOR (n:Commit) ON (n.at);
CREATE INDEX FOR (n:PullRequest) ON (n.id);
CREATE INDEX FOR (n:PullRequest) ON (n.number);
CREATE INDEX FOR (n:PullRequest) ON (n.merged_at);
CREATE INDEX FOR (n:Issue) ON (n.id);
CREATE INDEX FOR (n:Issue) ON (n.number);
CREATE INDEX FOR (n:Issue) ON (n.opened_at);
CREATE INDEX FOR (n:Comment) ON (n.id);
CREATE INDEX FOR (n:Comment) ON (n.at);
CREATE INDEX FOR (n:Doc) ON (n.id);
CREATE INDEX FOR (n:DocChunk) ON (n.id);
CREATE INDEX FOR (n:Release) ON (n.id);
CREATE INDEX FOR (n:Release) ON (n.at);
CREATE INDEX FOR (n:Decision) ON (n.id);
CREATE INDEX FOR (n:Topic) ON (n.name);
// Full-text on the text the Navigator searches. Vector indexes come in M6.
CALL db.idx.fulltext.createNodeIndex('Issue', 'title', 'body');
CALL db.idx.fulltext.createNodeIndex('PullRequest', 'title', 'body');
CALL db.idx.fulltext.createNodeIndex('Decision', 'statement', 'rationale');
CALL db.idx.fulltext.createNodeIndex('DocChunk', 'text')
