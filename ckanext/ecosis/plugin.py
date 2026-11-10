import json, os
import ckan.plugins as plugins
import ckan.plugins.toolkit as tk
import ckan.lib.base as base
from ckan.common import config, current_user
from ckan.logic.action.create import organization_member_create
from ckan.logic.action.delete import organization_member_delete
import ckan.logic as logic

from flask import Blueprint, make_response, send_from_directory, request, redirect
import ckanext.ecosis.lib.utils as utils

import ckanext.ecosis.datastore.query as query
from ckanext.ecosis.datastore import delete as deleteUtil
import ckanext.ecosis.controller.organization as orgController
import ckanext.ecosis.controller.package as pkgController
from ckanext.ecosis.controller.package.doi import handleDoiUpdate, validDoiUpdate, hasAppliedDoi, getDoiStatus, DOI_STATUS, applyDoi
import ckanext.ecosis.user_data.model as userDataModel
from ckanext.ecosis.controller import EcosisController

controller = EcosisController()

@tk.side_effect_free
def organization_member_create_wrapper(context, member_create):
    organization_member_create(context, member_create)
    orgController.notify_remotes(member_create.get('id'))

@tk.side_effect_free
def organization_member_delete_wrapper(context, member_delete):
    organization_member_delete(context, member_delete)
    orgController.notify_remotes(member_delete.get('id'))

