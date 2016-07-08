import ConfigParser
import cPickle as pickle
import logging
import logging.handlers
import os
import shutil
import json
import requests

###############################################
# Constants/Globals
###############################################

#Put your app name here (same as it is on the file system!) and it will be put in all the paths
APP_NAME = "main"

APP_PATH        = os.path.abspath(os.path.join(os.path.dirname( __file__ ), os.pardir))
#Put pkl file in log dir for easy deletion
ARCH_CACHE      = os.path.join(APP_PATH, 'log', '%s_archive.pkl' % APP_NAME)
CACHE_FILE      = os.path.join(APP_PATH, 'log', '%s.pkl' % APP_NAME)

LOG_PATH            = os.path.join(APP_PATH, 'log')
LOG_FILE            = os.path.join(LOG_PATH, '%s.log' % APP_NAME)
DEBUG_LOG_FILE      = os.path.join(LOG_PATH, 'debug.log')
CONFIG_FILE_DEFAULT = os.path.join(APP_PATH, 'default', '%s.conf' % APP_NAME)
CONFIG_FILE_LOCAL   = os.path.join(APP_PATH, 'local', '%s.conf' % APP_NAME)

DEBUG_LOG_LEVEL = logging.DEBUG
loggers = {}

###############################################
# Methods
###############################################

def getConfig(configFileDefault=CONFIG_FILE_DEFAULT, configFileLocal=CONFIG_FILE_LOCAL):
    config = ConfigParser.ConfigParser()
    try:
        config.readfp(open(configFileDefault, 'r'))
        #Local config entries overwrite default config entries if it exists
        if os.path.exists(configFileLocal):
            config.readfp(open(configFileLocal, 'r'))
    except Exception, e:
        raise Exception("Error loading config files: %s %s" % (type(e), str(e)) )

    return config

def setupLogger(path, name, level, formatter=None):
    logger = logging.getLogger(name)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=1024 * 1024 * 30, backupCount=3)#30MB, 3x backlog, totals 120mb of logs
    if formatter:
        handler.setFormatter(formatter)
    logger.setLevel(level)
    logger.addHandler(handler)

    return logger

def init_logging():
    # SET up DEBUG log
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(funcName)s - %(lineno)d - %(message)s")
    debug_logger = setupLogger(DEBUG_LOG_FILE, "debug", DEBUG_LOG_LEVEL, formatter)
    loggers["debug"] = debug_logger
    # END DEBUG log

    #SET up DUMP log
    formatter = logging.Formatter('%(message)s')
    logger = setupLogger(LOG_FILE, "logger", logging.INFO, formatter)
    loggers["output"] = logger
    #END DUMP Log

    return debug_logger, logger

def getDebugLogger():
    if not "debug" in loggers or not "output" in loggers:
        init_logging()

    return loggers["debug"]

def getOutputLogger():
    if not "debug" in loggers or not "output" in loggers:
        init_logging()

    return loggers["output"]

def readCache(filename=CACHE_FILE, archive=ARCH_CACHE):
    DEBUG_LOGGER = getDebugLogger()

    #Cache is a List
    cache = []

    try:
        DEBUG_LOGGER.info("Reading CACHE_FILE: %s" % filename)
        #CHECK if file exists otherwise create file
        try:
            with open(filename, "rb") as f:
                try:
                    cache = pickle.load(f)
                except Exception:
                    DEBUG_LOGGER.error("FAILED to read CACHE_FILE: %s" % filename)
                    DEBUG_LOGGER.error("Reading archived ARCH_CACHE_FILE: %s" % archive)
                    with open(archive, "rb") as f2:
                        cache = pickle.load(f2)

        #Create File  file does not exist
        except IOError, ex:
            DEBUG_LOGGER.warn("CACHE_FILE was not found. Creating new file: %s" % filename)
            f = open(filename,"w+")
            f.close()

    except Exception, ex:
        errorMessage = "Unable to open/read CACHE_FILE and Archived cache: %s %s..." % (type(ex), ex)
        DEBUG_LOGGER.error(errorMessage)


    DEBUG_LOGGER.debug("CACHE_FILE succesfully read.")
    return cache

def saveCache(cache, path=CACHE_FILE):
    """
    Description: saves old .pkl file as archive and writes new .pkl file to [path]
    Parameters: cache = cache to save
    """
    DEBUG_LOGGER = getDebugLogger()

    try:
        DEBUG_LOGGER.debug("Copying old Cache to archive file...")
        try:
            #Make an archive of the cache before writing the new one out.
            shutil.copyfile(CACHE_FILE, ARCH_CACHE)
        except IOError, ex:
            errorMessage = "Could not create archive cache file:\n\t%s" % str(ex)
            DEBUG_LOGGER.error(errorMessage)
            raise Exception(errorMessage)

        DEBUG_LOGGER.debug("Saving Cache...")
        with open(CACHE_FILE, "wb+") as f:
            pickle.dump(cache, f)
            DEBUG_LOGGER.debug("Cache successfully written to.")
    except IOError, ex:
        errorMessage = "Could not write cache to %s:\n\t%s" % (CACHE_FILE, str(ex))
        DEBUG_LOGGER.error(errorMessage)
        raise Exception(errorMessage)

def request(self, url=None, headers=None, cookies=None, payload=None, method='POST'):
        if url is None:
            raise Exception("No URL specified")

        if method.upper() == "POST":
            requests_fn = requests.post
        elif method.upper() == "GET":
            requests_fn = requests.get
        elif method.upper() == "PUT":
            requests_fn = requests.put
        else:
            raise Exception("%S - Unhandled HTTP Method" % method.upper())

        #If you want to specify headers for application/json, etc., do it here
        default_headers = {}

        if headers is not None:
            headers = merge_dicts(default_headers, headers)
        else:
            headers = default_headers

        if payload is None:
            payload = {}

        res = requests_fn(
            url,
            headers=headers,
            cookies=cookies,
            data=json.dumps(payload),
            #If you're getting ssl errors because of booz's man in the middle,
            #set verify to False ---for dev only!!---
            verify=True
        )

        #Return the response as well as the status code for the dev to deal with
        return res, res.status_code

def merge_dicts(*dict_args):
    '''
    Given any number of dicts, shallow copy and merge into a new dict,
    precedence goes to key value pairs in latter dicts.
    '''
    result = {}
    for dictionary in dict_args:
        result.update(dictionary)
    return result

def flatten_iterables(d, parent_key='', sep='_'):
    '''
    Take an iterable of any assortment of primitives, lists, and dicts and flatten it to a single level dict.
    Ex: {'1':{'2':{'3':'blah'}}} -> {'1_2_3': 'blah'}
    Please note that lists that contain dicts will have the dicts inside the list
    flattened, but lists cannot be flattened.
    Ex: {'1':[{'2':{'3':'blah'}}]} -> {'1': [{'2_3': 'blah'}]}
    '''
    items = []
    for k, v in d.iteritems():
        old_key = str(k).replace(" ", sep)
        new_key = parent_key + sep + old_key if parent_key else old_key
        if isinstance(v, dict):
            items.extend(flatten_iterables(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            newList = []
            for d in v:
                newList.append(flatten_iterables(d))
            items.append((new_key, newList))
        else:
            items.append((new_key, v))
    return dict(items)

if __name__ == "__main__":
    main()