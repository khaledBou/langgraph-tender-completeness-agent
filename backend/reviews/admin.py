from django.contrib import admin

from reviews.models import Checklist, Review, ReviewFile


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "created_at"]


class ReviewFileInline(admin.TabularInline):
    model = ReviewFile
    extra = 0
    readonly_fields = ["name", "file", "extraction_error"]


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ["candidate_name", "checklist", "status", "verdict", "created_at"]
    list_filter = ["status", "verdict", "checklist"]
    readonly_fields = ["id", "created_at", "updated_at", "started_at", "completed_at"]
    inlines = [ReviewFileInline]
