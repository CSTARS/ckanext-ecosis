import logging
import datetime

from sqlalchemy import Table, Column, types, inspect
from ckan.model.meta import registry, metadata, Session
from ckan.model.domain_object import DomainObject
from ckan import model
from ckan.model.types import make_uuid

log = logging.getLogger(__name__)

# good references for editing tables
# https://github.com/ckan/ckanext-harvest/blob/master/ckanext/harvest/model/__init__.py
# https://github.com/stadt-karlsruhe/ckanext-extractor/blob/master/ckanext/extractor/model.py

source_table = None

def setup():
    if source_table is None:
        define_table()
        log.debug('User github table defined in memory')

    # CKAN 2.11+ (SQLAlchemy 2.0): metadata is no longer bound to the
    # engine, so table checks/creation need the engine passed explicitly
    engine = model.ensure_engine()
    db = inspect(engine)

    if not db.has_table(model.package_table.name):
        log.debug('User github table creation deferred')
        return

    if not db.has_table(source_table.name):
        source_table.create(engine)
        log.debug('User github table created')

    else:
        log.debug('Github table already exist')
        # Check if existing tables need to be updated
        # for migration

def get(user_id):
    q = Session.query(UserGithubInfo).\
        filter(UserGithubInfo.user_id == user_id)
    return q.first()

def getAll():
    q = Session.query(UserGithubInfo)
    return q.all()

def update(user_id, github_username, github_access_token, github_data):
    info = get(user_id)

    if info is None:
        info = UserGithubInfo()
        info.user_id = user_id

    info.github_username = github_username
    info.github_access_token = github_access_token
    info.github_data = github_data # string encoded JSON
    info.save()

def define_table():

    global source_table

    if source_table is None:
        source_table = Table('user_github_info', metadata,
            Column('id', types.UnicodeText, primary_key=True, default=make_uuid),
            Column('created', types.DateTime, default=datetime.datetime.utcnow),
            Column('user_id', types.UnicodeText, default=u''),
            Column('github_username', types.UnicodeText, default=u''),
            Column('github_access_token', types.UnicodeText, default=u''),
            Column('github_data', types.UnicodeText, default=u'')
        )
        # SQLAlchemy 2.0 removed orm.mapper(); use classical mapping via the registry
        registry.map_imperatively(UserGithubInfo, source_table)


class UserGithubInfo(DomainObject):
    '''Contains a users github user account for EcoSML
    '''
    pass