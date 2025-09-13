from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)  # <-- This allows all origins (file://, http://localhost, etc.)

DB_PATH = "hashtags.db"

@app.route("/hashtags")
def get_hashtags():
    sort = request.args.get("sort", "collected_at DESC")
    search = request.args.get("search", "")
    limit = int(request.args.get("limit", 50))

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    query = f"SELECT hashtag, collected_at FROM hashtags WHERE hashtag LIKE ? ORDER BY {sort} LIMIT ?"
    cursor.execute(query, (f"%{search}%", limit))
    rows = cursor.fetchall()
    conn.close()
    
    data = [{"tag": row[0], "time": row[1]} for row in rows]
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)
