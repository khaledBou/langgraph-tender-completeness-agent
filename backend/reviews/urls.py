from rest_framework.routers import DefaultRouter

from reviews.views import ChecklistViewSet, ReviewViewSet

router = DefaultRouter()
router.register("checklists", ChecklistViewSet, basename="checklist")
router.register("reviews", ReviewViewSet, basename="review")

urlpatterns = router.urls
