import psycopg2.extras, json

connStr = None
schema = None

# inject global dependencies
def init(pgConn, s):
    global connStr, schema
    connStr = pgConn
    schema = s

# helper for returning EcoSIS attribute schema
def getSchema():
    return schema

def getPgConn():
    return psycopg2.connect(connStr)

# get a dataset by id
def get(package_id):
    conn = getPgConn()

    # query pg for dataset
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("select * from package where id = %s", (package_id,))
    package = cur.fetchall()
    cur.close()

    if len(package) == 0:
        raise Exception('Invalid package ID')
    else:
        package = package[0]

    # extras: CKAN 2.12 dropped the package_extra table; active extras now
    # live in the package.extras JSONB column ({key: string value}), which
    # psycopg2 already decodes to a dict (NULL when a package has none)
    package['extras'] = package.get('extras') or {}

    # append organization information
    ownerOrg = package.get('owner_org')
    if ownerOrg != None and ownerOrg != "":
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("select * from public.group where id = %s", (ownerOrg,))
        rows = cur.fetchall()
        cur.close()

        if len(rows) > 0:
            package['organization'] = rows[0]

    # append tag (keywords) information
    package['tags'] = []
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("select t.name from tag t, package_tag pt where t.id = pt.tag_id and pt.package_id = %s and pt.state = 'active'", (package_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    for row in rows:
        package['tags'].append(row.get('name'))

    return package

# query package by EcoSIS DOI status.  Uses pg-json functionality
# TODO: build index on doi status -> value field
def doiQuery(status="", query="", limit=10, offset=0):
    conn = getPgConn()

    if status == "" or status is None:
        status = "Pending Approval"
    if query is None:
        query = ""
    if limit is None:
        limit = 10
    if offset is None:
        offset = 0

    query = "%%%s%%" % query.lower()

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        # CKAN 2.12: extras are in the package.extras JSONB column
        ("select p.title as title, p.id, p.extras->>'EcoSIS DOI Status' as status, "
         "p.extras->>'EcoSIS DOI' as doi "
         "from package p "
         "where p.extras ? 'EcoSIS DOI Status' "
         "and (p.extras->>'EcoSIS DOI Status')::json->>'value' = ANY(%s) "
         "and lower(p.title) like %s order by title limit %s offset %s;"),
         (status.split(','), query, limit, offset)
        )
    packages = cur.fetchall()
    cur.close()

    for package in packages:
        if package.get('status') is not None:
            package['status'] = json.loads(package['status'])

    return packages