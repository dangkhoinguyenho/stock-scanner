from stock_scanner.storage.database import get_connection, get_events
from collections import Counter

conn = get_connection()
counts = Counter(e["category"] for e in get_events(conn) if e["source_type"] == "news")
for category, n in counts.most_common():
    print(f"{n:4d}  {category}")
