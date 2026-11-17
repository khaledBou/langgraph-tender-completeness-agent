from django.db import migrations


def copy_requirements(apps, schema_editor):
    Review = apps.get_model("reviews", "Review")
    for review in Review.objects.select_related("checklist").filter(requirements=[]):
        review.requirements = review.checklist.items
        review.save(update_fields=["requirements"])


class Migration(migrations.Migration):
    dependencies = [("reviews", "0002_review_requirements")]

    operations = [migrations.RunPython(copy_requirements, migrations.RunPython.noop)]
