from stock_scanner.storage.database import get_connection, get_events

conn = get_connection()
for e in get_events(conn, symbol="NFLX"):
    if e["source_type"] == "news" and "does not mention" in e["classification_reason"]:
        article_id = e["source_id"].split(":", 1)[1]
        row = conn.execute(
            "SELECT headline FROM news_articles WHERE article_id = ?", (article_id,)
        ).fetchone()
        print(e["classification_reason"], "|", row["headline"] if row else "(not found)")
