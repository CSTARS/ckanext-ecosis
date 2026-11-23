# from ckan.common import response, request
from ckan.common import request
import ckan.logic as logic
import json, jwt, re
from ckan.common import config
import ckan.lib.authenticator as authenticator
from ckanext.ecosis.lib.context import get_context
import ckanext.ecosis.user_data.model as githubInfoModel
import ckanext.ecosis.lib.utils as utils

from ckanext.ecosis.lib.auth import isAdmin

secret = config.get('ecosis.jwt.secret')

# get information about logged in user, including if they are logged in
def info():
    context = get_context()
    username = context.get('user')

    if len(username) == 0:
        return {"loggedIn": False}

    # see line 604 of ckan/logic/action/get about params for this method
    orgs = logic.get_action('organization_list_for_user')(context,{"permission": "create_dataset"})

    user = {
        "loggedIn": True,
        "username": username,
        "organizations" : orgs
    }

    githubInfo = githubInfoModel.get(username)
    if githubInfo is not None:
        user['githubUsername'] = githubInfo.github_username
        # user['githubAccessToken'] = githubInfo.github_access_token

    if isAdmin():
        user['isAdmin'] = True

    return user


def remote_login():
    token = request.form.get('token')
    token = jwt.decode(token, secret, algorithms=['HS256'])

    username = token.get('username');
    password = token.get('password');


    if username is None or password is None:
        return json.dumps({"loggedIn": False})


    identity = {
        'login' : username,
        'password' : password
    }

    user = authenticator.ckan_authenticator(identity)

    if user == None:
        return json.dumps({
            "loggedIn": False,
            "message": "invalid username or password",
        })

    return create_remote_login_response(user)

def create_remote_login_response(user):
    context = get_context()

    # see line 604 of ckan/logic/action/get about params for this method
    # orgs = logic.get_action('organization_list_for_user')(context,{"permission": "create_dataset"})

    # user = logic.get_action('user_show')(context, {'id':user.id})
    is_admin = user.get('sysadmin')

    user = {
        "loggedIn" : True,
        "username": user.name,
        "fullname": user.fullname,
        "email" : user.email,
        "id" : user.id,
        "state" : user.state,
        "github" : {}
        #"organizations": orgs
    }

    if is_admin:
        user['admin'] = True

    githubInfo = githubInfoModel.get(user['username'])
    if githubInfo is not None:
        user['github']['username'] = githubInfo.github_username
        user['github']['accessToken'] = githubInfo.github_access_token
        if githubInfo.github_data is not None:
            user['github']['data'] = json.loads(githubInfo.github_data)

    user['token'] = jwt.encode({
        'username': user['username'],
        'admin' : is_admin
    }, secret, algorithm='HS256')

    return user

# TODO: implementing JWT support is kinda a can of worms.
# will work as a workaround hack for now...
def set_github_info():
    params = request.get_json()
    token = request.headers.get('authorization')
    if not token:
        raise Exception('No jwt token provided')

    token = re.sub(r"Bearer ", "", token)
    token = jwt.decode(token, secret, algorithms=['HS256'])
    user_id = token.get("username")

    if not user_id:
        raise Exception('Jwt token did not provide user id')

    github_username = params.get('username')
    github_access_token = params.get('accessToken')
    github_data = params.get('data')

    githubInfoModel.update(user_id, github_username, github_access_token, github_data)
    return info()

def get_all_github_info():
    token = request.headers.get('authorization')
    if not token:
        raise Exception('No jwt token provided')

    token = re.sub(r"Bearer ", "", token)
    jwt.decode(token, secret, algorithms=['HS256'])

    githubInfo = githubInfoModel.getAll()
    results = []
    for user in githubInfo:
        results.append(user.as_dict())

    return json.dumps(results)

