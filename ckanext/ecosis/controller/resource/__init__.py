import os, json, re

# from ckan.common import request, response
from ckan.common import request, config
import ckan.logic as logic
import ckan.lib.uploader as uploader

import ckanext.ecosis.lib.utils as utils
from ckanext.ecosis.lib.auth import hasAccess
from ckanext.ecosis.lib.context import get_context
import ckanext.ecosis.datastore.delete as deleteUtil
import ckanext.ecosis.datastore.query as query
import ckanext.ecosis.datastore.workspace as workspace
from ckanext.ecosis.lib.utils import jsonStringify
from ckanext.ecosis.controller.package.doi import hasAppliedDoi
from ckanext.ecosis.datastore.ckan import resource as ckanResourceQuery

from flask import make_response

parseOptions = ["ignore", "layout", "metadata", "joinOn", "separator"]

# delete are resource
# By default, CKAN keeps resources on disk after they are deleted.  EcoSIS does not.
def delete():
    params = utils.get_request_data(request)

    # remove resource from disk - normally this doesn't happen
    resp = _delete(params)

    return resp

# Single HTTP call for deleting multiple resources
def deleteMany():
    ids = request.get_json().get('ids')

    resp = []
    for id in ids:
        resp.append(_delete({'id': id}))

    return resp

# Actually delete a resource
def _delete(params):
    # remove resource from disk - normally this doesn't happen
    context = get_context()
    resource = logic.get_action('resource_show')(context, params)

    # if package has DOI applied, resources cannot be modified
    if hasAppliedDoi(resource.get('package_id')):
        return {'error':True, 'message':'Cannot delete resource of package with applied DOI'}

    # this will fire error if user does not have access
    logic.get_action('resource_delete')(context, params)
    id = params.get('id')

    # if the resource is a file upload, remove from disk
    if resource.get('url_type') == "upload":
        upload = uploader.ResourceUpload(resource)
        path = upload.get_path(resource['id'])
        if os.path.exists(path):
            os.remove(path)

    # remove resource from EcoSIS
    deleteUtil.resource(resource.get("package_id"), id)

    params['success'] = True
    return params

# create new resource for dataset
def create():

    request_data = dict(request.form)

    # if the dataset has a DOI applied, you cannot add new resources
    if hasAppliedDoi(request_data.get('package_id')):
        return {'error': True, 'message': 'Cannot add resources to package with applied DOI'}

    # run the default CKAN create resource logic
    context = get_context()
    resource_create = logic.get_action('resource_create')
    resp = resource_create(context, request_data)

    return json.dumps({
        'result' : resp,
        'success' : True
    })

# process a resource
# this will be given a set of options, then parse the measurement data or metadata out of
# the resource based on this options
def process():
    package_id = request.form.get('package_id')
    hasAccess(package_id)

    if hasAppliedDoi(package_id):
        return {'error':True, 'message':'Cannot edit resource of package with applied DOI'}

    sheet_id = request.form.get('sheet_id')
    resource_id = request.form.get('resource_id')
    ids = request.form.get('resource_ids')

    if sheet_id == "":
        sheet_id = None

    try:
        options = json.loads(request.form.get('options'))
    except:
        options = {}

    return _process(package_id, sheet_id, resource_id, ids, options)


def _process(package_id, sheet_id, resource_id, ids, options):
    # option, if a resource id and a datasheet id are passed, then the full 'merged' view will be return
    # only allow specified options
    safeOptions = {}
    for option in parseOptions:
        if option in options:
            safeOptions[option] = options[option]

    # see if we are editing multiple files or just one
    result = []
    if ids is not None:
        ids = json.loads(ids)
        for resource_id in ids:
            workspace.prepareFile(package_id, resource_id, sheet_id, safeOptions)
            result.append(query.getResource(resource_id))
    else:
        workspace.prepareFile(package_id, resource_id, sheet_id, safeOptions)
        result = query.getResource(resource_id, sheet_id)

    # update the dataset, so the metadata timestamp changes
    context = get_context()
    pkg = logic.get_action('package_show')(context, {'id': package_id})

    # use this counter to poke the dataset.  This will update the last modified timestamps
    # required for 'updated since last pushed UI'
    resourceUpdateCount = utils.getPackageExtra('resourceUpdateCount', pkg)
    if resourceUpdateCount is None:
        resourceUpdateCount = 1
    else:
        resourceUpdateCount = int(resourceUpdateCount) + 1
    utils.setPackageExtra('resourceUpdateCount', resourceUpdateCount, pkg)
    pkg = logic.get_action('package_update')(context, pkg)

    result = {
        'metadata_modified' : pkg.get('metadata_modified'),
        'result' : result
    }

    return result

# get a specific resource
# optional sheet id, it the resource has multiple sheets (excel file)
def get():
    pid = request.args.get('package_id')
    rid = request.args.get('resource_id')
    sid = request.args.get('sheet_id')

    if sid == "":
        sid = None

    hasAccess(pid)

    return query.getResource(rid, sid)

# a get a row or column (depending on sheet orientation) of a resource file
# index is the row/column to retrieve
def getMetadataChunk():

    package_id = request.args.get('package_id')
    resource_id = request.args.get('resource_id')
    sheet_id = request.args.get('sheet_id')

    if sheet_id == "":
        sheet_id = None

    return query.getMetadataChunk(package_id, resource_id, sheet_id, _getIndex())

# get overview information for file, like number of rows/columns (chunks)
# also returns number of join rows/columns if metadata resource type
def getMetadataInfo():

    package_id = request.args.get('package_id')
    resource_id = request.args.get('resource_id')
    sheet_id = request.args.get('sheet_id')

    if sheet_id == "":
        sheet_id = None

    return query.getMetadataInfo(package_id, resource_id, sheet_id)

# get the number of spectra measurements found in the file
def getSpectraCount():
    package_id = request.args.get('package_id')
    resource_id = request.args.get('resource_id')
    sheet_id = request.args.get('sheet_id')

    if sheet_id == "":
        sheet_id = None

    return query.total(package_id, resource_id, sheet_id)

def getByName(package_id, resource_name):
    resource = ckanResourceQuery.getByName(package_id, resource_name)
    url = resource['url'];

    # ckan 2.9 doesn't seem to return full url...
    if not re.match(r'^https?', url, re.I):
      url = "%s/dataset/%s/resource/%s/download/%s" % (config.get('ckan.site_url'), package_id, resource['id'], resource_name)

    headers = {"Location": url}
    return make_response(("Redirecting", 307, headers))

# helper for getting index as int
def _getIndex():
    index = request.args.get('index')
    if index is None:
        return 0
    else:
        return int(index)
