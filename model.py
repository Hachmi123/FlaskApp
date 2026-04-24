import pandas as pd
import joblib
from sklearn.neighbors import NearestNeighbors
import mysql.connector

# Connexion DB
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="hotel_reservation_db"
)

query = """
SELECT 
    r.id,
    r.capacity,
    r.size_sqm,
    rlp.price
FROM rooms r
JOIN room_listed_prices rlp ON r.id = rlp.room_id
WHERE r.is_active = 1
"""

df = pd.read_sql(query, db)

X = df[['price', 'capacity', 'size_sqm']]

model = NearestNeighbors(n_neighbors=3)
model.fit(X)

joblib.dump(model, "room_recommender.pkl")
joblib.dump(df, "room_data.pkl")

print("✅ Modèle IA entraîné")
