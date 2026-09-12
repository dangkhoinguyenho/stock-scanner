from stock_scanner.storage.database import get_connection, get_events

conn = get_connection()
suspects = {"M&A", "Guidance", "Regulatory/Legal"}
for e in get_events(conn):
    if e["source_type"] == "news" and e["category"] in suspects:
        article_id = e["source_id"].split(":", 1)[1]
        row = conn.execute(
            "SELECT headline FROM news_articles WHERE article_id = ?", (article_id,)
        ).fetchone()
        print(e["category"], "|", e["classification_reason"], "|", row["headline"] if row else "(not found)")
