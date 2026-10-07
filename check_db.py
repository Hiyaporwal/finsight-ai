import sqlite3, glob
files = glob.glob("instance/*.db") + glob.glob("*.db")
print("Database files:", files)
if not files:
    print("No .db file found. Run: flask db upgrade")
else:
    c = sqlite3.connect(files[0])
    rows = c.execute("select name from sqlite_master where type='table'").fetchall()
    print("Tables:", [r[0] for r in rows])
