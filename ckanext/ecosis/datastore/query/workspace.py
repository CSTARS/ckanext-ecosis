from  ecosis.datastore.ckan import resource as ckanResourceQuery
from  ecosis.datastore.ckan import package as ckanPackageQuery

collections = None

def init(co):
    global collections

    collections = co


def get(package_id):
    # get all package resources
    resources = ckanResourceQuery.active(package_id)

    response = {
        "package" : collections.get("package").find_one({"packageId":package_id}),
        "resources" : [],
        "ckan" : {
            "package" : ckanPackageQuery.get(package_id),
            "resources" : resources
        }
    }

    if response['package'] is None:
        response['package'] = {}


    for resource in resources:
        sheets = collections.get("resource").find({
            "packageId" : package_id,
            "resourceId" : resource.get('id')
        })

        for sheet in sheets:
            response.get('resources').append(sheet)

    # now add all zip file resources
    resources = collections.get("resource").find({
        "packageId" : package_id,
        "fromZip" : True
    })

    for resourceOrSheet in resources:
        response.get('resources').append(resourceOrSheet)

    return response