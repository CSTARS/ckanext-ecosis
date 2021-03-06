import json
import os

import pylons.config as config

import ckan.lib.uploader as uploader
from ckan.controllers.package import PackageController
from ckanext.ecosis.controller import git, admin, organization, package, resource, spectra, user
from ckanext.ecosis.controller import workspace as workspaceController
from ckanext.ecosis.lib.utils import handleError
from ckanext.ecosis import datastore
from ckanext.ecosis.datastore.mongo import collections

usdaApiUrl = 'http://plants.usda.gov/java/AdvancedSearchServlet?symbol=&dsp_vernacular=on&dsp_category=on&dsp_genus=on&dsp_family=on&Synonyms=all&viewby=sciname&download=on'

path = os.path.dirname(__file__)
schema = os.path.join(path, "../../../spectra-importer/utils/metadata/schema.json")

pgConnStr = config.get("sqlalchemy.url")

with open(schema) as schema_file:
    schema = json.load(schema_file)

upload = uploader.ResourceUpload({})

datastore.init(schema, collections, pgConnStr, config.get("ecosis.search_url"), upload, config.get("ecosis.workspace.root"))
package.init(collections, pgConnStr)
organization.init(collections)

class EcosisController(PackageController):

    def createPackage(self):
        try:
            return package.create()
        except Exception as e:
            return handleError(e)

    def deletePackage(self):
        try:
            return package.delete()
        except Exception as e:
            return handleError(e)

    def updatePackage(self):
        try:
            return package.update()
        except Exception as e:
            return handleError(e)

    def cleanTests(self):
        try:
            return admin.cleanTests()
        except Exception as e:
            return handleError(e)

    def clean(self):
        try:
            return admin.clean(collections)
        except Exception as e:
            return handleError(e)

    def setPrivate(self):
        try:
            return package.setPrivate()
        except Exception as e:
            return handleError(e)

    def updateLinkedResources(self):
        try:
            return package.updateLinkedResources()
        except Exception as e:
            return handleError(e)

    def getTemplate(self):
        try:
            return package.getTemplate()
        except Exception as e:
            return handleError(e)

    def createResource(self):
        try:
            return resource.create()
        except Exception as e:
            return handleError(e)

    def deleteResource(self):
        try:
            return resource.delete()
        except Exception as e:
            return handleError(e)

    def deleteResources(self):
        try:
            return resource.deleteMany()
        except Exception as e:
            return handleError(e)

    def rebuildIndex(self):
        try:
            return admin.rebuildIndex(collections)
        except Exception as e:
            return handleError(e)

    def upgrade(self):
        try:
            return admin.upgrade()
        except Exception as e:
            return handleError(e)

    def fixUnits(self):
        try:
            return admin.fixUnits()
        except Exception as e:
            return handleError(e)

    def fixCitations(self):
        try:
            return admin.fixCitationText()
        except Exception as e:
            return handleError(e)

    def doiQuery(self):
        try:
            return package.doi.doiQuery()
        except Exception as e:
            return handleError(e)

    def clearDoi(self):
        try:
            return package.doi.clearDoi()
        except Exception as e:
            return handleError(e)

    # TODO: verify ok to remove
    # def doiUpdateStatus(self):
    #     try:
    #         return package.doi.doiUpdateStatus()
    #     except Exception as e:
    #         return handleError(e)

    def verifyWorkspace(self):
        try:
            return admin.verifyWorkspace(collections)
        except Exception as e:
            return handleError(e)

    def gitInfo(self):
        try:
            return git.info()
        except Exception as e:
            return handleError(e)

    def userInfo(self):
        try:
            return user.info()
        except Exception as e:
            return handleError(e)

    def remoteLogin(self):
        try:
            return user.remote_login()
        except Exception as e:
            return handleError(e)

    def setGithubInfo(self):
        try:
            return user.set_github_info()
        except Exception as e:
            return handleError(e)

    def getAllGithubInfo(self):
        try:
            return user.get_all_github_info()
        except Exception as e:
            return handleError(e)

    def createPackageRedirect(self):
        package.createPackageRedirect()

    def editPackageRedirect(self, id):
        package.editPackageRedirect(id)

    def rebuildUSDACollection(self):
        try:
            return admin.rebuildUSDACollection(collections, usdaApiUrl)
        except Exception as e:
            return handleError(e)

    def gcmdSuggest(self):
        try:
            return spectra.suggestGCMD()
        except Exception as e:
            return handleError(e)

    def topSuggest(self):
        try:
            return spectra.suggestAttributeName()
        except Exception as e:
            return handleError(e)

    def topOverview(self):
        try:
            return spectra.suggestOverview()
        except Exception as e:
            return handleError(e)

    def prepareWorkspace(self):
        try:
            return workspaceController.prepare()
        except Exception as e:
            return handleError(e)

    def cleanWorkspace(self):
        try:
            return workspaceController.clean()
        except Exception as e:
            return handleError(e)

    def getWorkspace(self):
        try:
            return workspaceController.get()
        except Exception as e:
            return handleError(e)

    def processResource(self):
        try:
            return resource.process()
        except Exception as e:
            return handleError(e)

    def getResource(self):
        try:
            return resource.get()
        except Exception as e:
            return handleError(e)

    def getResourceByName(self, package_id, resource_name):
        try:
            return resource.getByName(package_id, resource_name)
        except Exception as e:
            return handleError(e)

    def setPackageOptions(self):
        try:
            return package.setOptions()
        except Exception as e:
            return handleError(e)

    def getSpectra(self):
        try:
            return spectra.get()
        except Exception as e:
            return handleError(e)

    def getSpectraCount(self):
        try:
            return resource.getSpectraCount()
        except Exception as e:
            return handleError(e)

    def getMetadataChunk(self):
        try:
            return resource.getMetadataChunk()
        except Exception as e:
            return handleError(e)

    def getMetadataInfo(self):
        try:
            return resource.getMetadataInfo()
        except Exception as e:
            return handleError(e)

    def pushToSearch(self):
        try:
            return workspaceController.pushToSearch()
        except Exception as e:
            return handleError(e)