# Fork to add some functionalities that im using

1. Log file

Logfile in this project grows without limit, so ive added `from logging.handlers import RotatingFileHandler` to have 2 files, each with 20mb (last file had 2gb...)