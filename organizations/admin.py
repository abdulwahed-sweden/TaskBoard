from django.contrib import admin

from . import models


class MembershipInline(admin.TabularInline):
    model = models.Membership
    extra = 0
    autocomplete_fields = ["user"]


class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["created"]
    inlines = [MembershipInline]


class MembershipAdmin(admin.ModelAdmin):
    list_display = ["organization", "user", "role", "created"]
    list_filter = ["role"]
    search_fields = ["organization__name", "user__username"]
    autocomplete_fields = ["user", "organization"]
    readonly_fields = ["created"]


class ProjectAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "project_type", "created"]
    list_filter = ["organization", "project_type"]
    search_fields = ["name", "organization__name"]
    autocomplete_fields = ["organization"]
    readonly_fields = ["created"]


class FieldDefinitionInline(admin.TabularInline):
    model = models.FieldDefinition
    extra = 1


class StatusDefinitionInline(admin.TabularInline):
    model = models.StatusDefinition
    extra = 1


class ProjectTypeAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    inlines = [FieldDefinitionInline, StatusDefinitionInline]


admin.site.register(models.Organization, OrganizationAdmin)
admin.site.register(models.Membership, MembershipAdmin)
admin.site.register(models.Project, ProjectAdmin)
admin.site.register(models.ProjectType, ProjectTypeAdmin)
