import re, pymongo, json, dateutil

from ckanext.ecosis.datastore.ckan import package as ckanPackageQuery
from ckanext.ecosis.datastore.ckan import resource as ckanResourceQuery
from ckanext.ecosis.datastore.vocab import usda
from ckanext.ecosis.datastore.vocab import controlled as controlledVocab
from ckanext.ecosis.datastore.utils import mongo
import workspace


collections = None
host = ""

def init(co, hostUrl):
    global collections, host

    collections = co
    host = hostUrl
    workspace.init(co, getResource, isPushed)

def get(packageId="", resourceId=None, sheetId=None, index=0, showProcessInfo=False, must_be_valid=False, clean_wavelengths=True):
    # build out query
    query = {
        "type" : "data",
        "packageId" : packageId
    }
    if resourceId is not None:
        query["resourceId"] = resourceId
    if sheetId is not None:
        query["sheetId"] = sheetId

    main = collections.get('spectra').find_one(query, skip=index, sort=[("index", pymongo.ASCENDING)])

    if main == None:
        raise Exception('Unabled to get spectra from package_id: %s at index %s' % (packageId, index))

    spectra = main.get('spectra')


    moveWavelengths(spectra, clean_wavelengths)  # this also replaces , with .

    if must_be_valid:
        if 'datapoints' not in spectra:
            return {}
        if len(spectra['datapoints']) == 0:
            return {}

    sheetInfo = collections.get('resource').find_one({
        "packageId": packageId,
        "resourceId": main.get("resourceId"),
        "sheetId" : main.get("sheetId")
    })

    package = ckanPackageQuery.get(packageId)

    attributeProcessInfo = []
    join(packageId, spectra, attributeProcessInfo)


    config = collections.get('package').find_one({"packageId": packageId})
    if config == None:
        config = {}

    mapNames(spectra, config, attributeProcessInfo, package)

    usda.setCodes(spectra, info=attributeProcessInfo)

    controlledVocab.enforce(spectra)

    if showProcessInfo:
        addEcosisNamespace(spectra, package, main, sheetInfo, processInfo=attributeProcessInfo)
    else:
        addEcosisNamespace(spectra, package, main, sheetInfo)

    setSort(spectra, config, package)
    setLocation(spectra)

    return spectra

def getMetadataChunk(packageId, resourceId=None, sheetId=None, index=0):
    query = {
        "type" : "metadata",
        "packageId" : packageId
    }

    if resourceId is not None:
        query['resourceId'] = resourceId
    if sheetId is not None:
        query['sheetId'] = sheetId

    chunk = collections.get('spectra').find_one(query, skip=index, sort=[("index", pymongo.ASCENDING)])
    if chunk is None:
        raise Exception('Invalid resource ids given')

    del query['type']
    sheetInfo = collections.get('resource').find_one(query)

    joinedNames = []
    joinOn = sheetInfo.get("joinOn")
    if sheetInfo is not None and joinOn is not None and joinOn != "" and chunk.get('spectra') is not None:
        # now make join query
        joinQuery = {
            "type" : "data",
            "packageId" : packageId
        }

        joinQuery['spectra.%s' % sheetInfo.get("joinOn")] = chunk.get('spectra')[sheetInfo.get("joinOn")]

        joined = collections.get('spectra').find(joinQuery)
        for r in joined:
            # this is really SHITTY
            # TODO: figure out best place to commonly store resource name
            joinedInfo = collections.get('resource').find_one(
                {
                    'resourceId': r.get('resourceId'),
                    'sheetId': r.get('sheetId')
                },
                {"layout": 1,"name": 1})


            if joinedInfo is None: # Badness
                joinedName = {}
                joinedInfo = {}
            elif 'name' in joinedInfo:
                joinedName = joinedInfo
            else:
                try:
                    joinedName = ckanResourceQuery.get(r.get('resourceId'))
                except:
                    joinedName = {}

            if joinedName is not None:
                joinedNames.append({
                    "resourceId" : r.get('resourceId'),
                    "sheetId" : r.get('sheetId'),
                    "name" : joinedName.get('name'),
                    "layout" : joinedInfo.get('layout'),
                    "index" : r.get("index")
                })


    return {
        "metadata" : chunk.get('spectra'),
        "joinedResources" : joinedNames,
        "joinKey" : sheetInfo.get("joinOn")
    }

