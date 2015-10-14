import psycopg2.extras, psycopg2

connStr = None

def init(pgConn):
    global connStr
    connStr = pgConn

def get(resource_id):
    conn = psycopg2.connect(connStr)

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("select * from resource where id = %s", (resource_id,))
    resource = cur.fetchall()
    cur.close()

    if len(resource) == 0:
        raise Exception('Invalid resource ID')
    else:
        resource = resource[0]

    conn.close()

    return resource

# get all active resources
def active(package_id):
    conn = psycopg2.connect(connStr)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("select * from resource where state = 'active' and url_type = 'upload' and package_id = %s", (package_id,))
    results = cur.fetchall()
    cur.close()
    conn.close()
    return results