# actually process the datasheet with given workspace config

import xlrd, csv, re, json

from ckanext.esis.lib.join import SheetJoin
from pylons import config

# helpers from ./lib
joinlib = SheetJoin()

class ProcessWorkspace:

    workspaceCollection = None
    workspaceDir = ""

    def __init__(self):
        self.workspaceDir = config._process_configs[1]['ecosis.workspace.root']

    def setCollection(self, collection):
        self.workspaceCollection = collection

    def resources(self, resources, workspacePackage, ckanPackage, rootDir):
        # resourceInfo is the parsed resource information from setup.resources

        # break up into 2 groups, first is metadata, this needs to be parsed first,
        # second is data.  Pass the metadata group along with each data resource
        # so a join can be preformed
        for resourceInfo in resources:
            ckanResource =  self._getById(ckanPackage['resources'], resourceInfo['id'])
            self._processResource(ckanResource, resourceInfo['datasheets'], workspacePackage, metadataRun=True)

        # now do non-metadata run
        metadataSheets = self._getMetadataSheets(resources, workspacePackage)
        for resourceInfo in resources:
            ckanResource =  self._getById(ckanPackage['resources'], resourceInfo['id'])
            self._processResource(ckanResource, resourceInfo['datasheets'], workspacePackage, metadataSheets)

        # finally save all json files with current state
        for resourceInfo in resources:
            if resourceInfo.get('changes') == True:
                location = resourceInfo['location']
                del resourceInfo['location']
                del resourceInfo['changes']
                self._saveJson(location, resourceInfo)


    # process any user changes to resource
    def _processResource(self, ckanResource, datasheets, workspacePackage, metadataSheets=[], metadataRun=False):
        workspaceResource = self._getById(workspacePackage['resources'], ckanResource['id'])
        if workspaceResource == None:
            workspaceResource = {}

        if workspaceResource.get('ignore') == True:
            return None

        for datasheet in datasheets:
            self._processFile(datasheet, datasheets, ckanResource['id'], workspaceResource, metadataSheets, metadataRun)


    # actually parse file information object
    # must have name and location
    def _processFile(self, datasheet, datasheets, rid, workspaceResource, metadataSheets, metadataRun):
        ext = self._getFileExtension(datasheet['name'])

        if workspaceResource == None:
            workspaceResource = {}

        # at this point, check type and bail out if we are on a metadata and this is not metadata or vice versa
        # we have to wait till we open up and look at an excel file before we can make this decision, thus it's in
        # two places
        if ext == "csv" or ext == "spectra" or ext == "tsv":
            if not self._parseOnThisRun(datasheet, workspaceResource, metadataRun):
                return

        data = []
        if ext == "csv":
            self._processCsv(datasheet, workspaceResource, metadataSheets)
        elif ext == "tsv" or ext == "spectra":
            self._processTsv(datasheet, workspaceResource, metadataSheets)
        elif ext == "xlsx" or ext == "xls":
            # an excel file is going to actually expand to several files
            # so pass the files array so the placeholder can be removed
            # and the new 'sheet' files can be inserted
            self._processExcel(datasheet, datasheets, rid, workspaceResource, metadataSheets, metadataRun)



    # given a data array [[]], process based on config
    #  - type row = attribute names are in the first row
    #  - type col = attribute names are in the first col
    #
    # layout - row || column
    # sheetInfo - the sheet response object
    # TODO: this needs to have access to all metadata file information,
    #       Should be able to set match counts
    def _processSheetArray(self, data, sheetInfo, resourceConfig, metadataSheets):
        ranges = self._getDataRanges(data)

        # get config for sheet if on exists
        sheetConfig = self._getById(resourceConfig.get('datasheets'), sheetInfo['id'])

        # how should be parse this file?
        layout = 'row'
        if sheetConfig != None:
            if sheetConfig.get('type') == 'metadata':
                layout = 'row'
            elif 'layout' in sheetConfig:
                layout = sheetConfig['layout']

        sheetInfo['layout'] = layout

        localRange = {}
        globalRange = None
        if len(ranges) == 1:
            localRange = ranges[0]
        elif len(ranges) == 2:
            globalRange = ranges[0]
            localRange = ranges[1]

        # no local data
        if localRange['start'] == localRange['end']:
            return

        # find all the attribute types based on layout
        attrTypes = []
        if layout == "row":
            for i in range(0, len(data[localRange['start']])):
                info = self._parseAttrType(data[localRange['start']][i], [localRange['start'], i],  "local")
                attrTypes.append(info)
        else:
            names = []
            for i in range(localRange['start'], localRange['end']):
                info = self._parseAttrType(data[i][0], [i,0], "local")
                attrTypes.append(info)
        sheetInfo['attributes'] = attrTypes

        if sheetConfig != None and sheetConfig.get('metadata') == True:
            joinlib.processMetadataSheet(data, sheetConfig, sheetInfo)
        else:
            # now find the spectra count based on layout
            if layout == "row":
                sheetInfo['spectra_count'] = localRange['end'] - localRange['start']
            else:
                i = 0
                for i in reversed(range(len(data[localRange['start']]))):
                    if data[localRange['start']] != None or data[localRange['start']] != '':
                        break
                sheetInfo['spectra_count'] = i

            # finally find match counts for metadata joins
            joinlib.matchMetadataSheets(data, localRange, layout, sheetInfo, metadataSheets)


    # is a row array empty
    def _isEmptyRow(self, row):
        if len(row) == 0:
            return True

        for i in range(0, len(row)):
            if row[i] != "" or row[i] != None:
                return False

        return True

    # src:
    #  https://github.com/python-excel/xlrd
    # help:
    #  http://www.youlikeprogramming.com/2012/03/examples-reading-excel-xls-documents-using-pythons-xlrd/
    #  https://secure.simplistix.co.uk/svn/xlrd/trunk/xlrd/doc/xlrd.html?p=4966
    def _processExcel(self, datasheet, datasheets, rid, resourceConfig, metadataSheets, metadataRun):
        # remove the place holder, the sheets will be the actual 'files'

        fullPath = "%s%s%s" % (self.workspaceDir, datasheet['location'], datasheet['name'])

        try:
            workbook = xlrd.open_workbook(fullPath)
            sheets = workbook.sheet_names()

            for sheet in sheets:
                sheetInfo = {
                    "id" : self._getFileId(rid, datasheet['location'], "%s-%s" %  (datasheet['name'], sheet) ),
                    "sheet" : sheet,
                    "name" : datasheet['name'],
                    "location" : datasheet['location'],
                }

                # are we on the metadata run and should we be parsing this sheet?
                if not self._parseOnThisRun(sheetInfo, resourceConfig, metadataRun):
                    continue

                data = self._getWorksheetData(workbook.sheet_by_name(sheet))
                self._processSheetArray(data, layout, sheetInfo, resourceConfig, metadataSheets)
                datasheets.append(sheetInfo)

        #TODO: how do we really want to handle this?
        except Exception as e:
            datasheet['error'] = True
            datasheet['message'] = e

        if not 'error' in datasheet:
            datasheets.remove(datasheet)

    def _getWorksheetData(self, sheet):
        data = []
        for i in range(sheet.nrows):
            row = []
            for j in range(sheet.ncols):
                row.append(str(sheet.cell_value(i, j)))
            data.append(row)
        return data


    def _processCsv(self, datasheet, resourceConfig, metadataSheets):
        self._processSeperatorFile(datasheet, ",", resourceConfig, metadataSheets)

    def _processTsv(self, datasheet, resourceConfig, metadataSheets):
        self._processSeperatorFile(datasheet, "\t", resourceConfig, metadataSheets)

    # parse a csv or tsv file location into array
    def _processSeperatorFile(self, datasheet, separator, resourceConfig, metadataSheets):
        with open("%s%s%s" % (self.workspaceDir, datasheet['location'], datasheet['name']), 'rb') as csvfile:
            reader = csv.reader(csvfile, delimiter=separator, quotechar='"')
            data = []
            for row in reader:
                data.append(row)
            csvfile.close()

            self._processSheetArray(data, datasheet, resourceConfig, metadataSheets)

    # given information about the current datasheet, the config and if we are on the metadata run,
    # should we parse this datasheet on this run or not.  Remember, there are always two runs.  First,
    # one for metadata, second, one for data
    def _parseOnThisRun(self, datasheet, resourceConfig, metadataRun):
        sheetConfig = self._getById(resourceConfig.get('datasheets'), datasheet['id'])

        if sheetConfig == None and metadataRun:
            return False
        elif sheetConfig == None:
            return True

        if sheetConfig.get('metadata') == True:
            if metadataRun:
                return True
            else:
                return False

        if metadataRun:
            return False
        return True

    # parse out the attribute information from the attribute information
    # TODO: check for units and attribute data type
    def _parseAttrType(self, name, pos, attributeLocality, isData=False):
        original = name

        # clean up string
        name = name.strip()

        # parse out units
        # TODO

        type = "metadata"
        if re.match(r"^-?\d+\.?\d*", name) or re.match(r"^-?\d*\.\d+", name):
            type = "wavelength"
        elif re.match(r".*__d($|\s)", name) or isData:
            name = re.sub(r".*__d($|\s)", "", name)
            type = "data"

        attr = {
            "type" : type,
            "name" : name,
            "units" : "",
            "pos" : pos,
            "scope" : attributeLocality,
        }
        if original != name:
            attr["original"] = original

        return attr

    # find the table ranges (is there one or two)
    def _getDataRanges(self, data):
        ranges = []
        r = {
            "start" : 0,
            "end" : 0
        }
        started = False

        i = 0
        for i in range(0, len(data)):
            if self._isEmptyRow(data[i]):
                if started:
                    r['end'] = i
                    ranges.push(r)
                    if len(ranges) == 2:
                        break
                    else:
                        r = {"start":0, "stop":0}
                else:
                    continue

            if not started:
                r['start'] = i
                started = True

        if started and len(ranges) < 2:
            r['end'] = i
            ranges.append(r)
        elif not started and len(ranges) == 0:
            ranges.append(r)

        return ranges

    def _getMetadataSheets(self, resources, workspacePackage):
        sheets = []
        for workspaceResource in workspacePackage['resources']:
            r = self._getById(resources, workspaceResource['id'])
            for sheet in workspaceResource['datasheets']:
                if sheet.get('metadata') == True:
                    ds = self._getById(r['datasheets'], sheet['id'])
                    ds['metadata'] = True
                    sheets.append({
                        'config': sheet,
                        'datasheet' : ds
                    })

        return sheets

    def _saveJson(self, file, data):
        f = open(file, 'w')
        json.dump(data, f)
        f.close()

    def _getById(self, arr, id):
        if arr == None:
            return None

        for obj in arr:
            if obj.get('id') == id:
                return obj
        return None

    # get the extension from a filename
    def _getFileExtension(self, filename):
         return re.sub(r".*\.", "", filename)

