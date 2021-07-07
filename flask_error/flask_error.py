from    flask import current_app

import  copy
import  couchapy
import  flask

import  inspect
import  json
from    os import listdir
from    os.path import isfile, join, dirname


class FlaskApiError():
    def __init__(self, app=None, folders=[], files=[]):
        self.app = app

        self._definition_folders = [f"{dirname(__file__)}/errors"] + folders
        self._definition_files = files

        if app is not None:
            self.init_app(app)

    def _before_request(self):
        if hasattr(current_app, 'error') is False:
            current_app.error = self

    def init_app(self, app):
        [self.load_definitions(source) for source in self._definition_folders + self._definition_files]
        app.before_request(self._before_request)
        app.teardown_appcontext(self.teardown)

    def teardown(self, exception):
        pass

    def load_definitions(self, definition_resource):
        for file in [f for f in listdir(definition_resource) if isfile(join(definition_resource, f))]:
            with open(f"{definition_resource}/{file}") as error_definitions:
                errors = json.load(error_definitions)

                for error_key in errors:
                    if hasattr(self, error_key):
                        existing_error_key = getattr(self, error_key)
                        existing_error_key.update(errors[error_key])
                    else:
                        setattr(self, error_key, errors[error_key])

    def errors_exist(self, **kwargs):
        return flask.g.get('response_errors', None) is not None

    def register(self, error=None, **kwargs):
        includeFrameDetail = kwargs.get('includeFrame', False)
        callStackLimit = kwargs.get('frame_limit', 5)

        # don't raise on invalid arguments, instead report errors
        if error is not None and isinstance(error, dict) is False:
            self.register(self.CODING['999-000001'], includeFrame=True)
            self.abort_on_errors(status_code=500)

        if error is not None and isinstance(error, dict) is True:
            if 'id' not in error:
                self.register(self.CODING['999-000002'], includeFrame=True)
                self.abort_on_errors(status_code=500)

            if 'title' not in error:
                self.register(self.CODING['999-000003'], includeFrame=True)
                self.abort_on_errors(status_code=500)

            if 'detail' not in error:
                self.register(self.CODING['999-000004'], includeFrame=True)
                self.abort_on_errors(status_code=500)

            if 'meta' not in error:
                self.register(self.CODING['999-000005'], includeFrame=True)
                self.abort_on_errors(status_code=500)

        # if we are here, then the error argument is at least valid,
        # so carry on with the work to do...
        response_errors = flask.g.get('response_errors', None)

        if response_errors is None:
            response_errors = []
            flask.g.response_errors = response_errors

        if error is not None:
            error = copy.deepcopy(error)
            error['meta'] = {**error['meta'], **kwargs.get('meta', {})}
            error['meta']['containedAuthToken'] = flask.request.cookies.get('AuthSession', None) is not None
            error['meta']['url'] = flask.request.url

        # intentionally overwrite any error information passed as the
        # general default error even if error information was provided.
        if error is None or error['id'] == '000-000000':
            error = copy.deepcopy(self.GENERAL['000-000000'])
            includeFrameDetail = True

        if includeFrameDetail:
            error['meta']['stack'] = [{
                'filename': frameInfo.filename,
                'lineNumber': frameInfo.lineno,
                'function': frameInfo.function
            } for frameInfo in inspect.stack()[:callStackLimit]]

        response_errors.append(error)

        return len(response_errors)

    def register_couch_error(self, couch_result):
        if not isinstance(couch_result, couchapy.CouchError):
            self.register(self.CODING['999-000007'], includeFrame=True)

        if couch_result.reason == 'You are not allowed to access this db.':
            self.register(self.GENERAL['000-000003'])
        else:
            self.register(self.GENERAL['000-000002'], meta={'databaseError': couch_result.__dict__})

    def is_couch_error(self, response):
        return isinstance(response, couchapy.CouchError)

    def abort_on_errors(self, status_code=400):
        if flask.g.get('response_errors', None) is not None:
            flask.abort(flask.make_response(flask.jsonify({'errors': flask.g.get('response_errors')}), status_code))
