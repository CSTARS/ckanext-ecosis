import re, time

from pymongo import MongoClient
from pylons import config
import dateutil.parser, json, inspect
from bson.code import Code
from bson.son import SON

client = MongoClient(config._process_configs[1]['esis.mongo.url'])
db = client[config._process_configs[1]['esis.mongo.db']]
spectraCollection = db[config._process_configs[1]['esis.mongo.spectra_collection']]
searchCollectionName = config._process_configs[1]['esis.mongo.search_collection']
searchCollection = db[searchCollectionName]

class Push:

    workspaceDir = ""
    setup = None
    process = None
    workspace = None
    joinlib = None
    mapreduce = {}
    localdir = ""

    def __init__(self):
        self.workspaceDir = "%s/workspace" % config._process_configs[1]['ecosis.workspace.root']

        self.localdir = re.sub(r'/\w*.pyc?', '', inspect.getfile(self.__class__))

        # read in mapreduce strings
        f = open('%s/../mapreduce/map.js' % self.localdir, 'r')
        self.mapreduce['map'] = f.read()
        f.close()

        f = open('%s/../mapreduce/reduce.js' % self.localdir, 'r')
        self.mapreduce['reduce'] = f.read()
        f.close()

        f = open('%s/../mapreduce/finalize.js' % self.localdir, 'r')
        self.mapreduce['finalize'] = f.read()
        f.close()

    def setCollection(self, collection):
        self.workspaceCollection = collection

    def setHelpers(self, workspace, setup, process, joinlib):
        self.workspace = workspace
        self.setup = setup
        self.process = process
        self.joinlib = joinlib

    def pushToSearch(self, package_id):
        runTime = time.time()
        # first clean out data
        searchCollection.remove({'value.ecosis.package_id':package_id})
        spectraCollection.remove({'ecosis.package_id': package_id})

        # next add resources one at a time and join spectra
        (workspacePackage, ckanPackage, rootDir, fresh) = self.setup.init(package_id)

        if ckanPackage['private'] == True:
            return {'error':True,'message':'This dataset is private'}

        resources = self.setup.resources(workspacePackage, ckanPackage, rootDir)
        self.process.resources(resources, workspacePackage, ckanPackage, rootDir)

        package = self.workspace._mergeWorkspace(resources, workspacePackage, ckanPackage, fresh)

        for resource in package['resources']:
            resource = self.workspace._getMergedResources(resource['id'], resources, workspacePackage, removeValues=False)
            spectra = self._getResourceSpectra(resource, self.workspaceDir, package, ckanPackage)

            # now insert into mongo
            if len(spectra) > 0:
                spectraCollection.insert(spectra)

        # finally run map reduce
        map = Code(self.mapreduce['map'])
        reduce = Code(self.mapreduce['reduce'])
        #spectraCollection.map_reduce(map, reduce, finalize=finalize, out=SON([("merge", searchCollectionName)]), query={"ecosis.package_id": pkg['id']})
        spectraCollection.map_reduce(map, reduce, searchCollectionName, query={"ecosis.package_id": package_id})

        return {'success': True, 'runTime': (time.time()-runTime)}

    # this is a lot like process._getSpectra() but will be more efficent for access and joining all of
    # a files spectra
    def _getResourceSpectra(self, resource, rootDir, package, ckanPackage):
        if 'datasheets' not in resource:
            return []

        if resource.get('ignore') == True:
            return []

        runTime = time.time()
        spectra = []
        # cache for metadata datasheets file name to 2-dim array of data
        # so we don't need to keep opening and closing the files
        metadataCache = {}

        for datasheet in resource['datasheets']:
            if datasheet.get('ignore') == True or datasheet.get('metadata') == True:
                continue

            file = "%s%s%s" % (rootDir, datasheet['location'], datasheet['name'])
            data = self.process.getFile(file, datasheet)
            spectraList = []

            (layout, scope) = self.process.getLayout(datasheet)

            if layout == 'row':
                start = datasheet['localRange']['start']
                for j in range(start+1, datasheet['localRange']['end']):
                    sp = {}
                    for i in range(len(data[start])):
                        if data[start+j][i]:
                            sp[data[start][i]] = data[start+j][i]
                    spectraList.append(sp)
            else:
                start = datasheet['localRange']['start']
                for j in range(1, len(data[start])):
                    sp = {}
                    for i in range(start, datasheet['localRange']['stop']):
                        if data[i][j]:
                            sp[data[i][0]] = data[i][j]
                    spectraList.append(sp)

            for m in spectraList:
                m['datapoints'] = []

                # move wavelengths to datapoints array
                if "wavelengths" in package:
                    for attr in package["wavelengths"]:
                        if attr in m:
                            m['datapoints'].append({
                                "key" : attr,
                                "value" : m[attr]
                            })
                            del m[attr]

                # move data attributes to datapoints array
                if "attributes" in package:
                    for attr in package["attributes"]:
                        if attr in m and package["attributes"][attr]["type"] == "data":
                            m['datapoints'].append({
                                "key" : attr,
                                "value" : m[attr],
                                "units" : package["attributes"][attr]
                            })
                            del m[attr]

                # add global attributes if they exist
                if 'globalRange' in datasheet and len(data[0]) > 1:
                    for i in range(datasheet['globalRange']['start'], datasheet['globalRange']):
                        m[data[i][0]] = data[i][1]

                # join on many metadata sheets that matched
                for resource in package['resources']:
                    if 'datasheets' in resource:
                        for sheet in resource['datasheets']:
                            if sheet.get('metadata') == True:
                                if 'matches' in sheet and datasheet['id'] in sheet['matches']:
                                    metadatafile = "%s%s%s" % (rootDir, sheet['location'], sheet['name'])
                                    data = None

                                    if metadatafile in metadataCache:
                                        data = metadataCache[metadatafile]
                                    else:
                                        data = self.process.getFile(metadatafile, sheet)
                                        metadataCache[metadatafile] = data

                                    self.joinlib.joinOnSpectra(datasheet, m, sheet, data)

                # copy any mapped attributes
                if "attributeMap" in package:
                    for key, value in package["attributeMap"].iteritems():
                        if value in m:
                            m[key] = m[value]

                # TODO: Look up USDA Plant Codes


                # finally, set ckan dataset info, as well as specific info on, sort, geolocation
                self._addEcosisNamespace(m, ckanPackage, resource, datasheet['id'])

                if 'datasetAttributes' in package:
                    attrInfo = package.get('datasetAttributes')
                    sort = attrInfo.get('sort_on')
                    type = attrInfo.get('sort_type')
                    if sort != None and sort in m:
                        if type == 'datetime':
                            m['ecosis']['sort'] = dateutil.parser.parse(m[sort])
                        elif type == 'numberic':
                            m['ecosis']['sort'] = float(m[sort])
                        else:
                            m['ecosis']['sort'] = m[sort]

                    location = attrInfo.get('location')
                    if location != None and sort in location:
                        try:
                            m['ecosis']['location'] = json.loads(m[location])
                            del m[location]
                        except:
                            t = 1

                spectra.append(m)


        print " Push resource process time: %ss" % (time.time() - runTime)


        return spectra

    def _addEcosisNamespace(self, m, ckanPackage, resource, dsid):
        ecosis = {
            'push_time' : time.time(),
            'package_id': ckanPackage['id'],
            'package_name': ckanPackage['name'],
            'package_title': ckanPackage['title'],
            'resource_id' : resource['id'],
            'filename': resource['name'],
            'datasheet_id': dsid,
            'groups': []
        }

        if ckanPackage.get('organization') != None:
            ecosis['organization'] = ckanPackage['organization']['title']

        m['ecosis'] = ecosis

    def getUSDACommonName(self, codes):
        resp = {}
        #for code in codes:
            #item = usdaCollection.find_one({'Accepted Symbol': code.upper()},{'_id':0})
            #if item != None:
            #    resp[code] = item
            #else:
            #    resp[code] = {
            #        'error' : True,
            #        'message' : 'Unknown Code'
            #    }
        return resp
