from stock_scanner.events.classifier import classify_and_store_all
from stock_scanner.storage.database import get_connection

conn = get_connection()
print(classify_and_store_all(conn=conn))
