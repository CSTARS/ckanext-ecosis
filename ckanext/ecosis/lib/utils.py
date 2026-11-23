import urllib.parse, json, datetime, re
import ckan.lib.helpers as h
from flask import make_response
import traceback, sys

# replicating default param parsing in ckan... really python... really...
# TODO: see if this is really needed
def get_request_data(request):
    # Flask request (CKAN 2.11+ removed the Pylons request.POST / request.body)
    try:
        keys = list(request.form.keys())
        # Parsing breaks if there is a = in the value, so for now
        # we will check if the data is actually all in a single key
        if keys and request.form[keys[0]] in [u'1', u'']:
            request_data = keys[0]
        else:
            request_data = urllib.parse.unquote(request.get_data(as_text=True))
    except Exception as inst:
        msg = "Could not find the POST data: %r : %s" % \
              (request.form, inst)
        raise ValueError(msg)

    try:
        request_data = json.loads(request_data)
    except ValueError as e:
        raise ValueError('Error decoding JSON data. '
                         'Error: %r '
                         'JSON data extracted from the request: %r' %
                          (e, request_data))
    return request_data

# We don't want to send HTML templated errors when things go wrong (CKAN default).
# Instead we catch errors and respond with this.
def handleError(e):
    headers = {"Content-Type": "application/json"}

    stack = ""
    try:
        stack = traceback.format_exc()
    except e:
        pass

    if hasattr(e, 'message'):
        if e.message is not None:
            return make_response((json.dumps({
                "error": True,
                "message": "%s:%s" % (type(e).__name__, e.message),
                "stack" : stack
            }), 500, headers))
    if hasattr(e, 'error_summary'):
        if e.error_summary is not None:
            return make_response((json.dumps({
                "error": True,
                "message": "%s:%s" % (type(e).__name__, e.error_summary),
                "stack" : "stack"
            }), 500, headers))

    return make_response(json.dumps({
        "error": True,
        "message": "%s:%s" % (type(e).__name__, str(e)),
        "stack" : stack
    }), 500, headers)

# helper for sending json, mostly adds ability to encode dates in ISO format.
def jsonStringify(obj, formatted=False):
    if not formatted:
        return json.dumps(obj, default=jsondefault)
    return json.dumps(obj, default=jsondefault, indent=4, separators=(',', ': '))

def jsondefault(obj):
    if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
        return obj.isoformat()
    else:
        return None

def setPackageExtra(attr, value, pkg):
    extra = pkg.get('extras')
    if extra == None:
        pkg['extras'] = []
        extra = pkg['extras']

    for item in extra:
        if item.get('key') == attr:
            item['value'] = value;
            return

    extra.append({
        'key' : attr,
        'value' : value
    })

def getPackageExtra(attr, pkg):
    extra = pkg.get('extras')
    if extra == None:
        return None

    for item in extra:
        if item.get('key') == attr:
            return item.get('value')
    return None

# a 'flat' name is when the name is in lower case with no spaces
def flatten(name):
    return re.sub(r'\s', '', name).lower()