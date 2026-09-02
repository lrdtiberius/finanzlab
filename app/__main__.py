import os

from . import web
from .archive_support import install_repository_archive_support, install_web_archive_support

install_repository_archive_support(web.Repository)
install_web_archive_support(web.Handler)
web.run(int(os.environ.get("PORT", "8798")))
