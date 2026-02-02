import uuid
from django.db import models
from django.contrib import admin


class Restaurant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class RestaurantAdmin(admin.ModelAdmin):
    list_display = ('name', 'id')
    search_fields = ['name']    


class Menu(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class MenuAdmin(admin.ModelAdmin):
    list_display = ('name', 'id')
    search_fields = ['name']