# get number or chunks and number of joined chunks
def getMetadataInfo(packageId, resourceId=None, sheetId=None):
    query = {
        "packageId" : packageId
    }

    if resourceId is not None:
        query['resourceId'] = resourceId
    if sheetId is not None:
        query['sheetId'] = sheetId

    sheetInfo = collections.get('resource').find_one(query)
    if sheetInfo is None:
        raise Exception('No resource found')

    query['type'] = "metadata"

    attrs = mongo.distinct(collections.get('spectra'), 'spectra.%s' % sheetInfo.get('joinOn'), query)
    total = mongo.count(collections.get('spectra'), query)

    query = {
        "packageId" : packageId,
        "type" : "data"
    }
    query['spectra.%s' % sheetInfo.get('joinOn')] = {
        "$in" : attrs
    }

    return {
        "joinCount": mongo.count(collections.get('spectra'), query),
        "total" : total
    }


def total(packageId, resourceId=None, sheetId=None):
    query = {
        "type" : "data",
        "packageId" : packageId
    }

    if resourceId is not None:
        query['resourceId'] = resourceId
    if sheetId is not None:
        query['sheetId'] = sheetId

    # need to support 2.8 drive cause pythons 3.0 seems to be a POS
    return {"total" : mongo.count(collections.get('spectra'), query)}

def setLocation(spectra):
    if spectra.get('geojson') != None:
        js = json.loads(spectra['geojson'])

        # extract geometry from feature
        if js.get("type") == "Feature":
            spectra['ecosis']['geojson'] = js.get('geometry')

        # extract geometries from feature collection in geo collection
        elif js.get("type") == "FeatureCollection":
            result ={
                "type": "GeometryCollection",
                "geometries": []
            }

            for f in js.get("features"):
                result['geometries'].append(f.get("geometry"))
            spectra['ecosis']['geojson'] = result

        # else we should be good to just add the geometry
        else:
             spectra['ecosis']['geojson'] = js

        del spectra['geojson']
    elif spectra.get('Latitude') != None and spectra.get('Longitude') != None:
        try:
            spectra['ecosis']['geojson'] = {
                "type" : "Point",
                "coordinates": [
                    float(spectra.get('Longitude')),
                    float(spectra.get('Latitude'))
                ]
            }
        except:
            pass
    elif spectra.get('latitude') != None and spectra.get('longitude') != None:
        try:
            spectra['ecosis']['geojson'] = {
                "type" : "Point",
                "coordinates": [
                    float(spectra.get('longitude')),
                    float(spectra.get('latitude'))
                ]
            }
        except:
            pass

def setSort(spectra, config, package):
    sort = None

    # backword compatibility.  But moving away from config object
    # all 'advanced data' should be stored in package
    extras = package.get('extras')
    if extras != None and extras.get('sort') != None:
        sort = json.loads(extras.get('sort'))
    elif config.get("sort") != None:
        sort = config.get("sort")

    if sort == None:
        return

    on = sort.get('on')
    type = sort.get('type')

    if on is None:
        return

    if on not in spectra:
        return

    if type == 'datetime':
        try:
            spectra['ecosis']['sort'] = dateutil.parser.parse(spectra[on])
        except:
            pass
    elif type == 'numeric':
        try:
            spectra['ecosis']['sort'] = float(spectra[on])
        except:
            pass
    else:
        spectra['ecosis']['sort'] = spectra[on]

def addEcosisNamespace(spectra, package, main, sheetInfo, processInfo=None):
    name = sheetInfo.get('name')
    if name is None and sheetInfo.get('fromZip') != True:
        resource = ckanResourceQuery.get(sheetInfo.get('resourceId'))
        name = resource.get('name')

    ecosis = {
        'package_id': sheetInfo.get("packageId"),
        'package_title': package.get('title'),
        'resource_id' : main.get('resourceId'),
        'filename': name,
        'sheet_id': main.get('sheetId'),
        'layout' : sheetInfo.get('layout'),
        'index' : main.get('index'),
        'dataset_link' : '%s#result/%s' % (host, sheetInfo.get('packageId')),
        'dataset_api_link' : '%spackage/get?id=%s' % (host, sheetInfo.get('packageId')),
    }

    if 'zip' in sheetInfo:
        ecosis['zip_package'] = {
            "id" : sheetInfo.get('zip').get('resourceId'),
            "name" : sheetInfo.get('zip').get('name')
        }


    if processInfo is not None:
        ecosis['processInfo'] = processInfo

    if package.get('organization') != None:
        ecosis['organization'] = package['organization']['title']

    spectra['ecosis'] = ecosis

