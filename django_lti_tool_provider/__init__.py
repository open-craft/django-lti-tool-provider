import logging


class NullHandler(logging.Handler):
    """ Noop logger to avoid logging errors when logging is not configured """
    def emit(self, record):
        pass

h = NullHandler()
logging.getLogger("").addHandler(h)