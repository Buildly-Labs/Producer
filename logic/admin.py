from .models import *
from django.contrib import admin

from import_export.admin import ImportExportModelAdmin
from import_export import resources


admin.site.register(Restaurant, RestaurantAdmin)
admin.site.register(Menu, MenuAdmin)