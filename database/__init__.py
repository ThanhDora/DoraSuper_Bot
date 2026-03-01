from async_pymongo import AsyncClient

from dorasuper.vars import DATABASE_NAME, DATABASE_URI

mongo = AsyncClient(DATABASE_URI)
dbname = mongo[DATABASE_NAME]
