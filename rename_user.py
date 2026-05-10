import sqlite3
con = sqlite3.connect('data/db/facelock.db')
con.execute("UPDATE users SET name=? WHERE name=?", ('windows', 'fatma'))
con.commit()
rows = con.execute('SELECT id, name, created_at FROM users').fetchall()
for r in rows:
    print('DB:', r[0], r[1], r[2])
con.close()
print('Done.')