def mapNames(spectra, config, processInfo, package):
    # backword compatibility.  But moving away from config object
    # all 'advanced data' should be stored in package

    aliases = None
    extras = package.get('extras')
    if extras != None and extras.get('aliases') != None:
        aliases = json.loads(extras.get('aliases'))
    elif config.get("map") != None:
        aliases = config.get("map")

    if aliases != None and isinstance(aliases, dict):
        for key, value in aliases.iteritems():
            if value in spectra:
                spectra[key] = spectra[value]

                processInfo.append({
                    "type" : "mapped",
                    "key" : key,
                    "from" : value
                })

def moveWavelengths(spectra, clean):
    wavelengths = {}
    toRemove = []
    for name in spectra:
        if re.match(r"^-?\d+\,?\d*", name) or re.match(r"^-?\d*\,\d+", name):
            if clean:
                wavelengths[uncleanKey(name)] = spectra[name].strip()
            else:
                wavelengths[name] = spectra[name].strip()
            toRemove.append(name)

    for name in toRemove:
        del spectra[name]

    spectra['datapoints'] = wavelengths

def join(packageId, spectra, processInfo):
    joinableSheets = collections.get('resource').find({"metadata": True, "packageId": packageId})

    for sheetConfig in joinableSheets:
        joinOn = sheetConfig.get('joinOn')
        if joinOn == None:
            continue

        joinVar = spectra.get(joinOn)

        if joinVar != None:
            query = {
                "type" : "metadata",
                "packageId" : packageId,
                "resourceId" : sheetConfig["resourceId"]
            }
            query["spectra.%s" % sheetConfig.get('joinOn')] = joinVar

            if sheetConfig.get('sheetId') != None:
                query["sheetId"] = sheetConfig.get('sheetId')

            joinData = collections.get('spectra').find_one(query)
            if joinData != None:
                for key in joinData.get("spectra"):
                    if key not in spectra:
                        spectra[key] = joinData.get("spectra").get(key)

                        processInfo.append({
                            "type" : "join",
                            "key" : key,
                            "resourceId" : joinData.get("resourceId"),
                            "sheetId" : joinData.get("sheetId"),
                        })

def uncleanKey(key):
    return re.sub(r',', '.', key)

def getResource(resource_id, sheet_id=None):
    query = {
        "$or" : [
            {"resourceId" : resource_id},
            {"zip.resourceId" : resource_id}
        ]
    }

    if sheet_id is not None:
        query['sheetId'] = sheet_id

    sheets = collections.get("resource").find(query,{
        "localRange" : 0,
        "hash" : 0,
        "file" : 0,
        "_id" : 0
    })

    response = []
    for sheet in sheets:
        # only send metadata attributes
        metadata = []
        repeats = []
        units = {}
        attributeRepeatFlag = False # proly have wrong layout
        if sheet.get('attributes') is not None:
            for attr in sheet.get('attributes'):
                if attr.get("type") != "metadata":
                    continue

                if attr.get("name") in metadata:
                    if attr.get("name") not in repeats:
                        repeats.append(attr.get("name"))
                    attributeRepeatFlag = True
                    continue

                metadata.append(attr.get("name"))

                if attr.get("units") is not None:
                    units[attr.get("name")] = attr.get("units")

        sheet['attributes'] = metadata
        sheet['units'] = units
        if attributeRepeatFlag:
            sheet['repeatAttributes'] = True
            sheet['repeats'] = repeats
        response.append(sheet)

    return response

def allUnits(package_id):
    query = {
        "package_id" : package_id
    }

    sheets = collections.get("resource").find(query,{
        "localRange" : 0,
        "hash" : 0,
        "file" : 0,
        "_id" : 0
    })

    units = {}
    for sheet in sheets:
        if sheet.get('attributes') is not None:
            for attr in sheet.get('attributes'):
                if attr.get("units") is not None and attr.get("units") != "":
                    units[attr.get("name")] = attr.get("units")

    return units

def isPushed(package_id):
    result = collections.get("search_package").find_one({"value.ecosis.package_id": package_id},{"value.ecosis.pushed": 1})

    if result is None:
        return result

    ecosis = result.get("value").get("ecosis")
    if ecosis is None:
        return ecosis

    return ecosis.get("pushed")