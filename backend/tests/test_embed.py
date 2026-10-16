from lore.graph.search import NO_TEXT, fulltext_query, keyword_query
from lore.ingest.embed import chunk_id, chunk_text, decision_text, issue_text


def test_chunk_short_text_is_one_chunk():
    assert chunk_text("  hello world  ") == ["hello world"]
    assert chunk_text("") == []


def test_chunks_respect_size_and_overlap():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(12))
    chunks = chunk_text(text, size=300, overlap=60)
    assert len(chunks) > 1
    assert all(len(c) <= 300 for c in chunks)
    # Each chunk starts with text the previous chunk already ended with.
    for a, b in zip(chunks, chunks[1:]):
        assert b[:20] in a
    # Nothing is lost: the last words of the text are in the last chunk.
    assert chunks[-1].endswith(text.strip()[-30:])


def test_chunk_cuts_on_whitespace():
    chunks = chunk_text("abcdefghij " * 100, size=200, overlap=40)
    assert all(c.endswith("abcdefghij") for c in chunks)


def test_chunk_id():
    assert chunk_id("doc:FalkorDB/FalkorDB:docs/a.md", 2) == "chunk:FalkorDB/FalkorDB:docs/a.md#2"


def test_decision_and_issue_text():
    assert decision_text("Use Redis.", None, "we moved to Redis") == "Use Redis.\nwe moved to Redis"
    assert decision_text("Use Redis.", "", None) == "Use Redis."
    body = "<!-- template -->\n\n" + "x" * 900
    t = issue_text("Title", body)
    assert t.startswith("Title\nx") and "template" not in t and len(t) == len("Title\n") + 500
    assert issue_text("Title", None) == "Title"


def test_fulltext_query_keeps_specific_terms_only():
    assert fulltext_query("Why did the Rust engine drop all_nodes_matrix?") == "all_nodes_matrix"
    assert fulltext_query("Why does the engine fold MVCC deltas?") == "mvcc"
    assert fulltext_query("Why were graphblas.sh and redisearch.sh replaced with a native-deps crate?") == \
        '"graphblas sh"|"redisearch sh"|"native deps"'
    assert fulltext_query("What changed in v3 for GRAPH.BULK?") == 'v3|"graph bulk"'
    assert fulltext_query("Why do we cache links in Redis?") == NO_TEXT


def test_keyword_query_drops_stopwords_and_operators():
    assert keyword_query("Why do we cache links in Redis?") == "cache|links|redis"
    assert "-" not in keyword_query("native-deps crate")
    assert keyword_query("why is it?") == NO_TEXT
