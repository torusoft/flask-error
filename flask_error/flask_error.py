import  copy
import  deprecation
from    flask import current_app, g, request, abort, jsonify, make_response
from    flask_torusoft_api_core import __version__
import  inspect
import  json
from    os import listdir
from    os.path import isfile, join, dirname


class FlaskApiError():
    def __init__(self, app=None, folders=[], files=[], db_error_type=None):
        self.app = app
        self._db_error_type = db_error_type
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
        return g.get('response_errors', None) is not None

    def register(self, error=None, **kwargs):
        includeFrameDetail = kwargs.get('include_frame', kwargs.get('includeFrame', False))
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
        response_errors = g.get('response_errors', None)

        if response_errors is None:
            response_errors = []
            g.response_errors = response_errors

        if error is not None:
            error = copy.deepcopy(error)
            error['meta'] = {**error['meta'], **kwargs.get('meta', {})}
            error['meta']['containedAuthToken'] = request.cookies.get('AuthSession', None) is not None
            error['meta']['url'] = request.url

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

    def register_couch_error(self, couch_result, **kwargs):
        if not isinstance(couch_result, self._db_error_type):
            self.register(self.CODING['999-000007'], includeFrame=True)
            self.abort_on_errors(status_code=500)

        if couch_result.reason == 'You are not allowed to access this db.':
            self.register(self.GENERAL['000-000003'], **kwargs)
        else:
            self.register(self.GENERAL['000-000002'], meta={'databaseError': couch_result.__dict__}, **kwargs)

    def is_db_error(self, object):
        return isinstance(object, self._db_error_type)

    @deprecation.deprecated(deprecated_in="0.1.0", removed_in="1.0.0", current_version=__version__, details="Use is_db_error()")
    def is_couch_error(self, response):
        return isinstance(response, self._db_error_type)

    def abort_on_errors(self, status_code=400):
        if g.get('response_errors', None) is not None:
            abort(make_response(jsonify({'errors': g.get('response_errors')}), status_code))
