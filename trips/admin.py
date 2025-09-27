from django.contrib import admin
from .models import Vehicle, Trip, User

admin.site.register(Vehicle)


admin.site.register(Trip)
admin.site.register(User)