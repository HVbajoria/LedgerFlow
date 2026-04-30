from .base import *  # noqa

DEBUG = True


REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += [  # noqa
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# Relax permissions for local dev if needed
# REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = [
#     "rest_framework.permissions.AllowAny",
# ]
