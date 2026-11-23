import ckanext.ecosis.datastore.workspace as workspace
import ckanext.ecosis.datastore.query.workspace as workspaceQuery
from ckanext.ecosis.datastore.push import Push
from ckanext.ecosis.lib.utils import jsonStringify
from ckanext.ecosis.lib.context import get_context

import ckan.model as model
from ckan.common import request
import ckan.logic as logic

def prepare():
    package_id = request.args.get('package_id')

    # get package by name or id
    context = get_context()
    ckanPackage = logic.get_action('package_show')(context, {'id': package_id})

    if ckanPackage == None:
        raise Exception('Invalid package ID')

    force = request.args.get('force')
    clean = request.args.get('clean')
    if force == "true":
        force = True
    else:
        force = False

    # remove old unused packages
    workspace.clean(current_package_id=package_id)

    if clean == "true":
        workspace.cleanPackage(ckanPackage.get("id"))

    result = workspace.prepare(ckanPackage.get("id"), force)

    if clean == "true":
        result['cleaned'] = True

    return jsonStringify(result)

def pushToSearch():
    package_id = request.args.get('package_id')
    email = request.args.get('email')
    if email is None:
        email = "false"

    context = get_context()
    ckanPackage = logic.get_action('package_show')(context, {"id": package_id})

    # might be: model = context['model']
    user = model.User.get(context.get('user'))

    if email == True or email.lower() == "true":
        email = True
    else:
        email = False

    push = Push()

    return push.run(ckanPackage, email, user.email, user.display_name)

def get():
    package_id = request.args.get('package_id')

    # get package by name or id
    context = get_context()
    ckanPackage = logic.get_action('package_show')(context, {'id': package_id})

    return jsonStringify(workspaceQuery.get(ckanPackage.get("id")))

def clean():

    package_id = request.args.get('package_id')
    workspace.cleanPackage(package_id)

    return jsonStringify({
        "cleaned": True,
        "packageId" : package_id
    })