class EcosisPlugin(plugins.SingletonPlugin,
        tk.DefaultDatasetForm):
    '''An example IDatasetForm CKAN plugin.

    Uses a tag vocabulary to add a custom metadata field to datasets.

    '''
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.ITemplateHelpers)
    # plugins.implements(plugins.IRoutes, inherit=True)
    plugins.implements(plugins.IOrganizationController)
    plugins.implements(plugins.IPackageController)
    plugins.implements(plugins.IResourceController)
    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IMiddleware)
    # plugins.implements(plugins.IDatasetForm)

    # map of ecosis required package property to a nice property label
    REQUIRED_FIELDS = {
      'license_id': { 'label': 'License', 'empty_value' : 'notspecified'}
    }

    # paths that must stay reachable by anonymous visitors so the login
    # flow itself works and so other services (eg the public ecosis.org
    # search app) can keep hitting the read-only API
    LOGIN_WALL_ALLOWED_PATH_PREFIXES = (
        '/base/',
        '/webassets/',
        '/fanstatic/',
        '/favicon.ico',
        '/api/',
        '/user/login',
        '/user/_logout',
        '/user/reset',
        '/ecosis/user/remoteLogin',
    )

    # dataset/resource read endpoints that stay public when the package
    # has an applied DOI, so minted DOIs keep resolving to a public page
    LOGIN_WALL_PUBLIC_DOI_ENDPOINTS = (
        'dataset.read',
        'dataset_resource.read',
        'dataset_resource.download',
        'resource.read',
        'resource.download',
    )

    def _require_login(self):
        """Flask before_request hook that redirects anonymous visitors to
        the login page, with exceptions for static assets, the login flow
        itself, the read-only API, and dataset/resource pages whose
        package has an applied DOI (which must stay publicly resolvable).
        """
        if not tk.asbool(config.get('ecosis.require_login', True)):
            return None

        path = request.path

        if path.startswith(self.LOGIN_WALL_ALLOWED_PATH_PREFIXES):
            return None

        if current_user.is_authenticated:
            return None

        endpoint = request.endpoint or ''
        if endpoint in self.LOGIN_WALL_PUBLIC_DOI_ENDPOINTS:
            package_id = (request.view_args or {}).get('id')
            if package_id:
                try:
                    if hasAppliedDoi(package_id):
                        return None
                except Exception:
                    pass

        came_from = path
        if request.query_string:
            came_from += '?' + request.query_string.decode('utf-8')

        # build with _external=True (uses ckan.site_url) rather than a bare
        # relative redirect: Werkzeug's Location-header autocorrection
        # otherwise rebuilds the URL from the request's Host header, which
        # behind the ckan-cache/queue proxy chain is the internal docker
        # service address (eg ckan:5000), not the public site URL
        login_url = tk.url_for('user.login', came_from=came_from, _external=True)
        return redirect(login_url)


    # IClick
    def get_commands(self):
        """Implemented for IClick Plugin
        
        register the 'ckan ecosis' CLI commands
        """
        # import click
        from ckanext.ecosis.user_data.paster import ecosis as ecosisCmd

        return [ecosisCmd]

    # add iauth functions
    def get_auth_functions(self):
        return {
          'package_update' : self.package_update_auth,
          'package_create' : self.package_create_auth,
          'package_delete' : self.package_delete_auth,
          'resource_delete' : self.resource_delete_auth,
          'resource_create' : self.resource_create_auth
        }

    def get_class_name(self, entity):
        """Helper for getting nice class name string
        required because some plugin methods overlap, need to sniff
        test which is calling
        """
        return entity.__class__.__name__ 

    def is_group(self, entity):
        return self.get_class_name(entity) == 'Group'

    def is_package(self, entity):
        return self.get_class_name(entity) == 'Package'

    def is_resource(self, entity):
        return self.get_class_name(entity) == 'Resource'

    def read(self, entity):
        """Implemented for IOrganizationController and IPackageController Plugins

        not used by the EcoSIS Plugin
        """
        pass

    def create(self, entity):
        """Implemented for IOrganizationController and IPackageController Plugins

        IOrganizationController: notify remotes of org update
        """
        if self.is_group(entity):
            orgController.notify_remotes(entity.id)

    def after_update(self, context, pkg_dict):
        if pkg_dict.get('type') == "dataset":    
          # if doi status changed to ACCEPTED, start DOI application process
          resp = handleDoiUpdate(context['before_package_update'], pkg_dict)

          doiStatus = getDoiStatus(pkg_dict)
          if doiStatus.get('status').get('value') == DOI_STATUS["ACCEPTED"]:
              applyDoi(pkg_dict)

          if resp.get('email') is not None:
              pkg_dict['doi_user_email'] = resp.get('email')
              pkg_dict['doi_user_name'] = resp.get('user')

    def before_create(self, context, resource):
        pass

    def after_create(self, context, pkg_dict):
        """Implemented for IPackageController"""
        if self.get_class_name(pkg_dict) == "dict": # safety check
            if pkg_dict.get('type') == "dataset":
              pkgController.after_create()
        return pkg_dict

    def before_index(self, pkg_dict):
        """Implemented for IPackageController"""
        return pkg_dict

    def edit(self, entity):
        pass
        # orgController.update(entity)

    @tk.auth_sysadmins_check
    def package_create_auth(self, context, data_dict=None):
        """Check for required fields
        """

        # hack.  how do we know if this is a view check or not?!
        if data_dict is not None and len(data_dict) == 0:
          return {'success': True}

        if data_dict is not None:
            for field, props in self.REQUIRED_FIELDS.items():
              value = data_dict.get(field)
              if value == None or value == '' or value == props.get('empty_value'):
                return {
                  'success' : False,
                  'msg' : 'The %s field is required' % props.get('label')
              }
        
        return self.package_update_auth(context, data_dict)
    
    @tk.auth_sysadmins_check
    def package_update_auth(self, context, data_dict=None):
        """Check for DOI issues that should prevent saving. store old values
        to be used in the after_update() method so we know which DOI actions to
        preform
        """
        if data_dict is not None:
          # bypass flag for view elements to see if something should be displayed
          # DOI editing is not part of this, so we can ignore
          if data_dict.get('view_auth_check') != True and data_dict.get('id') is not None:
            cpkg = {}
            if  data_dict['id'] != '':
              cpkg = logic.get_action('package_show')(context, {'id': data_dict['id']})
            context['before_package_update'] = cpkg
            return validDoiUpdate(cpkg, data_dict)
        
        return {'success': True}

    @tk.auth_sysadmins_check
    def package_delete_auth(self, context, data_dict=None):
        """Check that a package can be deleted
        """
        if hasAppliedDoi(data_dict.get('id')):
          return {'success': False, 'message':'Cannot delete package with applied DOI'}

        return {'success': True}

    @tk.auth_sysadmins_check
    def resource_delete_auth(self, context, data_dict=None):
        """Check that a resource can be deleted
        """
        resource = logic.get_action('resource_show')(context, {'id': data_dict['id']})
        if hasAppliedDoi(resource.get('package_id')):
          return {'success': False, 'msg': 'Cannot delete resource of package with applied DOI'}

        return {'success': True}

    @tk.auth_sysadmins_check
    def resource_create_auth(self, context, data_dict=None):
        """Check that a resource can be created
        """
        if hasAppliedDoi(data_dict.get('package_id')):
          return {'success': False, 'msg': 'Cannot create resource of package with applied DOI'}

        return {'success': True}

    def authz_add_role(self, object_role):
        pass

    def authz_remove_role(self, object_role):
        pass

    def before_delete(self, context, resource, resources):
      pass

    def delete(self, entity):
      pass

    def after_delete(self, context, pkg_dict):
      if self.is_group(pkg_dict):
        orgController.delete(pkg_dict)
      if self.is_package(pkg_dict):
        deleteUtil.package(pkg_dict.get('id'))

    def after_show(self, context, entity):
        return entity

    def before_show(self, resource_dict):
        pass

    def before_view(self, pkg_dict):
        return pkg_dict

    def before_search(self, search_params):
      return search_params

    def after_search(self, search_results, search_params):
      return search_results

    # we need to listen for org create/update/delete events and notify remotes
    def get_actions(self):
        return {
            'organization_member_create' : organization_member_create_wrapper,
            'organization_member_delete': organization_member_delete_wrapper
        }


    def update_config(self, config):
        # Add this plugin's templates dir to CKAN's extra_template_paths, so
        # that CKAN will use this plugin's custom templates.
        tk.add_template_directory(config, 'templates')
        tk.add_resource('public/fanstatic', 'ecosis')
        userDataModel.define_table()

    # set helpers for ecosis templates
    def get_helpers(self):
        # Example:
        #return { 'to_json' : 'self.to_json' }
        return {
            'get_google_analytics_code' : self.get_google_analytics_code,
            'get_search_url' : self.get_search_url,
            'get_last_pushed_str' : self.get_last_pushed_str,
            'pushed_to_search' :  self.pushed_to_search,
            'get_admin_email' : self.get_admin_email
        }

    def get_admin_email(self):
        return config.get('ecosis.admin_email', '')

    def pushed_to_search(self, package_id):
        result = query.isPushed(package_id)
        if result is None:
            return False
        return True

    def get_last_pushed_str(self, package_id):
        result = query.isPushed(package_id)
        if result is None:
            return None
        try:
            return result.strftime("%Y-%m-%d %H:%M")
        except:
            return result

    def get_search_url(self):
        return config.get('ecosis.search_url','')

    def get_google_analytics_code(self):
        return config.get('ckan.google_analytics_code', '')


    def is_fallback(self):
        # Return True to register this plugin as the default handler for
        # spectral types not handled by any other IDatasetForm plugin.
        return False

    def make_middleware(self, app, config):
      # REDIRECTS
      editor_redirects = Blueprint(u'editor_redirects', __name__, url_prefix=u'/')
      
      # route all resource edit screens to main ecosis dataset editor
      editor_redirects.add_url_rule(u'/dataset/new', methods=[u'GET'],
          view_func=controller.createPackageRedirect)

      # TODO: the below don't actually work and are currently handled by the template.  badness.
      editor_redirects.add_url_rule(u'/dataset/resources/<package_id>', methods=[u'GET'],
          view_func=controller.editPackageRedirect)
      editor_redirects.add_url_rule(u'/dataset/edit/<package_id>', methods=[u'GET'],
          view_func=controller.editPackageRedirect)
      editor_redirects.add_url_rule(u'/dataset/new_resource/<package_id>', methods=[u'GET'],
          view_func=controller.editPackageRedirect)
      editor_redirects.add_url_rule(u'/dataset/<package_id>/resource_edit/<resource_id>', methods=[u'GET'],
          view_func=controller.editPackageRedirect)
      editor_redirects.add_url_rule(u'/dataset/new_resource/<package_id>', methods=[u'GET'],
          view_func=controller.editPackageRedirectWResource)

      # Serve index.html static paths
      root_dir = os.environ.get('CKAN_HOME', os.getcwd())
      if not os.path.exists(root_dir):
        raise Exception('CKAN_HOME not found: %s.  Unable to load static assests' % root_dir)
      editor_redirects.add_url_rule(u'/import', methods=[u'GET'],
          endpoint="spectra-importer",
          strict_slashes=False,
          view_func=lambda: send_from_directory(os.path.join(root_dir, 'ckanext-ecosis/spectra-importer/dist/import'), 'index.html'))
      editor_redirects.add_url_rule(u'/doi-admin', methods=[u'GET'],
          endpoint="doi-admin",
          strict_slashes=False,
          view_func=lambda: send_from_directory(os.path.join(root_dir, 'ckanext-ecosis/doi-admin/dist/doi-admin'), 'index.html'))
      # print(os.path.join(root_dir, 'ckanext-ecosis/spectra-importer/dist/import'), 'index.html')

      app.register_blueprint(editor_redirects)

      # API
      api = Blueprint(u'ecosis', __name__, url_prefix=u'/ecosis')

      # ecosis - admin
      api.add_url_rule(u'/admin/rebuildIndex', methods=[u'GET'],
          view_func=controller.rebuildIndex)
      api.add_url_rule(u'/admin/clean', methods=[u'GET'],
          view_func=controller.clean)
      api.add_url_rule(u'/admin/verifyWorkspace', methods=[u'GET'],
          view_func=controller.verifyWorkspace)

      # ecosis - root
      api.add_url_rule(u'/user/get', methods=[u'GET'],
          view_func=controller.userInfo)
      api.add_url_rule(u'/gitInfo', methods=[u'GET'],
          view_func=controller.gitInfo)
      api.add_url_rule(u'/user/remoteLogin', methods=[u'POST'],
          view_func=controller.remoteLogin)
      api.add_url_rule(u'/user/githubInfo', methods=[u'POST'],
          view_func=controller.setGithubInfo)

      # ecosis - workspace
      api.add_url_rule(u'/workspace/prepare', methods=[u'GET'],
          view_func=controller.prepareWorkspace)
      api.add_url_rule(u'/workspace/get', methods=[u'GET'],
          view_func=controller.getWorkspace)
      api.add_url_rule(u'/workspace/push', methods=[u'GET'],
          view_func=controller.pushToSearch)

      # ecosis - package
      api.add_url_rule(u'/package/getTemplate', methods=[u'GET'],
          view_func=controller.getTemplate)
      api.add_url_rule(u'/package/updateLinkedResources', methods=[u'POST'],
          view_func=controller.updateLinkedResources)
      api.add_url_rule(u'/package/import', methods=[u'GET'],
          view_func=controller.importPackage)

      # ecosis - spectra
      api.add_url_rule(u'/spectra/suggestOverview', methods=[u'GET', 'POST'],
          view_func=controller.topOverview)
      api.add_url_rule(u'/spectra/get', methods=[u'GET'],
          view_func=controller.getSpectra)
      api.add_url_rule(u'/spectra/gcmd', methods=[u'GET'],
          view_func=controller.gcmdSuggest)
      api.add_url_rule(u'/spectra/suggest', methods=[u'GET'],
          view_func=controller.topSuggest)

      # ecosis - resource
      api.add_url_rule(u'/resource/getSpectraCount', methods=[u'GET'],
          view_func=controller.getSpectraCount)
      api.add_url_rule(u'/resource/process', methods=[u'POST'],
          view_func=controller.processResource)
      api.add_url_rule(u'/resource/getMetadataInfo', methods=[u'GET'],
          view_func=controller.getMetadataInfo)
      api.add_url_rule(u'/resource/byname/<package_id>/<resource_name>', methods=[u'GET'],
          view_func=controller.getResourceByName)
      api.add_url_rule(u'/resource/deleteMany', methods=[u'POST'],
          view_func=controller.deleteResources)
      api.add_url_rule(u'/resource/getMetadataChunk', methods=[u'GET'],
          view_func=controller.getMetadataChunk)
      api.add_url_rule(u'/resource/get', methods=[u'GET'],
          view_func=controller.getResource)

      # ecosis - admin doi
      # map.connect('doi_query', '/ecosis/admin/doi/query', controller=controller, action='doiQuery')
      # map.connect('doi_clear', '/ecosis/admin/doi/clear', controller=controller, action='clearDoi')      
      # ecosis - admin doi
      api.add_url_rule(u'/admin/doi/query', methods=[u'GET'],
          view_func=controller.doiQuery)
      api.add_url_rule(u'/admin/doi/clear', methods=[u'GET'],
          view_func=controller.clearDoi)
      # map.connect('getAllGithubInfo', '/ecosis/admin/github/sync', controller=controller, action='getAllGithubInfo')     
      api.add_url_rule(u'/admin/github/sync', methods=[u'GET'],
          view_func=controller.getAllGithubInfo)

      app.register_blueprint(api)

      # require login for the whole site, see _require_login() for exceptions
      app.before_request(self._require_login)

      return app

    def make_error_log_middleware(self, app, config):
      return app


    # def before_map(self, map):
    #     self.set_map(map)
    #     return map

    # override?
    # def set_map(self, map):

    #     # The 'new' way
    #     controller = 'ckanext.ecosis.controller:EcosisController'

    #     # Standard CKAN overrides
    #     # map.connect('create_package_3', '/api/3/action/package_create', controller=controller, action='createPackage')
    #     # map.connect('create_package', '/api/action/package_create', controller=controller, action='createPackage')
    #     # map.connect('update_package_3', '/api/3/action/package_update', controller=controller, action='updatePackage')
    #     # map.connect('update_package', '/api/action/package_update', controller=controller, action='updatePackage')
    #     # map.connect('delete_package_3', '/api/3/action/package_delete', controller=controller, action='deletePackage')
        # # map.connect('delete_package', '/api/action/package_delete', controller=controller, action='deletePackage')
        # # map.connect('delete_resource_3', '/api/3/action/resource_delete', controller=controller, action='deleteResource')
        # # map.connect('delete_resource', '/api/action/resource_delete', controller=controller, action='deleteResource')
        # # map.connect('create_resource_3', '/api/3/action/resource_create', controller=controller, action='createResource')
        # # map.connect('create_resource', '/api/action/resource_create', controller=controller, action='createResource')

        # # ecosis - admin
        # map.connect('rebuild_usda_collection', '/ecosis/admin/rebuildUSDA', controller=controller, action='rebuildUSDACollection')
        # map.connect('clean_tests', '/ecosis/admin/cleanTests', controller=controller, action='cleanTests')
        # map.connect('upgrade', '/ecosis/admin/upgrade', controller=controller, action='upgrade')
        # map.connect('fixUnits', '/ecosis/admin/fixUnits', controller=controller, action='fixUnits')
        # map.connect('fixCitations', '/ecosis/admin/fixCitations', controller=controller, action='fixCitations')

        # # ecosis - admin doi
        # map.connect('getAllGithubInfo', '/ecosis/admin/github/sync', controller=controller, action='getAllGithubInfo')

        # # ecosis - package
        # map.connect('setPrivate', '/ecosis/package/setPrivate', controller=controller, action='setPrivate')

        # # ecosis - workspace

        # # custom pages
        # # map.connect('remotelogin', '/user/remotelogin', controller='ckanext.ecosis.plugin:StaticPageController', action='remotelogin')


        # return map

    def package_types(self):
        # This plugin doesn't handle any special package types, it just
        # registers itself as the default (above).
        return []

    def _modify_package_schema(self, schema):
        # Add custom access_level as extra field
        return schema

    def create_package_schema(self):
        schema = super(EcosisPlugin, self).create_package_schema()
        schema = self._modify_package_schema(schema)
        return schema

    def update_package_schema(self):
        schema = super(EcosisPlugin, self).update_package_schema()
        schema = self._modify_package_schema(schema)
        return schema

    def show_package_schema(self):
        schema = super(EcosisPlugin, self).show_package_schema()

        return schema

    # check_data_dict() is deprecated, this method is only here to test that
    # legacy support for the deprecated method works.
    def check_data_dict(self, data_dict, schema=None):
        return

    def setup_template_variables(self, context, data_dict):
        return super(EcosisPlugin, self).setup_template_variables(
                context, data_dict)

    def new_template(self):
        return super(EcosisPlugin, self).new_template()

    def read_template(self):
        return super(EcosisPlugin, self).read_template()

    def edit_template(self):
        return super(EcosisPlugin, self).edit_template()

    def comments_template(self):
        return super(EcosisPlugin, self).comments_template()

    def search_template(self):
        return super(EcosisPlugin, self).search_template()

    def history_template(self):
        return super(EcosisPlugin, self).history_template()

    def package_form(self):
        return super(EcosisPlugin, self).package_form()

    ###
    # IPackageController
    ###
