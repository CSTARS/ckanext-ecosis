import json

from ckan.common import request

import ckanext.ecosis.datastore.query as query
from ckanext.ecosis.datastore.vocab import top
from ckanext.ecosis.datastore.vocab import gcmd

# get a spectra measurement with joined metadata
def get():
    package_id = request.args.get('package_id')
    resource_id = request.args.get('resource_id')
    sheet_id = request.args.get('sheet_id')

    return query.get(package_id, resource_id, sheet_id, _getIndex(), showProcessInfo=True)

# get TOP suggestions for given attribute name
def suggestAttributeName():
    name = request.args.get('name')
    if name is None:
        name = ""

    return top.suggest(name)

# for a list of attributes of a spectra, returns attributes which might
# have TOP suggestions
def suggestOverview():
    params = {
      'names' : request.form.get('names')
    }
    if params.get('names') is None:
      params['names'] = request.args.get('names')

    if params.get('names') is None:
        raise Exception('Name list not provided')

    return top.overview(json.loads(params.get('names')))

# Query NASA GCDM vocab
def suggestGCMD():
    query = request.args.get('query')
    if query is None:
        query = ""

    return gcmd.suggest(query)


def _getIndex():
    index = request.args.get('index')
    if index is None:
        return 0
    else:
        return int(index)